#!/usr/bin/env python3
"""
Market Comparison Scraper - Multiple Sources
Uses: imot.bg, olx.bg, alo.bg (imoti.net blocked)
"""

import json
import re
import sqlite3
import urllib.request
from datetime import datetime
import os
import sys

DB_PATH = "data/auctions.db"
MARKET_DB = "data/market.db"

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def fetch_imot_bg():
    """Scrape imot.bg"""
    listings = []
    url = "https://www.imot.bg/obiavi/prodazhbi"
    
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode('windows-1251', errors='ignore')
            
            # Extract listing blocks - price and size pairs
            # Pattern: price in € followed by size in кв.м
            blocks = re.findall(r'<div class="price[^"]*">\s*<div>([\d\s]+)\s*€.*?(\d+)\s*(?:кв\.м|m²)', html, re.DOTALL)
            
            for price_str, size_str in blocks:
                try:
                    price = float(price_str.replace(' ', ''))
                    size = float(size_str)
                    if price > 5000 and size > 10:
                        listings.append({
                            'price_eur': price,
                            'size_sqm': size,
                            'price_per_sqm': price / size,
                            'source': 'imot.bg'
                        })
                except:
                    pass
            
            # Also try extracting separately and pairing
            prices = re.findall(r'<div class="price[^"]*">\s*<div>([\d\s]+)\s*€', html)
            sizes = re.findall(r'(\d+)\s*(?:кв\.м|m²)', html)
            
            # Pair prices with sizes (they appear in order)
            for i, price_str in enumerate(prices):
                if i < len(sizes):
                    try:
                        price = float(price_str.replace(' ', ''))
                        size = float(sizes[i])
                        if price > 5000 and size > 10:
                            listings.append({
                                'price_eur': price,
                                'size_sqm': size,
                                'price_per_sqm': price / size,
                                'source': 'imot.bg'
                            })
                    except:
                        pass
    except Exception as e:
        print(f"  imot.bg error: {e}")
    
    return listings

