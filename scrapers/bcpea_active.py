#!/usr/bin/env python3
"""
КЧСИ Scraper - Active Listings Only
Scrapes recent IDs (85000+) which have complete price data
"""

import json
import re
import sqlite3
import time
import urllib.request
import urllib.error
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
            html = resp.read().decode('utf-8', errors='ignore')
            return parse_detail(prop_id, html, url)
    except urllib.error.HTTPError:
        return None
    except Exception as e:
        return None

def parse_detail(prop_id, html, url):
    """Parse detail page HTML"""
    # Convert HTML to text
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    
    data = {
        'id': str(prop_id),
        'url': url,
        'scraped_at': datetime.utcnow().isoformat()
    }
    
    # Price - multiple patterns
    # Pattern 1: "Начална цена, от която ще започне наддаването – 33110.73 €"
    price_match = re.search(r'Начална цена[^–€\d]*([\d\s]+[.,]?\d*)\s*€', text, re.IGNORECASE)
    if not price_match:
        # Pattern 2: "33 110.73 EUR" or "33110.73 EUR"
        price_match = re.search(r'([\d\s]+[.,]?\d*)\s*(?:EUR|€)', text)
    if price_match:
        try:
            price_str = price_match.group(1).replace(' ', '').replace(',', '.')
            data['price_eur'] = float(price_str)
        except:
            pass
    
    # Size - look for площ followed by number and кв.м
    size_match = re.search(r'площ[:\s]*([\d\s.,]+)\s*(?:кв\.?\s*м|кв\.м|m²)', text, re.IGNORECASE)
    if size_match:
        try:
            size_str = size_match.group(1).replace(' ', '').replace(',', '.')
            data['size_sqm'] = float(size_str)
        except:
            pass
    
    # Also look for дка (decare = 1000 sqm)
    if 'size_sqm' not in data:
        dka_match = re.search(r'([\d\s.,]+)\s*дка', text, re.IGNORECASE)
        if dka_match:
            try:
                dka_str = dka_match.group(1).replace(' ', '').replace(',', '.')
                data['size_sqm'] = float(dka_str) * 1000  # Convert to sqm
            except:
                pass
    
    # City
    city_match = re.search(r'гр\.\s*([А-Яа-яЁё]+)', text)
    if city_match:
        data['city'] = f"гр. {city_match.group(1)}"
    else:
        village_match = re.search(r'с\.\s*([А-Яа-яЁё]+)', text)
        if village_match:
            data['city'] = f"с. {village_match.group(1)}"
    
    # District/neighborhood
    district_match = re.search(r'район\s*["\']?([А-Яа-яЁё\-\s]+)["\']?[,;]', text, re.IGNORECASE)
    if district_match:
        data['district'] = district_match.group(1).strip()[:100]
    
    # Address
    addr_match = re.search(r'адрес[^:]*:\s*([^;\.]{10,200})', text, re.IGNORECASE)
    if addr_match:
        data['address'] = addr_match.group(1).strip()[:300]
    
    # Property type detection (Bulgarian)
    text_lower = text.lower()
    
    # Apartment types
    if 'едностаен' in text_lower:
        data['property_type'] = 'едностаен'
        data['rooms'] = 1
    elif 'двустаен' in text_lower:
        data['property_type'] = 'двустаен'
        data['rooms'] = 2
    elif 'тристаен' in text_lower:
        data['property_type'] = 'тристаен'
        data['rooms'] = 3
    elif 'четиристаен' in text_lower or 'многостаен' in text_lower:
        data['property_type'] = 'многостаен'
        data['rooms'] = 4
    elif 'апартамент' in text_lower:
        data['property_type'] = 'апартамент'
    elif 'мезонет' in text_lower:
        data['property_type'] = 'мезонет'
    elif 'ателие' in text_lower or 'таван' in text_lower:
        data['property_type'] = 'ателие'
    # Houses
    elif 'къща' in text_lower:
        data['property_type'] = 'къща'
    elif 'вила' in text_lower:
        data['property_type'] = 'вила'
    elif 'етаж от къща' in text_lower:
        data['property_type'] = 'етаж от къща'
    # Land
    elif 'парцел' in text_lower:
        data['property_type'] = 'парцел'
    elif any(x in text_lower for x in ['нива', 'земеделска земя', 'земеделски имот']):
        data['property_type'] = 'земеделска земя'
    elif 'поземлен имот' in text_lower:
        data['property_type'] = 'поземлен имот'
    # Commercial
    elif 'магазин' in text_lower:
        data['property_type'] = 'магазин'
    elif 'офис' in text_lower:
        data['property_type'] = 'офис'
    elif 'заведение' in text_lower:
        data['property_type'] = 'заведение'
    elif 'склад' in text_lower:
        data['property_type'] = 'склад'
    elif 'хотел' in text_lower:
        data['property_type'] = 'хотел'
    elif 'фабрика' in text_lower or 'производствен' in text_lower:
        data['property_type'] = 'производствен'
    # Other
    elif 'гараж' in text_lower:
        data['property_type'] = 'гараж'
    elif 'паркомясто' in text_lower:
        data['property_type'] = 'паркомясто'
    else:
        data['property_type'] = 'друго'
    
    # Extract floor
    floor_match = re.search(r'етаж[:\s]*(\d+)', text, re.IGNORECASE)
    if floor_match:
        data['floor'] = int(floor_match.group(1))
    
    # Auction dates
    start_match = re.search(r'започне на\s*(\d+)\s+(\w+)\s+(\d+)', text)
    if start_match:
        data['auction_start'] = f"{start_match.group(1)} {start_match.group(2)} {start_match.group(3)}"
    
    end_match = re.search(r'приключи[^0-9]*(\d+)\s+(\w+)\s+(\d+)', text)
    if end_match:
        data['auction_end'] = f"{end_match.group(1)} {end_match.group(2)} {end_match.group(3)}"
    
    # Court
    court_match = re.search(r'ОКРЪЖЕН СЪД[:\s]*([А-Яа-яЁё\s]+?)(?:\s*НАСЕЛЕНО|\s*ТИП|\s*$)', text)
    if court_match:
        data['court'] = court_match.group(1).strip()
    
    return data

