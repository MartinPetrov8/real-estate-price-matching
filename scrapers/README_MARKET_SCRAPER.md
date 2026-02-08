# Market Data Scraper

Scrapes real estate market data from Bulgarian property sites for price comparison with КЧСИ auction data.

## Data Sources

- **olx.bg** - Major Bulgarian classifieds site
- **imot.bg** - Popular real estate portal
- **alo.bg** - General classifieds with real estate section
- **homes.bg** - Real estate listings

## Database Schema

```sql
CREATE TABLE market_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT,
    district TEXT,
    property_type TEXT DEFAULT 'апартамент',
    size_sqm REAL,
    price_eur REAL,
    price_per_sqm REAL,
    rooms INTEGER,
    source TEXT,
    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## Current Data Volume

| City | Listings | Avg €/m² | Min €/m² | Max €/m² |
|------|----------|----------|----------|----------|
| София | 88 | €2,183 | €1,280 | €3,622 |
| Бургас | 89 | €1,272 | €880 | €1,920 |
| Пловдив | 84 | €1,347 | €920 | €2,100 |
| Варна | 81 | €1,732 | €1,150 | €2,450 |

**Total: 362 listings from 100 districts**

## Usage

Run the main scraper:
```bash
cd /workspace/real-estate-price-matching
python3 scrapers/market_data_scraper.py
```

## Files

- `market_data_scraper.py` - Main scraper with urllib
- `market_scraper_v2.py` - Parser for web_fetch output
- `fetch_all_market.py` - Simplified fetcher
- `collect_market_data.py` - Data collection utilities

## Price Comparison Integration

The market data is used by `market_comparison.py` to calculate bargain scores for auction properties:

1. Query similar properties by city + size (±15m²)
2. Calculate median market price per m²
3. Compare auction price to market median
4. Generate bargain score (0-100, higher = better deal)
