# Architecture Overview

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                      DATA PIPELINE                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   BCPEA      │    │   Market     │    │  Geocode     │       │
│  │   Scraper    │───▶│   Scraper    │    │  Neighborhoods│      │
│  │              │    │ (OLX+imot)   │    │ (step 1.5)   │       │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘       │
│         │                   │                   │                │
│         ▼                   ▼                   ▼                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ auctions.db  │    │  market.db   │    │  Export      │       │
│  │  (~1,400)    │    │  (~7,200)    │───▶│  Deals       │       │
│  └──────────────┘    └──────────────┘    └──────┬───────┘       │
│                                                  │               │
│                                                  ▼               │
│                                          ┌──────────────┐       │
│                                          │  deals.json  │       │
│                                          │  (~500)      │       │
│                                          └──────┬───────┘       │
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
- **Frequency:** Daily at 9:00 AM Sofia time
- **Records:** ~1,400 active auctions

### 2. Market Scraper (`scrapers/market_scraper.py`)
- **Sources:**
  - `imot.bg` — per-city scrape (~30 pages each)
  - `olx.bg` — per-district scrape (discovers district filter IDs dynamically)
  - `olx.bg` search supplements — for neighborhoods not covered by district filters
- **Output:** `data/market.db`
- **Frequency:** Daily at 9:00 AM Sofia time (runs after BCPEA)
- **Records:** ~7,200 market listings (7 day retention)
- **Rental exclusion:** Only `/prodazhbi/` (sales) URLs; hard floor `price_eur < 15,000` filtered out

#### OLX Search Supplements
Some neighborhoods don't appear in OLX's district filter list. These are scraped via
text search (`/nedvizhimi-imoti/prodazhbi/q-{slug}/`):

| City     | Neighborhood     | Reason                              |
|----------|-----------------|--------------------------------------|
| София    | Сухата Река     | Not in OLX district list             |
| София    | Подуяне         | Not in OLX district list             |
| София    | Хиподрума       | Not in OLX district list             |
| Пловдив  | Изгрев          | Insufficient district-level listings |
| Русе     | Изток           | Not in OLX district list             |
| Русе     | Здравец-Север   | Not in OLX district list             |
| Хасково  | Орфей           | Not in OLX district list             |

### 3. Geocode Neighborhoods (`scripts/geocode_neighborhoods.py`)
- **Runs as step 1.5** in the daily pipeline (between BCPEA scrape and market scrape)
- **Strategy (in priority order):**
  1. `extract_neighborhood()` — regex patterns from address text (`ж.к.`, `кв.`, `р-н`, `местност`)
  2. Street → neighborhood lookup table (city-scoped, see `neighborhood_matcher.py`)
  3. Nominatim OSM geocoding (1 req/sec, fallback for unstructured addresses)
- **Output:** Populates `auctions.neighborhood` column

### 4. Export Deals (`export_deals.py`)
- **Input:** `auctions.db` + `market.db`
- **Output:** `deals.json`
- **Price comparison logic (in priority order):**
  1. **Hood + size match** — neighborhood similarity ≥ 0.7, size ±15sqm (best)
  2. **Hood match, any size** — neighborhood similarity ≥ 0.7, all sizes (still hood-level)
  3. **City + size fallback** — no neighborhood match, size ±15sqm (labeled `city_size`)
  4. **City-wide fallback** — no neighborhood, any size (labeled `city`, last resort)
- **`comparables_level` field:** `hood` | `city_size` | `city` — shown in frontend UI
- **Records:** ~500 deals

## Database Schema

### auctions.db
```sql
CREATE TABLE auctions (
    id INTEGER PRIMARY KEY,
    url TEXT,
    price_eur REAL,
    city TEXT,
    neighborhood TEXT,       -- populated by geocode step + extract_neighborhood()
    address TEXT,
    property_type TEXT,
    size_sqm REAL,
    rooms INTEGER,
    floor INTEGER,
    is_partial_ownership INTEGER DEFAULT 0,
    is_expired INTEGER DEFAULT 0,
    court TEXT,
    auction_start TEXT,
    auction_end TEXT,
    scraped_at TEXT,
    first_seen_at TEXT,
    last_updated_at TEXT
);
```

