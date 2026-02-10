#!/bin/bash
cd /workspace/real-estate-price-matching

# Scrape КЧСИ properties (optimized range 84000-90000 where listings exist)
# v5 includes fixed partial ownership detection
python3 scrapers/bcpea_v5.py --start-id 84000 --end-id 90000 --include-houses --include-garages --include-small-towns --min-sqm 10 --max-sqm 5000

# Run market comparison
python3 scrapers/neighborhood_comparison.py

# Export to deals.json
python3 export_deals_v2.py

# Push to GitHub
git add -A && git commit -m "Daily КЧСИ scan update" && git push origin main
