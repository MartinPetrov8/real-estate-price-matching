# КЧСИ Scraper Prototype - Detailed Plan

## 🎯 Objective

Build a working scraper that:
1. Extracts all property listings from sales.bcpea.org
2. Parses structured data (price, location, dates, executor)
3. Stores in database for querying
4. Sends alerts for new listings matching criteria

---

## 📊 Data Source Analysis

**URL:** https://sales.bcpea.org/properties

**Pagination:** 12 items per page, ~85+ pages (~1,027 listings)

**Data Points Available:**
- Starting price (EUR)
- Location (city/village)
- Address (partial)
- Regional court (Окръжен съд)
- Executor name (ЧСИ)
- Bidding period (from - to dates)
- Announcement date/time
- Property ID (from URL)

**Missing from list view:**
- Property type (apartment, house, land, commercial)
- Size (sqm)
- Detailed description
- Photos

**Detail page likely has:** Full description, photos, legal info

---

## 🔧 Technical Approach

### Stack
- **Runtime:** Node.js
- **HTTP Client:** axios
- **HTML Parser:** cheerio
- **Database:** SQLite (simple, portable)
- **Alerting:** Telegram Bot API

### Scraping Strategy
1. Fetch listing pages sequentially (with delays)
2. Parse basic data from list view
3. Optionally fetch detail pages for full info
4. Store new listings, update existing
5. Diff against previous run to find new items
6. Send Telegram alerts for new matches

### Rate Limiting
- 2-second delay between requests
- Respectful User-Agent
- No parallel requests
- Run once per hour max

---

## 📐 Data Schema

```sql
CREATE TABLE listings (
  id TEXT PRIMARY KEY,           -- from URL: /properties/85750
  price_eur REAL,
  city TEXT,
  address TEXT,
  court TEXT,
  executor TEXT,
  bid_start DATE,
  bid_end DATE,
  announce_date DATETIME,
  property_type TEXT,            -- if available
  size_sqm REAL,                 -- if available
  description TEXT,              -- from detail page
  url TEXT,
  first_seen DATETIME,
  last_seen DATETIME,
  notified BOOLEAN DEFAULT 0
);

CREATE TABLE alerts (
  id INTEGER PRIMARY KEY,
  user_id TEXT,                  -- Telegram user ID
  city TEXT,                     -- filter: city name or NULL for any
  max_price_eur REAL,            -- filter: max price or NULL
  min_price_eur REAL,            -- filter: min price or NULL
  keywords TEXT,                 -- comma-separated keywords
  active BOOLEAN DEFAULT 1,
  created_at DATETIME
);
```

---

## 🔄 Process Flow

```
┌─────────────────────┐
│   Cron Trigger      │
│   (every 2 hours)   │
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│   Fetch Page 1      │
│   Parse Listings    │
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│   Has Next Page?    │──No──┐
└──────────┬──────────┘      │
           │ Yes             │
           ▼                 │
┌─────────────────────┐      │
│   Wait 2 seconds    │      │
│   Fetch Next Page   │      │
└──────────┬──────────┘      │
           │                 │
           └────────◄────────┘
                    │
                    ▼
┌─────────────────────┐
│   Upsert to DB      │
│   Mark last_seen    │
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│   Find new listings │
│   (first_seen=now)  │
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│   Match against     │
│   alert rules       │
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│   Send Telegram     │
│   notifications     │
└─────────────────────┘
```

---

## 📝 MVP Scope

### Include
- [x] Basic list page scraper
- [x] SQLite storage
- [x] New listing detection
- [x] Console output of new listings
- [ ] Telegram alerting (needs bot token)

### Exclude (Phase 2)
- Detail page scraping
- Photo extraction
- AI valuation comparison
- Web dashboard
- User registration

---

## ⚠️ Technical Risks

| Risk | Mitigation |
|------|------------|
| Site structure changes | Use resilient selectors, monitor for failures |
| IP blocking | Respectful rate limits, can add proxy if needed |
| Data encoding issues | Handle Bulgarian text properly (UTF-8) |
| Price format variations | Robust parsing with fallbacks |

---

## ✅ Success Criteria

1. Scrapes all ~1,000 listings successfully
2. Correctly parses price, location, dates
3. Identifies new listings between runs
4. Runs without errors for 24 hours
5. Alert matching works for sample criteria
