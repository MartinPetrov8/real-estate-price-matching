# Bulgarian Real Estate Auction Analyzer

Scrapes КЧСИ (BCPEA) court auctions and compares prices to market listings.

## Features

- **КЧСИ Scraper**: 754 auction listings from https://sales.bcpea.org
- **Market Scrapers**: imot.bg, OLX.bg, alo.bg (~1000 listings)
- **Price Comparison**: Calculates €/m² deviation from market median
- **Bargain Detection**: Scores 0-100 (higher = better deal)

## Matching Criteria

- Same city
- Similar size (±15 sqm)
- Property type: apartments only

## Quick Start

```bash
# Scrape auctions
python scrapers/bcpea_v4.py

# Scrape market data + compare
python scrapers/market_scraper.py

# View top bargains
sqlite3 data/auctions.db "SELECT * FROM comparisons ORDER BY bargain_score DESC LIMIT 10"
```

## Data Sources

| Source | Listings | Notes |
|--------|----------|-------|
| КЧСИ (auctions) | 754 | Court-enforced sales |
| OLX.bg | 853 | Private listings |
| imot.bg | 79 | Agency listings |
| alo.bg | 34 | Mixed |

## Output

Bargain score = 100 means auction is 100% below market (free).
Score of 90+ = auction is 90%+ below market price per sqm.

Example output:
```
гр. Варна: €45,000 (85m²)
  Auction: €529/m² vs Market: €1,981/m² (-73%)
  Score: 73/100
```
