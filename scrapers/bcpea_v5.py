#!/usr/bin/env python3
"""
КЧСИ Scraper v5 - With proper timeouts and neighborhood extraction
- Adds socket timeouts to prevent hanging
- Extracts neighborhoods from addresses (ж.к., кв. patterns)
- Better error handling
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
import socket

BASE_URL = "https://sales.bcpea.org"
DB_PATH = "data/auctions.db"

REQUEST_TIMEOUT = 25
SOCKET_TIMEOUT = 30
MAX_RETRIES = 2


def extract_neighborhood_from_address(address):
    if not address:
        return None
    addr_lower = address.lower()
    
    jk_patterns = [
        r'ж\.\s*к\.\s*["\']?([а-яА-Я\s\d-]+?)(?:[,;\s]|$)',
        r'жк\s+["\']?([а-яА-Я\s\d-]+?)(?:[,;\s]|$)',
    ]
    
    for pattern in jk_patterns:
        match = re.search(pattern, addr_lower)
        if match:
            hood = match.group(1).strip()
            hood = re.sub(r'\s*бл\.?\s*\d+.*$', '', hood).strip()
            hood = re.sub(r'\s+\d+\s*$', '', hood).strip()
            return hood.capitalize() if hood else None
    
    kv_patterns = [
        r'кв\.\s*["\']?([а-яА-Я\s\d-]+?)(?:[,;\s]|$)',
        r'кв\s+["\']?([а-яА-Я\s\d-]+?)(?:[,;\s]|$)',
    ]
    
    for pattern in kv_patterns:
        match = re.search(pattern, addr_lower)
        if match:
            hood = match.group(1).strip()
            return hood.capitalize() if hood else None
    
    rayon_match = re.search(r'район\s+["\']?([а-яА-Я\s-]+?)(?:[,;\s]|$)', addr_lower)
    if rayon_match:
        return rayon_match.group(1).strip().capitalize()
    
    return None


def extract_rooms(text_lower):
    word_patterns = [
        (r'\bедностаен', 1), (r'\bдвустаен', 2), (r'\bтристаен', 3),
        (r'\bчетиристаен', 4), (r'\bпетстаен', 5), (r'\bшестстаен', 6),
        (r'\bмногостаен', 4), (r'\bгарсониера', 1), (r'\bмезонет', 3),
    ]
    
    for pattern, rooms in word_patterns:
        if re.search(pattern, text_lower):
            return rooms
    
    numeric_match = re.search(r'\b(\d)\s*[-]?\s*ст(?:аен|айн|\.?)', text_lower)
    if numeric_match:
        return int(numeric_match.group(1))
    
    return None


def fetch_detail_with_timeout(prop_id, retries=0):
    try:
        url = f"{BASE_URL}/properties/{prop_id}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(SOCKET_TIMEOUT)
        
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                return parse_detail(prop_id, resp.read().decode('utf-8', errors='ignore'), url)
        finally:
            socket.setdefaulttimeout(old_timeout)
            
    except (socket.timeout, urllib.error.URLError, urllib.error.HTTPError) as e:
        if retries < MAX_RETRIES:
            return fetch_detail_with_timeout(prop_id, retries + 1)
        return None
    except Exception as e:
        return None


def parse_detail(prop_id, html_text, url):
    decoded = html.unescape(html_text)
    
    data = {
        'id': str(prop_id),
        'url': url,
        'scraped_at': datetime.utcnow().isoformat()
    }
    
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
    
    city_match = re.search(r'Населено място</div>\s*<div class="info">([^<]+)', decoded)
    if city_match:
        data['city'] = city_match.group(1).strip()
    
    addr_match = re.search(r'Адрес</div>\s*<div class="info">([^<]+)', decoded)
    if addr_match:
        data['address'] = addr_match.group(1).strip()[:300]
    
    size_match = re.search(r'ПЛОЩ</div>\s*<div class="info">([\d\s\.,]+)\s*кв', decoded, re.IGNORECASE)
    if not size_match:
        size_match = re.search(r'class="info">([\d\s\.,]+)\s*кв\.?\s*м', decoded, re.IGNORECASE)
    if size_match:
        try:
            data['size_sqm'] = float(size_match.group(1).replace(' ', '').replace(',', '.'))
        except:
            pass
    
    court_match = re.search(r'ОКРЪЖЕН СЪД</div>\s*<div class="info">([^<]+)', decoded)
    if court_match:
        data['court'] = court_match.group(1).strip()
    
    period_match = re.search(r'от\s*(\d{2}\.\d{2}\.\d{4})\s*до\s*(\d{2}\.\d{2}\.\d{4})', decoded)
    if period_match:
        data['auction_start'] = period_match.group(1)
        data['auction_end'] = period_match.group(2)
    
    if 'address' in data:
        data['neighborhood'] = extract_neighborhood_from_address(data['address'])
    
    text_lower = decoded.lower()
    rooms = extract_rooms(text_lower)
    if rooms:
        data['rooms'] = rooms
    
    if any(x in text_lower for x in ['самостоятелен обект', 'жилищен етаж', 'жилище,', 'жилище ']):
        data['property_type'] = 'апартамент'
    elif 'апартамент' in text_lower:
        data['property_type'] = 'апартамент'
    elif any(x in text_lower for x in ['жилищна сграда', 'къща', 'вила']):
        data['property_type'] = 'къща'
    elif any(x in text_lower for x in ['гараж', 'паркомясто', 'паркинг']):
        data['property_type'] = 'гараж'
    elif any(x in text_lower for x in ['магазин', 'търговски']):
        data['property_type'] = 'магазин'
    elif any(x in text_lower for x in ['офис', 'кантора']):
        data['property_type'] = 'офис'
    elif any(x in text_lower for x in ['склад', 'складов']):
        data['property_type'] = 'склад'
    elif any(x in text_lower for x in ['хотел', 'ресторант', 'заведение']):
        data['property_type'] = 'търговски'
    elif any(x in text_lower for x in ['поземлен имот', 'земеделска', 'нива', 'парцел']):
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
            neighborhood TEXT, address TEXT, property_type TEXT, size_sqm REAL, 
            rooms INTEGER, court TEXT, auction_start TEXT, auction_end TEXT, scraped_at DATETIME
        )
    """)
    conn.execute("CREATE INDEX idx_city ON auctions(city)")
    conn.execute("CREATE INDEX idx_type ON auctions(property_type)")
    conn.execute("CREATE INDEX idx_neighborhood ON auctions(neighborhood)")
    conn.commit()
    return conn


