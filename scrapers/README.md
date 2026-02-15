# Market Scrapers

## Overview

Scrapes Bulgarian real estate listing sites to get market prices for comparison with КЧСИ auctions.

## Scrapers

### market_scraper_v4.py (Recommended)

Production scraper using `requests` + `BeautifulSoup`.

**Features:**
- Session-based requests for cookie persistence
- Simple retry logic with exponential backoff
- Proper encoding handling (windows-1251 for imot.bg)
- 0.5-1.5s delay between requests (polite, not excessive)
- No timeouts or 404 errors

**Sources:**
- **imot.bg**: Scrapes listing URLs from index, then individual pages for price
- **olx.bg**: Single-page scrape with pagination (3 pages per city)

**Usage:**
```bash
pip install beautifulsoup4 requests
python scrapers/market_scraper_v4.py
```

**Output:**
- `scrapers/data/market.db` - SQLite database
- `scrapers/data/market_listings.json` - JSON export

**Performance (2026-02-15):**
| Source | Listings | Avg €/m² |
|--------|----------|----------|
| imot.bg | 118 | €2,114 |
| olx.bg | 492 | €1,868 |
| **TOTAL** | **610** | €1,920 |

### market_scraper_v3.py (Legacy)

Earlier version with more aggressive anti-blocking measures.
- Rotating user agents
- Random delays (2-5s per request)
- Slower but works

## Data Format

```json
{
  "city": "София",
  "size_sqm": 74.0,
  "price_eur": 148000.0,
  "price_per_sqm": 2000.0,
  "rooms": 2,
  "source": "imot.bg",
  "scraped_at": "2026-02-15T08:20:00"
}
```

## Cities Covered

| City | Bulgarian | imot.bg URL | olx.bg URL |
|------|-----------|-------------|------------|
| София | Sofia | grad-sofiya | sofiya |
| Пловдив | Plovdiv | grad-plovdiv | plovdiv |
| Варна | Varna | grad-varna | varna |
| Бургас | Burgas | grad-burgas | burgas |

## Troubleshooting

### 404 Errors
- OLX uses transliterated names: `sofiya` not `sofia`
- imot.bg uses Bulgarian transliteration: `grad-sofiya`

### Encoding Issues
- imot.bg uses `windows-1251` encoding
- OLX uses UTF-8

### Brotli Compression
- Don't include `br` in Accept-Encoding header
- We only handle gzip/deflate
