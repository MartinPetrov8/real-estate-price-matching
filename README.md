# 🏠 Bulgarian Real Estate Auction Analyzer

Scrapes КЧСИ (BCPEA) court-enforced property auctions and compares prices to market listings to find bargains.

**Live:** https://martinpetrov8.github.io/real-estate-price-matching/

![Status](https://img.shields.io/badge/status-MVP-green)
![Python](https://img.shields.io/badge/python-3.8+-blue)

## 🎯 What This Does

1. **Scrapes КЧСИ auctions** from [sales.bcpea.org](https://sales.bcpea.org) - court-enforced property sales
2. **Scrapes market data** from imot.bg and olx.bg for price comparison
3. **Calculates bargain scores** by comparing auction €/m² to market median
4. **Displays results** on a static GitHub Pages site

## 📊 Data Sources

| Source | Type | Purpose |
|--------|------|---------|
| КЧСИ (bcpea.org) | **Main** | Court-enforced auction listings |
| imot.bg | Comparison | Agency market prices |
| olx.bg | Comparison | Private market prices |

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/MartinPetrov8/real-estate-price-matching.git
cd real-estate-price-matching

# Install dependencies
pip install requests beautifulsoup4

# Run full pipeline (scrape + export)
python run_pipeline.py --no-push

# View results
open frontend/deals.json
# Or serve locally: python -m http.server 8080
```

## 📁 Project Structure

```
real-estate-price-matching/
├── scrapers/
│   ├── bcpea_scraper.py      # КЧСИ auction scraper (v6)
│   └── market_scraper.py     # Market scraper (imot.bg, olx.bg)
├── data/
│   ├── auctions.db           # КЧСИ auctions (SQLite)
│   └── market.db             # Market listings (SQLite)
├── frontend/
│   └── deals.json            # Exported deals with comparisons
├── docs/
│   ├── ARCHITECTURE.md       # System design
│   └── PIPELINE.md           # Daily automation
├── export_deals.py           # Generate deals JSON
├── run_pipeline.py           # Pipeline orchestrator
├── index.html                # GitHub Pages site
└── README.md
```

## ⚙️ How It Works

### Daily Pipeline
```bash
python run_pipeline.py
```

1. **Market Scraper** → Fetches ~600 listings from imot.bg + olx.bg
2. **Export Deals** → Joins auctions with market data, calculates discounts
3. **Git Push** → Updates GitHub Pages site

### Bargain Score Calculation

```
discount = (market_median_eur_m2 - auction_eur_m2) / market_median_eur_m2
bargain_score = discount * 100  # e.g., 30 = 30% below market
```

## 📖 Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design, database schema
- [Pipeline](docs/PIPELINE.md) - Daily automation setup
- [Market Scraper](scrapers/README_MARKET_SCRAPER.md) - Scraper details

## ⚠️ Disclaimer

This tool is for research purposes only. Always verify auction details directly on [sales.bcpea.org](https://sales.bcpea.org) before making any decisions. Property auctions involve legal complexity and risk.

## 🚀 Deployment

### Frontend (GitHub Pages)
Automatically deployed from `main` branch to:
https://martinpetrov8.github.io/real-estate-price-matching/

### API (Railway)
Flask API for email subscriptions:
https://web-production-36c65.up.railway.app

**Deploy to Railway:**
1. Connect GitHub repo
2. Add environment variables:
   ```
   RESEND_API_KEY=your_key
   SENDER_EMAIL=onboarding@resend.dev
   SITE_URL=https://martinpetrov8.github.io/real-estate-price-matching
   ```
3. Generate domain in Settings → Networking

### Scrapers
Run locally or via cron:
```bash
# Set Playwright browsers path
export PLAYWRIGHT_BROWSERS_PATH=/path/to/browsers

# Run full pipeline
python run_pipeline.py
```

## 📧 Email Alerts

Users can subscribe for deal alerts via the website. System uses:
- **Resend** for email delivery (free tier: 3K/month)
- **SQLite** for subscriber storage
- **Flask** API on Railway

### Manual alert send:
```bash
cd /path/to/repo
python alerts/send_alerts.py
```
