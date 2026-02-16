# Changelog

## [2026-02-16] OLX Playwright Scraper

### Added
- `scrapers/olx_playwright.py` - Playwright-based OLX scraper (bypasses CAPTCHA)
- Playwright to requirements.txt

### Fixed
- OLX scraping now works (was blocked by CAPTCHA since ~Feb 2026)
- EUR price extraction (was grabbing BGN first)

### Changed
- `run_pipeline.py` - Now runs both imot.bg (requests) and OLX (Playwright)
- Pipeline uses `PLAYWRIGHT_BROWSERS_PATH` environment variable

### Stats
- imot.bg: 178 listings (6 cities)
- OLX: 179 listings (4 cities)
- BCPEA: 1,114 auctions

---

## [2026-02-15] Production Ready

### Added
- FAQ section explaining rating system (Bulgarian)
- Mobile-responsive fixes
- Data quality: require ≥3 comparables for discount

### Fixed
- SQL injection vulnerability
- Database indexes
- Removed 29 duplicate files (14,683 lines)

### Stats
- 94 deals exported
- 15 validated with ≥3 comparables
- Top deal: Varna -53%
