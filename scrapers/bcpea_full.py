#!/usr/bin/env python3
"""
КЧСИ (BCPEA) Full Production Scraper
Scrapes all listings AND detail pages for complete data
"""

import json
import re
import sqlite3
import time
import urllib.request
import urllib.error
from datetime import datetime
from html.parser import HTMLParser
import os

BASE_URL = "https://sales.bcpea.org"
DB_PATH = "data/properties.db"

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, data):
        self.text.append(data.strip())
    def get_text(self):
        return '\n'.join(t for t in self.text if t)

def fetch_url(url, retries=3):
    """Fetch URL with retries"""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode('utf-8', errors='ignore')
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  ✗ Failed to fetch {url}: {e}")
                return None
    return None

def parse_listing_page(html):
    """Parse a listing page and extract basic info + IDs"""
    listings = []
    
    # Extract property IDs from links
    ids = re.findall(r'/properties/(\d+)', html)
    
    # Extract prices
    prices = re.findall(r'([\d\s]+(?:[.,]\d+)?)\s*EUR', html)
    
    # Extract cities
    cities = re.findall(r'НАСЕЛЕНО МЯСТО[^>]*>([^<]+)', html)
    
    for i, prop_id in enumerate(set(ids)):
        listing = {
            'id': prop_id,
            'url': f"{BASE_URL}/properties/{prop_id}"
        }
        listings.append(listing)
    
    return listings

def parse_detail_page(html, listing_id):
    """Parse detail page for complete property info"""
    if not html:
        return None
    
    parser = HTMLTextExtractor()
    parser.feed(html)
    text = parser.get_text()
    
    data = {
        'id': listing_id,
        'raw_text': text[:5000]  # Store first 5000 chars for debugging
    }
    
    # Extract price
    price_match = re.search(r'Начална цена[^€]*?([\d\s]+(?:[.,]\d+)?)\s*€', text)
    if price_match:
        price_str = price_match.group(1).replace(' ', '').replace(',', '.')
        try:
            data['price_eur'] = float(price_str)
        except:
            pass
    
    # Extract size - look for кв.м. or m²
    size_match = re.search(r'площ[:\s]*([\d\s.,]+)\s*(?:кв\.?\s*м|m²|кв\.м)', text, re.IGNORECASE)
    if size_match:
        size_str = size_match.group(1).replace(' ', '').replace(',', '.')
        try:
            data['size_sqm'] = float(size_str)
        except:
            pass
    
    # Extract address
    addr_match = re.search(r'адрес[^:]*:\s*([^;]+)', text, re.IGNORECASE)
    if addr_match:
        data['address'] = addr_match.group(1).strip()[:200]
    
    # Extract city from address
    city_match = re.search(r'гр\.\s*([^,\s]+)', text)
    if city_match:
        data['city'] = f"гр. {city_match.group(1)}"
    else:
        # Try село
        village_match = re.search(r'с\.\s*([^,\s]+)', text)
        if village_match:
            data['city'] = f"с. {village_match.group(1)}"
    
    # Extract district/neighborhood
    district_match = re.search(r'район\s*["\']?([^"\']+)["\']?', text, re.IGNORECASE)
    if district_match:
        data['district'] = district_match.group(1).strip()[:100]
    
    # Determine property type
    text_lower = text.lower()
    if 'апартамент' in text_lower:
        data['property_type'] = 'apartment'
    elif 'къща' in text_lower or 'вила' in text_lower:
        data['property_type'] = 'house'
    elif 'парцел' in text_lower or 'земя' in text_lower or 'нива' in text_lower or 'земеделска' in text_lower:
        data['property_type'] = 'land'
    elif 'офис' in text_lower or 'магазин' in text_lower or 'търговск' in text_lower:
        data['property_type'] = 'commercial'
    elif 'гараж' in text_lower or 'паркомясто' in text_lower:
        data['property_type'] = 'parking'
    else:
        data['property_type'] = 'other'
    
    # Extract auction dates
    period_match = re.search(r'започне на\s*(\d+\s*\w+\s*\d+)\s*г', text)
    if period_match:
        data['auction_start'] = period_match.group(1)
    
    end_match = re.search(r'приключи[^0-9]*(\d+\s*\w+\s*\d+)\s*г', text)
    if end_match:
        data['auction_end'] = end_match.group(1)
    
    # Extract court
    court_match = re.search(r'(Софийски[^,]+съд|[А-Яа-я]+\s+районен\s+съд)', text)
    if court_match:
        data['court'] = court_match.group(1)
    
    # Extract executor
    executor_match = re.search(r'частен съдебен изпълнител[^А-Я]*([А-Я][а-я]+\s+[А-Я][а-я]+)', text, re.IGNORECASE)
    if executor_match:
        data['executor'] = executor_match.group(1)
    
    # Extract rooms if apartment
    rooms_match = re.search(r'(\d+)\s*(?:-\s*)?(?:стаен|стаи|стая)', text, re.IGNORECASE)
    if rooms_match:
        data['rooms'] = int(rooms_match.group(1))
    
    # Extract floor
    floor_match = re.search(r'етаж[:\s]*(\d+)', text, re.IGNORECASE)
    if floor_match:
        data['floor'] = int(floor_match.group(1))
    
    return data

