#!/usr/bin/env python3
"""
Market Scraper v5 - Production Ready
=====================================
Uses requests + BeautifulSoup
- Graceful SIGTERM handling (saves progress on shutdown)
- No DROP TABLE — uses CREATE IF NOT EXISTS + 7-day cleanup
- WAL mode for safe concurrent reads
- Proper exception handling (no bare excepts)
- Per-city commit checkpointing
- File logging

Sources: imot.bg, olx.bg
"""

import json
import logging
import os
import re
import signal
import sqlite3
import sys
import time
import random
from datetime import datetime, timedelta
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
LOG_DIR = "data/logs"
DATA_RETENTION_DAYS = 7

# Graceful shutdown
SHUTDOWN_REQUESTED = False

def signal_handler(signum, frame):
    global SHUTDOWN_REQUESTED
    logging.warning(f"Received signal {signum}, requesting graceful shutdown...")
    SHUTDOWN_REQUESTED = True

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

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
    'Русе': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-ruse/',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/ruse/',
    },
    'Стара Загора': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-stara-zagora/',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/stara-zagora/',
    },
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'bg-BG,bg;q=0.9,en;q=0.8',
}

# ============================================================================
# LOGGING
# ============================================================================

def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"market_{datetime.utcnow().strftime('%Y-%m-%d')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ]
    )

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
    session = requests.Session()
    session.headers.update(HEADERS)
    return session

def fetch_page(session: requests.Session, url: str, encoding: str = 'utf-8', retries: int = 3) -> Optional[str]:
    for attempt in range(retries):
        if SHUTDOWN_REQUESTED:
            return None
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            if encoding == 'windows-1251':
                resp.encoding = 'windows-1251'
            return resp.text
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logging.debug(f"404: {url[:60]}...")
                return None
            logging.warning(f"HTTP {e.response.status_code} for {url[:60]}, retry {attempt+1}/{retries}")
            time.sleep(2 ** attempt)
        except requests.exceptions.RequestException as e:
            logging.warning(f"Request error: {e}, retry {attempt+1}/{retries}")
            time.sleep(2 ** attempt)
    
    logging.error(f"Failed after {retries} retries: {url[:80]}")
    return None

# ============================================================================
# IMOT.BG SCRAPER
# ============================================================================

def scrape_imot_index(session: requests.Session, url: str) -> List[str]:
    html = fetch_page(session, url, encoding='windows-1251')
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'obiava' in href and 'prodava' in href and 'apartament' in href:
            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = 'https://www.imot.bg' + href
            clean_href = href.split('#')[0]
            if clean_href not in links:
                links.append(clean_href)
    
    return links[:30]

def parse_imot_listing(session: requests.Session, url: str, city: str) -> Optional[Listing]:
    html = fetch_page(session, url, encoding='windows-1251')
    if not html:
        return None
    
    soup = BeautifulSoup(html, 'html.parser')
    
    try:
        # Find price
        price_eur = None
        for text in soup.stripped_strings:
            match = re.search(r'(\d[\d\s]*\d)\s*[€EUR]', text)
            if match:
                price_str = match.group(1).replace(' ', '').replace('\xa0', '')
                if price_str.isdigit():
                    price_eur = float(price_str)
                    if price_eur > 5000:
                        break
        
        if not price_eur:
            return None
        
        # Find size
        size_sqm = None
        for text in soup.stripped_strings:
            match = re.search(r'(\d+)\s*кв\.?\s*м', text)
            if match:
                size_sqm = float(match.group(1))
                if 15 <= size_sqm <= 500:
                    break
        
        if not size_sqm:
            return None
        
        price_per_sqm = round(price_eur / size_sqm, 2)
        if not (200 <= price_per_sqm <= 15000):
            return None
        
        # Extract rooms from URL
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
        
        return Listing(
            neighborhood=None, city=city, size_sqm=size_sqm,
            price_eur=price_eur, price_per_sqm=price_per_sqm,
            rooms=rooms, source='imot.bg',
            scraped_at=datetime.utcnow().isoformat()
        )
    
    except (ValueError, TypeError, AttributeError) as e:
        logging.debug(f"Parse error for {url[:60]}: {e}")
        return None

def scrape_imot_city(session: requests.Session, url: str, city: str) -> List[Listing]:
    listings = []
    urls = scrape_imot_index(session, url)
    if not urls:
        return listings
    
    logging.info(f"  imot.bg: found {len(urls)} links, scraping...")
    print(f"found {len(urls)}, scraping...", end=" ", flush=True)
    
    for listing_url in urls:
        if SHUTDOWN_REQUESTED:
            logging.warning("Shutdown requested mid-imot scrape, returning partial results")
            break
        listing = parse_imot_listing(session, listing_url, city)
        if listing:
            listings.append(listing)
        time.sleep(0.5 + random.random())
    
    return listings

# ============================================================================
# OLX.BG SCRAPER
# ============================================================================

