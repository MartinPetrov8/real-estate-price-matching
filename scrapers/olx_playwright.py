#!/usr/bin/env python3
"""
OLX Playwright Scraper v2 - Fixed parsing
==========================================
"""

import re
import sqlite3
import os
import sys
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: Playwright not installed")
    sys.exit(1)

DB_PATH = "data/market.db"

CITIES = {
    'София': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/sofiya/',
    'Пловдив': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/plovdiv/',
    'Варна': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/varna/',
    'Бургас': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/burgas/',
    'Русе': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/ruse/',
    'Стара Загора': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/stara-zagora/',
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL, neighborhood TEXT, size_sqm REAL NOT NULL,
            price_eur REAL NOT NULL, price_per_sqm REAL NOT NULL,
            rooms INTEGER, source TEXT NOT NULL, scraped_at TEXT NOT NULL
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_city ON market_listings(city)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_source ON market_listings(source)')
    conn.commit()
    return conn

def save_listings(conn, listings):
    c = conn.cursor()
    for l in listings:
        c.execute('''INSERT OR REPLACE INTO market_listings 
            (city, neighborhood, size_sqm, price_eur, price_per_sqm, rooms, source, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (l.city, l.neighborhood, l.size_sqm, l.price_eur, l.price_per_sqm, l.rooms, l.source, l.scraped_at))
    conn.commit()
    return len(listings)

def scrape_olx_city(page, city, url):
    listings = []
    try:
        page.goto(url, wait_until='networkidle', timeout=60000)
        page.wait_for_selector('[data-cy="l-card"]', timeout=30000)
        cards = page.query_selector_all('[data-cy="l-card"]')
        print(f"found {len(cards)} cards", end="", flush=True)
        
        for card in cards[:60]:
            try:
                text = card.inner_text()
                
                # Extract EUR price - pattern: "247071 €" or "/ 247071 €"
                eur_match = re.search(r'(\d[\d\s]*)\s*€', text)
                if not eur_match:
                    continue
                price_str = eur_match.group(1).replace(' ', '').replace('\xa0', '')
                price_eur = float(price_str)
                if price_eur < 10000 or price_eur > 2000000:
                    continue
                
                # Extract size - pattern: "150 кв.м" or "150 кв.м - 1647"
                size_match = re.search(r'(\d+)\s*кв\.?м', text)
                if not size_match:
                    continue
                size_sqm = float(size_match.group(1))
                if size_sqm < 15 or size_sqm > 500:
                    continue
                
                # Neighborhood from location
                neighborhood = None
                loc_match = re.search(r'гр\.\s*\S+,\s*([^-]+?)\s*-', text)
                if loc_match:
                    neighborhood = loc_match.group(1).strip()
                
                # Rooms from title
                rooms = None
                rooms_match = re.search(r'(\d)-?стаен|(\d)-?стаи|Едностаен|Двустаен|Тристаен|Четиристаен|Многостаен', text, re.I)
                if rooms_match:
                    if rooms_match.group(1):
                        rooms = int(rooms_match.group(1))
                    elif rooms_match.group(2):
                        rooms = int(rooms_match.group(2))
                    elif 'Едностаен' in text:
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
                    city=city, neighborhood=neighborhood, size_sqm=size_sqm,
                    price_eur=round(price_eur, 2), price_per_sqm=round(price_eur / size_sqm, 2),
                    rooms=rooms, source='olx.bg', scraped_at=datetime.utcnow().isoformat()
                ))
            except:
                continue
    except Exception as e:
        print(f" ERROR: {e}", end="")
    return listings

def main():
    print(f"🏠 OLX Playwright Scraper v2")
    print(f"⏰ {datetime.now().isoformat()}")
    print("=" * 60)
    
    conn = init_db()
    c = conn.cursor()
    c.execute("DELETE FROM market_listings WHERE source = 'olx.bg'")
    conn.commit()
    print(f"🗑️  Cleared {c.rowcount} old OLX listings")
    
    total = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            locale='bg-BG',
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        
        for city, url in CITIES.items():
            print(f"\n📍 {city}")
            print(f"  🔍 olx.bg... ", end="", flush=True)
            listings = scrape_olx_city(page, city, url)
            if listings:
                saved = save_listings(conn, listings)
                print(f" → saved {saved}")
                total.extend(listings)
            else:
                print(" → 0 found")
        
        browser.close()
    conn.close()
    print(f"\n{'=' * 60}")
    print(f"✅ Total: {len(total)} OLX listings scraped")

if __name__ == "__main__":
    main()
