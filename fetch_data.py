#!/usr/bin/env python3
"""
fetch_data.py
Runs in GitHub Actions. Fetches BLS and Treasury data,
writes to data/bls.json and data/treasury.json.
"""

import json
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

    if errors:
        log(f"\nCompleted with errors: {'; '.join(errors)}")
        sys.exit(1)
    else:
        log(f"\nAll data updated successfully at {updated}")

if __name__ == "__main__":
    main()