def scrape_olx(session: requests.Session, url: str, city: str) -> List[Listing]:
    listings = []
    
    for page in range(1, 4):  # Pages 1-3
        if SHUTDOWN_REQUESTED:
            break
        
        page_url = url if page == 1 else f"{url}?page={page}"
        html = fetch_page(session, page_url)
        if not html:
            if page == 1:
                logging.warning(f"OLX failed for {city} page 1")
            break
        
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()
        
        pattern = re.compile(r'(\d+)\s*кв\.м\s*-\s*([\d\.,]+)')
        
        for match in pattern.finditer(text):
            try:
                size_sqm = float(match.group(1))
                price_per_sqm = float(match.group(2).replace(',', '.'))
                
                if not (15 <= size_sqm <= 500):
                    continue
                if not (200 <= price_per_sqm <= 15000):
                    continue
                
                price_eur = round(size_sqm * price_per_sqm, 2)
                
                listings.append(Listing(
                    neighborhood=None, city=city, size_sqm=size_sqm,
                    price_eur=price_eur, price_per_sqm=price_per_sqm,
                    rooms=None, source='olx.bg',
                    scraped_at=datetime.utcnow().isoformat()
                ))
            except (ValueError, TypeError):
                continue
        
        if page < 3:
            time.sleep(0.5)
    
    return listings

# ============================================================================
# DATABASE
# ============================================================================

def init_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_listings (
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_city ON market_listings(city)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON market_listings(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_size ON market_listings(size_sqm)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scraped ON market_listings(scraped_at)")
    
    # Purge stale data instead of DROP TABLE
    cutoff = (datetime.utcnow() - timedelta(days=DATA_RETENTION_DAYS)).isoformat()
    cursor = conn.execute("DELETE FROM market_listings WHERE scraped_at < ?", (cutoff,))
    if cursor.rowcount > 0:
        logging.info(f"Purged {cursor.rowcount} listings older than {DATA_RETENTION_DAYS} days")
    
    conn.commit()
    return conn

def save_listings(conn: sqlite3.Connection, listings: List[Listing]) -> int:
    saved = 0
    for l in listings:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO market_listings 
                (city, size_sqm, price_eur, price_per_sqm, rooms, source, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (l.city, l.size_sqm, l.price_eur, l.price_per_sqm, l.rooms, l.source, l.scraped_at))
            saved += 1
        except sqlite3.Error as e:
            logging.warning(f"DB insert error: {e}")
    conn.commit()  # Commit per-city batch (checkpoint)
    return saved

def export_json(conn: sqlite3.Connection) -> int:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT city, size_sqm, price_eur, price_per_sqm, rooms, source, scraped_at 
        FROM market_listings
        ORDER BY city, price_per_sqm
    """)
    
    listings = []
    for row in cursor.fetchall():
        listings.append({
            'city': row[0], 'size_sqm': row[1], 'price_eur': row[2],
            'price_per_sqm': row[3], 'rooms': row[4], 'source': row[5],
            'scraped_at': row[6]
        })
    
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)
    
    return len(listings)

# ============================================================================
# MAIN
# ============================================================================

def main():
    setup_logging()
    
    logging.info("🏠 Market Scraper v5 (Production)")
    print("🏠 Market Scraper v5 (Production)")
    print(f"⏰ {datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    conn = init_db()
    session = create_session()
    
    total = 0
    cities_completed = 0
    
    for city, urls in CITIES.items():
        if SHUTDOWN_REQUESTED:
            logging.warning(f"Shutdown requested, stopping after {cities_completed} cities")
            print(f"\n⚠️  Shutdown after {cities_completed}/{len(CITIES)} cities")
            break
        
        print(f"\n📍 {city}")
        
        # imot.bg
        print(f"  🔍 imot.bg... ", end="", flush=True)
        listings = scrape_imot_city(session, urls['imot'], city)
        saved = save_listings(conn, listings)
        print(f"✓ {len(listings)} → {saved} saved")
        total += saved
        
        if SHUTDOWN_REQUESTED:
            logging.warning("Shutdown after imot.bg, skipping olx.bg")
            break
        
        # olx.bg
        print(f"  🔍 olx.bg... ", end="", flush=True)
        listings = scrape_olx(session, urls['olx'], city)
        saved = save_listings(conn, listings)
        print(f"✓ {len(listings)} → {saved} saved")
        total += saved
        
        cities_completed += 1
    
    # Always export whatever we have (even partial)
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
    print(f"TOTAL: {exported} listings ({cities_completed}/{len(CITIES)} cities)")
    if SHUTDOWN_REQUESTED:
        print("⚠️  PARTIAL RUN (graceful shutdown)")
    print(f"{'=' * 60}")
    
    conn.close()
    
    status = "partial (shutdown)" if SHUTDOWN_REQUESTED else "complete"
    logging.info(f"Done: {exported} listings, {cities_completed} cities, {status}")
    print(f"\n✅ Done: {datetime.utcnow().isoformat()} [{status}]")

if __name__ == '__main__':
    main()
