#!/usr/bin/env python3
"""
КЧСИ Scraper - Fixed Price Parser
"""

import json
import re
import sqlite3
import time
import urllib.request
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys

BASE_URL = "https://sales.bcpea.org"
DB_PATH = "data/auctions.db"

def fetch_detail(prop_id):
    """Fetch detail page"""
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
    except Exception as e:
        return None

def parse_detail(prop_id, html, url):
    """Parse detail page HTML with fixed price extraction"""
    data = {
        'id': str(prop_id),
        'url': url,
        'scraped_at': datetime.utcnow().isoformat()
    }
    
    # Extract main content - look for "ОПИСАНИЕ" section
    desc_match = re.search(r'ОПИСАНИЕ.*?<p>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if not desc_match:
        return None
    
    desc_html = desc_match.group(1)
    
    # Clean HTML for text extraction
    text = re.sub(r'<[^>]+>', ' ', desc_html)
    text = re.sub(r'\s+', ' ', text)
    
    # Price: Look for specific pattern in announcement
    # Pattern: "Начална цена... – [number] €"
    price_match = re.search(r'Начална[^–€]*?([\d\s,\.]+)\s*(?:€|&euro;|EUR)', html, re.IGNORECASE)
    if price_match:
        try:
            price_str = price_match.group(1).replace(' ', '').replace(',', '.')
            price = float(price_str)
            if price > 1000:  # Sanity check - filter prices > 1000 EUR
                data['price_eur'] = price
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
                data['size_sqm'] = float(dka_str) * 1000
            except:
                pass
    
    # City from HTML headers
    city_match = re.search(r'Населено място[^<]*<[^>]*>([^<]+)', html)
    if city_match:
        city = city_match.group(1).strip()
        if city:
            data['city'] = city
    
    # District from description
    district_match = re.search(r'район\s*["\']?([А-Яа-яЁё\-\s]+)["\']?[,;]', text, re.IGNORECASE)
    if district_match:
        data['district'] = district_match.group(1).strip()[:100]
    
    # Address
    addr_match = re.search(r'адрес[^:]*:\s*([^;\.]{10,200})', text, re.IGNORECASE)
    if addr_match:
        data['address'] = addr_match.group(1).strip()[:300]
    
    # Property type detection
    text_lower = text.lower()
    html_lower = html.lower()
    
    # Map from dropdown values in HTML
    if 'едностаен' in html_lower:
        data['property_type'] = 'едностаен'
        data['rooms'] = 1
    elif 'двустаен' in html_lower:
        data['property_type'] = 'двустаен'
        data['rooms'] = 2
    elif 'тристаен' in html_lower:
        data['property_type'] = 'тристаен'
        data['rooms'] = 3
    elif 'четиристаен' in html_lower or 'многостаен' in html_lower:
        data['property_type'] = 'многостаен'
        data['rooms'] = 4
    elif 'апартамент' in text_lower or 'апартамент' in html_lower:
        data['property_type'] = 'апартамент'
    elif 'мезонет' in html_lower:
        data['property_type'] = 'мезонет'
    elif 'ателие' in html_lower or 'таван' in html_lower:
        data['property_type'] = 'ателие'
    elif 'къща' in text_lower or 'вила' in text_lower:
        data['property_type'] = 'къща'
    elif 'етаж от къща' in html_lower:
        data['property_type'] = 'етаж от къща'
    elif 'парцел' in html_lower:
        data['property_type'] = 'парцел'
    elif any(x in text_lower for x in ['нива', 'земеделска земя', 'земеделски имот', 'поземлен имот']):
        data['property_type'] = 'земеделска земя'
    elif 'магазин' in html_lower:
        data['property_type'] = 'магазин'
    elif 'офис' in html_lower:
        data['property_type'] = 'офис'
    elif 'гараж' in html_lower:
        data['property_type'] = 'гараж'
    elif 'паркомясто' in html_lower:
        data['property_type'] = 'паркомясто'
    else:
        data['property_type'] = 'друго'
    
    # Auction dates from headers
    period_match = re.search(r'СРОК[^\d]*(\d{2}\.\d{2}\.\d{4})[^\d]*(\d{2}\.\d{2}\.\d{4})', html)
    if period_match:
        data['auction_start'] = period_match.group(1)
        data['auction_end'] = period_match.group(2)
    
    # Court from headers
    court_match = re.search(r'ОКРЪЖЕН СЪД[^>]*>([^<]+)', html)
    if court_match:
        data['court'] = court_match.group(1).strip()
    
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
            floor INTEGER,
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

def scrape_range(start_id=85000, end_id=85900, workers=10):
    """Scrape a range of IDs"""
    conn = init_db()
    
    print(f"=== КЧСИ Scrape - Fixed Parser - {datetime.utcnow().isoformat()} ===")
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
                if data and data.get('price_eur') and data.get('price_eur') > 1000:
                    all_data.append(data)
                    success += 1
                    
                    conn.execute("""
                        INSERT OR REPLACE INTO auctions 
                        (id, url, price_eur, city, district, address, property_type, 
                         size_sqm, rooms, court, auction_start, auction_end, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    
    # Stats
    print(f"\n=== SCRAPE COMPLETE ===")
    print(f"Total scanned: {done}")
    print(f"With prices: {success}")
    
    cursor = conn.cursor()
    
    # By type
    print("\nBy property type:")
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
        SELECT city, COUNT(*), ROUND(AVG(price_eur), 0) 
        FROM auctions 
        WHERE city IS NOT NULL 
        GROUP BY city ORDER BY COUNT(*) DESC LIMIT 10
    """):
        print(f"  {row[0]}: {row[1]} listings, avg €{row[2]}")
    
    # Data quality
    print("\nData quality:")
    quality = cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN price_eur IS NOT NULL THEN 1 ELSE 0 END) as has_price,
            SUM(CASE WHEN size_sqm IS NOT NULL THEN 1 ELSE 0 END) as has_size
        FROM auctions
    """).fetchone()
    total = quality[0] or 1
    print(f"  Has price: {quality[1]}/{total} ({100*quality[1]/total:.1f}%)")
    print(f"  Has size: {quality[2]}/{total} ({100*quality[2]/total:.1f}%)")
    
    # Sofia stats
    sofia = cursor.execute("""
        SELECT COUNT(*), ROUND(AVG(price_eur), 0), ROUND(AVG(size_sqm), 0)
        FROM auctions WHERE city LIKE '%София%'
    """).fetchone()
    print(f"\nSofia: {sofia[0]} listings, avg €{sofia[1]}, avg {sofia[2]} m²")
    
    conn.close()
    
    # Save JSON
    with open('data/bcpea_active.json', 'w', encoding='utf-8') as f:
        json.dump({
            'scraped_at': datetime.utcnow().isoformat(),
            'total': len(all_data),
            'listings': all_data
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Saved to {DB_PATH}")

if __name__ == '__main__':
    scrape_range()
