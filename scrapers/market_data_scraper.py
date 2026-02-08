#!/usr/bin/env python3
"""
Enhanced Market Data Scraper for Bulgarian Real Estate
Fetches from: imot.bg, alo.bg, olx.bg, homes.bg
"""

import re
import sqlite3
import urllib.request
from datetime import datetime
import os
import time

DB_PATH = "data/market_listings.db"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

OLX_CITIES = {
    'София': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-sofia/',
    'Варна': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-varna/',
    'Бургас': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-burgas/',
    'Пловдив': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-plovdiv/',
}

ALO_CITIES = {
    'София': 1, 'Пловдив': 2, 'Варна': 3, 'Бургас': 4,
}

HOMES_URLS = {
    'София': 'https://www.homes.bg/obiavi/apartamenti/prodazhba/sofia/',
    'Пловдив': 'https://www.homes.bg/obiavi/apartamenti/prodazhba/plovdiv/',
    'Варна': 'https://www.homes.bg/obiavi/apartamenti/prodazhba/varna/',
    'Бургас': 'https://www.homes.bg/obiavi/apartamenti/prodazhba/burgas/',
}


def extract_rooms(text):
    if not text:
        return None
    text_lower = text.lower()
    patterns = [
        (r'\bедностаен', 1), (r'\bдвустаен', 2), (r'\bтристаен', 3),
        (r'\bчетиристаен', 4), (r'\bпетстаен', 5), (r'\bмногостаен', 4),
        (r'\bгарсониера', 1),
    ]
    for pattern, rooms in patterns:
        if re.search(pattern, text_lower):
            return rooms
    return None


def fetch_url(url, retries=3):
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            return None
    return None


def fetch_olx():
    listings = []
    for city, url in OLX_CITIES.items():
        print(f"  Fetching OLX.bg {city}...", end=" ", flush=True)
        count = 0
        for page in range(1, 4):
            page_url = f"{url}?page={page}" if page > 1 else url
            data = fetch_url(page_url)
            if not data:
                break
            html = data.decode('utf-8', errors='ignore')
            pattern = rf'гр\.\s*{city},\s*([^-\n<]+)'
            districts = re.findall(pattern, html)
            size_prices = re.findall(r'(\d+)\s*кв\.м\s*-\s*([\d\.]+)', html)
            for i, (size_str, price_sqm_str) in enumerate(size_prices):
                try:
                    size = float(size_str)
                    price_per_sqm = float(price_sqm_str)
                    total = size * price_per_sqm
                    district = districts[i].strip() if i < len(districts) else None
                    if size >= 30 and price_per_sqm >= 300:
                        listings.append({
                            'city': city, 'district': district, 'size_sqm': size,
                            'price_per_sqm': round(price_per_sqm, 2), 'price_eur': round(total, 2),
                            'property_type': 'апартамент', 'source': 'olx.bg', 'rooms': None
                        })
                        count += 1
                except:
                    continue
        print(f"{count} listings")
    return listings


def fetch_imot():
    listings = []
    print(f"  Fetching imot.bg...", end=" ", flush=True)
    data = fetch_url("https://www.imot.bg/obiavi/prodazhbi")
    if data:
        html = data.decode('windows-1251', errors='ignore')
        # Price: 134 352 euro followed by size
        blocks = re.findall(r'Цена:\s*([\d\s]+)\s*euro.*?([\d\s]+)\s*кв\.м', html, re.DOTALL | re.IGNORECASE)
        for price_str, size_str in blocks[:100]:  # Limit to first 100
            try:
                price = float(price_str.replace(' ', ''))
                size = float(size_str.replace(' ', ''))
                if price > 5000 and size > 30:
                    listings.append({
                        'city': None, 'district': None, 'size_sqm': size, 'price_eur': price,
                        'price_per_sqm': round(price / size, 2), 'property_type': 'апартамент',
                        'source': 'imot.bg', 'rooms': None
                    })
            except:
                continue
    print(f"{len(listings)} listings")
    return listings