### market.db
```sql
CREATE TABLE market_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    neighborhood TEXT,       -- district-level tag from OLX filter or imot.bg breadcrumb
    size_sqm REAL NOT NULL,
    price_eur REAL NOT NULL,
    price_per_sqm REAL NOT NULL,
    rooms INTEGER,
    source TEXT NOT NULL,    -- 'olx.bg' | 'imot.bg'
    scraped_at TEXT NOT NULL
);
```

## Neighborhood Matching (`neighborhood_matcher.py`)

Three functions:
- `extract_neighborhood(address)` — extracts district from raw address text
- `normalize_neighborhood(text)` — strips prefixes (ж.к., кв., р-н), removes block numbers, lowercases
- `neighborhood_similarity(hood1, hood2)` — fuzzy match score 0.0–1.0 (threshold: 0.7)

### Extraction patterns (in order of priority)
1. Explicit prefixes: `ж.к.`, `жк`, `кв.`, `квартал`, `р-н`, `район`, `местност`
2. imot.bg title pattern: `... в град [City], [Neighborhood] -`
3. imot.bg URL slug: `grad-sofiya-lyulin-9-...`
4. Street → neighborhood lookup table (city-scoped)

### Street lookup coverage
| Street              | City    | Neighborhood          |
|--------------------|---------|-----------------------|
| ул. Роза            | Варна   | Цветен квартал        |
| ул. Стефан Стамболов| Пловдив | Южен                  |
| бул. Македония      | Пловдив | Южен                  |
| ул. Босилек         | Пловдив | Изгрев                |
| ул. Рени            | Русе    | Широк Център          |
| ул. Панайот Волов   | Русе    | Широк Център          |
| бул. Ал. Стамболийски| София  | Красно Село           |
| ул. Ивайло Петров   | София   | Люлин                 |
| ул. Светлоструй     | София   | Красно Село           |

## Neighborhood Coverage (as of 2026-02-26)

| City    | Apartments | Hood-level | City fallback | No data (partial) |
|---------|-----------|------------|---------------|-------------------|
| София   | 13        | 9 (69%)    | 1             | 3                 |
| Пловдив | 4         | 2 (50%)    | 1             | 1                 |
| Варна   | 9         | 5 (55%)    | 0             | 4                 |

Remaining city fallbacks:
- **ЖП Блокове-Гара Илиянци (Sofia)** — very niche area, no market data on OLX or imot.bg
- **Изгрев (Plovdiv)** — OLX supplement added; will resolve on next daily run

## Cities Covered

| City         | OLX Districts | imot.bg | Market Listings | Avg €/m² |
|--------------|--------------|---------|-----------------|----------|
| София        | 30 + 3 supp  | ✅      | ~2,500          | €2,600   |
| Пловдив      | 29 + 1 supp  | ✅      | ~1,200          | €1,560   |
| Варна        | 30           | ✅      | ~1,100          | €2,050   |
| Бургас       | 18           | ✅      | ~450            | €1,700   |
| Русе         | 24 + 2 supp  | ✅      | ~350            | €1,550   |
| Стара Загора | 22           | ✅      | ~350            | €1,300   |

## Tech Stack

- **Backend:** Python 3.11
- **Database:** SQLite3
- **Scraping:** requests, BeautifulSoup4, Playwright (OLX fallback)
- **Geocoding:** Nominatim (OSM), 1 req/sec
- **Frontend:** Static HTML/JS (GitHub Pages)
- **Automation:** OpenClaw cron jobs (09:00 Sofia time daily)

## Security

- No API keys required (all public data sources)
- SQL injection protected via parameterized queries
- No user data collected
- Rate limiting on all scrapers (0.4s between requests)
- Rental filtering: sales-only URLs + €15,000 total price floor
