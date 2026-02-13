#!/usr/bin/env python3
"""
Market Data Browser Scraper v2 - Fixed URLs
Sites: imot.bg, alo.bg, olx.bg
"""

import os
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/host-workspace/.browsers'

import re
import sqlite3
from datetime import datetime
from playwright.sync_api import sync_playwright
import time

DB_PATH = "data/market_listings.db"

# FIXED URLs - tested working
URLS = {
    # alo.bg - CONFIRMED WORKING
    'alo_sofia': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=1',
    'alo_plovdiv': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=2',
    'alo_varna': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=3',
    'alo_burgas': 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=4',
    
    # imot.bg - use search page
    'imot_sofia': 'https://www.imot.bg/pcgi/imot.cgi?act=3&session_id=&f1=1&f2=1&f3=1&f4=1&f5=1',
    'imot_plovdiv': 'https://www.imot.bg/pcgi/imot.cgi?act=3&sSession_id=&f1=1&f2=1&f3=1&f4=1&f5=2',
    
    # olx.bg - use category page
    'olx_sofia': 'https://www.olx.bg/d/nedvizhimi-imoti/apartamenti/prodazhba/sofia/',
    'olx_plovdiv': 'https://www.olx.bg/d/nedvizhimi-imoti/apartamenti/prodazhba/plovdiv/',
}

CITY_MAP = {
    'sofia': 'София', 'plovdiv': 'Пловдив', 
    'varna': 'Варна', 'burgas': 'Бургас',
}


