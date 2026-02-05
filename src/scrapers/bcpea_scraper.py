#!/usr/bin/env python3
"""
КЧСИ (BCPEA) Auction Scraper
Bulgarian Chamber of Private Enforcement Agents - Property Auctions
"""

import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup

BASE_URL = "https://sales.bcpea.org/properties"

def parse_price(text):
    """Extract EUR price from text like '33 110.73 EUR'"""
    match = re.search(r'([\d\s]+(?:\.\d+)?)\s*EUR', text.replace(',', '.'))
    if match:
        return float(match.group(1).replace(' ', ''))
    return None

def scrape_page(page=1, per_page=12):
    """Scrape a single page of auctions"""
    url = f"{BASE_URL}?page={page}&per_page={per_page}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    listings = []
    
    # Parse the text-based format
    text = soup.get_text(separator='\n')
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    current = {}
    for i, line in enumerate(lines):
        if 'EUR' in line and 'Начална цена' in lines[i-1] if i > 0 else False:
            if current:
                listings.append(current)
            current = {'price_eur': parse_price(line)}
        elif 'НАСЕЛЕНО МЯСТО' in line and i + 1 < len(lines):
            current['city'] = lines[i + 1]
        elif 'Адрес' in line and i + 1 < len(lines):
            current['address'] = lines[i + 1]
        elif 'ОКРЪЖЕН СЪД' in line and i + 1 < len(lines):
            current['court'] = lines[i + 1]
        elif 'ЧАСТЕН СЪДЕБЕН ИЗПЪЛНИТЕЛ' in line and i + 1 < len(lines):
            current['executor'] = lines[i + 1]
        elif 'СРОК' in line and i + 1 < len(lines):
            current['period'] = lines[i + 1]
        elif 'ОБЯВЯВАНЕ НА' in line and i + 1 < len(lines):
            current['announcement_date'] = lines[i + 1]
        elif line.startswith('/properties/'):
            current['id'] = line.replace('/properties/', '')
            current['url'] = f"https://sales.bcpea.org{line}"
    
    if current:
        listings.append(current)
    
    return listings

def scrape_all(max_pages=92, cities=None):
    """Scrape all pages, optionally filter by city"""
    all_listings = []
    
    for page in range(1, max_pages + 1):
        print(f"Scraping page {page}...")
        try:
            listings = scrape_page(page)
            for l in listings:
                if cities:
                    if any(c.lower() in l.get('city', '').lower() for c in cities):
                        all_listings.append(l)
                else:
                    all_listings.append(l)
        except Exception as e:
            print(f"Error on page {page}: {e}")
            break
    
    return all_listings

def save_to_json(listings, filepath):
    """Save listings to JSON file"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump({
            'scraped_at': datetime.utcnow().isoformat(),
            'count': len(listings),
            'listings': listings
        }, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(listings)} listings to {filepath}")

if __name__ == "__main__":
    # Scrape Sofia properties
    sofia_cities = ['София', 'Sofia']
    listings = scrape_all(max_pages=92, cities=sofia_cities)
    save_to_json(listings, '../data/bcpea_sofia.json')
