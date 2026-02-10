#!/bin/bash
cd /workspace/real-estate-price-matching
# Scrape ALL property types (apartments, houses, garages, commercial, land)
# Expanded range 84000-86000 to capture property 84744
python3 scrapers/bcpea_v5.py --start-id 84000 --end-id 86000 --include-houses --include-garages --include-small-towns --min-sqm 10 --max-sqm 1000
python3 scrapers/neighborhood_comparison.py
python3 export_deals_v2.py
