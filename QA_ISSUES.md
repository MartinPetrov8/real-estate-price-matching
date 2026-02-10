# QA Issues & Edge Cases

## Active Issues (2026-02-10)

### 1. Partial Ownership Still Shows Discount %
**Status:** FIXING
**Problem:** Properties like ID 85435 (1/4 share) show 87% discount when they shouldn't
**Solution:** Frontend should show "Дробна собственост" instead of discount % for partial ownership

### 2. Expired Auctions Showing
**Status:** FIXING  
**Problem:** "⏰ Край на търга: Приключи" shown for expired auctions
**Root cause:** `auction_end` is NULL for most properties (scraper not capturing dates)
**Solution:** 
- Short-term: Filter out properties where auction has ended
- Long-term: Fix scraper to capture auction_end dates

### 3. Property Type Filter Returns 0 for House/Garage
**Status:** FIXING
**Problem:** Filter for "Къща" or "Гараж" returns 0 results
**Root cause:** deals.json only contains apartments (from comparison script)
**Solution:** Export ALL property types, show basic info without price comparison

### 4. Non-Apartment Types Incorrectly Classified
**Status:** MONITORING
**Types to exclude from apartment comparison:**
- Магазин (shop) - 22 in DB
- Офис (office) - 15 in DB
- Заведение (restaurant)
- Склад (warehouse) - 12 in DB
- Гараж (garage) - 23 in DB
- Ателие, Таван (attic studio) - 14 in DB
- Земеделска земя (agricultural land)
- Парцел (plot)

## Partial Ownership Detection Patterns

### Currently Detected (is_partial_ownership = 1)
- `1/2`, `½`, `една втора`, `половин идеална част`
- `1/3`, `една трета`
- `1/4`, `¼`, `една четвърт`
- `1/5`, `една пета`
- `1/6`, `една шеста`
- `ид.ч.`, `идеална част`, `идеални части`

### Edge Cases to Watch
- Fractions like `419/1001` (not partial ownership, just cadastral numbers)
- Properties with "част от" in description
- Multiple property bundles

## High Discount Verification (50%+)

All 50%+ discounts should be manually verified:

| ID | City | Discount | Status | Notes |
|----|------|----------|--------|-------|
| 85226 | Варна | 91% | ⚠️ PARTIAL | Correctly flagged |
| 85435 | Варна | 90% | ⚠️ PARTIAL | 1/4 share - correctly flagged |
| 85505 | София | 86% | ⚠️ PARTIAL | Correctly flagged |
| 85849 | Варна | 86% | ⚠️ PARTIAL | Correctly flagged |
| 85286 | София | 82% | ⚠️ PARTIAL | Correctly flagged |
| 85383 | София | 71% | ⚠️ PARTIAL | Correctly flagged |
| 84300 | Варна | 56% | ✅ LEGIT | Full ownership, real deal |

## Property Type Classification

### Should Compare to Market (apartments only)
- Едностаен апартамент
- Двустаен апартамент
- Тристаен апартамент
- Многостаен апартамент

### Show Without Comparison (basic info only)
- Къща, Къща с парцел, Етаж от къща
- Гараж
- Вила
- Парцел, Парцел с къща
- Земеделска земя
- Магазин, Офис, Склад
- Ателие, Таван

## Frontend Display Rules

1. **Partial Ownership:** Show "⚠️ Дробна собственост" badge, NO discount %
2. **Expired Auctions:** Don't show at all (or show with "Приключил" badge, grayed out)
3. **Non-Apartments:** Show basic info, NO market comparison or discount
4. **Valid Apartments:** Show full comparison with discount %

## Database Schema Notes

- `is_partial_ownership`: 1 = partial, 0 = full ownership
- `is_expired`: 1 = expired, 0 = active
- `auction_end`: Date string or NULL (many NULL - scraper issue)
- `property_type`: Bulgarian string describing property type
