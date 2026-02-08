#!/usr/bin/env python3
"""
Market Data Scraper v2 - Uses web_fetch tool results
Fetches from: imot.bg, alo.bg, olx.bg, homes.bg
"""

import re
import sqlite3
import json
from datetime import datetime
import os
import subprocess
import sys

DB_PATH = "data/market_listings.db"

OLX_URLS = {
    'София': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-sofia/',
    'Варна': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-varna/',
    'Бургас': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-burgas/',
    'Пловдив': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-plovdiv/',
}

ALO_URLS = {
    'София': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=1',
    'Пловдив': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=2',
    'Варна': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=3',
    'Бургас': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=4',
}

HOMES_URLS = {
    'София': 'https://www.homes.bg/obiavi/apartamenti/prodazhba/sofia/',
    'Пловдив': 'https://www.homes.bg/obiavi/apartamenti/prodazhba/plovdiv/',
    'Варна': 'https://www.homes.bg/obiavi/apartamenti/prodazhba/varna/',
    'Бургас': 'https://www.homes.bg/obiavi/apartamenti/prodazhba/burgas/',
}

IMOT_URL = 'https://www.imot.bg/obiavi/prodazhbi'


def parse_olx(text, city):
    """Parse OLX text output"""
    listings = []
    # Pattern: гр. София, District - ... 46 кв.м - 3621.74
    pattern = rf'гр\.\s*{re.escape(city)},\s*([^-\n]+).*?(\d+)\s*кв\.м\s*-\s*([\d\.]+)'
    matches = re.findall(pattern, text, re.DOTALL)
    
    seen = set()
    for district, size_str, price_sqm_str in matches:
        key = (size_str, price_sqm_str)
        if key in seen:
            continue
        seen.add(key)
        try:
            size = float(size_str)
            price_per_sqm = float(price_sqm_str)
            total = size * price_per_sqm
            if size >= 30 and price_per_sqm >= 300:
                listings.append({
                    'city': city, 'district': district.strip(), 'size_sqm': size,
                    'price_per_sqm': round(price_per_sqm, 2), 'price_eur': round(total, 2),
                    'source': 'olx.bg'
                })
        except:
            continue
    return listings


def parse_alo(text):
    """Parse alo.bg text output"""
    listings = []
    # Extract city from each entry
    entries = re.split(r'Цена:', text)[1:]  # Skip first empty
    
    for entry in entries:
        # Find price
        price_match = re.search(r'([\d\s]+)\s*€', entry)
        if not price_match:
            continue
        try:
            price = float(price_match.group(1).replace(' ', ''))
        except:
            continue
        
        # Find price per sqm
        sqm_price_match = re.search(r'за кв\.м:\s*([\d\.]+)\s*€/кв\.м', entry)
        if sqm_price_match:
            try:
                price_per_sqm = float(sqm_price_match.group(1))
            except:
                price_per_sqm = None
        else:
            price_per_sqm = None
        
        # Find size
        size_match = re.search(r'Квадратура:(\d+)\s*кв\.м', entry)
        if not size_match:
            continue
        try:
            size = float(size_match.group(1))
        except:
            continue
        
        # Find city - usually "в City" in the property type
        city_match = re.search(r'в\s+(София|Пловдив|Варна|Бургас)', entry)
        city = city_match.group(1) if city_match else None
        
        if size > 30 and price > 5000:
            if not price_per_sqm:
                price_per_sqm = round(price / size, 2)
            listings.append({
                'city': city, 'district': None, 'size_sqm': size,
                'price_eur': price, 'price_per_sqm': price_per_sqm,
                'source': 'alo.bg'
            })
    
    return listings


