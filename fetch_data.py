#!/usr/bin/env python3
"""
fetch_data.py
Runs in GitHub Actions. Fetches BLS, Treasury, and FRED data,
writes to data/bls.json, data/treasury.json, and data/fred.json.
"""

import json
import os
import urllib.request
import urllib.error
import sys
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

def log(msg):
    print(msg, flush=True)

# ── BLS ───────────────────────────────────────────────────────────────────────

def fetch_bls():
    log("Fetching BLS data...")
    now = datetime.now()
    payload = json.dumps({
        "seriesid": ["CUUR0000SA0", "CUUR0000SA0L1E", "LNS14000000"],
        "startyear": str(now.year - 2),
        "endyear":   str(now.year)
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.bls.gov/publicAPI/v1/timeseries/data/",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "MacroMonitor/1.0 (github.com/sgmil/macro-monitor)"
        }
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())

    if data.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS error: {data.get('message', data.get('status'))}")

    log(f"  BLS OK — {len(data['Results']['series'])} series")
    return data

# ── Treasury Yield Curve XML → JSON ──────────────────────────────────────────

def fetch_treasury_year(year):
    url = (
        "https://home.treasury.gov/resource-center/data-chart-center/"
        f"interest-rates/pages/xml?data=daily_treasury_yield_curve"
        f"&field_tdr_date_value={year}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "MacroMonitor/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8")

def parse_treasury_xml(xml_text):
    """Parse Treasury XML into list of dicts without external dependencies."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text)

    # Namespace used by Treasury feed
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    rows = []

    for entry in root.findall("atom:entry", ns):
        content = entry.find("atom:content", ns)
        if content is None:
            continue

        def get(tag):
            # Tags are in a properties namespace
            for child in content.iter():
                if child.tag.endswith(tag):
                    try:
                        return float(child.text) if child.text else None
                    except (ValueError, TypeError):
                        return None
            return None

        def get_text(tag):
            for child in content.iter():
                if child.tag.endswith(tag):
                    return child.text
            return None

        date_str = get_text("NEW_DATE")
        if not date_str:
            continue

        rows.append({
            "date":      date_str[:10],
            "bc_1month":  get("BC_1MONTH"),
            "bc_3month":  get("BC_3MONTH"),
            "bc_6month":  get("BC_6MONTH"),
            "bc_1year":   get("BC_1YEAR"),
            "bc_2year":   get("BC_2YEAR"),
            "bc_3year":   get("BC_3YEAR"),
            "bc_5year":   get("BC_5YEAR"),
            "bc_7year":   get("BC_7YEAR"),
            "bc_10year":  get("BC_10YEAR"),
            "bc_20year":  get("BC_20YEAR"),
            "bc_30year":  get("BC_30YEAR"),
        })

    rows.sort(key=lambda r: r["date"])
    return rows

def fetch_treasury():
    now = datetime.now()
    years = [now.year - 1, now.year]
    all_rows = []
    for yr in years:
        log(f"Fetching Treasury yield curve {yr}...")
        xml = fetch_treasury_year(yr)
        rows = parse_treasury_xml(xml)
        all_rows.extend(rows)
        log(f"  Treasury {yr} OK — {len(rows)} trading days")

    # Deduplicate and sort
    seen = set()
    deduped = []
    for r in all_rows:
        if r["date"] not in seen:
            seen.add(r["date"])
            deduped.append(r)
    deduped.sort(key=lambda r: r["date"])
    return deduped

# ── FRED ──────────────────────────────────────────────────────────────────────

def fetch_fred_series(series_id, start="2015-01-01"):
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key:
        raise RuntimeError("FRED_API_KEY environment variable not set")
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={api_key}&file_type=json"
        f"&observation_start={start}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "MacroMonitor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from FRED ({series_id}): {body[:300]}") from None
    obs = [
        {"date": o["date"], "value": float(o["value"])}
        for o in data["observations"]
        if o["value"] != "."
    ]
    log(f"  FRED {series_id} OK — {len(obs)} observations")
    return obs

# ── Buffett Indicator helper ──────────────────────────────────────────────────

def _compute_buffett(will5000, gdp):
    """Divide monthly Wilshire 5000 index by most-recent quarterly GDP."""
    gdp_sorted = sorted(gdp, key=lambda x: x["date"])
    result = []
    g = 0
    for pt in sorted(will5000, key=lambda x: x["date"]):
        while g + 1 < len(gdp_sorted) and gdp_sorted[g + 1]["date"] <= pt["date"]:
            g += 1
        if gdp_sorted[g]["date"] > pt["date"]:
            continue
        result.append({"date": pt["date"], "value": round(pt["value"] / gdp_sorted[g]["value"] * 100, 1)})
    return result

# ── Metals (Yahoo Finance) ────────────────────────────────────────────────────

def fetch_yahoo_chart(ticker, label):
    """Fetch 1y of daily closing prices for a Yahoo Finance ticker."""
    encoded = ticker.replace("^", "%5E").replace("=", "%3D")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?interval=1d&range=1y"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept":     "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from Yahoo ({ticker}): {body[:300]}") from None

    result    = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes     = result["indicators"]["quote"][0]["close"]
    obs = [
        {"date": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d"), "value": round(c, 2)}
        for ts, c in zip(timestamps, closes)
        if c is not None
    ]
    obs.sort(key=lambda x: x["date"])
    log(f"  Yahoo Finance {label} OK — {len(obs)} trading days")
    return obs

def fetch_gold_yahoo():
    return fetch_yahoo_chart("GC=F", "Gold")

def fetch_silver_yahoo():
    return fetch_yahoo_chart("SI=F", "Silver")

def fetch_sp500_yahoo():
    return fetch_yahoo_chart("^GSPC", "S&P 500")

def fetch_brent_yahoo():
    return fetch_yahoo_chart("BZ=F", "Brent Crude")

def fetch_dxy_yahoo():
    return fetch_yahoo_chart("DX-Y.NYB", "DXY")

def fetch_vix_yahoo():
    return fetch_yahoo_chart("^VIX", "VIX")

def fetch_russell2000_yahoo():
    return fetch_yahoo_chart("^RUT", "Russell 2000")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    errors = []
    updated = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # BLS
    try:
        bls_data = fetch_bls()
        bls_out = {"updated": updated, "data": bls_data}
        (DATA_DIR / "bls.json").write_text(json.dumps(bls_out, separators=(",", ":")))
        log("  Wrote data/bls.json")
    except Exception as e:
        log(f"  BLS FAILED: {e}")
        errors.append(f"BLS: {e}")

    # Treasury
    try:
        treasury_rows = fetch_treasury()
        treasury_out = {"updated": updated, "rows": treasury_rows}
        (DATA_DIR / "treasury.json").write_text(json.dumps(treasury_out, separators=(",", ":")))
        log("  Wrote data/treasury.json")
    except Exception as e:
        log(f"  Treasury FAILED: {e}")
        errors.append(f"Treasury: {e}")

    # FRED (M2, Fed Funds, OAS)
    fred_out = {"updated": updated}
    try:
        fred_out["m2"]        = fetch_fred_series("M2SL")
        fred_out["fed_funds"] = fetch_fred_series("FEDFUNDS")
        fred_out["oas"]       = fetch_fred_series("BAMLH0A0HYM2")
    except Exception as e:
        log(f"  FRED FAILED: {e}")
        errors.append(f"FRED: {e}")

    # Buffett Indicator (Yahoo Finance Wilshire 5000 + FRED GDP)
    try:
        will_obs = fetch_yahoo_chart("^W5000", "Wilshire 5000")
        gdp_obs  = fetch_fred_series("GDP")
        fred_out["buffett"] = _compute_buffett(will_obs, gdp_obs)
    except Exception as e:
        log(f"  Buffett FAILED: {e}")
        errors.append(f"Buffett: {e}")

    (DATA_DIR / "fred.json").write_text(json.dumps(fred_out, separators=(",", ":")))
    log("  Wrote data/fred.json")

    # DXY (Yahoo Finance)
    try:
        dxy_obs = fetch_dxy_yahoo()
        dxy_out = {"updated": updated, "prices": dxy_obs}
        (DATA_DIR / "dxy.json").write_text(json.dumps(dxy_out, separators=(",", ":")))
        log("  Wrote data/dxy.json")
    except Exception as e:
        log(f"  DXY FAILED: {e}")
        errors.append(f"DXY: {e}")

    # VIX (Yahoo Finance)
    try:
        vix_obs = fetch_vix_yahoo()
        vix_out = {"updated": updated, "prices": vix_obs}
        (DATA_DIR / "vix.json").write_text(json.dumps(vix_out, separators=(",", ":")))
        log("  Wrote data/vix.json")
    except Exception as e:
        log(f"  VIX FAILED: {e}")
        errors.append(f"VIX: {e}")

    # Brent Crude (Yahoo Finance)
    try:
        brent_obs = fetch_brent_yahoo()
        brent_out = {"updated": updated, "prices": brent_obs}
        (DATA_DIR / "brent.json").write_text(json.dumps(brent_out, separators=(",", ":")))
        log("  Wrote data/brent.json")
    except Exception as e:
        log(f"  Brent FAILED: {e}")
        errors.append(f"Brent: {e}")

    # Gold (Yahoo Finance)
    try:
        gold_obs = fetch_gold_yahoo()
        gold_out = {"updated": updated, "prices": gold_obs}
        (DATA_DIR / "gold.json").write_text(json.dumps(gold_out, separators=(",", ":")))
        log("  Wrote data/gold.json")
    except Exception as e:
        log(f"  Gold FAILED: {e}")
        errors.append(f"Gold: {e}")

    # Silver (Yahoo Finance)
    try:
        silver_obs = fetch_silver_yahoo()
        silver_out = {"updated": updated, "prices": silver_obs}
        (DATA_DIR / "silver.json").write_text(json.dumps(silver_out, separators=(",", ":")))
        log("  Wrote data/silver.json")
    except Exception as e:
        log(f"  Silver FAILED: {e}")
        errors.append(f"Silver: {e}")

    # S&P 500 (Yahoo Finance)
    try:
        sp500_obs = fetch_sp500_yahoo()
        sp500_out = {"updated": updated, "prices": sp500_obs}
        (DATA_DIR / "sp500.json").write_text(json.dumps(sp500_out, separators=(",", ":")))
        log("  Wrote data/sp500.json")
    except Exception as e:
        log(f"  S&P 500 FAILED: {e}")
        errors.append(f"S&P 500: {e}")

    # Russell 2000 (Yahoo Finance)
    try:
        rut_obs = fetch_russell2000_yahoo()
        rut_out = {"updated": updated, "prices": rut_obs}
        (DATA_DIR / "rut.json").write_text(json.dumps(rut_out, separators=(",", ":")))
        log("  Wrote data/rut.json")
    except Exception as e:
        log(f"  Russell 2000 FAILED: {e}")
        errors.append(f"Russell 2000: {e}")

    if errors:
        log(f"\nCompleted with errors: {'; '.join(errors)}")
        sys.exit(1)
    else:
        log(f"\nAll data updated successfully at {updated}")

if __name__ == "__main__":
    main()