def scrape_range(start_id=85000, end_id=85100, workers=10):
    conn = init_db()
    
    print(f"=== КЧСИ Scraper v5 - {datetime.utcnow().isoformat()} ===")
    print(f"Range: {start_id} to {end_id}")
    print(f"Timeouts: Request={REQUEST_TIMEOUT}s, Socket={SOCKET_TIMEOUT}s")
    print(f"Workers: {workers}\n")
    
    all_data = []
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_detail_with_timeout, pid): pid for pid in range(start_id, end_id + 1)}
        
        done = 0
        success = 0
        neighborhoods_found = 0
        
        for future in as_completed(futures):
            done += 1
            
            try:
                data = future.result()
                if data and data.get('price_eur'):
                    all_data.append(data)
                    success += 1
                    
                    if data.get('neighborhood'):
                        neighborhoods_found += 1
                    
                    conn.execute("""
                        INSERT OR REPLACE INTO auctions 
                        (id, url, price_eur, city, district, neighborhood, address, property_type, 
                         size_sqm, rooms, court, auction_start, auction_end, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data.get('id'), data.get('url'), data.get('price_eur'),
                        data.get('city'), data.get('district'), data.get('neighborhood'),
                        data.get('address'), data.get('property_type'), data.get('size_sqm'), 
                        data.get('rooms'), data.get('court'), data.get('auction_start'), 
                        data.get('auction_end'), data.get('scraped_at')
                    ))
            except Exception as e:
                pass
            
            if done % 20 == 0:
                conn.commit()
                print(f"  Progress: {done}/{end_id-start_id+1} scanned, {success} valid, {neighborhoods_found} neighborhoods found")
                sys.stdout.flush()
    
    conn.commit()
    
    print(f"\nSCRAPED: {success} listings")
    print(f"Neighborhoods extracted: {neighborhoods_found}")
    
    cursor = conn.cursor()
    
    print("\nBy property type:")
    for row in cursor.execute("""
        SELECT property_type, COUNT(*), ROUND(AVG(price_eur), 0), ROUND(AVG(size_sqm), 0)
        FROM auctions GROUP BY property_type ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]:15} : {row[1]:3} listings")
    
    print("\nTop neighborhoods:")
    for row in cursor.execute("""
        SELECT neighborhood, city, COUNT(*), ROUND(AVG(price_eur), 0)
        FROM auctions WHERE neighborhood IS NOT NULL 
        GROUP BY neighborhood ORDER BY COUNT(*) DESC LIMIT 10
    """):
        print(f"  {row[0]:20} ({row[1]}): {row[2]:3} listings")
    
    conn.close()
    
    with open('data/bcpea_v5.json', 'w', encoding='utf-8') as f:
        json.dump({
            'scraped_at': datetime.utcnow().isoformat(), 
            'count': len(all_data), 
            'listings': all_data
        }, f, ensure_ascii=False)
    
    print(f"\n✓ Saved to {DB_PATH}")
    return success, neighborhoods_found


if __name__ == '__main__':
    scrape_range(start_id=85000, end_id=85100, workers=10)
