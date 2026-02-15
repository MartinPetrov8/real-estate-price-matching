# 🏠 Bulgarian Real Estate Auction Analyzer

Scrapes КЧСИ (BCPEA) court-enforced property auctions and compares prices to market listings to find bargains.

[![Live Site](https://img.shields.io/badge/Live-GitHub%20Pages-brightgreen)](https://martinpetrov8.github.io/real-estate-price-matching/)
![Status](https://img.shields.io/badge/status-Production-green)
![Python](https://img.shields.io/badge/python-3.8+-blue)

## 🎯 Features

- **КЧСИ Scraper**: Extracts auction listings from [sales.bcpea.org](https://sales.bcpea.org)
- **Market Scrapers**: Aggregates listings from imot.bg and OLX.bg
- **Price Comparison**: Calculates discount vs market median €/m²
- **Bargain Detection**: Finds properties selling below market value
- **Web Frontend**: Bulgarian UI showing top deals

## 📊 Current Data (Updated Daily)

| Source | Type | Listings | Avg €/m² |
|--------|------|----------|----------|
| КЧСИ (bcpea.org) | Auctions | ~1,100 | varies |
| OLX.bg | Market | ~490 | €1,868 |
| imot.bg | Market | ~120 | €2,114 |

**Cities covered:** София, Пловдив, Варна, Бургас

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/MartinPetrov8/real-estate-price-matching.git
cd real-estate-price-matching

# Install dependencies
pip install -r requirements.txt

# Run full pipeline (scrape + export + push)
python run_pipeline.py

# Or run individual components:
python scrapers/market_scraper.py  # Scrape market data (~3 min)
python export_deals.py             # Export deals to frontend
```

## 📁 Project Structure

```
real-estate-price-matching/
├── scrapers/
│   ├── market_scraper.py    # Production market scraper (imot.bg, olx.bg)
│   ├── bcpea_scraper.py     # КЧСИ auction scraper
│   └── archive/             # Legacy scraper versions
├── data/
│   ├── auctions.db          # Auction data (SQLite)
│   └── market.db            # Market listings (SQLite)
├── docs/
│   ├── ARCHITECTURE.md      # System design
│   └── PIPELINE.md          # Daily pipeline docs
├── frontend/
│   └── deals.json           # Frontend data
├── export_deals.py          # Compare & export deals
├── run_pipeline.py          # Daily pipeline runner
├── requirements.txt         # Python dependencies
├── deals.json              # Root copy for GitHub Pages
└── index.html              # Frontend
```

## 🔄 Daily Pipeline

The pipeline runs automatically at 6:00 AM Sofia time:

1. **Scrape** market data from imot.bg and olx.bg
2. **Compare** auction prices to market medians
3. **Export** top deals to `deals.json`
4. **Push** to GitHub (triggers Pages rebuild)

See [docs/PIPELINE.md](docs/PIPELINE.md) for details.

## 📖 Documentation

- [Architecture Overview](docs/ARCHITECTURE.md) - System design, database schema
- [Pipeline Guide](docs/PIPELINE.md) - Daily automation, troubleshooting
- [Scrapers README](scrapers/README.md) - Scraper implementation details

## 🛠️ Tech Stack

- **Language:** Python 3.8+
- **Database:** SQLite3
- **Scraping:** requests, BeautifulSoup4
- **Frontend:** Static HTML/JS
- **Hosting:** GitHub Pages
- **Automation:** OpenClaw cron

## 📈 Sample Output

Top deals found (example):
| City | Price | Size | €/m² | Market | Discount |
|------|-------|------|------|--------|----------|
| Варна | €66,632 | 80m² | €838 | €1,749 | **-52%** |
| София | €111,871 | 86m² | €1,303 | €2,213 | **-41%** |
| Бургас | €53,600 | 61m² | €875 | €1,397 | **-37%** |

## 📝 License

MIT License - see [LICENSE](LICENSE)

## 👨‍💻 Authors

- Martin Petrov
- Cookie 🍪 (AI Assistant)
