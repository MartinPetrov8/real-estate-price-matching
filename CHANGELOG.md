# Changelog

## 2026-03-26 - Pipeline Resilience + Dependency Fix

### Bug Fixes
- **ensure-tools.sh pip path hardcoded** (`scripts/ensure-tools.sh`): `pip_install()` was hardcoded to `/home/node/.local/bin/pip` which does not exist in the container. This caused silent failures on every container restart — `bs4`, `lxml`, `requests`, `anthropic` were never actually installed. Fixed to auto-detect the correct pip binary (`pip` → `pip3` → `python3 -m pip`).
- **PYTHONPATH unbound variable** (`scripts/ensure-tools.sh`): `export PYTHONPATH=...:$PYTHONPATH` crashed with `unbound variable` when PYTHONPATH was not already set. Fixed to `${PYTHONPATH:-}`.
- **Missing dep: bs4 + lxml** (2026-03-25 outage): Both packages were missing after a container restart. Pipeline pre-flight correctly detected and blocked the run, but ensure-tools.sh auto-restore silently failed due to the above pip path bug. Mar 25 pipeline did not run. Fixed by patching ensure-tools.sh.

### Resilience Improvements
- **market_scraper.py `fetch_page()` timeout**: Changed from single `timeout=30` to split `timeout=(connect=15, read=45)` tuple. This prevents indefinite hangs when slow sites (imot.bg, OLX on smaller cities like Стара Загора/Русе) accept the TCP connection but delay sending response bytes. Old single timeout only guarded against connection failures, not slow reads. New split timeout gives 45s read window (generous for slow sites) while capping total per-attempt to 60s.
- **Timeout logging**: Added explicit `requests.exceptions.Timeout` catch with log message showing connect/read values, distinct from generic `RequestException`. Easier to diagnose future network issues.
- **Backoff on timeout**: Exponential backoff (2^attempt seconds) now applies to timeouts too — gives slow external sites recovery time between retries.

### Root Cause Analysis
| Date | Issue | Impact | Fix |
|------|-------|--------|-----|
| 2026-03-25 | bs4/lxml missing after restart | ❌ Pipeline skipped entirely | ensure-tools.sh pip path fixed |
| 2026-03-26 | market_scraper hung on Стара Загора | ❌ Pipeline killed, no data update | fetch_page() read timeout added |
| Both | ensure-tools.sh pip path wrong | Silent dep install failures | Auto-detect pip binary |

## 2026-03-03 - Neighborhood Accuracy + UI/UX Overhaul

### Data Pipeline Fixes
- **BCPEA Район extraction** (`scrapers/bcpea_scraper.py`): Scraper now extracts the structured "Район" field from BCPEA property pages (e.g. "Овча купел", "Оборище"). Previously only extracted address text, missing the district entirely.
- **Neighborhood in DB inserts** (`scrapers/bcpea_scraper.py`): Added `neighborhood` column to both full-scan and incremental-scan INSERT statements.
- **Street lookup scoping** (`neighborhood_matcher.py`): All 6 Sofia street→neighborhood mappings now scoped to `['софия']`. Previously unscoped `[]` caused cross-city contamination (e.g. ул. Стамболийски in Кула → "красно село").
- **Street map fix** (`neighborhood_matcher.py`): `ул. Роден кът` corrected from `витоша` → `овча купел`.
- **Sofia neighborhood clusters** (`neighborhood_matcher.py`): Added 6 geographic clusters (център, южен, запад, изток, север, среден център) for fallback comparisons. Similarity score 0.75 for same-cluster neighborhoods.
- **Cross-city misclassifications**: Fixed 3 properties (Силистра, Кула, с. Екзарх Йосиф) incorrectly tagged with Sofia neighborhoods.
- **Full neighborhood sweep**: Audited all 543 active auctions against BCPEA structured data — 0 mismatches after fixes.

### Frontend / UI
- **Logo scroll-to-top** (`index.html`, `app.js`): Clicking logo scrolls to top (mobile UX).
- **Tagline fix**: "Изгодни имоти от търгове" → "Изгодни имоти под пазарна цена" (removed "търгове" redundancy with site name).
- **Hero reword** (`index.html`): "Имоти от Частни Съдебни Изпълнители" → "Намерете имоти под пазарна цена" (benefit-first, no repetition).
- **Brand unification**: Replaced "КЧСИ Сделки" → "ЧСИ Търгове" across all 14 HTML files (cities, blog, contact, privacy, 404).
- **Logo enlarged**: 56px → 67px (HTML) / 64px → 77px (CSS), ~20% larger.
- **Warning text fix** (`app.js`): "Частна собственост - проверете дела" → "Недостатъчни имоти за сравнение" (partial ownership properties now correctly explain why there's no market comparison).
- **Pin emoji removed** from cities page title.

### UI/UX Polish (from professional review)
- **Hero stats placeholder**: Show "—" instead of "0" before JavaScript loads.
- **Color consistency**: Replaced all hardcoded `#667eea` and `#1a1a2e` with CSS variables (`var(--primary)`, `var(--gray-700)`) across blog/FAQ/cookie sections.
- **Price vs discount hierarchy**: Price bumped to 26px/800 weight, discount badge reduced to 16px — clear visual hierarchy.
- **Collapsible FAQ**: FAQ items now toggle open/closed with +/− indicator. First item open by default.
- **Mobile hero stats**: Stats stay in horizontal row on mobile (no longer stack vertically pushing content below fold).
- **Data freshness indicator**: "Данни от: [дата]" shown next to results count.

### Performance
- **`defer` on scripts** (`index.html`): All 3 script tags now use `defer` attribute.
- **Mobile touch targets** (`styles.css`): Filter pills, selects, modal close button all ≥44px on mobile.
- **Keyboard navigation**: Filter pills and logo now support Enter/Space key activation.
- **Single global countdown**: Replaced 100+ per-card `setInterval` with one global timer updating all `[data-end]` elements.
- **Fluid typography**: Hero title uses `clamp(24px, 4vw + 12px, 42px)` instead of fixed breakpoints.
- **Twitter image meta**: Added missing `twitter:image` meta tag.

### Typo Fixes
- "пазарната ниво" → "пазарното ниво" (gender agreement, 4 occurrences in app.js + app.min.js)

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
