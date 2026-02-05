#!/usr/bin/env python3
"""
КЧСИ Scraper - Fixed Property Type Detection
Uses Bulgarian legal terminology for better apartment detection
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
    
    # Price from div.price
    price_match = re.search(r'Начална цена</div>.*?<div class="price">([\d\s\xa0,\.]+)', decoded, re.DOTALL)
    if price_match:
        try:
            price_str = price_match.group(1).replace(' ', '').replace('\xa0', '').replace(',', '.')
            price = float(price_str)
            if price > 500:
                data['price_eur'] = price
        except:
            pass
    
    if 'price_eur' not in data:
        return None
    
    # City from header
    city_match = re.search(r'Населено място</div>\s*<div class="info">([^<]+)', decoded)
    if city_match:
        data['city'] = city_match.group(1).strip()
    
    # Address from header
    addr_match = re.search(r'Адрес</div>\s*<div class="info">([^<]+)', decoded)
    if addr_match:
        data['address'] = addr_match.group(1).strip()[:300]
    
    # Size from header (ПЛОЩ div)
    size_match = re.search(r'ПЛОЩ</div>\s*<div class="info">([\d\s\.,]+)\s*кв', decoded, re.IGNORECASE)
    if not size_match:
        size_match = re.search(r'class="info">([\d\s\.,]+)\s*кв\.?\s*м', decoded, re.IGNORECASE)
    if size_match:
        try:
            data['size_sqm'] = float(size_match.group(1).replace(' ', '').replace(',', '.'))
        except:
            pass
    
    # Court from header
    court_match = re.search(r'ОКРЪЖЕН СЪД</div>\s*<div class="info">([^<]+)', decoded)
    if court_match:
        data['court'] = court_match.group(1).strip()
    
    # Auction dates
    period_match = re.search(r'от\s*(\d{2}\.\d{2}\.\d{4})\s*до\s*(\d{2}\.\d{2}\.\d{4})', decoded)
    if period_match:
        data['auction_start'] = period_match.group(1)
        data['auction_end'] = period_match.group(2)
    
    # District from address
    if 'address' in data:
        district_match = re.search(r'район\s*["\']?([^"\']+)["\']?', data['address'], re.IGNORECASE)
        if district_match:
            data['district'] = district_match.group(1).strip()[:100]
    
    # Property type detection - use full page text
    text_lower = decoded.lower()
    
    # Apartments/Units (Bulgarian legal terms)
    if any(x in text_lower for x in ['самостоятелен обект', 'жилищен етаж', 'жилище,', 'жилище ']):
        data['property_type'] = 'апартамент'
        # Try to detect rooms
        if 'едностаен' in text_lower:
            data['rooms'] = 1
        elif 'двустаен' in text_lower:
            data['rooms'] = 2
        elif 'тристаен' in text_lower:
            data['rooms'] = 3
        elif 'многостаен' in text_lower or 'четиристаен' in text_lower:
            data['rooms'] = 4
    elif 'апартамент' in text_lower and 'option' not in text_lower[:text_lower.find('апартамент')+100]:
        data['property_type'] = 'апартамент'
    # Houses
    elif any(x in text_lower for x in ['жилищна сграда', 'къща', 'вила']):
        data['property_type'] = 'къща'
    # Garages/Parking
    elif any(x in text_lower for x in ['гараж', 'паркомясто', 'паркинг']):
        data['property_type'] = 'гараж'
    # Commercial
    elif any(x in text_lower for x in ['магазин', 'търговски']):
        data['property_type'] = 'магазин'
    elif any(x in text_lower for x in ['офис', 'кантора']):
        data['property_type'] = 'офис'
    elif any(x in text_lower for x in ['склад', 'складов']):
        data['property_type'] = 'склад'
    elif any(x in text_lower for x in ['хотел', 'ресторант', 'заведение']):
        data['property_type'] = 'търговски'
    # Land
    elif any(x in text_lower for x in ['поземлен имот', 'земеделска', 'нива', 'парцел', 'урегулиран']):
        data['property_type'] = 'земя'
    else:
        data['property_type'] = 'друго'
    
    return data

def init_db():
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DROP TABLE IF EXISTS auctions")
    conn.execute("""
        CREATE TABLE auctions (
            id TEXT PRIMARY KEY, url TEXT, price_eur REAL, city TEXT, district TEXT,
            address TEXT, property_type TEXT, size_sqm REAL, rooms INTEGER, court TEXT,
            auction_start TEXT, auction_end TEXT, scraped_at DATETIME
        )
    """)
    conn.execute("CREATE INDEX idx_city ON auctions(city)")
    conn.execute("CREATE INDEX idx_type ON auctions(property_type)")
    conn.commit()
    return conn

def scrape_range(start_id=85000, end_id=85900, workers=15):
    conn = init_db()
    
    print(f"=== КЧСИ Scraper v4 - {datetime.utcnow().isoformat()} ===")
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
            except:
                pass
            
            if done % 50 == 0:
                conn.commit()
                print(f"  {done}/{end_id-start_id+1} scanned, {success} valid")
                sys.stdout.flush()
    
    conn.commit()
    
    # Stats
    print(f"\n{'='*50}")
    print(f"SCRAPED: {success} listings")
    print(f"{'='*50}")
    
    cursor = conn.cursor()
    
    print("\nBy property type:")
    for row in cursor.execute("""
        SELECT property_type, COUNT(*), ROUND(AVG(price_eur), 0), ROUND(AVG(size_sqm), 0)
        FROM auctions GROUP BY property_type ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]:15} : {row[1]:3} listings, avg €{row[2] or 0:>10}, avg {row[3] or 0}m²")
    
    print("\nTop cities:")
    for row in cursor.execute("""
        SELECT city, COUNT(*), ROUND(AVG(price_eur), 0)
        FROM auctions WHERE city IS NOT NULL GROUP BY city ORDER BY COUNT(*) DESC LIMIT 10
    """):
        print(f"  {row[0]:20} : {row[1]:3} listings, avg €{row[2] or 0}")
    
    # Apartments specifically
    print("\nApartments breakdown:")
    for row in cursor.execute("""
        SELECT city, COUNT(*), ROUND(AVG(price_eur), 0), ROUND(AVG(size_sqm), 0)
        FROM auctions WHERE property_type = 'апартамент'
        GROUP BY city ORDER BY COUNT(*) DESC LIMIT 10
    """):
        print(f"  {row[0]:20} : {row[1]:3} listings, avg €{row[2]}, avg {row[3]}m²")
    
    sofia = cursor.execute("SELECT COUNT(*), ROUND(AVG(price_eur), 0) FROM auctions WHERE city LIKE '%София%'").fetchone()
    print(f"\nSofia total: {sofia[0]} listings, avg €{sofia[1]}")
    
    conn.close()
    
    with open('data/bcpea_v4.json', 'w', encoding='utf-8') as f:
        json.dump({'scraped_at': datetime.utcnow().isoformat(), 'count': len(all_data), 'listings': all_data}, f, ensure_ascii=False)
    
    print(f"\n✓ Saved to {DB_PATH}")

if __name__ == '__main__':
    scrape_range()
