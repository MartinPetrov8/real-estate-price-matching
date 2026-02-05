#!/usr/bin/env python3
"""
imot.bg Production Scraper
Uses browser automation to extract property listings
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

def parse_price(price_str):
    """Extract price in EUR from string like '255 000 €' or '498 736.65 лв.'"""
    if not price_str:
        return None
    
    # Clean the string
    price_str = price_str.replace('\xa0', ' ').replace(' ', '').strip()
    
    # Try EUR first
    eur_match = re.search(r'([\d,.]+)\s*€', price_str.replace(' ', ''))
    if eur_match:
        return float(eur_match.group(1).replace(',', '').replace(' ', ''))
    
    # Try BGN (convert to EUR at ~1.96)
    bgn_match = re.search(r'([\d,.]+)\s*лв', price_str.replace(' ', ''))
    if bgn_match:
        bgn = float(bgn_match.group(1).replace(',', '').replace(' ', ''))
        return round(bgn / 1.9558, 2)  # Fixed EUR/BGN rate
    
    return None

def parse_size(size_str):
    """Extract size in sqm from string like '68 кв.м'"""
    if not size_str:
        return None
    match = re.search(r'(\d+)\s*кв\.?м?', size_str.replace(' ', ''))
    if match:
        return int(match.group(1))
    return None

def parse_listing_from_snapshot(text_block):
    """Parse a single listing from snapshot text"""
    listing = {}
    
    # Extract price
    price_match = re.search(r'([\d\s]+)\s*€', text_block)
    if price_match:
        price_str = price_match.group(1).replace(' ', '').replace('\xa0', '')
        listing['price_eur'] = int(price_str) if price_str.isdigit() else None
    
    # Extract size
    size_match = re.search(r'(\d+)\s*кв\.?м', text_block)
    if size_match:
        listing['size_sqm'] = int(size_match.group(1))
    
    # Calculate price per sqm
    if listing.get('price_eur') and listing.get('size_sqm'):
        listing['price_per_sqm'] = round(listing['price_eur'] / listing['size_sqm'], 2)
    
    return listing

def extract_listings_from_snapshot(snapshot_text):
    """
    Extract all listings from a browser snapshot
    Returns list of listing dicts
    """
    listings = []
    
    # Pattern for listing blocks - they contain price in EUR, size, and location
    # Looking for patterns like: "255 000 € 498 736.65 лв. 68 кв.м"
    listing_pattern = re.compile(
        r'link\s+"[^"]*Продава\s+([^"]+)"[^}]*'
        r'url:\s*//www\.imot\.bg/obiava-([^\s]+)',
        re.MULTILINE | re.DOTALL
    )
    
    # Alternative simpler pattern for text content
    price_size_pattern = re.compile(
        r'(\d[\d\s]*)\s*€\s*[\d\s,.]+\s*лв\.\s*(\d+)\s*кв\.м',
        re.MULTILINE
    )
    
    # Find all price/size pairs
    for match in price_size_pattern.finditer(snapshot_text):
        price_str = match.group(1).replace(' ', '').replace('\xa0', '')
        size_str = match.group(2)
        
        try:
            price = int(price_str)
            size = int(size_str)
            if price > 0 and size > 0:
                listings.append({
                    'price_eur': price,
                    'size_sqm': size,
                    'price_per_sqm': round(price / size, 2)
                })
        except ValueError:
            continue
    
    return listings

# Property types mapping
PROPERTY_TYPES = {
    'ednostaen': '1-стаен',
    'dvustaen': '2-стаен',
    'tristaen': '3-стаен',
    'chetiristaen': '4-стаен',
    'mnogostaen': '5+ стаен',
    'mezonet': 'мезонет',
    'kashta': 'къща',
    'vila': 'вила',
    'partsel': 'парцел',
}

# Major cities
CITIES = [
    'grad-sofiya',
    'grad-plovdiv', 
    'grad-varna',
    'grad-burgas',
    'grad-ruse',
    'grad-stara-zagora',
]

def get_search_urls(city='grad-sofiya', property_type='dvustaen', max_pages=5):
    """Generate URLs for scraping"""
    base = f"https://www.imot.bg/obiavi/prodazhbi/{city}/{property_type}"
    urls = [base]
    for page in range(2, max_pages + 1):
        urls.append(f"{base}/p-{page}")
    return urls

if __name__ == '__main__':
    # Test parsing
    test_text = "255 000 € 498 736.65 лв. 68 кв.м"
    listings = extract_listings_from_snapshot(test_text)
    print(f"Parsed {len(listings)} listings")
    for l in listings:
        print(f"  {l}")