def init_db():
    """Initialize database with proper schema"""
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
            rooms INTEGER,
            floor INTEGER,
            court TEXT,
            executor TEXT,
            auction_start TEXT,
            auction_end TEXT,
            description TEXT,
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_auctions_city ON auctions(city)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_auctions_type ON auctions(property_type)
    """)
    conn.commit()
    return conn

def scrape_all(max_pages=92, delay=0.5):
    """Scrape all КЧСИ listings with details"""
    conn = init_db()
    
    all_listings = []
    seen_ids = set()
    
    print(f"=== КЧСИ Full Scrape - {datetime.utcnow().isoformat()} ===\n")
    
    # Phase 1: Collect all listing IDs
    print("Phase 1: Collecting listing IDs from all pages...")
    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/properties?page={page}"
        html = fetch_url(url)
        
        if not html:
            print(f"  Page {page}: Failed to fetch")
            continue
        
        # Extract IDs
        ids = set(re.findall(r'/properties/(\d+)', html))
        new_ids = ids - seen_ids
        seen_ids.update(ids)
        
        print(f"  Page {page}: Found {len(new_ids)} new listings (total: {len(seen_ids)})")
        
        if len(new_ids) == 0 and page > 5:
            print("  No new listings found, stopping pagination")
            break
        
        time.sleep(delay)
    
    print(f"\nFound {len(seen_ids)} unique listings\n")
    
    # Phase 2: Fetch detail pages
    print("Phase 2: Fetching detail pages...")
    success = 0
    failed = 0
    
    for i, listing_id in enumerate(seen_ids, 1):
        detail_url = f"{BASE_URL}/properties/{listing_id}"
        html = fetch_url(detail_url)
        
        if html:
            data = parse_detail_page(html, listing_id)
            if data:
                data['url'] = detail_url
                data['scraped_at'] = datetime.utcnow().isoformat()
                all_listings.append(data)
                success += 1
                
                # Save to DB
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO auctions 
                        (id, url, price_eur, city, district, address, property_type, 
                         size_sqm, rooms, floor, court, executor, auction_start, 
                         auction_end, description, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        data.get('executor'),
                        data.get('auction_start'),
                        data.get('auction_end'),
                        data.get('raw_text', '')[:1000],
                        data.get('scraped_at')
                    ))
                except Exception as e:
                    print(f"  DB error for {listing_id}: {e}")
        else:
            failed += 1
        
        if i % 50 == 0:
            conn.commit()
            print(f"  Progress: {i}/{len(seen_ids)} ({success} success, {failed} failed)")
        
        time.sleep(delay)
    
    conn.commit()
    
    # Print summary
    print(f"\n=== SCRAPE COMPLETE ===")
    print(f"Total listings: {len(seen_ids)}")
    print(f"Successful: {success}")
    print(f"Failed: {failed}")
    
    # Stats by type
    cursor = conn.execute("""
        SELECT property_type, COUNT(*), 
               ROUND(AVG(price_eur), 0), 
               ROUND(AVG(size_sqm), 0)
        FROM auctions 
        WHERE property_type IS NOT NULL
        GROUP BY property_type
    """)
    
    print("\nBy property type:")
    for row in cursor:
        print(f"  {row[0]}: {row[1]} listings, avg €{row[2]}, avg {row[3]} m²")
    
    # Stats by city
    cursor = conn.execute("""
        SELECT city, COUNT(*) 
        FROM auctions 
        WHERE city IS NOT NULL
        GROUP BY city
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)
    
    print("\nTop cities:")
    for row in cursor:
        print(f"  {row[0]}: {row[1]} listings")
    
    # Check data quality
    cursor = conn.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN price_eur IS NOT NULL THEN 1 ELSE 0 END) as has_price,
            SUM(CASE WHEN size_sqm IS NOT NULL THEN 1 ELSE 0 END) as has_size,
            SUM(CASE WHEN city IS NOT NULL THEN 1 ELSE 0 END) as has_city,
            SUM(CASE WHEN property_type IS NOT NULL THEN 1 ELSE 0 END) as has_type
        FROM auctions
    """)
    row = cursor.fetchone()
    print(f"\nData quality:")
    print(f"  Has price: {row[1]}/{row[0]} ({100*row[1]/row[0]:.1f}%)")
    print(f"  Has size: {row[2]}/{row[0]} ({100*row[2]/row[0]:.1f}%)")
    print(f"  Has city: {row[3]}/{row[0]} ({100*row[3]/row[0]:.1f}%)")
    print(f"  Has type: {row[4]}/{row[0]} ({100*row[4]/row[0]:.1f}%)")
    
    conn.close()
    
    # Save JSON backup
    with open('data/bcpea_full.json', 'w', encoding='utf-8') as f:
        json.dump({
            'scraped_at': datetime.utcnow().isoformat(),
            'total': len(all_listings),
            'listings': all_listings
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\nSaved to {DB_PATH} and data/bcpea_full.json")

if __name__ == '__main__':
    scrape_all()
