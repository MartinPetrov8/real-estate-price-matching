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
- **Neighborhood extraction:** Reads structured "Район" field from BCPEA HTML (added 2026-03-03). Falls back to address text extraction via `neighborhood_matcher.py` if Район field absent.

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
- **Price comparison logic — 6-pass priority (rooms first, then size):**
  1. **Hood + rooms + ±10sqm** — same neighborhood, same room type, similar size (tightest)
  2. **Hood + ±10sqm** — same neighborhood, similar size, no room filter
  3. **Hood + rooms** — same neighborhood, same room type, any size (handles 40sqm vs 70sqm 1-beds)
  4. **Hood only** — same neighborhood, any size/rooms
  5. **City + rooms + ±10sqm** — city fallback, room-typed
  6. **City + ±10sqm** — city fallback, size only
- **Room types** derived from Bulgarian `property_type` field (Двустаен=2-bed, etc.) — `rooms` DB field is sparse
- **Size bands per room type:** 1-bed 15–55m², 2-bed 40–90m², 3-bed 65–130m², 4-bed+ 100–200m²
- **`comparables_level` field:** `hood` | `city_size` — shown in frontend UI
- **Records:** ~490 deals

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
All street lookups are **city-scoped** (as of 2026-03-03) to prevent cross-city contamination.

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
| ул. Роден кът       | София   | Овча Купел            |

### Neighborhood Clusters (added 2026-03-03)
Adjacent neighborhoods with similar price levels. Used for fallback comparisons when exact neighborhood has thin comps. Cluster match scores 0.75 (above 0.7 threshold).

| Cluster            | Neighborhoods                                                      |
|--------------------|--------------------------------------------------------------------|
| софия_център       | център, оборище, яворов, изток, изгрев, лозенец, докторски паметник|
| софия_южен         | витоша, бояна, драгалевци, симеоново, кръстова вада, гоце делчев, борово, манастирски ливади, бъкстон |
| софия_запад        | люлин, красно село, хиподрума, овча купел, банишора, илинден       |
| софия_изток        | младост, дружба, мусагеница, дървеница, студентски                 |
| софия_север        | надежда, подуяне, хаджи димитър, сухата река, военна рампа         |
| софия_ср_център    | гео милев, слатина, редута, разсадника                             |

## Neighborhood Coverage (as of 2026-03-03)

| City    | Active | With Hood | Coverage |
|---------|--------|-----------|----------|
| София   | 26     | 26        | 100%     |
| Пловдив | 9      | 9         | 100%     |
| Варна   | 27     | 6         | 22%      |
| Overall | 543    | 132       | 24%      |

Note: Most non-Sofia/Plovdiv properties lack BCPEA "Район" field. Coverage for villages relies on text extraction + Nominatim geocoding.

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
