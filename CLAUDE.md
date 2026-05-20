# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A static financial dashboard (CPI, Treasury yields, unemployment) hosted on GitHub Pages. No build step, no package manager, no framework. Everything is vanilla HTML/CSS/JS plus Chart.js (loaded from CDN).

## Running locally

```bash
# Fetch fresh data (writes data/bls.json, data/treasury.json, data/fred.json)
FRED_API_KEY=your_key_here python fetch_data.py

# Or export for the session
export FRED_API_KEY=your_key_here
python fetch_data.py

# Serve the dashboard (must use a server — file:// won't work due to fetch())
python -m http.server 8080
# then open http://localhost:8080
```

Get a free FRED API key at https://fred.stlouisfed.org/docs/api/api_key.html.

## Architecture

```
GitHub Actions (weekdays 7am MT, cron '0 13 * * 1-5')
  └── fetch_data.py
        ├── BLS public API v1 (JSON, no API key) → data/bls.json
        └── U.S. Treasury XML feed → data/treasury.json
        commits data/ and pushes

GitHub Pages
  └── serves index.html + data/*.json as static files

Browser
  └── index.html fetches data/*.json (same-origin, no CORS)
        └── computes CPI YoY client-side from raw monthly index
        └── renders 6 charts via Chart.js 4.4.1
```

### Data files

- `data/bls.json` — raw BLS API response envelope plus `updated` timestamp. BLS series IDs: `CUUR0000SA0` (CPI), `CUUR0000SA0L1E` (Core CPI), `LNS14000000` (Unemployment). Covers current year minus 2 years.
- `data/treasury.json` — `{ updated, rows: [...] }` where each row has daily yield curve fields (`bc_1month` through `bc_30year`). Covers the prior and current calendar year.

### Key behaviors in index.html

- `charts` object tracks live Chart.js instances; each chart is destroyed before re-rendering.
- CPI year-over-year is computed client-side in `calcYoY()` from raw monthly index values.
- Stale data warning fires if `json.updated` is more than 3 days old.
- Charts thin treasury rows to every 3rd point for performance (`i%3===0`).
- The 10Y–2Y spread chart uses a bar chart (red when negative, green when positive).

### fetch_data.py notes

- Uses only stdlib (`urllib`, `xml.etree.ElementTree`, `json`) — no pip dependencies.
- Treasury XML is parsed with a custom namespace-aware walker; the Atom namespace is `http://www.w3.org/2005/Atom` and yield fields are in a properties namespace matched by tag suffix.
- Exits with code 1 if either fetch fails, which fails the GitHub Action.

## Deployment

Pushes to `main` are immediately live on GitHub Pages. The Actions workflow commits updated JSON on schedule; no manual deploy step.