def init_db():
    """Initialize database with clean schema"""
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    
    # Drop and recreate for clean data
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
            floor INTEGER,
            court TEXT,
            auction_start TEXT,
            auction_end TEXT,
            scraped_at DATETIME
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_city ON auctions(city)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON auctions(property_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_price ON auctions(price_eur)")
    conn.commit()
    return conn

def scrape_active(start_id=85000, end_id=85900, workers=10):
    """Scrape active listings"""
    conn = init_db()
    
    print(f"=== КЧСИ Active Listings Scrape - {datetime.utcnow().isoformat()} ===")
    print(f"Scanning IDs {start_id} to {end_id}...\n")
    
    all_data = []
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_detail, pid): pid for pid in range(start_id, end_id + 1)}
        
        done = 0
        success = 0
        for future in as_completed(futures):
            done += 1
            
            try:
                data = future.result()
                if data and data.get('price_eur'):  # Only keep listings with prices
                    all_data.append(data)
                    success += 1
                    
                    # Save to DB
                    conn.execute("""
                        INSERT OR REPLACE INTO auctions 
                        (id, url, price_eur, city, district, address, property_type, 
                         size_sqm, rooms, floor, court, auction_start, auction_end, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data.get('id'),
                        data.get('url'),
                        data.get('price_eur'),
                        data.get('city'),
                        data.get('district'),
                        data.get('address'),
                        data.get('property_type'),
                        data.get('size_sqm'),
                        data.get('rooms'),
                        data.get('floor'),
                        data.get('court'),
                        data.get('auction_start'),
                        data.get('auction_end'),
                        data.get('scraped_at')
                    ))
            except Exception as e:
                pass
            
            if done % 100 == 0:
                conn.commit()
                print(f"  Progress: {done}/{end_id - start_id + 1}, {success} with prices")
                sys.stdout.flush()
    
    conn.commit()
    
    # Print stats
    print(f"\n=== SCRAPE COMPLETE ===")
    print(f"Total scanned: {done}")
    print(f"With prices: {success}")
    
    # By type
    print("\nBy property type:")
    cursor = conn.cursor()
    for row in cursor.execute("""
        SELECT property_type, COUNT(*), 
               ROUND(AVG(price_eur), 0) as avg_price,
               ROUND(AVG(size_sqm), 0) as avg_size
        FROM auctions 
        GROUP BY property_type ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]}: {row[1]} listings, avg €{row[2]}, avg {row[3]} m²")
    
    # By city
    print("\nTop 10 cities:")
    for row in cursor.execute("""
        SELECT city, COUNT(*) FROM auctions 
        WHERE city IS NOT NULL GROUP BY city ORDER BY COUNT(*) DESC LIMIT 10
    """):
        print(f"  {row[0]}: {row[1]}")
    
    # Data quality
    print("\nData quality:")
    quality = cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN price_eur IS NOT NULL THEN 1 ELSE 0 END) as has_price,
            SUM(CASE WHEN size_sqm IS NOT NULL THEN 1 ELSE 0 END) as has_size,
            SUM(CASE WHEN city IS NOT NULL THEN 1 ELSE 0 END) as has_city,
            SUM(CASE WHEN property_type IS NOT NULL THEN 1 ELSE 0 END) as has_type,
            SUM(CASE WHEN district IS NOT NULL THEN 1 ELSE 0 END) as has_district
        FROM auctions
    """).fetchone()
    total = quality[0] or 1
    print(f"  Has price: {quality[1]}/{total} ({100*quality[1]/total:.1f}%)")
    print(f"  Has size: {quality[2]}/{total} ({100*quality[2]/total:.1f}%)")
    print(f"  Has city: {quality[3]}/{total} ({100*quality[3]/total:.1f}%)")
    print(f"  Has type: {quality[4]}/{total} ({100*quality[4]/total:.1f}%)")
    print(f"  Has district: {quality[5]}/{total} ({100*quality[5]/total:.1f}%)")
    
    # Sofia stats
    print("\nSofia listings:")
    sofia = cursor.execute("""
        SELECT COUNT(*), ROUND(AVG(price_eur), 0), ROUND(AVG(size_sqm), 0)
        FROM auctions WHERE city LIKE '%София%'
    """).fetchone()
    print(f"  Count: {sofia[0]}, avg price: €{sofia[1]}, avg size: {sofia[2]} m²")
    
    conn.close()
    
    # Save JSON
    with open('data/bcpea_active.json', 'w', encoding='utf-8') as f:
        json.dump({
            'scraped_at': datetime.utcnow().isoformat(),
            'total': len(all_data),
            'listings': all_data
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Saved to {DB_PATH} and data/bcpea_active.json")

if __name__ == '__main__':
    scrape_active()
