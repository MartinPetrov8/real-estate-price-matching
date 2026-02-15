# Data Quality Assurance - Real Estate Price Matching

## Overview

This document describes the data flow, validation rules, and quality checks
for the КЧСИ price comparison system.

---

## Data Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  КЧСИ Auctions  │     │  Market Data    │     │  Price Compare  │
│  (bcpea.org)    │     │  (OLX, imot.bg) │     │  (export)       │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         ▼                       ▼                       ▼
   bcpea_scraper.py      market_scraper.py       export_deals.py
         │                       │                       │
         ▼                       ▼                       ▼
   data/auctions.db        data/market.db          deals.json
```

---

## Validation Rules

### 1. Market Comparison Requirements

| Rule | Value | Reason |
|------|-------|--------|
| **Minimum comparables** | ≥3 | Statistical reliability |
| **Size tolerance** | ±15 m² | Similar property size |
| **City match** | Exact | Local market comparison |

**If < 3 comparables:** No discount percentage shown.

### 2. Price Validation

| Check | Range | Action if Failed |
|-------|-------|------------------|
| Price/m² | €200 - €15,000 | Exclude listing |
| Size | 15 - 500 m² | Exclude listing |
| Total price | > €5,000 | Require for market listing |

### 3. Property Type Matching

Only **apartments** get market comparison:
- Market data only scraped for apartments
- Houses, garages, commercial → No discount shown

### 4. Partial Ownership

Properties with fractional shares (1/2, 1/4, 1/6):
- Flagged as "Дробна собственост"
- **No discount calculated** (price is for fraction only)

---

## Frontend Display Rules

### Discount Display
```
comparables_count ≥ 3:  Show discount with "Based on X comparables"
comparables_count < 3:  Show "Insufficient data for comparison"
comparables_count = 0:  Show "No comparison data"
```

### Rating (Stars)
```
5★: discount ≥ 40%
4★: discount ≥ 30%
3★: discount ≥ 20%
2★: discount ≥ 10%
1★: discount > 0%
0★: No discount or insufficient data
```

---

## Data Fields (deals.json)

| Field | Type | Description |
|-------|------|-------------|
| `price` | int | Auction starting price (EUR) |
| `market_price` | int | Estimated market price (EUR) |
| `market_avg` | int | Market €/m² average |
| `discount` | float | Percentage below market (null if unreliable) |
| `comparables_count` | int | Number of similar listings used |
| `savings_eur` | int | Potential savings in EUR |
| `partial_ownership` | str | Warning if fractional share |

---

## Quality Checks (Automated)

Run after each export:

```bash
python3 -c "
import json
with open('deals.json') as f:
    deals = json.load(f)

# Check 1: No discount without comparables
bad = [d for d in deals if d.get('discount') and d.get('comparables_count', 0) < 3]
assert len(bad) == 0, f'{len(bad)} deals show discount with <3 comparables'

# Check 2: No discount for partial ownership
partial_with_discount = [d for d in deals if d.get('partial_ownership') and d.get('discount')]
assert len(partial_with_discount) == 0, 'Partial ownership deals showing discount'

# Check 3: Reasonable discounts (0-70%)
extreme = [d for d in deals if d.get('discount', 0) > 70]
assert len(extreme) == 0, f'{len(extreme)} deals with >70% discount'

print('✅ All quality checks passed')
"
```

---

## Troubleshooting

### "Discount shown but no comparables"
1. Check `comparables_count` in deals.json
2. Verify market.db has listings for that city
3. Check size range (±15 m²)

### "High discount seems unreliable"
1. Check `comparables_count` - should be ≥10 for high confidence
2. Verify market listings are current (scraped recently)
3. Check for data entry errors in auction price

### "No comparisons for apartments"
1. Check market_scraper ran successfully
2. Verify city name matches exactly (Bulgarian spelling)
3. Check apartment size is in typical range (30-150 m²)

---

*Last updated: 2026-02-15*
