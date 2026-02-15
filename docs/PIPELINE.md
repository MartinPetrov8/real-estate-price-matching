# Daily Pipeline

## Overview

The data pipeline runs daily to:
1. Scrape fresh market listings from imot.bg and olx.bg
2. Compare auction prices to market prices
3. Export deals to the frontend
4. Push updates to GitHub (triggers GitHub Pages rebuild)

## Automated Schedule

| Job | Time (Sofia) | Description |
|-----|--------------|-------------|
| Market Scraper | 06:00 | Scrape imot.bg, olx.bg |
| (Export + Push) | Part of scraper | Auto-runs after scraping |

## Manual Execution

```bash
# Full pipeline
python run_pipeline.py

# Without git push
python run_pipeline.py --no-push

# Only market scraping
python run_pipeline.py --market-only

# Only export (use existing data)
python run_pipeline.py --export-only
```

## Individual Components

### 1. Market Scraper
```bash
cd scrapers
python market_scraper.py
```
- Duration: ~3 minutes
- Output: `data/market.db`
- Listings: ~610 per run

### 2. BCPEA Scraper (Auctions)
```bash
cd scrapers
python bcpea_scraper.py
```
- Duration: ~5-10 minutes
- Output: `data/auctions.db`
- Run manually or set up separate cron

### 3. Export Deals
```bash
python export_deals.py
```
- Duration: ~10 seconds
- Output: `deals.json`, `frontend/deals.json`

## Monitoring

Check the latest data:
```bash
# Market listings count
sqlite3 data/market.db "SELECT source, COUNT(*) FROM market_listings GROUP BY source"

# Auction count
sqlite3 data/auctions.db "SELECT COUNT(*) FROM auctions WHERE is_expired = 0"

# Deals count
python -c "import json; d=json.load(open('deals.json')); print(len(d), 'deals')"
```

## Troubleshooting

### "No market data"
- Run `python scrapers/market_scraper.py`
- Check if imot.bg/olx.bg are accessible

### "404 errors"
- OLX uses Bulgarian transliteration: `sofiya` not `sofia`
- imot.bg uses: `grad-sofiya`

### "Encoding issues"
- imot.bg uses `windows-1251`, handled automatically
- OLX uses UTF-8

### "Git push fails"
- Check GitHub PAT token has push access
- Run manually: `git push origin main`
