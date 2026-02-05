#!/usr/bin/env python3
"""
КЧСИ Scraper by ID Range
Scans through property IDs since pagination is JavaScript-based
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

def check_id_exists(prop_id):
    """Check if a property ID exists (returns 200)"""
    try:
        url = f"{BASE_URL}/properties/{prop_id}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
        })
        req.get_method = lambda: 'HEAD'
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        return False
    except:
        return None  # Network error, retry later

def fetch_detail(prop_id):
    """Fetch and parse detail page"""
    try:
        url = f"{BASE_URL}/properties/{prop_id}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            return parse_detail(prop_id, html, url)
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
    
    # Price
    price_match = re.search(r'Начална цена[^€]*([\d\s]+(?:[.,]\d+)?)\s*€', text)
    if price_match:
        try:
            data['price_eur'] = float(price_match.group(1).replace(' ', '').replace(',', '.'))
        except:
            pass
    
    # Size - look for площ followed by number and кв.м
    size_match = re.search(r'площ[:\s]*([\d\s.,]+)\s*(?:кв\.?\s*м|кв\.м)', text, re.IGNORECASE)
    if size_match:
        try:
            data['size_sqm'] = float(size_match.group(1).replace(' ', '').replace(',', '.'))
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
    
    # District
    district_match = re.search(r'район\s*["\']?([А-Яа-яЁё\s]+)["\']?[,;]', text, re.IGNORECASE)
    if district_match:
        data['district'] = district_match.group(1).strip()
    
    # Address
    addr_match = re.search(r'адрес[^:]*:\s*([^;]+)', text, re.IGNORECASE)
    if addr_match:
        data['address'] = addr_match.group(1).strip()[:300]
    
    # Property type
    text_lower = text.lower()
    if 'апартамент' in text_lower:
        data['property_type'] = 'apartment'
    elif 'къща' in text_lower or 'вила' in text_lower:
        data['property_type'] = 'house'
    elif any(x in text_lower for x in ['парцел', 'земя', 'нива', 'земеделска', 'поземлен имот']):
        data['property_type'] = 'land'
    elif any(x in text_lower for x in ['офис', 'магазин', 'търговск']):
        data['property_type'] = 'commercial'
    elif 'гараж' in text_lower or 'паркомясто' in text_lower:
        data['property_type'] = 'parking'
    else:
        data['property_type'] = 'other'
    
    # Court
    court_match = re.search(r'ОКРЪЖЕН СЪД\s*([А-Яа-яЁё\s]+)', text)
    if court_match:
        data['court'] = court_match.group(1).strip()
    
    # Auction dates
    start_match = re.search(r'започне на\s*(\d+\s+\w+\s+\d+)', text)
    if start_match:
        data['auction_start'] = start_match.group(1)
    
    end_match = re.search(r'приключи[^0-9]*(\d+\s+\w+\s+\d+)', text)
    if end_match:
        data['auction_end'] = end_match.group(1)
    
    return data

def init_db():
    """Initialize database"""
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auctions (
            id TEXT PRIMARY KEY,
            url TEXT,
            price_eur REAL,
            city TEXT,
            district TEXT,
            address TEXT,
            property_type TEXT,
            size_sqm REAL,
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

def scan_id_range(start_id, end_id, workers=10):
    """Scan a range of IDs in parallel"""
    valid_ids = []
    
    print(f"Scanning IDs {start_id} to {end_id}...")
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(check_id_exists, i): i for i in range(start_id, end_id + 1)}
        
        done = 0
        for future in as_completed(futures):
            prop_id = futures[future]
            done += 1
            
            try:
                exists = future.result()
                if exists:
                    valid_ids.append(prop_id)
            except:
                pass
            
            if done % 100 == 0:
                print(f"  Scanned {done}/{end_id - start_id + 1}, found {len(valid_ids)} valid")
    
    return sorted(valid_ids)

def scrape_all_details(prop_ids, conn, workers=5):
    """Scrape detail pages for all IDs"""
    print(f"\nFetching details for {len(prop_ids)} properties...")
    
    all_data = []
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_detail, pid): pid for pid in prop_ids}
        
        done = 0
        for future in as_completed(futures):
            done += 1
            
            try:
                data = future.result()
                if data:
                    all_data.append(data)
                    
                    # Save to DB
                    conn.execute("""
                        INSERT OR REPLACE INTO auctions 
                        (id, url, price_eur, city, district, address, property_type, 
                         size_sqm, court, auction_start, auction_end, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data.get('id'),
                        data.get('url'),
                        data.get('price_eur'),
                        data.get('city'),
                        data.get('district'),
                        data.get('address'),
                        data.get('property_type'),
                        data.get('size_sqm'),
                        data.get('court'),
                        data.get('auction_start'),
                        data.get('auction_end'),
                        data.get('scraped_at')
                    ))
            except Exception as e:
                print(f"  Error: {e}")
            
            if done % 50 == 0:
                conn.commit()
                print(f"  Progress: {done}/{len(prop_ids)} ({len(all_data)} successful)")
    
    conn.commit()
    return all_data

def print_stats(conn):
    """Print database statistics"""
    cursor = conn.cursor()
    
    total = cursor.execute("SELECT COUNT(*) FROM auctions").fetchone()[0]
    print(f"\n=== STATISTICS ===")
    print(f"Total listings: {total}")
    
    # By type
    print("\nBy property type:")
    for row in cursor.execute("""
        SELECT property_type, COUNT(*), 
               ROUND(AVG(price_eur), 0) as avg_price,
               ROUND(AVG(size_sqm), 0) as avg_size
        FROM auctions GROUP BY property_type ORDER BY COUNT(*) DESC
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
            SUM(CASE WHEN city IS NOT NULL THEN 1 ELSE 0 END) as has_city
        FROM auctions
    """).fetchone()
    print(f"  Has price: {quality[1]}/{quality[0]} ({100*quality[1]/quality[0]:.1f}%)")
    print(f"  Has size: {quality[2]}/{quality[0]} ({100*quality[2]/quality[0]:.1f}%)")
    print(f"  Has city: {quality[3]}/{quality[0]} ({100*quality[3]/quality[0]:.1f}%)")

def main():
    print(f"=== КЧСИ Full Scrape by ID - {datetime.utcnow().isoformat()} ===\n")
    
    # Initialize DB
    conn = init_db()
    
    # Scan ID range (based on known IDs around 85000-85889)
    # Expand range to catch more
    START_ID = 84000
    END_ID = 86000
    
    valid_ids = scan_id_range(START_ID, END_ID, workers=20)
    print(f"\nFound {len(valid_ids)} valid property IDs")
    
    if not valid_ids:
        print("No valid IDs found!")
        return
    
    # Scrape all details
    all_data = scrape_all_details(valid_ids, conn, workers=10)
    
    # Print stats
    print_stats(conn)
    
    # Save JSON backup
    with open('data/bcpea_full.json', 'w', encoding='utf-8') as f:
        json.dump({
            'scraped_at': datetime.utcnow().isoformat(),
            'total': len(all_data),
            'listings': all_data
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Saved to {DB_PATH} and data/bcpea_full.json")
    conn.close()

if __name__ == '__main__':
    main()
