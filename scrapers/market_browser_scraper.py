#!/usr/bin/env python3
"""
Market Data Browser Scraper - Uses Playwright/Chromium
Scrapes: imot.bg, alo.bg, olx.bg
"""

import os
import re
import sqlite3
import json
from datetime import datetime

# Set browser path before importing playwright
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/host-workspace/.browsers'

from playwright.sync_api import sync_playwright

DB_PATH = "data/market_listings.db"

# Search URLs for apartments in major cities
URLS = {
    'imot_sofia': 'https://www.imot.bg/pcgi/imot.cgi?act=3&session_id=&f1=1&f2=1&f3=1&f4=1&f5=1',
    'imot_plovdiv': 'https://www.imot.bg/pcgi/imot.cgi?act=3&session_id=&f1=1&f2=1&f3=1&f4=1&f5=2',
    'imot_varna': 'https://www.imot.bg/pcgi/imot.cgi?act=3&session_id=&f1=1&f2=1&f3=1&f4=1&f5=3',
    'imot_burgas': 'https://www.imot.bg/pcgi/imot.cgi?act=3&session_id=&f1=1&f2=1&f3=1&f4=1&f5=4',
    'olx_sofia': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/sofia/',
    'olx_plovdiv': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/plovdiv/',
    'olx_varna': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/varna/',
    'olx_burgas': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/burgas/',
    'alo_sofia': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=1',
    'alo_plovdiv': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=2',
    'alo_varna': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=3',
    'alo_burgas': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=4',
}

CITY_MAP = {
    'sofia': 'София',
    'plovdiv': 'Пловдив', 
    'varna': 'Варна',
    'burgas': 'Бургас',
}


def init_db():
    """Initialize market listings database"""
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS market_listings")
    c.execute("""
        CREATE TABLE market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT,
            district TEXT,
            property_type TEXT DEFAULT 'апартамент',
            size_sqm REAL,
            price_eur REAL,
            price_per_sqm REAL,
            rooms INTEGER,
            source TEXT,
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("CREATE INDEX idx_city ON market_listings(city)")
    c.execute("CREATE INDEX idx_source ON market_listings(source)")
    conn.commit()
    return conn


def save_listings(conn, listings):
    """Save listings to database"""
    c = conn.cursor()
    saved = 0
    for l in listings:
        try:
            c.execute("""
                INSERT INTO market_listings (city, district, size_sqm, price_eur, price_per_sqm, source)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (l.get('city'), l.get('district'), l.get('size_sqm'),
                  l.get('price_eur'), l.get('price_per_sqm'), l.get('source')))
            saved += 1
        except Exception as e:
            print(f"  Error saving listing: {e}")
    conn.commit()
    return saved


def parse_imot(page, city):
    """Parse imot.bg listings from page"""
    listings = []
    try:
        # Wait for listings to load
        page.wait_for_selector('.lnk2, .lnk1', timeout=10000)
        
        # Get all listing links
        items = page.query_selector_all('.lnk2, .lnk1')
        print(f"  Found {len(items)} imot.bg listing elements")
        
        # Extract from each visible listing
        content = page.content()
        
        # Pattern: price in EUR, size in sqm
        # Look for price patterns like "45 000 EUR" or "€45000"
        price_patterns = re.findall(r'([\d\s]+)\s*(?:EUR|€|euro)', content, re.IGNORECASE)
        size_patterns = re.findall(r'(\d+)\s*(?:кв\.?\s*м|m²|кв\.м)', content)
        
        # Also look for combined patterns in listing blocks
        blocks = re.findall(r'(\d+)\s*кв\.м.*?([\d\s]+)\s*EUR', content, re.DOTALL)
        
        for size_str, price_str in blocks[:30]:  # Limit to 30
            try:
                size = float(size_str)
                price = float(price_str.replace(' ', ''))
                if 20 < size < 300 and 5000 < price < 500000:
                    listings.append({
                        'city': city,
                        'size_sqm': size,
                        'price_eur': price,
                        'price_per_sqm': round(price / size, 2),
                        'source': 'imot.bg'
                    })
            except:
                continue
                
    except Exception as e:
        print(f"  imot.bg parse error: {e}")
    
    return listings


def parse_olx(page, city):
    """Parse OLX listings from page"""
    listings = []
    try:
        # Wait for listings
        page.wait_for_selector('[data-cy="l-card"]', timeout=10000)
        
        # Get listing cards
        cards = page.query_selector_all('[data-cy="l-card"]')
        print(f"  Found {len(cards)} OLX listing cards")
        
        for card in cards[:30]:  # Limit to 30
            try:
                text = card.inner_text()
                
                # Price: look for EUR or лв
                price_match = re.search(r'([\d\s]+)\s*(?:EUR|€|лв)', text)
                if not price_match:
                    continue
                price_str = price_match.group(1).replace(' ', '')
                price = float(price_str)
                
                # Convert BGN to EUR if needed (лв)
                if 'лв' in text and 'EUR' not in text:
                    price = price / 1.96  # Approximate BGN to EUR
                
                # Size
                size_match = re.search(r'(\d+)\s*(?:кв\.?\s*м|m²)', text)
                if not size_match:
                    continue
                size = float(size_match.group(1))
                
                if 20 < size < 300 and 5000 < price < 500000:
                    listings.append({
                        'city': city,
                        'size_sqm': size,
                        'price_eur': round(price, 2),
                        'price_per_sqm': round(price / size, 2),
                        'source': 'olx.bg'
                    })
            except Exception as e:
                continue
                
    except Exception as e:
        print(f"  OLX parse error: {e}")
    
    return listings


