#!/usr/bin/env python3
"""
КЧСИ Scraper - Fixed Price Parser v2
Correctly extracts prices from div.price after Начална цена label
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
    """Fetch and parse detail page"""
    try:
        url = f"{BASE_URL}/properties/{prop_id}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status != 200:
                return None
            html_text = resp.read().decode('utf-8', errors='ignore')
            return parse_detail(prop_id, html_text, url)
    except Exception:
        return None

def parse_detail(prop_id, html_text, url):
    """Parse detail page"""
    decoded = html.unescape(html_text)
    
    data = {
        'id': str(prop_id),
        'url': url,
        'scraped_at': datetime.utcnow().isoformat()
    }
    
    # Price: Look for price in div after "Начална цена" label
    price_match = re.search(r'Начална цена</div>.*?<div class="price">([\d\s\xa0,\.]+)', decoded, re.DOTALL)
    if not price_match:
        # Alternative: look for pattern in text
        price_match = re.search(r'Начална цена[^€\d]*([\d\s\xa0,\.]+)\s*€', decoded, re.IGNORECASE | re.DOTALL)
    
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
    
    # Extract main description
    desc_match = re.search(r'ОПИСАНИЕ.*?<p[^>]*>(.*?)</p>', decoded, re.DOTALL | re.IGNORECASE)
    if desc_match:
        desc = desc_match.group(1)
        text = re.sub(r'<[^>]+>', ' ', desc)
        text = re.sub(r'\s+', ' ', text)
    else:
        text = decoded
    
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
    
    # City
    city_match = re.search(r'Населено място[^<]*<[^>]*>([^<]+)', html_text)
    if city_match:
        data['city'] = city_match.group(1).strip()
    
    # District
    district_match = re.search(r'район\s*["\']?([^"\']+)["\']?', text, re.IGNORECASE)
    if district_match:
        data['district'] = district_match.group(1).strip()[:100]
    
    # Address
    addr_match = re.search(r'адрес[^:]*:\s*([^;\.]{10,200})', text, re.IGNORECASE)
    if addr_match:
        data['address'] = addr_match.group(1).strip()[:300]
    
    # Property type from HTML dropdown values
    html_lower = html_text.lower()
    if 'едностаен' in html_lower:
        data['property_type'] = 'едностаен'
        data['rooms'] = 1
    elif 'двустаен' in html_lower:
        data['property_type'] = 'двустаен'
        data['rooms'] = 2
    elif 'тристаен' in html_lower:
        data['property_type'] = 'тристаен'
        data['rooms'] = 3
    elif 'многостаен' in html_lower or 'четиристаен' in html_lower:
        data['property_type'] = 'многостаен'
        data['rooms'] = 4
    elif 'мезонет' in html_lower:
        data['property_type'] = 'мезонет'
    elif 'ателие' in html_lower or 'таван' in html_lower:
        data['property_type'] = 'ателие'
    elif 'къща' in html_lower:
        data['property_type'] = 'къща'
    elif 'апартамент' in html_lower:
        data['property_type'] = 'апартамент'
    elif any(x in text.lower() for x in ['парцел', 'поземлен', 'нива', 'земеделска']):
        data['property_type'] = 'земя'
    elif 'гараж' in html_lower:
        data['property_type'] = 'гараж'
    elif 'офис' in html_lower:
        data['property_type'] = 'офис'
    elif 'магазин' in html_lower:
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
    """Initialize database"""
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DROP TABLE IF EXISTS auctions")
    conn.execute("""
        CREATE TABLE auctions (
            id TEXT PRIMARY KEY,
            url TEXT,
            price_eur REAL,
            city TEXT,
            district TEXT,
            address TEXT,
            property_type TEXT,
            size_sqm REAL,
            rooms INTEGER,
            court TEXT,
            auction_start TEXT,
            auction_end TEXT,
            scraped_at DATETIME
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_city ON auctions(city)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON auctions(property_type)")
    conn.commit()
    return conn

def scrape_range(start_id=85850, end_id=85900, workers=15):
    """Scrape auction listings"""
    conn = init_db()
    
    print(f"=== КЧСИ Scraper v2 - {datetime.utcnow().isoformat()} ===")
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
                         size_sqm, rooms, court, auction_start, auction_end, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data.get('id'), data.get('url'), data.get('price_eur'),
                        data.get('city'), data.get('district'), data.get('address'),
                        data.get('property_type'), data.get('size_sqm'), data.get('rooms'),
                        data.get('court'), data.get('auction_start'), data.get('auction_end'),
                        data.get('scraped_at')
                    ))
            except Exception as e:
                pass
            
            if done % 10 == 0:
                conn.commit()
                print(f"  {done}/{end_id-start_id+1} scanned, {success} valid")
                sys.stdout.flush()
    
    conn.commit()
    
    # Stats
    print(f"\n{'='*50}")
    print(f"SCRAPED: {success} listings with prices")
    print(f"{'='*50}")
    
    cursor = conn.cursor()
    
    # By type
    print("\nBy property type:")
    for row in cursor.execute("""
        SELECT property_type, COUNT(*), ROUND(AVG(price_eur), 0), ROUND(AVG(size_sqm), 0)
        FROM auctions GROUP BY property_type ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]:12} : {row[1]:3} listings, avg €{row[2] or 0:>10}, avg {row[3] or 0}m²")
    
    # By city
    print("\nTop cities:")
    for row in cursor.execute("""
        SELECT city, COUNT(*), ROUND(AVG(price_eur), 0)
        FROM auctions WHERE city IS NOT NULL GROUP BY city ORDER BY COUNT(*) DESC LIMIT 10
    """):
        print(f"  {row[0]:20} : {row[1]:3} listings, avg €{row[2] or 0}")
    
    # Sofia
    sofia = cursor.execute("""
        SELECT COUNT(*), ROUND(AVG(price_eur), 0), ROUND(AVG(size_sqm), 0)
        FROM auctions WHERE city LIKE '%София%'
    """).fetchone()
    print(f"\nSofia: {sofia[0]} listings, avg €{sofia[1]}, avg {sofia[2]}m²")
    
    conn.close()
    
    # Save JSON
    with open('data/bcpea_v2.json', 'w', encoding='utf-8') as f:
        json.dump({'scraped_at': datetime.utcnow().isoformat(), 'count': len(all_data), 'listings': all_data}, f, ensure_ascii=False)
    
    print(f"\n✓ Saved to {DB_PATH}")

if __name__ == '__main__':
    scrape_range()