def parse_homes(text, city):
    """Parse homes.bg text output"""
    listings = []
    # Look for: room_type, size, price, price_per_sqm
    lines = text.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        # Find room type and size: "Тристаен, 102m²"
        match = re.search(r'(\w+стаен),\s*(\d+)m²', line)
        if match:
            room_type = match.group(1)
            size = float(match.group(2))
            
            # Look for price in this or next lines
            price_text = line + ' ' + lines[i+1] if i+1 < len(lines) else line
            price_match = re.search(r'([\d,]+)\s*EUR\s*([\d,]+)EUR/m²', price_text)
            
            if price_match:
                try:
                    price = float(price_match.group(1).replace(',', ''))
                    price_per_sqm = float(price_match.group(2).replace(',', ''))
                    
                    if size > 30 and price > 5000:
                        listings.append({
                            'city': city, 'district': None, 'size_sqm': size,
                            'price_eur': price, 'price_per_sqm': round(price_per_sqm, 2),
                            'source': 'homes.bg'
                        })
                except:
                    pass
        i += 1
    
    return listings


def parse_imot(text):
    """Parse imot.bg text output"""
    listings = []
    # Price: 134 352 euro
    # Size: 75 кв.м
    
    # Find price-size pairs
    price_matches = list(re.finditer(r'Цена:\s*([\d\s]+)\s*euro', text, re.IGNORECASE))
    
    for pmatch in price_matches:
        try:
            price = float(pmatch.group(1).replace(' ', ''))
        except:
            continue
        
        # Look for size near this price
        nearby_text = text[pmatch.end():pmatch.end()+200]
        size_match = re.search(r'(\d+)\s*кв\.м', nearby_text)
        
        if size_match:
            try:
                size = float(size_match.group(1))
                if price > 5000 and size > 30:
                    listings.append({
                        'city': None, 'district': None, 'size_sqm': size,
                        'price_eur': price, 'price_per_sqm': round(price / size, 2),
                        'source': 'imot.bg'
                    })
            except:
                continue
    
    return listings


def init_db():
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS market_listings")
    c.execute("""
        CREATE TABLE market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, city TEXT, district TEXT,
            property_type TEXT DEFAULT 'апартамент', size_sqm REAL, price_eur REAL, 
            price_per_sqm REAL, rooms INTEGER, source TEXT, 
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("CREATE INDEX idx_city ON market_listings(city)")
    c.execute("CREATE INDEX idx_source ON market_listings(source)")
    conn.commit()
    return conn


def save_listings(conn, listings):
    c = conn.cursor()
    for l in listings:
        c.execute("""
            INSERT INTO market_listings (city, district, size_sqm, price_eur, price_per_sqm, source)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (l.get('city'), l.get('district'), l.get('size_sqm'),
              l.get('price_eur'), l.get('price_per_sqm'), l.get('source')))
    conn.commit()


def print_stats(conn):
    c = conn.cursor()
    print(f"\n{'='*60}")
    print("MARKET DATA STATISTICS")
    print(f"{'='*60}")
    c.execute("SELECT COUNT(*) FROM market_listings")
    total = c.fetchone()[0]
    print(f"\nTotal listings: {total}")
    
    print("\nBy source:")
    c.execute("SELECT source, COUNT(*), ROUND(AVG(price_per_sqm), 0) FROM market_listings GROUP BY source ORDER BY COUNT(*) DESC")
    for row in c.fetchall():
        print(f"  {row[0]:15}: {row[1]:4} listings, avg €{row[2]}/m²")
    
    print("\nBy city:")
    c.execute("SELECT city, COUNT(*), ROUND(AVG(price_per_sqm), 0) FROM market_listings WHERE city IS NOT NULL GROUP BY city ORDER BY COUNT(*) DESC")
    for row in c.fetchall():
        print(f"  {row[0]:15}: {row[1]:4} listings, avg €{row[2]}/m²")
    
    print(f"\n{'='*60}")


def main():
    print(f"=== Market Scraper v2 - {datetime.utcnow().isoformat()} ===\n")
    
    # This script is designed to be called with pre-fetched data
    # For now, just show usage
    print("Usage: Fetch data from websites first, then parse")
    print("Sources:")
    print(f"  - OLX: {len(OLX_URLS)} cities")
    print(f"  - alo.bg: {len(ALO_URLS)} cities")
    print(f"  - homes.bg: {len(HOMES_URLS)} cities")
    print(f"  - imot.bg: 1 page")


if __name__ == '__main__':
    main()
