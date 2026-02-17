# Changelog

## 2026-02-17 - Production Hardening (P0 + P1 Fixes)

### P0 - Critical Fixes
- **Address parsing** (`bcpea_scraper.py`): Reject HTML fragments, URLs, and garbage from address extraction. Require Cyrillic characters.
- **Floor regex** (`bcpea_scraper.py`): Narrowed to description section only. Added sanity check (1-30). Prevents false matches from navigation/forms.
- **Thread safety** (`bcpea_scraper.py`): Added `threading.Lock()` around all SQLite writes from thread pool. Prevents DB corruption.
- **Discount bug** (`export_deals.py`): Negative discounts now set to `None` instead of `0`. No longer hides overpriced properties.
- **XSS protection** (`app.js`): Added `escHtml()` function. City, property type, and neighborhood escaped in modal innerHTML.

### P1 - Important Fixes
- **Rate limiting** (`bcpea_scraper.py`): Reduced thread pool from 8 to 4 workers.
- **Bare excepts** (all files): Replaced with specific exception types (`ValueError`, `TypeError`, `sqlite3.Error`).
- **Error logging** (`bcpea_scraper.py`): Log errors instead of silently swallowing them.
- **DB indexes** (`export_deals.py`): Auto-create composite index `(city, size_sqm)` on market_listings.
- **Outlier filtering** (`export_deals.py`): Market price queries now filter `200 < price_per_sqm < 5000` to remove bad data.
- **Import path** (`export_deals.py`): Use `__file__`-relative path instead of hardcoded `src/matching`.
- **Pipeline safety** (`run_pipeline.py`): Removed `shell=True` from subprocess calls. Fixed hardcoded Playwright browser path.
- **Floor in INSERT** (`bcpea_scraper.py`): Floor data now saved to DB during both full and incremental scans.

## 2026-02-16 - UI/UX Cleanup
- Removed AI-generated feel (emojis, exclamation marks)
- Added Русе and Стара Загора to scrapers

## 2026-02-15 - Floor Data
- Added floor extraction from КЧСИ descriptions
- Added neighborhood matching