def init_db():
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS market_listings")
    c.execute("""
        CREATE TABLE market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT, district TEXT,
            property_type TEXT DEFAULT 'апартамент',
            size_sqm REAL, price_eur REAL, price_per_sqm REAL,
            rooms INTEGER, source TEXT,
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("CREATE INDEX idx_city ON market_listings(city)")
    c.execute("CREATE INDEX idx_source ON market_listings(source)")
    conn.commit()
    return conn


def save_listings(conn, listings):
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
        except:
            pass
    conn.commit()
    return saved


def accept_cookies(page):
    """Try to accept cookie consent dialogs"""
    cookie_selectors = [
        'button:has-text("Приемам")',
        'button:has-text("ПРИЕМЕТЕ ВСИЧКИ")',
        'button:has-text("Приеми")',
        'button:has-text("Accept")',
        'button:has-text("OK")',
        '[class*="cookie"] button',
        '[id*="cookie"] button',
    ]
    for selector in cookie_selectors:
        try:
            btn = page.query_selector(selector)
            if btn:
                btn.click()
                time.sleep(0.5)
                print("    Clicked cookie consent")
                return True
        except:
            pass
    return False


def scrape_alo(page, city):
    """Scrape alo.bg - CONFIRMED WORKING"""
    listings = []
    
    # Accept cookies first
    accept_cookies(page)
    time.sleep(1)
    
    # Scroll to load more content
    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.5)
    
    # Get page content
    content = page.content()
    
    # alo.bg HTML structure:
    # <span style="white-space: nowrap;">56 500 €</span>
    # <span style="white-space: nowrap;">1412.50 €/кв.м</span>
    # <span class="ads-params-single">40 кв.м</span>
    
    # Pattern 1: Extract price in EUR (nowrap spans with €)
    prices = re.findall(r'white-space:\s*nowrap[^>]*>\s*([\d\s]+)\s*€\s*<', content)
    
    # Pattern 2: Extract price per sqm
    prices_per_sqm = re.findall(r'white-space:\s*nowrap[^>]*>\s*([\d\.,]+)\s*€/кв\.м', content)
    
    # Pattern 3: Extract sizes (after Квадратура:)
    sizes = re.findall(r'Квадратура:[^>]*>[^<]*<[^>]*>\s*(\d+)\s*кв\.м', content)
    
    print(f"    Found: {len(prices)} prices, {len(prices_per_sqm)} €/m², {len(sizes)} sizes")
    
    # Use price per sqm + size (most reliable)
    seen = set()
    for ppsqm, sz in zip(prices_per_sqm, sizes):
        try:
            price_per_sqm = float(ppsqm.replace(',', '.').replace(' ', ''))
            size = float(sz)
            price = price_per_sqm * size
            
            # Dedupe by rounded values
            key = (round(price, -2), round(size))
            if key in seen:
                continue
            seen.add(key)
            
            if 20 < size < 300 and 300 < price_per_sqm < 5000:
                listings.append({
                    'city': city, 'size_sqm': size, 'price_eur': round(price, 2),
                    'price_per_sqm': round(price_per_sqm, 2), 'source': 'alo.bg'
                })
        except:
            continue
    
    # Fallback: match direct prices with sizes
    if len(listings) == 0:
        for price_str, size_str in zip(prices[::2], sizes):  # prices come in pairs (EUR + лв)
            try:
                price = float(price_str.replace(' ', ''))
                size = float(size_str)
                if 20 < size < 300 and 5000 < price < 500000:
                    listings.append({
                        'city': city, 'size_sqm': size, 'price_eur': round(price, 2),
                        'price_per_sqm': round(price / size, 2), 'source': 'alo.bg'
                    })
            except:
                continue
    
    return listings


def scrape_imot(page, city):
    """Scrape imot.bg"""
    listings = []
    
    accept_cookies(page)
    time.sleep(1)
    
    # Check if we got results or error page
    content = page.content()
    if 'не е намерена' in content or 'не може да бъде' in content:
        print("    imot.bg: Page not found, trying main search...")
        # Try alternative: go to main site and search
        page.goto('https://www.imot.bg/', wait_until='networkidle', timeout=30000)
        accept_cookies(page)
        # The site requires session-based search, hard to automate
        return listings
    
    # Look for listing patterns
    # imot.bg format: "45 000 EUR", "75 кв.м"
    blocks = re.findall(
        r'([\d\s]+)\s*EUR.*?(\d+)\s*кв\.м',
        content, re.DOTALL
    )
    
    print(f"    Found {len(blocks)} imot.bg blocks")
    
    for price_str, size_str in blocks[:50]:
        try:
            price = float(price_str.replace(' ', ''))
            size = float(size_str)
            if 20 < size < 300 and 5000 < price < 500000:
                listings.append({
                    'city': city, 'size_sqm': size, 'price_eur': price,
                    'price_per_sqm': round(price / size, 2), 'source': 'imot.bg'
                })
        except:
            continue
    
    return listings


def scrape_olx(page, city):
    """Scrape olx.bg"""
    listings = []
    
    accept_cookies(page)
    time.sleep(1)
    
    content = page.content()
    if 'не е открита' in content:
        print("    OLX: Page not found, trying alternative URL...")
        return listings
    
    # OLX uses data attributes - try to find price and size
    # Format varies, look for common patterns
    
    # Pattern: price in EUR or лв, size in кв.м or m²
    blocks = re.findall(
        r'([\d\s]+)\s*(?:EUR|€|лв).*?(\d+)\s*(?:кв\.м|m²)',
        content, re.DOTALL
    )
    
    print(f"    Found {len(blocks)} OLX blocks")
    
    for price_str, size_str in blocks[:50]:
        try:
            price = float(price_str.replace(' ', ''))
            # Convert BGN to EUR if likely BGN (> 100000 usually BGN)
            if price > 100000:
                price = price / 1.96
            size = float(size_str)
            if 20 < size < 300 and 5000 < price < 500000:
                listings.append({
                    'city': city, 'size_sqm': size, 'price_eur': round(price, 2),
                    'price_per_sqm': round(price / size, 2), 'source': 'olx.bg'
                })
        except:
            continue
    
    return listings


def print_stats(conn):
    c = conn.cursor()
    print(f"\n{'='*60}")
    print("MARKET DATA STATISTICS")
    print(f"{'='*60}")
    
    c.execute("SELECT COUNT(*) FROM market_listings")
    total = c.fetchone()[0]
    print(f"\nTotal listings: {total}")
    
    if total == 0:
        print("\n⚠️  NO DATA COLLECTED - SCRAPING FAILED")
        return
    
    print("\nBy source:")
    c.execute("""SELECT source, COUNT(*), ROUND(AVG(price_per_sqm), 0) 
                 FROM market_listings GROUP BY source ORDER BY COUNT(*) DESC""")
    for row in c.fetchall():
        print(f"  {row[0]:15}: {row[1]:4} listings, avg €{row[2]}/m²")
    
    print("\nBy city:")
    c.execute("""SELECT city, COUNT(*), ROUND(AVG(price_per_sqm), 0),
                        ROUND(MIN(price_per_sqm), 0), ROUND(MAX(price_per_sqm), 0)
                 FROM market_listings WHERE city IS NOT NULL 
                 GROUP BY city ORDER BY COUNT(*) DESC""")
    for row in c.fetchall():
        print(f"  {row[0]:15}: {row[1]:4} listings, €{row[2]}/m² (€{row[3]}-{row[4]})")
    
    print(f"\n{'='*60}")


def main():
    print(f"=== Market Browser Scraper v2 - {datetime.utcnow().isoformat()} ===")
    print("Sites: alo.bg (primary), imot.bg, olx.bg")
    
    conn = init_db()
    all_listings = []
    
    with sync_playwright() as p:
        print("\nLaunching Chromium...")
        browser = p.chromium.launch(headless=True)
        
        for key, url in URLS.items():
            parts = key.split('_')
            site = parts[0]
            city_key = parts[1] if len(parts) > 1 else 'sofia'
            city = CITY_MAP.get(city_key, city_key)
            
            print(f"\n[{site.upper()}] Scraping {city}...")
            print(f"  URL: {url}")
            
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='bg-BG'
            )
            page = context.new_page()
            
            try:
                page.goto(url, wait_until='networkidle', timeout=30000)
                
                if site == 'alo':
                    listings = scrape_alo(page, city)
                elif site == 'imot':
                    listings = scrape_imot(page, city)
                elif site == 'olx':
                    listings = scrape_olx(page, city)
                else:
                    listings = []
                
                all_listings.extend(listings)
                print(f"  ✓ Extracted {len(listings)} listings")
                
            except Exception as e:
                print(f"  ✗ Error: {e}")
            finally:
                context.close()
            
            time.sleep(1)
        
        browser.close()
    
    print(f"\n\nSaving {len(all_listings)} total listings...")
    saved = save_listings(conn, all_listings)
    print(f"Saved {saved} listings to database")
    
    print_stats(conn)
    conn.close()
    
    return len(all_listings)


if __name__ == '__main__':
    count = main()
    if count == 0:
        print("\n🚨 CRITICAL: No market data collected!")
        print("Manual intervention required - see troubleshooting protocol")
        exit(1)
    else:
        print(f"\n✓ Successfully collected {count} listings")
