# 🏠 Bulgarian Real Estate Auction Analyzer

Scrapes КЧСИ (BCPEA) court-enforced property auctions and compares prices to market listings to find bargains.

![Status](https://img.shields.io/badge/status-MVP-green)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![License](https://img.shields.io/badge/license-MIT-gray)

## 🎯 Features

- **КЧСИ Scraper**: Extracts auction listings from [sales.bcpea.org](https://sales.bcpea.org)
- **Market Scrapers**: Aggregates listings from imot.bg, OLX.bg, alo.bg
- **Price Comparison**: Calculates €/m² deviation from market median
- **Bargain Detection**: Scores 0-100 (higher = better deal)
- **Room Matching**: Enhanced comparison with room count data
- **Neighborhood Matching**: District-aware price comparison
- **Web Frontend**: Bulgarian UI showing top deals

## 📊 Data Sources

| Source | Type | Listings | Notes |
|--------|------|----------|-------|
| КЧСИ (bcpea.org) | Auctions | ~1,100 | Court-enforced sales |
| OLX.bg | Market | ~490 | Private listings (€1,868/m²) |
| imot.bg | Market | ~120 | Agency listings (€2,114/m²) |

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/MartinPetrov8/real-estate-price-matching.git
cd real-estate-price-matching

# Scrape auctions (takes ~5 min)
python scrapers/bcpea_v4.py

# Scrape market data + run comparison
python scrapers/market_scraper_v4.py

# Export deals to frontend
python export_deals.py

# Serve frontend
cd frontend && python -m http.server 8080
# Open http://localhost:8080
```

## 📁 Project Structure

```
real-estate-price-matching/
├── scrapers/
│   ├── bcpea_v4.py          # КЧСИ auction scraper (main)
│   ├── market_scraper.py    # OLX/imot.bg/alo.bg combined
│   └── market_comparison.py # OLX-only alternative
├── src/
│   └── matching/
│       ├── analyzer.js      # Legacy JS analyzer
│       └── neighborhood_matcher.py  # District matching
├── data/
│   ├── auctions.db          # SQLite: auctions + comparisons
│   └── market.db            # SQLite: market listings
├── frontend/
│   ├── index.html           # Deals UI (Bulgarian)
│   ├── app.js               # Frontend logic
│   ├── styles.css           # Styling
│   └── deals.json           # Exported deals
├── web/                     # Alternative web interface
├── export_deals.py          # Generate frontend JSON
└── README.md
```

## ⚙️ How It Works

### 1. Scrape Auctions
```bash
python scrapers/bcpea_v4.py
```
- Scans property IDs 85000-86500 on bcpea.org
- Extracts: price, city, address, size, rooms, auction dates
- Detects property type using Bulgarian legal terms
- Saves to `data/auctions.db`

### 2. Scrape Market Data
```bash
python scrapers/market_scraper_v4.py
```
- Fetches listings from OLX.bg, imot.bg, alo.bg
- Extracts: price, size, €/m², rooms (when available)
- Covers major cities: София, Варна, Бургас, Пловдив, Несебър, Банско
- Saves to `data/market.db`

### 3. Compare Prices
The `market_scraper.py` automatically runs comparison after scraping:
- Matches by: **city** + **size (±15 sqm)** + **rooms** (when available)
- Calculates deviation: `(auction €/m² - market median €/m²) / market €/m²`
- Bargain score = negative deviation (90 = 90% below market)

### 4. Export & View
```bash
python export_deals.py
cd frontend && python -m http.server 8080
```

## 🔍 Matching Criteria

| Factor | Weight | Tolerance |
|--------|--------|-----------|
| City | Required | Exact match |
| Size | Required | ±15 sqm |
| Rooms | Optional | Exact (if available) |
| Neighborhood | Optional | Normalized match |

### Matching Strategy
1. **Room + Size match**: Same city, same rooms, similar size (needs ≥3 comparables)
2. **Size-only match**: Same city, similar size (fallback)
3. **City average**: Last resort if no size match

## 📈 Output Example

```
🔥 TOP BARGAINS (>15% below market):

  гр. Варна: €45,000 (85m², 2-room)
    Auction: €529/m² vs Market: €1,981/m² (-73%)
    Score: 73/100 | ✓ room-matched
    https://sales.bcpea.org/properties/85123

  гр. София: €128,250 (90m², unknown rooms)
    Auction: €1,425/m² vs Market: €3,653/m² (-61%)
    Score: 60/100 | size-only
    https://sales.bcpea.org/properties/85051
```

## 🇧🇬 Bulgarian-Specific Features

### Property Type Detection
Uses Bulgarian legal terminology instead of generic words:
- `САМОСТОЯТЕЛЕН ОБЕКТ` → apartment
- `жилищен етаж` → residential floor
- `жилище` → dwelling

### Room Extraction
Handles Bulgarian patterns:
- `едностаен`, `двустаен`, `тристаен`...
- `2-стаен`, `3-ст.`
- `гарсониера` (studio)
- `мезонет` (maisonette)

### Neighborhood Normalization
- `ж.к. Люлин 9` → `люлин`
- `кв. Лозенец` → `лозенец`
- `район Триадица` → `триадица`

## 🗄️ Database Schema

### auctions table
```sql
id TEXT PRIMARY KEY,
url TEXT,
price_eur REAL,
city TEXT,
district TEXT,
address TEXT,
property_type TEXT,
size_sqm REAL,
rooms INTEGER,
court TEXT,
auction_start TEXT,
auction_end TEXT,
scraped_at DATETIME
```

### comparisons table
```sql
auction_id TEXT PRIMARY KEY,
city TEXT,
auction_price REAL,
auction_size REAL,
auction_rooms INTEGER,
auction_price_sqm REAL,
market_median_sqm REAL,
market_mean_sqm REAL,
market_count INTEGER,
room_matched INTEGER,
deviation_pct REAL,
bargain_score INTEGER
```

## ✅ Data Quality Features

### Partial Ownership Detection
Properties with fractional ownership (e.g., "1/4 идеална част") are:
- Flagged with `is_partial_ownership: true`
- Shown with warning badge in UI
- NOT included in market comparisons (prices aren't comparable)

Detection patterns:
- `притежава 1/6` (owns 1/6)
- `1/4 идеална част от апартамент`
- `продава 1/2` (sells 1/2)
- Common area shares (`идеални части от общите части`) are NOT flagged

### Property Type Classification
Correctly classifies Bulgarian property types:
- **Магазин** → commercial (shop)
- **Апартамент** → apartment
- **Къща** → house
- **Гараж** → garage

### Discount Display
- **No artificial caps** - actual values shown to expose data quality issues
- Extreme discounts (>70%) likely indicate bugs in data (partial ownership, wrong sqm, etc.)
- Only apartments get market comparison; garages/shops shown without discount

## ⚠️ Known Limitations

1. **imoti.net blocked**: Heavy JavaScript + Cloudflare protection
2. **Small towns**: May match to city prices (filtered with min €10K threshold)
3. **Missing sqm**: Some auctions lack size data
4. **Stale data**: Market prices change; re-scrape regularly
5. **Neighborhood data sparse**: Many properties lack neighborhood info for granular matching

## 🛠️ Development

### Re-scrape Everything
```bash
# Full refresh
python scrapers/bcpea_v4.py      # ~5 min
python scrapers/market_scraper_v4.py # ~2 min
python export_deals.py
```

### Query Database
```bash
# Top bargains
python -c "
import sqlite3
conn = sqlite3.connect('data/auctions.db')
for row in conn.execute('''
    SELECT city, auction_price, bargain_score 
    FROM comparisons 
    WHERE bargain_score > 50 
    ORDER BY bargain_score DESC 
    LIMIT 10
'''):
    print(row)
"
```

### Test Neighborhood Matcher
```bash
python src/matching/neighborhood_matcher.py
```

## 📝 Changelog

### 2026-02-11
- **Fixed**: Partial ownership detection now catches "X/Y идеална част от ап." patterns
- **Fixed**: Property type "Магазин" correctly classified as commercial (was showing raw text)
- **Added**: Data quality documentation in README
- **Improved**: Export script properly excludes partial ownership from comparisons

### 2026-02-10
- Initial QA pass: partial ownership, property types, expired auctions
- Neighborhood-aware price caps for Sofia districts

## 📄 License

MIT

## 👤 Author

Built by Cookie 🍪 for Martin
