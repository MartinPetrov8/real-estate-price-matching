# Real Estate Matcher — PLAN

## Objective
Build a Sofia-focused sales-listing intelligence pipeline (for sale only, no rent) across top agency feeds (imot.bg subdomains) and prepare matching logic to detect likely duplicate listings across agencies.

## Scope (Phase 1)
- Seed 20 agency feeds from imot.bg (Sofia ecosystem)
- Scrape sale listings into a fresh SQLite DB
- Normalize key fields (price, sqm, type, floor, neighborhood, agency, source URL)
- Add first-pass fuzzy matching to identify likely same-property clusters
- Produce daily digest artifacts for pilot review

## Non-goals (Phase 1)
- No public website
- No automated outreach
- No rental listings
- No non-Sofia expansion

## Success Criteria
1. DB populated with >= 1,000 sale listings from the 20 agency feeds
2. Parser success rate >= 90% for key fields (price + area + URL + agency)
3. Matching engine produces candidate clusters with confidence scores
4. Exportable report (CSV/JSON) usable in Telegram digest/manual QA

## Risks
- Source HTML changes / parser brittleness
- Duplicate agencies under multiple subdomains
- False-positive fuzzy matches
- Rate limiting / temporary blocks

## Mitigations (web-scraping skill)
- Polite pacing + jitter delays
- Retry with backoff
- Graceful degradation (continue on per-page failures)
- Structured logs and failed-page tracking
- Keep selectors/parser logic centralized and testable

## Work Plan
### Step 1 — Foundation
- [x] Create project structure
- [x] Create fresh SQLite schema
- [x] Define agency seed list

### Step 2 — Scraping (overnight-ready)
- [ ] Implement paginated sale scraper per agency
- [ ] Persist raw + normalized listing records
- [ ] Capture scrape runs and errors

### Step 3 — Matching
- [ ] Implement fuzzy matching baseline
- [ ] Score by neighborhood + area + price + property type + floor
- [ ] Emit candidate clusters

### Step 4 — Reporting
- [ ] Generate daily snapshot and match candidates
- [ ] Prepare pilot digest format for Address contact

## Deliverables
- `projects/real-estate-matcher/data/real_estate_matcher.db`
- `projects/real-estate-matcher/scripts/scrape_agencies.py`
- `projects/real-estate-matcher/scripts/match_listings.py`
- `projects/real-estate-matcher/docs/agency_seed.md`
- `projects/real-estate-matcher/LOG.md`
