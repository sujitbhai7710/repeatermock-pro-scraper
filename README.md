# RepeaterMock PRO Mass Scraper

Scrapes ALL PRO tests (6,803 tests across 23 tb-pro series) from RepeaterMock using a 1-day PRO trial account.

## Quick Start

### 1. Setup Cloudflare (one-time)

```bash
# Create D1 database
npx wrangler d1 create repeatermock-pro-scraper

# Copy the database_id into worker/wrangler.toml
# Apply schema
npx wrangler d1 execute repeatermock-pro-scraper --remote --file=db/schema.sql

# Deploy worker
cd worker
npx wrangler deploy
echo "BloggingTest@7" | npx wrangler secret put ADMIN_PASSWORD
echo "sujitbhai7710/repeatermock-pro-scraper" | npx wrangler secret put GH_REPO
echo "YOUR_GITHUB_PAT" | npx wrangler secret put GH_TOKEN
```

### 2. Add GitHub Secrets

- `CLOUDFLARE_API_TOKEN` — Cloudflare API token with D1 + Workers permissions
- `CLOUDFLARE_ACCOUNT_ID` — Your Cloudflare account ID
- `D1_DATABASE_ID` — The D1 database ID from step 1

### 3. Add PRO Account Cookies

1. Login to RepeaterMock with a PRO trial account
2. Export cookies (Cookie-Editor extension → JSON)
3. Save to `cookies/account_pro.json` in the repo
4. Commit + push

### 4. Run

**GitHub Actions**: Trigger "Scrape PRO Tests" workflow manually, or let the 15-min cron handle it.

**Locally**:
```bash
pip install -r requirements.txt
playwright install chromium
python -m src.mass_scraper --time-limit-minutes 350
```

## Dashboard

**URL**: `https://repeatermock-pro-dashboard.<your-subdomain>.workers.dev`
**Admin**: `/admin` (password: `BloggingTest@7`)

## How It Works

1. **Startup**: Force-refreshes access token (gets full 15-min window)
2. **Inventory**: Fetches all 6,803 test IDs via API (cached in progress.json)
3. **Scrape loop** (per test, ~3 sec):
   - GET `/attempt` → extract questions from RSC payload
   - POST `/api/v1/attempts/{id}/start` → create attempt
   - POST `/api/v1/attempts/{id}/submit` → submit empty answers
   - GET `/solution` → extract answers + solutions
   - GET `/analysis` → extract rank, percentile, cutoffs
   - Save JSON file ONLY if all 4 components present
4. **Token rotation** (every 8 tests):
   - POST `/auth/refresh` → captures new refreshToken from Set-Cookie
   - Saves to `cookies/account_pro.json` immediately
   - Git commits (preserves chain for next run)
5. **Auto-commit**: Rotated cookies + progress committed after each run

## Time Estimate

- **6,803 PRO tests × 3 sec/test = 5.7 hours**
- 1-day trial (24h) = more than enough headroom
- GitHub Actions runs in 350-min chunks (5.8h), resuming from committed progress

## Files

```
cookies/account_pro.json   — PRO account cookies (auto-rotated)
data/progress.json         — Scrape progress (committed)
data/tests/*.json          — Fully scraped test data
src/mass_scraper.py        — Main orchestrator
src/token_rotation.py      — Token refresh + Set-Cookie capture
src/full_scraper.py        — Per-test scraper (Q+A+Sol+Ana)
worker/src/index.js        — Dashboard + cron trigger
```
