# Macro Monitor

Live financial dashboard — CPI, Treasury yields, unemployment — hosted on GitHub Pages and refreshed automatically each weekday morning.

**Live URL:** https://sgmil.github.io/macro-monitor

---

## One-Time Setup

### 1. Create the GitHub repo

1. Go to https://github.com/new
2. Repository name: **macro-monitor**
3. Set to **Public** (required for free GitHub Pages)
4. Do NOT initialize with README (you're uploading files)
5. Click **Create repository**

### 2. Upload the files

On the repo page, click **uploading an existing file** and drag in everything from this zip:

```
macro-monitor/
├── index.html
├── fetch_data.py
├── data/
│   ├── bls.json
│   └── treasury.json
└── .github/
    └── workflows/
        └── update_data.yml
```

Commit directly to `main`.

### 3. Enable GitHub Pages

1. Go to your repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / **/ (root)**
4. Click **Save**

Your site will be live at **https://sgmil.github.io/macro-monitor** within a minute or two.

### 4. Add the FRED API key secret

M2 money supply data comes from FRED (St. Louis Fed). Get a free API key at https://fred.stlouisfed.org/docs/api/api_key.html, then add it to your repo:

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `FRED_API_KEY`, Value: your key
4. Click **Add secret**

### 5. Trigger the first data fetch

The Action runs automatically at 7am MT on weekdays. To get data immediately:

1. Go to your repo → **Actions** tab
2. Click **Update Market Data** in the left sidebar
3. Click **Run workflow** → **Run workflow**

Wait about 30 seconds, then reload the dashboard. You should see live data.

---

## How It Works

```
GitHub Actions (7am MT, Mon–Fri)
  └── runs fetch_data.py
        ├── fetches CPI + unemployment from BLS
        ├── fetches yield curve from U.S. Treasury
        └── commits updated JSON to data/

GitHub Pages
  └── serves index.html + data/*.json as static files

Your browser
  └── opens sgmil.github.io/macro-monitor
        └── reads data/*.json (same origin, no CORS issues)
```

## Troubleshooting

**Dashboard shows "Data not yet populated"**
→ Trigger the Action manually (Step 4 above)

**Action fails**
→ Go to Actions tab, click the failed run, read the log — BLS, Treasury, and FRED occasionally have brief outages

**Data is stale**
→ The dashboard shows a warning if data is more than 3 days old
→ Check Actions tab for failed runs

**Change the refresh time**
→ Edit `.github/workflows/update_data.yml`, change the cron line
→ `'0 13 * * 1-5'` = 7am MT (UTC−6) weekdays
→ Cron reference: https://crontab.guru
