# КЧСИ Deal Finder

Find underpriced properties in Bulgarian enforcement auctions by comparing КЧСИ prices to market data.

## Quick Start

```bash
# Install dependencies
npm install

# Run full pipeline (scrapes КЧСИ + market data + analyzes deals)
npm run full

# Or step by step:
npm run scrape        # Scrape КЧСИ listings
npm run market        # Scrape market data (requires Puppeteer)
npm run analyze       # Run analysis with cached data
```

## How It Works

1. **КЧСИ Scraper** - Extracts all ~1000 auction listings from sales.bcpea.org
2. **Market Scraper** - Uses Puppeteer to scrape homes.bg/imot.bg for comparison
3. **Deal Finder** - Matches properties and calculates "deal score" (1-5 stars)

## Deal Score

| Score | Discount vs Market | Verdict |
|-------|-------------------|---------|
| ⭐⭐⭐⭐⭐ | >35% | Exceptional deal |
| ⭐⭐⭐⭐ | 25-35% | Strong buy |
| ⭐⭐⭐ | 15-25% | Good deal |
| ⭐⭐ | 5-15% | Slight discount |
| ⭐ | ±5% | Market price |
| ❌ | Above market | Skip |

## CLI Options

```bash
# Full pipeline
node full-pipeline.js [options]

Options:
  --city=sofia       Target city (sofia, plovdiv, varna, burgas)
  --skip-kcsi        Use cached КЧСИ data
  --skip-market      Use cached market data
```

## Output

Reports are saved to `./reports/`:
- `deal-report-{city}-{date}.json` - Full analysis
- `market-cache-{city}.json` - Cached market data

## Files

```
├── scraper.js        # КЧСИ list page scraper
├── browser-scraper.js # Puppeteer-based market scraper
├── market-scraper.js  # Comparison utilities
├── deal-finder.js     # Deal scoring algorithm
├── full-pipeline.js   # Main orchestrator
└── run-analysis.js    # Legacy analysis runner
```

## Requirements

- Node.js 18+
- Puppeteer (for browser automation)
- ~500MB disk for Chrome/Chromium

## Notes

- КЧСИ auctions have 30-day bidding windows
- Most КЧСИ listings are NOT apartments (land, garages, commercial)
- Pipeline filters for residential in €15k-300k range
- Market comparison works best for Sofia (most data)
