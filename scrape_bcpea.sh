#!/bin/bash
cd /workspace/real-estate-price-matching
python3 scrapers/bcpea_v5.py --start-id 85000 --end-id 86000
python3 scrapers/neighborhood_comparison.py
python3 export_deals_v2.py
