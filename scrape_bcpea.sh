#!/bin/bash
cd /workspace/real-estate-price-matching
# Scrape ALL КЧСИ properties (full range)
python3 scrapers/bcpea_v5.py --start-id 80000 --end-id 90000 --include-houses --include-garages --include-small-towns --min-sqm 10 --max-sqm 5000
python3 scrapers/neighborhood_comparison.py
python3 export_deals_v2.py
