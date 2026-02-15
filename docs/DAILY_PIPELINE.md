# Daily Pipeline Documentation

## Overview

One cron job runs daily at **9:00 AM Sofia time** (7:00 AM UTC).

**Cron ID:** `42b97908-51fa-4f92-8fb9-e7003d2d02c7`

---

## Pipeline Steps

### 1. КЧСИ Incremental Scrape
```bash
python3 scrapers/bcpea_scraper.py --incremental
```

**Logic:**
1. Get existing active auction IDs from DB (`is_expired = 0`)
2. Fetch current auction IDs from bcpea.org (all 28 courts)
3. Calculate: `new_ids = current - existing`
4. Calculate: `expired_ids = existing - current`
5. Only fetch details for NEW properties
6. Mark expired properties with `is_expired = 1`

**NOT doing:**
- ❌ Full ID range scanning
- ❌ Re-fetching existing auctions
- ❌ Guessing IDs

---

### 2. Market Data Scrape
```bash
python3 scrapers/market_scraper.py
```

**Cities covered:** София, Варна, Пловдив, Бургас

**Sources:**
- imot.bg (~150 listings)
- olx.bg (~500 listings)

**Coverage:**
- ~11% of auctions are in these 4 cities
- Small villages don't have market data on OLX/imot.bg

---

### 3. Export Deals
```bash
python3 export_deals.py
```

**Logic:**
1. Join auctions + market data by city and size (±15 m²)
2. Require ≥3 comparable listings for discount calculation
3. Calculate: `discount = (market_median - auction_price_per_sqm) / market_median`
4. Output to `frontend/deals.json`

---

### 4. Git Push
```bash
cp frontend/deals.json deals.json
git add -A && git commit -m "Daily pipeline YYYY-MM-DD" && git push
```

Updates GitHub Pages site automatically.

---

## Expired Auction Handling

Auctions are marked expired when:
1. No longer appear on bcpea.org listing pages
2. `auction_end` date has passed

Expired auctions:
- Set `is_expired = 1` in database
- Excluded from export to frontend
- NOT deleted (kept for historical analysis)

---

## Data Flow Diagram

```
bcpea.org (28 courts)
       │
       ▼ (incremental)
  bcpea_scraper.py
       │
       ▼
  data/auctions.db ──────────────┐
                                  │
  imot.bg + olx.bg               │
       │                          │
       ▼                          ▼
  market_scraper.py          export_deals.py
       │                          │
       ▼                          ▼
  data/market.db            deals.json
                                  │
                                  ▼
                           GitHub Pages
```

---

## Monitoring

Check cron status:
- Last run time
- Duration (~10-15 min expected)
- Any errors

Delivery: Announces summary to Telegram topic after completion.
