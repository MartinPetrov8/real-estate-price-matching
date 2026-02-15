# Changelog

## [2026-02-15] - Major Cleanup & Features

### Added
- **Neighborhood matching** - Extract district from auction addresses for better price comparison
- **"No Comparison" filter** - Frontend pill to show deals without market data
- **Code audit report** - Security and quality review (`docs/AUDIT_2026-02-15.md`)
- **size_sqm index** - Performance improvement for market queries

### Changed
- **market_scraper.py** - Fixed DB path (`data/market.db` instead of `scrapers/data/market.db`)
- **export_deals.py** - Now uses neighborhood_matcher for address parsing
- **README.md** - Updated with clean project structure

### Removed
- **29 legacy files** (14,683 lines deleted)
  - bcpea_v2, v4, v5, active, fixed, full, id_scan, production scrapers
  - market_scraper_v2, market_data_scraper, etc.
  - Duplicate server.py files
  - Debug HTML/PNG files
  - Legacy src/ code

### Security
- ✅ No SQL injection vulnerabilities
- ✅ No hardcoded credentials
- ✅ All queries parameterized

## [2026-02-13] - Initial Scraper Fixes

### Added
- bcpea_scraper v6 with smart incremental scraping
- market_scraper v4 with requests+BeautifulSoup

### Fixed
- Brotli encoding issue (removed `br` from Accept-Encoding)
- OLX URL format (sofiya not sofia)
- imot.bg windows-1251 encoding
