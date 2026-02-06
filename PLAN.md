# BG Real Estate Price Matcher - Production Plan

## Goal
Compare КЧСИ auction prices against market prices to identify bargains.

## Core Flow
```
1. INCREMENTAL SCAN - only new listings since last run
   ↓
2. Filter out expired auctions (auction_end < today)
   ↓
3. For each residential property:
   - Extract: city, neighborhood, size (m²), property type
   - Parse room count from description (едностаен=1, двустаен=2, тристаен=3, etc.)
   - Mark garages (гараж) - track but skip price comparison
   ↓
4. Find comparable listings from market sources:
   - imot.bg
   - imoti.net  
   - alo.bg
   - homes.bg
   ↓
5. Calculate price deviation:
   - vs Median price in area
   - vs Mean price in area
   - Show % difference
   ↓
6. Display on web app:
   - Bargain score
   - Price comparison chart
   - Similar listings
   - NEW DEALS highlighted
```

## Scanning Modes
- **Full scan**: All active КЧСИ listings (for initial load or reset)
- **Incremental scan**: Only listings announced since last scan (daily runs)
- **Active-only**: Filter out expired auctions automatically

## Data Requirements

### КЧСИ (bcpea.org) - MUST HAVE
- [ ] Property ID
- [ ] Price (EUR)
- [ ] City/Town
- [ ] Address/Neighborhood
- [ ] Property type (apartment, house, land, commercial)
- [ ] Size (m²) - **CRITICAL for comparison**
- [ ] Auction dates
- [ ] Court/Executor info
- [ ] Full description (parse for room count, floor, etc.)

### Market Sources - MUST HAVE
- [ ] Price (EUR)
- [ ] City/District
- [ ] Size (m²)
- [ ] Property type
- [ ] Price per m²

## Technical Challenges

### 1. КЧСИ Scraping
- 92 pages, 12 listings per page
- Need to fetch DETAIL pages for full info (size, description)
- Detail URL: https://sales.bcpea.org/properties/{id}

### 2. Market Sources (JS-rendered)
- **imot.bg**: Needs browser - complex URL structure
- **imoti.net**: Needs browser - prices loaded via JS
- **alo.bg**: URL structure changed, needs investigation

### 3. Browser Access
- OpenClaw browser not available in sandbox
- Options:
  a) Use Playwright/Puppeteer in container
  b) Build API proxy on host
  c) Use existing chrome-standalone container

## Implementation Phases

### Phase 1: КЧСИ Full Scrape (NOW)
1. Scrape all 92 pages of listings
2. For each listing, fetch detail page to get:
   - Full description
   - Size (m²)
   - Property type
   - Photos/documents
3. Parse and normalize data
4. Store in SQLite with proper schema

### Phase 2: Market Data Collection
1. Solve browser access issue
2. Build scrapers for each source
3. Focus on Sofia initially, then expand
4. Store comparable listings

### Phase 3: Price Comparison Engine
1. Match КЧСИ properties to market comparables
2. Calculate:
   - Area median price/m²
   - Area mean price/m²
   - Deviation percentage
   - Bargain score (0-100)

### Phase 4: Web App
1. List all КЧСИ auctions
2. Show price comparison for each
3. Filter by bargain score
4. District/city breakdown
5. Price trend charts

## Database Schema

```sql
-- Auctions (КЧСИ)
CREATE TABLE auctions (
    id TEXT PRIMARY KEY,
    url TEXT,
    price_eur REAL,
    city TEXT,
    district TEXT,
    address TEXT,
    property_type TEXT,
    size_sqm REAL,
    rooms INTEGER,
    floor INTEGER,
    description TEXT,
    court TEXT,
    executor TEXT,
    auction_start DATE,
    auction_end DATE,
    announcement_date DATETIME,
    scraped_at DATETIME
);

-- Market Listings (imot.bg, imoti.net, alo.bg)
CREATE TABLE market_listings (
    id TEXT PRIMARY KEY,
    source TEXT,
    url TEXT,
    price_eur REAL,
    city TEXT,
    district TEXT,
    property_type TEXT,
    size_sqm REAL,
    price_per_sqm REAL,
    rooms INTEGER,
    scraped_at DATETIME
);

-- Area Statistics (pre-calculated)
CREATE TABLE area_stats (
    city TEXT,
    district TEXT,
    property_type TEXT,
    median_price_sqm REAL,
    mean_price_sqm REAL,
    listing_count INTEGER,
    updated_at DATETIME,
    PRIMARY KEY (city, district, property_type)
);

-- Auction Comparisons
CREATE TABLE auction_comparisons (
    auction_id TEXT PRIMARY KEY,
    area_median_sqm REAL,
    area_mean_sqm REAL,
    auction_price_sqm REAL,
    deviation_from_median REAL,  -- percentage
    deviation_from_mean REAL,    -- percentage
    bargain_score INTEGER,       -- 0-100
    comparable_count INTEGER,
    updated_at DATETIME
);
```

## QA Checklist
- [ ] All КЧСИ pages scraped (92 pages)
- [ ] Detail pages fetched for each listing
- [ ] Size (m²) extracted for residential
- [ ] No N/A values for key fields
- [ ] District filter works correctly
- [ ] Price comparisons accurate
- [ ] Bargain scores make sense

## Status
- [x] Basic scraper structure
- [ ] КЧСИ full scrape with details
- [ ] Market source scrapers
- [ ] Price comparison engine
- [ ] Production web app
