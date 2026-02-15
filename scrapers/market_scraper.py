#!/usr/bin/env python3
"""
Market Scraper v4 - Clean Implementation
========================================
Uses requests + BeautifulSoup (like promobg project)
- Simple retry logic
- Proper encoding handling  
- No excessive rate limiting
- Session-based requests

Sources: imot.bg, olx.bg
"""

import json
import os
import re
import sqlite3
import time
import random
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ============================================================================
# CONFIG
# ============================================================================

DB_PATH = "data/market.db"
OUTPUT_JSON = "data/market_listings.json"

# Cities with correct URL formats
CITIES = {
    'София': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-sofiya/',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/sofiya/',
    },
    'Пловдив': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-plovdiv/',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/plovdiv/',
    },
    'Варна': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-varna/',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/varna/',
    },
    'Бургас': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-burgas/',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/burgas/',
    },
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'bg-BG,bg;q=0.9,en;q=0.8',
}

# ============================================================================
# DATA MODEL
# ============================================================================

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

# ============================================================================
# HTTP UTILS
# ============================================================================

def create_session() -> requests.Session:
    """Create a requests session with proper headers."""
    session = requests.Session()
    session.headers.update(HEADERS)
    return session

def fetch_page(session: requests.Session, url: str, encoding: str = 'utf-8', retries: int = 3) -> Optional[str]:
    """Fetch a page with retry logic."""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            
            # Handle encoding
            if encoding == 'windows-1251':
                resp.encoding = 'windows-1251'
            return resp.text
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"404: {url[:60]}...")
                return None
            print(f"HTTP {e.response.status_code}, retry {attempt+1}/{retries}")
            time.sleep(2 ** attempt)
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}, retry {attempt+1}/{retries}")
            time.sleep(2 ** attempt)
    
    return None

# ============================================================================
# IMOT.BG SCRAPER
# ============================================================================

def scrape_imot_index(session: requests.Session, url: str) -> List[str]:
    """Get listing URLs from imot.bg index page."""
    html = fetch_page(session, url, encoding='windows-1251')
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find apartment listing links
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'obiava' in href and 'prodava' in href and 'apartament' in href:
            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = 'https://www.imot.bg' + href
            
            # Skip duplicates and anchors
            clean_href = href.split('#')[0]
            if clean_href not in links:
                links.append(clean_href)
    
    return links[:30]  # Limit to 30 per city

def parse_imot_listing(session: requests.Session, url: str, city: str) -> Optional[Listing]:
    """Parse a single imot.bg listing page."""
    html = fetch_page(session, url, encoding='windows-1251')
    if not html:
        return None
    
    soup = BeautifulSoup(html, 'html.parser')
    
    try:
        # Find price - look for EUR price
        price_eur = None
        for text in soup.stripped_strings:
            # Match patterns like "148 000 €" or "148000€"
            match = re.search(r'(\d[\d\s]*\d)\s*[€EUR]', text)
            if match:
                price_str = match.group(1).replace(' ', '').replace('\xa0', '')
                if price_str.isdigit():
                    price_eur = float(price_str)
                    if price_eur > 5000:  # Sanity check
                        break
        
        if not price_eur:
            return None
        
        # Find size - look for sqm
        size_sqm = None
        for text in soup.stripped_strings:
            match = re.search(r'(\d+)\s*кв\.?\s*м', text)
            if match:
                size_sqm = float(match.group(1))
                if 15 <= size_sqm <= 500:
                    break
        
        if not size_sqm:
            return None
        
        # Calculate price per sqm
        price_per_sqm = round(price_eur / size_sqm, 2)
        
        # Validate
        if not (200 <= price_per_sqm <= 15000):
            return None
        
        # Extract rooms from URL or text
        rooms = None
        url_lower = url.lower()
        if 'ednostaen' in url_lower:
            rooms = 1
        elif 'dvustaen' in url_lower:
            rooms = 2
        elif 'tristaen' in url_lower:
            rooms = 3
        elif 'chetiristaen' in url_lower or 'mnogostaen' in url_lower:
            rooms = 4
        
        return Listing(neighborhood=None, 
            city=city,
            size_sqm=size_sqm,
            price_eur=price_eur,
            price_per_sqm=price_per_sqm,
            rooms=rooms,
            source='imot.bg',
            scraped_at=datetime.utcnow().isoformat()
        )
    
    except Exception as e:
        return None

def scrape_imot_city(session: requests.Session, url: str, city: str) -> List[Listing]:
    """Scrape all imot.bg listings for a city."""
    listings = []
    
    # Get listing URLs
    urls = scrape_imot_index(session, url)
    if not urls:
        return listings
    
    print(f"found {len(urls)}, scraping...", end=" ", flush=True)
    
    # Scrape each listing (with small delay)
    for listing_url in urls:
        listing = parse_imot_listing(session, listing_url, city)
        if listing:
            listings.append(listing)
        time.sleep(0.5 + random.random())  # 0.5-1.5s delay
    
    return listings

# ============================================================================
# OLX.BG SCRAPER
# ============================================================================

