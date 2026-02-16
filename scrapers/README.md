# Market Scrapers

## Production Scrapers

### market_scraper.py
Production market scraper using `requests` + `BeautifulSoup`.

**Sources:**
- **imot.bg**: ~120 listings from Sofia, Plovdiv, Varna, Burgas
- **olx.bg**: ~490 listings from same cities

**Usage:**
```bash
python market_scraper.py
```

**Output:**
- `../data/market.db` - SQLite database
- `data/market_listings.json` - JSON export

**Performance:**
- Runtime: ~3 minutes
- No 404s or timeouts
- 0.5-1.5s delay between requests (polite scraping)

### bcpea_scraper.py
КЧСИ (court auction) scraper.

**Source:** https://sales.bcpea.org

**Usage:**
```bash
python bcpea_scraper.py
```

**Output:**
- `../data/auctions.db` - SQLite database

## URL Formats

| Site | City | URL Pattern |
|------|------|-------------|
| imot.bg | София | `obiavi/prodazhbi/grad-sofiya/` |
| olx.bg | София | `nedvizhimi-imoti/prodazhbi/apartamenti/sofiya/` |

**Note:** OLX uses Bulgarian transliteration (`sofiya` not `sofia`).

## Encoding

- **imot.bg**: `windows-1251`
- **olx.bg**: `UTF-8`

## Archive

Old scraper versions are in `archive/` (not tracked in git).

## OLX Playwright Scraper (NEW)

OLX.bg now requires Playwright to bypass CAPTCHA protection.

### Setup
```bash
pip install playwright
PLAYWRIGHT_BROWSERS_PATH=/path/to/browsers playwright install chromium
```

### Usage
```bash
export PLAYWRIGHT_BROWSERS_PATH=/host-workspace/.playwright-browsers
python3 scrapers/olx_playwright.py
```

### Output
- Saves to `data/market.db` (same table as imot.bg)
- ~50 listings per city (Sofia, Plovdiv, Varna, Burgas)
