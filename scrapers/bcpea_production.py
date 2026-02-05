#!/usr/bin/env python3
"""
КЧСИ Scraper - Production v3
Fixed city and price extraction
"""

import json
import re
import html
import sqlite3
import urllib.request
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys

BASE_URL = "https://sales.bcpea.org"
DB_PATH = "data/auctions.db"

def fetch_detail(prop_id):
    try:
        url = f"{BASE_URL}/properties/{prop_id}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status != 200:
                return None
            return parse_detail(prop_id, resp.read().decode('utf-8', errors='ignore'), url)
    except Exception:
        return None

def parse_detail(prop_id, html_text, url):
    decoded = html.unescape(html_text)
    
    data = {
        'id': str(prop_id),
        'url': url,
        'scraped_at': datetime.utcnow().isoformat()
    }
    
    # Price
    price_match = re.search(r'Начална цена</div>.*?<div class="price">([\d\s\xa0,\.]+)', decoded, re.DOTALL)
    if price_match:
        try:
            price_str = price_match.group(1).replace(' ', '').replace('\xa0', '').replace(',', '.')
            price = float(price_str)
            if price > 1000:
                data['price_eur'] = price
        except:
            pass
    
    if 'price_eur' not in data:
        return None
    
    # City
    city_match = re.search(r'Населено място</div>\s*<div class="info">([^<]+)', decoded)
    if city_match:
        data['city'] = city_match.group(1).strip()
    
    # District from address
    district_match = re.search(r'район\s*["\']?([^"\']+)["\']?', decoded, re.IGNORECASE)
    if district_match:
        data['district'] = district_match.group(1).strip()[:100]
    
    # Address
    addr_match = re.search(r'Адрес</div>\s*<div class="info">([^<]+)', decoded)
    if addr_match:
        data['address'] = addr_match.group(1).strip()[:300]
    
    # Size from description
    desc_match = re.search(r'ОПИСАНИЕ.*?<p[^>]*>(.*?)</p>', decoded, re.DOTALL | re.IGNORECASE)
    if desc_match:
        desc = desc_match.group(1)
        text = re.sub(r'<[^>]+>', ' ', desc)
        
        # Size
        size_match = re.search(r'площ[:\s]*([\d\s.,]+)\s*(?:кв\.?\s*м|кв\.м)', text, re.IGNORECASE)
        if size_match:
            try:
                data['size_sqm'] = float(size_match.group(1).replace(' ', '').replace(',', '.'))
            except:
                pass
        
        # Decare
        if 'size_sqm' not in data:
            dka_match = re.search(r'([\d\s.,]+)\s*дка', text, re.IGNORECASE)
            if dka_match:
                try:
                    data['size_sqm'] = float(dka_match.group(1).replace(' ', '').replace(',', '.')) * 1000
                except:
                    pass
        
        # Property type from description
        text_lower = text.lower()
        if any(x in text_lower for x in ['поземлен имот', 'земеделска', 'нива', 'парцел']):
            data['property_type'] = 'земя'
        elif 'апартамент' in text_lower:
            data['property_type'] = 'апартамент'
        elif 'къща' in text_lower or 'вила' in text_lower:
            data['property_type'] = 'къща'
        elif 'гараж' in text_lower:
            data['property_type'] = 'гараж'
        elif 'офис' in text_lower:
            data['property_type'] = 'офис'
        elif 'магазин' in text_lower:
            data['property_type'] = 'магазин'
        else:
            data['property_type'] = 'друго'
    
    # Court
    court_match = re.search(r'ОКРЪЖЕН СЪД[^>]*>([^<]+)', html_text)
    if court_match:
        data['court'] = court_match.group(1).strip()
    
    # Auction dates
    period_match = re.search(r'от\s*(\d{2}\.\d{2}\.\d{4})\s*до\s*(\d{2}\.\d{2}\.\d{4})', decoded)
    if period_match:
        data['auction_start'] = period_match.group(1)
        data['auction_end'] = period_match.group(2)
    
    return data

def init_db():
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DROP TABLE IF EXISTS auctions")
    conn.execute("""
        CREATE TABLE auctions (
            id TEXT PRIMARY KEY, url TEXT, price_eur REAL, city TEXT, district TEXT,
            address TEXT, property_type TEXT, size_sqm REAL, court TEXT,
            auction_start TEXT, auction_end TEXT, scraped_at DATETIME
        )
    """)
    conn.execute("CREATE INDEX idx_city ON auctions(city)")
    conn.execute("CREATE INDEX idx_type ON auctions(property_type)")
    conn.commit()
    return conn

def scrape_range(start_id=85000, end_id=85900, workers=15):
    conn = init_db()
    
    print(f"=== КЧСИ Production Scraper - {datetime.utcnow().isoformat()} ===")
    print(f"Range: {start_id} to {end_id}\n")
    
    all_data = []
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_detail, pid): pid for pid in range(start_id, end_id + 1)}
        
        done = 0
        success = 0
        for future in as_completed(futures):
            done += 1
            
            try:
                data = future.result()
                if data and data.get('price_eur'):
                    all_data.append(data)
                    success += 1
                    
                    conn.execute("""
                        INSERT OR REPLACE INTO auctions 
                        (id, url, price_eur, city, district, address, property_type, 
                         size_sqm, court, auction_start, auction_end, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data.get('id'), data.get('url'), data.get('price_eur'),
                        data.get('city'), data.get('district'), data.get('address'),
                        data.get('property_type'), data.get('size_sqm'), data.get('court'),
                        data.get('auction_start'), data.get('auction_end'), data.get('scraped_at')
                    ))
            except:
                pass
            
            if done % 50 == 0:
                conn.commit()
                print(f"  {done}/{end_id-start_id+1} scanned, {success} valid")
                sys.stdout.flush()
    
    conn.commit()
    
    # Stats
    print(f"\n{'='*50}")
    print(f"SCRAPED: {success} listings with prices")
    print(f"{'='*50}")
    
    cursor = conn.cursor()
    
    print("\nBy property type:")
    for row in cursor.execute("""
        SELECT property_type, COUNT(*), ROUND(AVG(price_eur), 0), ROUND(AVG(size_sqm), 0)
        FROM auctions GROUP BY property_type ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]:12} : {row[1]:3} listings, avg €{row[2] or 0:>10}, avg {row[3] or 0}m²")
    
    print("\nTop cities:")
    for row in cursor.execute("""
        SELECT city, COUNT(*), ROUND(AVG(price_eur), 0)
        FROM auctions WHERE city IS NOT NULL GROUP BY city ORDER BY COUNT(*) DESC LIMIT 10
    """):
        print(f"  {row[0]:20} : {row[1]:3} listings, avg €{row[2] or 0}")
    
    sofia = cursor.execute("SELECT COUNT(*), ROUND(AVG(price_eur), 0), ROUND(AVG(size_sqm), 0) FROM auctions WHERE city LIKE '%София%'").fetchone()
    print(f"\nSofia: {sofia[0]} listings, avg €{sofia[1]}, avg {sofia[2]}m²")
    
    conn.close()
    
    with open('data/bcpea_production.json', 'w', encoding='utf-8') as f:
        json.dump({'scraped_at': datetime.utcnow().isoformat(), 'count': len(all_data), 'listings': all_data}, f, ensure_ascii=False)
    
    print(f"\n✓ Saved to {DB_PATH}")

if __name__ == '__main__':
    scrape_range()
