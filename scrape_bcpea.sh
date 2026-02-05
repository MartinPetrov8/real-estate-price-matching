#!/bin/bash
# BCPEA Auction Scraper - Sofia properties

mkdir -p data
echo "[]" > data/bcpea_sofia.json

for page in $(seq 1 92); do
  echo "Scraping page $page..."
  curl -s "https://sales.bcpea.org/properties?page=$page" > /tmp/page.html
  
  # Extract Sofia properties with prices using grep/sed
  grep -B5 "гр\. София" /tmp/page.html | grep -oP '[\d\s]+\.\d+\s*EUR' | head -5 >> /tmp/sofia_prices.txt
  
  sleep 0.5  # Be nice to server
done

echo "Done! Found $(wc -l < /tmp/sofia_prices.txt) Sofia prices"
