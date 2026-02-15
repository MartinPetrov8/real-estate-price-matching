# Architecture Overview

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                      DATA PIPELINE                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   BCPEA      │    │   Market     │    │   Export     │       │
│  │   Scraper    │───▶│   Scraper    │───▶│   Deals      │       │
│  │              │    │              │    │              │       │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘       │
│         │                   │                   │                │
│         ▼                   ▼                   ▼                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ auctions.db  │    │  market.db   │    │  deals.json  │       │
│  │  (1,114)     │    │   (610)      │    │   (100)      │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                 │                │
│                                                 ▼                │
│                                          ┌──────────────┐       │
│                                          │ GitHub Pages │       │
│                                          │   Frontend   │       │
│                                          └──────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. BCPEA Scraper (`scrapers/bcpea_scraper.py`)
- **Source:** https://sales.bcpea.org (КЧСИ court auctions)
- **Output:** `data/auctions.db`
- **Frequency:** Daily at 5:00 AM Sofia time
- **Records:** ~1,100 active auctions

### 2. Market Scraper (`scrapers/market_scraper.py`)
- **Sources:** 
  - imot.bg (~120 listings)
  - olx.bg (~490 listings)
- **Output:** `data/market.db`
- **Frequency:** Daily at 6:00 AM Sofia time
- **Records:** ~610 market listings

### 3. Export Deals (`export_deals.py`)
- **Input:** auctions.db + market.db
- **Output:** deals.json (root) + frontend/deals.json
- **Logic:** Compare auction price/m² to market median
- **Records:** ~100 deals with valid comparisons

## Database Schema

### auctions.db
```sql
CREATE TABLE auctions (
    id INTEGER PRIMARY KEY,
    url TEXT,
    price_eur REAL,
    city TEXT,
    neighborhood TEXT,
    address TEXT,
    property_type TEXT,
    size_sqm REAL,
    rooms INTEGER,
    is_partial_ownership INTEGER DEFAULT 0,
    is_expired INTEGER DEFAULT 0,
    court TEXT,
    auction_start TEXT,
    auction_end TEXT,
    scraped_at TEXT
);

-- Indexes for performance
CREATE INDEX idx_auctions_city ON auctions(city);
CREATE INDEX idx_auctions_neighborhood ON auctions(neighborhood);
CREATE INDEX idx_auctions_auction_end ON auctions(auction_end);
CREATE INDEX idx_auctions_property_type ON auctions(property_type);
CREATE INDEX idx_auctions_is_expired ON auctions(is_expired);
```

### market.db
```sql
CREATE TABLE market_listings (
    id INTEGER PRIMARY KEY,
    city TEXT NOT NULL,
    size_sqm REAL NOT NULL,
    price_eur REAL,
    price_per_sqm REAL,
    rooms INTEGER,
    source TEXT NOT NULL,
    scraped_at TEXT
);

-- Indexes
CREATE INDEX idx_market_city ON market_listings(city);
CREATE INDEX idx_market_size ON market_listings(size_sqm);
CREATE INDEX idx_market_source ON market_listings(source);
```

## Cities Covered

| City | Bulgarian | Market Listings | Avg €/m² |
|------|-----------|-----------------|----------|
| София | Sofia | 164 | €2,439 |
| Варна | Varna | 165 | €2,022 |
| Пловдив | Plovdiv | 149 | €1,471 |
| Бургас | Burgas | 132 | €1,634 |

## Tech Stack

- **Backend:** Python 3.8+
- **Database:** SQLite3
- **Scraping:** requests, BeautifulSoup4
- **Frontend:** Static HTML/JS (GitHub Pages)
- **Automation:** OpenClaw cron jobs

## Security

- No API keys required (public data sources)
- SQL injection protected via parameterized queries
- No user data collected
- Rate limiting on scrapers to avoid blocking
