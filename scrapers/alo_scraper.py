#!/usr/bin/env python3
"""
Alo.bg Scraper - Apartment Listings
====================================
"""

import os
import re
import sqlite3
import time
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List

import requests
from bs4 import BeautifulSoup

DB_PATH = "data/market.db"

CITIES = {
    'София': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=1',
    'Пловдив': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=2',
    'Варна': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=3',
    'Бургас': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=4',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'bg-BG,bg;q=0.9,en;q=0.8',
}

@dataclass
class Listing:
    city: str
    neighborhood: Optional[str]
    size_sqm: float
    price_eur: float
    price_per_sqm: float
    rooms: Optional[int]
    source: str
    scraped_at: str

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else '.', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS market_listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        city TEXT NOT NULL, neighborhood TEXT, size_sqm REAL NOT NULL,
        price_eur REAL NOT NULL, price_per_sqm REAL NOT NULL,
        rooms INTEGER, source TEXT NOT NULL, scraped_at TEXT NOT NULL,
        UNIQUE(city, size_sqm, price_eur, source))''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_city ON market_listings(city)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_source ON market_listings(source)')
    conn.commit()
    return conn

def save_listings(conn, listings):
    c = conn.cursor()
    saved = 0
    for l in listings:
        try:
            c.execute('''INSERT OR REPLACE INTO market_listings 
                (city, neighborhood, size_sqm, price_eur, price_per_sqm, rooms, source, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (l.city, l.neighborhood, l.size_sqm, l.price_eur, l.price_per_sqm, l.rooms, l.source, l.scraped_at))
            saved += 1
        except:
            continue
    conn.commit()
    return saved

def scrape_alo_city(city, url):
    """Scrape alo.bg listings for a city."""
    listings = []
    
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR: {e}")
        return listings
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Find listing param containers
    param_divs = soup.find_all('div', class_='listtop-item-params')
    
    for div in param_divs:
        try:
            text = div.get_text()
            
            # Extract price in EUR - format: "125 900 €"
            price_match = re.search(r'Цена:\s*([\d\s]+)\s*€', text)
            if not price_match:
                # Try alternative format
                price_match = re.search(r'([\d\s]+)\s*€', text)
            
            if not price_match:
                continue
            
            price_str = price_match.group(1).replace(' ', '').replace('\xa0', '')
            price_eur = float(price_str)
            
            if price_eur < 10000 or price_eur > 2000000:
                continue
            
            # Extract size - format: "Квадратура:60 кв.м"
            size_match = re.search(r'Квадратура:\s*(\d+)', text)
            if not size_match:
                size_match = re.search(r'(\d+)\s*кв\.?м', text)
            
            if not size_match:
                continue
            
            size_sqm = float(size_match.group(1))
            if size_sqm < 15 or size_sqm > 500:
                continue
            
            # Extract rooms from property type
            rooms = None
            if 'Едностаен' in text:
                rooms = 1
            elif 'Двустаен' in text:
                rooms = 2
            elif 'Тристаен' in text:
                rooms = 3
            elif 'Четиристаен' in text:
                rooms = 4
            elif 'Многостаен' in text:
                rooms = 5
            
            listings.append(Listing(
                city=city,
                neighborhood=None,
                size_sqm=size_sqm,
                price_eur=round(price_eur, 2),
                price_per_sqm=round(price_eur / size_sqm, 2),
                rooms=rooms,
                source='alo.bg',
                scraped_at=datetime.utcnow().isoformat()
            ))
            
        except Exception:
            continue
    
    return listings[:60]

def main():
    print(f"🏠 Alo.bg Scraper")
    print(f"⏰ {datetime.now().isoformat()}")
    print("=" * 60)
    
    conn = init_db()
    c = conn.cursor()
    c.execute("DELETE FROM market_listings WHERE source = 'alo.bg'")
    conn.commit()
    print(f"🗑️  Cleared {c.rowcount} old alo.bg listings")
    
    total = []
    
    for city, url in CITIES.items():
        print(f"\n📍 {city}")
        print(f"  🔍 alo.bg... ", end="", flush=True)
        
        listings = scrape_alo_city(city, url)
        
        if listings:
            saved = save_listings(conn, listings)
            print(f"found {len(listings)}, saved {saved}")
            total.extend(listings)
        else:
            print("0 found")
        
        time.sleep(1)  # Be polite
    
    conn.close()
    print(f"\n{'=' * 60}")
    print(f"✅ Total: {len(total)} alo.bg listings scraped")

if __name__ == "__main__":
    main()