def scrape_olx(session: requests.Session, url: str, city: str) -> List[Listing]:
    """Scrape OLX.bg listings for a city."""
    listings = []
    
    html = fetch_page(session, url)
    if not html:
        return listings
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # OLX shows listings with format: "XX кв.м - YYYY.YY"
    text = soup.get_text()
    
    # Pattern: size sqm - price per sqm
    pattern = re.compile(r'(\d+)\s*кв\.м\s*-\s*([\d\.,]+)')
    
    for match in pattern.finditer(text):
        try:
            size_sqm = float(match.group(1))
            price_per_sqm = float(match.group(2).replace(',', '.'))
            
            # Validate
            if not (15 <= size_sqm <= 500):
                continue
            if not (200 <= price_per_sqm <= 15000):
                continue
            
            price_eur = round(size_sqm * price_per_sqm, 2)
            
            listings.append(Listing(neighborhood=None, 
                city=city,
                size_sqm=size_sqm,
                price_eur=price_eur,
                price_per_sqm=price_per_sqm,
                rooms=None,
                source='olx.bg',
                scraped_at=datetime.utcnow().isoformat()
            ))
        except:
            continue
    
    # Also try pagination
    for page in range(2, 4):  # Pages 2-3
        page_url = f"{url}?page={page}"
        html = fetch_page(session, page_url)
        if not html:
            break
        
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()
        
        for match in pattern.finditer(text):
            try:
                size_sqm = float(match.group(1))
                price_per_sqm = float(match.group(2).replace(',', '.'))
                
                if not (15 <= size_sqm <= 500):
                    continue
                if not (200 <= price_per_sqm <= 15000):
                    continue
                
                price_eur = round(size_sqm * price_per_sqm, 2)
                
                listings.append(Listing(neighborhood=None, 
                    city=city,
                    size_sqm=size_sqm,
                    price_eur=price_eur,
                    price_per_sqm=price_per_sqm,
                    rooms=None,
                    source='olx.bg',
                    scraped_at=datetime.utcnow().isoformat()
                ))
            except:
                continue
        
        time.sleep(0.5)
    
    return listings

# ============================================================================
# DATABASE
# ============================================================================

def init_db() -> sqlite3.Connection:
    """Initialize database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DROP TABLE IF EXISTS market_listings")
    conn.execute("""
        CREATE TABLE market_listings (
            id INTEGER PRIMARY KEY,
            city TEXT NOT NULL,
            neighborhood TEXT,
            size_sqm REAL NOT NULL,
            price_eur REAL,
            price_per_sqm REAL,
            rooms INTEGER,
            source TEXT NOT NULL,
            scraped_at TEXT,
            UNIQUE(city, size_sqm, price_eur, source)
        )
    """)
    conn.execute("CREATE INDEX idx_city ON market_listings(city)")
    conn.execute("CREATE INDEX idx_neighborhood ON market_listings(neighborhood)")
    conn.execute("CREATE INDEX idx_source ON market_listings(source)")
    conn.commit()
    return conn

def save_listings(conn: sqlite3.Connection, listings: List[Listing]) -> int:
    """Save listings to database."""
    saved = 0
    for l in listings:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO market_listings 
                (city, size_sqm, price_eur, price_per_sqm, rooms, source, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (l.city, l.size_sqm, l.price_eur, l.price_per_sqm, l.rooms, l.source, l.scraped_at))
            saved += 1
        except:
            pass
    conn.commit()
    return saved

def export_json(conn: sqlite3.Connection) -> int:
    """Export to JSON."""
    cursor = conn.cursor()
    cursor.execute("SELECT city, size_sqm, price_eur, price_per_sqm, rooms, source, scraped_at FROM market_listings")
    
    listings = []
    for row in cursor.fetchall():
        listings.append({
            'city': row[0],
            'size_sqm': row[1],
            'price_eur': row[2],
            'price_per_sqm': row[3],
            'rooms': row[4],
            'source': row[5],
            'scraped_at': row[6]
        })
    
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)
    
    return len(listings)

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("🏠 Market Scraper v4 (requests + BeautifulSoup)")
    print(f"⏰ {datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    conn = init_db()
    session = create_session()
    
    total = 0
    
    for city, urls in CITIES.items():
        print(f"\n📍 {city}")
        
        # imot.bg
        print(f"  🔍 imot.bg... ", end="", flush=True)
        listings = scrape_imot_city(session, urls['imot'], city)
        saved = save_listings(conn, listings)
        print(f"✓ {len(listings)} → {saved} saved")
        total += saved
        
        # olx.bg
        print(f"  🔍 olx.bg... ", end="", flush=True)
        listings = scrape_olx(session, urls['olx'], city)
        saved = save_listings(conn, listings)
        print(f"✓ {len(listings)} → {saved} saved")
        total += saved
    
    # Export
    exported = export_json(conn)
    print(f"\n📤 Exported {exported} to {OUTPUT_JSON}")
    
    # Stats
    print("\n" + "=" * 60)
    print("📊 STATISTICS")
    print("=" * 60)
    
    cursor = conn.cursor()
    
    print("\nBy source:")
    for row in cursor.execute("""
        SELECT source, COUNT(*), ROUND(AVG(price_per_sqm), 0)
        FROM market_listings WHERE price_per_sqm IS NOT NULL
        GROUP BY source
    """):
        print(f"  {row[0]}: {row[1]} listings, avg €{row[2]}/m²")
    
    print("\nBy city:")
    for row in cursor.execute("""
        SELECT city, COUNT(*), ROUND(AVG(price_per_sqm), 0)
        FROM market_listings WHERE price_per_sqm IS NOT NULL
        GROUP BY city ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]}: {row[1]} listings, avg €{row[2]}/m²")
    
    print(f"\n{'=' * 60}")
    print(f"TOTAL: {total} listings")
    print(f"{'=' * 60}")
    
    conn.close()
    print(f"\n✅ Done: {datetime.utcnow().isoformat()}")

if __name__ == '__main__':
    main()