def parse_alo(page, city):
    """Parse alo.bg listings from page"""
    listings = []
    try:
        # Wait for listings
        page.wait_for_selector('.ads-list-item, .listing-item', timeout=10000)
        
        content = page.content()
        
        # Look for price and size patterns
        # alo.bg format varies, try multiple patterns
        
        # Pattern 1: "Цена: X €" and "Квадратура: Y кв.м"
        prices = re.findall(r'Цена[:\s]*([\d\s]+)\s*€', content)
        sizes = re.findall(r'Квадратура[:\s]*(\d+)\s*кв', content)
        
        # Pattern 2: Combined in listing text
        blocks = re.findall(r'(\d+)\s*кв\.м.*?([\d\s]+)\s*€', content, re.DOTALL)
        
        for size_str, price_str in blocks[:30]:
            try:
                size = float(size_str)
                price = float(price_str.replace(' ', ''))
                if 20 < size < 300 and 5000 < price < 500000:
                    listings.append({
                        'city': city,
                        'size_sqm': size,
                        'price_eur': price,
                        'price_per_sqm': round(price / size, 2),
                        'source': 'alo.bg'
                    })
            except:
                continue
                
    except Exception as e:
        print(f"  alo.bg parse error: {e}")
    
    return listings


def scrape_site(browser, url, site_type, city):
    """Scrape a single site URL"""
    print(f"\nScraping {site_type} for {city}...")
    print(f"  URL: {url}")
    
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        locale='bg-BG'
    )
    
    page = context.new_page()
    listings = []
    
    try:
        page.goto(url, wait_until='networkidle', timeout=30000)
        
        # Parse based on site
        if 'imot' in site_type:
            listings = parse_imot(page, city)
        elif 'olx' in site_type:
            listings = parse_olx(page, city)
        elif 'alo' in site_type:
            listings = parse_alo(page, city)
            
        print(f"  Extracted {len(listings)} listings")
        
    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        context.close()
    
    return listings


def print_stats(conn):
    """Print database statistics"""
    c = conn.cursor()
    print(f"\n{'='*60}")
    print("MARKET DATA STATISTICS")
    print(f"{'='*60}")
    
    c.execute("SELECT COUNT(*) FROM market_listings")
    total = c.fetchone()[0]
    print(f"\nTotal listings: {total}")
    
    print("\nBy source:")
    c.execute("""
        SELECT source, COUNT(*), ROUND(AVG(price_per_sqm), 0) 
        FROM market_listings 
        GROUP BY source 
        ORDER BY COUNT(*) DESC
    """)
    for row in c.fetchall():
        print(f"  {row[0]:15}: {row[1]:4} listings, avg €{row[2]}/m²")
    
    print("\nBy city:")
    c.execute("""
        SELECT city, COUNT(*), ROUND(AVG(price_per_sqm), 0), 
               ROUND(MIN(price_per_sqm), 0), ROUND(MAX(price_per_sqm), 0)
        FROM market_listings 
        WHERE city IS NOT NULL 
        GROUP BY city 
        ORDER BY COUNT(*) DESC
    """)
    for row in c.fetchall():
        print(f"  {row[0]:15}: {row[1]:4} listings, avg €{row[2]}/m² (€{row[3]}-{row[4]})")
    
    print(f"\n{'='*60}")


def main():
    print(f"=== Market Browser Scraper - {datetime.utcnow().isoformat()} ===")
    print("Sites: imot.bg, olx.bg, alo.bg")
    print("Using: Playwright + Chromium headless")
    
    conn = init_db()
    all_listings = []
    
    with sync_playwright() as p:
        print("\nLaunching Chromium...")
        browser = p.chromium.launch(headless=True)
        
        for key, url in URLS.items():
            # Determine site type and city
            parts = key.split('_')
            site_type = parts[0]
            city_key = parts[1] if len(parts) > 1 else 'sofia'
            city = CITY_MAP.get(city_key, city_key)
            
            listings = scrape_site(browser, url, site_type, city)
            all_listings.extend(listings)
            
            # Small delay between requests
            import time
            time.sleep(1)
        
        browser.close()
    
    # Save all listings
    print(f"\n\nSaving {len(all_listings)} total listings...")
    saved = save_listings(conn, all_listings)
    print(f"Saved {saved} listings to database")
    
    # Print stats
    print_stats(conn)
    
    conn.close()
    
    return len(all_listings)


if __name__ == '__main__':
    count = main()
    print(f"\nDone. Total listings collected: {count}")