def fetch_olx_bg(city, url):
    """Scrape OLX.bg for a city"""
    listings = []
    
    for page in range(1, 6):  # 5 pages
        page_url = f"{url}?page={page}" if page > 1 else url
        
        try:
            req = urllib.request.Request(page_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read().decode('utf-8', errors='ignore')
                
                # OLX format: "85 кв.м - 1964.71"
                matches = re.findall(r'(\d+)\s*кв\.м\s*-\s*([\d\.]+)', html)
                
                for size_str, price_sqm_str in matches:
                    try:
                        size = float(size_str)
                        price_sqm = float(price_sqm_str)
                        total = size * price_sqm
                        
                        listings.append({
                            'city': city,
                            'size_sqm': size,
                            'price_per_sqm': price_sqm,
                            'price_eur': total,
                            'source': 'olx.bg'
                        })
                    except:
                        pass
        except:
            break
    
    return listings

def fetch_alo_bg():
    """Scrape alo.bg"""
    listings = []
    url = "https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=1"
    
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode('utf-8', errors='ignore')
            
            # Find prices: "150 000 €"
            prices = re.findall(r'(\d[\d\s]*\d)\s*€', html)
            
            for price_str in prices:
                try:
                    price = float(price_str.replace(' ', ''))
                    if price > 5000:
                        listings.append({
                            'price_eur': price,
                            'source': 'alo.bg'
                        })
                except:
                    pass
    except Exception as e:
        print(f"  alo.bg error: {e}")
    
    return listings

def init_market_db():
    """Initialize market DB"""
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(MARKET_DB)
    conn.execute("DROP TABLE IF EXISTS market_listings")
    conn.execute("""
        CREATE TABLE market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT, size_sqm REAL, price_per_sqm REAL,
            price_eur REAL, source TEXT,
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX idx_market_city ON market_listings(city)")
    conn.execute("CREATE INDEX idx_market_size ON market_listings(size_sqm)")
    conn.commit()
    return conn

OLX_CITIES = {
    'София': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-sofia/',
    'Варна': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-varna/',
    'Бургас': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-burgas/',
    'Пловдив': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-plovdiv/',
    'Банско': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-bansko/',
    'Несебър': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-nesebar/',
}

def scrape_all_markets():
    """Scrape all market sources"""
    conn = init_market_db()
    total = 0
    
    print(f"=== Market Scraper - {datetime.utcnow().isoformat()} ===\n")
    
    # imot.bg
    print("Scraping imot.bg...", end=" ")
    sys.stdout.flush()
    listings = fetch_imot_bg()
    for l in listings:
        conn.execute("INSERT INTO market_listings (city, size_sqm, price_per_sqm, price_eur, source) VALUES (?, ?, ?, ?, ?)",
                    (l.get('city', 'Unknown'), l.get('size_sqm'), l.get('price_per_sqm'), l.get('price_eur'), l.get('source')))
    print(f"{len(listings)} listings")
    total += len(listings)
    conn.commit()
    
    # OLX.bg
    for city, url in OLX_CITIES.items():
        print(f"Scraping OLX.bg {city}...", end=" ")
        sys.stdout.flush()
        listings = fetch_olx_bg(city, url)
        for l in listings:
            conn.execute("INSERT INTO market_listings (city, size_sqm, price_per_sqm, price_eur, source) VALUES (?, ?, ?, ?, ?)",
                        (l.get('city'), l.get('size_sqm'), l.get('price_per_sqm'), l.get('price_eur'), l.get('source')))
        print(f"{len(listings)} listings")
        total += len(listings)
        conn.commit()
    
    # alo.bg
    print("Scraping alo.bg...", end=" ")
    sys.stdout.flush()
    listings = fetch_alo_bg()
    for l in listings:
        conn.execute("INSERT INTO market_listings (city, size_sqm, price_per_sqm, price_eur, source) VALUES (?, ?, ?, ?, ?)",
                    (l.get('city', 'Unknown'), l.get('size_sqm'), l.get('price_per_sqm'), l.get('price_eur'), l.get('source')))
    print(f"{len(listings)} listings")
    total += len(listings)
    conn.commit()
    
    # Stats
    print(f"\n{'='*50}")
    print(f"TOTAL MARKET LISTINGS: {total}")
    print(f"{'='*50}")
    
    cursor = conn.cursor()
    print("\nBy source:")
    for row in cursor.execute("SELECT source, COUNT(*), ROUND(AVG(price_per_sqm), 0) FROM market_listings WHERE price_per_sqm IS NOT NULL GROUP BY source"):
        print(f"  {row[0]}: {row[1]} listings, avg €{row[2]}/m²")
    
    print("\nBy city (OLX):")
    for row in cursor.execute("SELECT city, COUNT(*), ROUND(AVG(price_per_sqm), 0) FROM market_listings WHERE city IS NOT NULL AND city != 'Unknown' GROUP BY city ORDER BY COUNT(*) DESC"):
        print(f"  {row[0]}: {row[1]} listings, avg €{row[2]}/m²")
    
    conn.close()
    print(f"\n✓ Saved to {MARKET_DB}")
    return total

def calculate_comparisons():
    """Compare auctions to market prices"""
    if not os.path.exists(MARKET_DB):
        print("Run market scrape first")
        return
    
    auction_conn = sqlite3.connect(DB_PATH)
    market_conn = sqlite3.connect(MARKET_DB)
    
    auction_conn.execute("DROP TABLE IF EXISTS comparisons")
    auction_conn.execute("""
        CREATE TABLE comparisons (
            auction_id TEXT PRIMARY KEY, city TEXT, auction_price REAL,
            auction_size REAL, auction_price_sqm REAL, market_median_sqm REAL,
            market_mean_sqm REAL, market_count INTEGER, deviation_pct REAL,
            bargain_score INTEGER
        )
    """)
    
    print("\n=== Price Comparisons ===\n")
    
    auctions = auction_conn.execute("""
        SELECT id, city, price_eur, size_sqm FROM auctions 
        WHERE property_type = 'апартамент' AND size_sqm > 0 AND price_eur > 0
    """).fetchall()
    
    compared = 0
    bargains = []
    
    for auction in auctions:
        auction_id, city, price, size = auction
        city_clean = city.replace('гр. ', '').replace('с. ', '').strip() if city else ''
        
        # Get market data (±15 sqm tolerance)
        market = market_conn.execute("""
            SELECT price_per_sqm FROM market_listings 
            WHERE (city = ? OR city IS NULL OR city = 'Unknown')
            AND size_sqm BETWEEN ? AND ?
            AND price_per_sqm IS NOT NULL
        """, (city_clean, size - 15, size + 15)).fetchall()
        
        if len(market) >= 3:  # Need at least 3 comparables
            prices = sorted([r[0] for r in market])
            median = prices[len(prices) // 2]
            mean = sum(prices) / len(prices)
            
            auction_sqm = price / size
            deviation = ((auction_sqm - median) / median) * 100
            score = max(0, min(100, int(-deviation)))
            
            auction_conn.execute("""
                INSERT OR REPLACE INTO comparisons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (auction_id, city, price, size, auction_sqm, median, mean, len(prices), deviation, score))
            
            compared += 1
            
            if score > 15:
                bargains.append((city, price, size, auction_sqm, median, deviation, score, auction_id))
    
    auction_conn.commit()
    
    print(f"Compared: {compared} auctions\n")
    
    if bargains:
        print("🔥 TOP BARGAINS (>15% below market):\n")
        bargains.sort(key=lambda x: -x[6])
        
        for b in bargains[:10]:
            city, price, size, asqm, msqm, dev, score, aid = b
            print(f"  {city}: €{price:,.0f} ({size:.0f}m²)")
            print(f"    Auction: €{asqm:.0f}/m² vs Market: €{msqm:.0f}/m² ({dev:+.1f}%)")
            print(f"    Score: {score}/100 | https://sales.bcpea.org/properties/{aid}\n")
    
    auction_conn.close()
    market_conn.close()

if __name__ == '__main__':
    scrape_all_markets()
    calculate_comparisons()