def fetch_alo():
    listings = []
    for city, city_id in ALO_CITIES.items():
        print(f"  Fetching alo.bg {city}...", end=" ", flush=True)
        count = 0
        url = f"https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id={city_id}"
        data = fetch_url(url)
        if not data:
            print("0 listings")
            continue
        html = data.decode('utf-8', errors='ignore')
        # Simpler pattern - just price and sqm price
        entries = re.findall(
            r'Цена:([\d\s]+)\s*€.*?за кв\.м:\s*([\d\.]+)\s*€/кв\.м.*?Квадратура:(\d+)\s*кв\.м',
            html, re.DOTALL | re.IGNORECASE
        )
        for price_str, price_sqm_str, size_str in entries:
            try:
                price = float(price_str.replace(' ', ''))
                price_per_sqm = float(price_sqm_str)
                size = float(size_str)
                if size > 30 and price > 5000:
                    listings.append({
                        'city': city, 'district': None, 'size_sqm': size, 'price_eur': price,
                        'price_per_sqm': round(price_per_sqm, 2), 'property_type': 'апартамент',
                        'source': 'alo.bg', 'rooms': None
                    })
                    count += 1
            except:
                continue
        print(f"{count} listings")
    return listings


def fetch_homes():
    listings = []
    for city, url in HOMES_URLS.items():
        print(f"  Fetching homes.bg {city}...", end=" ", flush=True)
        count = 0
        data = fetch_url(url)
        if not data:
            print("0 listings")
            continue
        html = data.decode('utf-8', errors='ignore')
        # Pattern: room type, size, price, price_per_sqm
        blocks = re.findall(r'(\w+стаен),\s*(\d+)m².*?([\d,]+)\s*EUR\s*([\d,]+)EUR/m²', html, re.DOTALL | re.IGNORECASE)
        for room_type, size_str, price_str, price_sqm_str in blocks:
            try:
                size = float(size_str)
                price = float(price_str.replace(',', ''))
                price_per_sqm = float(price_sqm_str.replace(',', ''))
                rooms = extract_rooms(room_type)
                if size > 30 and price > 5000:
                    listings.append({
                        'city': city, 'district': None, 'size_sqm': size, 'price_eur': price,
                        'price_per_sqm': round(price_per_sqm, 2), 'property_type': 'апартамент',
                        'source': 'homes.bg', 'rooms': rooms
                    })
                    count += 1
            except:
                continue
        print(f"{count} listings")
    return listings


def init_db():
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS market_listings")
    c.execute("""
        CREATE TABLE market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, city TEXT, district TEXT,
            property_type TEXT, size_sqm REAL, price_eur REAL, price_per_sqm REAL,
            rooms INTEGER, source TEXT, scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("CREATE INDEX idx_city ON market_listings(city)")
    c.execute("CREATE INDEX idx_source ON market_listings(source)")
    c.execute("CREATE INDEX idx_size ON market_listings(size_sqm)")
    conn.commit()
    return conn


def save_listings(conn, listings):
    c = conn.cursor()
    for l in listings:
        c.execute("""
            INSERT INTO market_listings (city, district, property_type, size_sqm, price_eur, price_per_sqm, rooms, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (l.get('city'), l.get('district'), l.get('property_type'), l.get('size_sqm'),
              l.get('price_eur'), l.get('price_per_sqm'), l.get('rooms'), l.get('source')))
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
    print(f"=== Market Scraper - {datetime.utcnow().isoformat()} ===\n")
    conn = init_db()
    all_listings = []
    print("Fetching from OLX.bg...")
    all_listings.extend(fetch_olx())
    print("\nFetching from imot.bg...")
    all_listings.extend(fetch_imot())
    print("\nFetching from alo.bg...")
    all_listings.extend(fetch_alo())
    print("\nFetching from homes.bg...")
    all_listings.extend(fetch_homes())
    print(f"\nSaving {len(all_listings)} listings...")
    save_listings(conn, all_listings)
    print_stats(conn)
    conn.close()
    print(f"\n✓ Database: {DB_PATH}")
    return len(all_listings)


if __name__ == '__main__':
    main()
