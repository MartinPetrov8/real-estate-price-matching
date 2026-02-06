#!/usr/bin/env python3
"""
Market Comparison Scraper - OLX.bg (Fixed)
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

OLX_URLS = {
    'София': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-sofia/',
    'Варна': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-varna/',
    'Бургас': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-burgas/',
    'Пловдив': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-plovdiv/',
    'Несебър': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-nesebar/',
    'Банско': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-bansko/',
    'Свети Влас': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-sveti-vlas/',
    'Пазарджик': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/q-pazardzhik/',
}

def fetch_olx_listings(city, url, max_pages=5):
    """Fetch apartment listings from OLX.bg"""
    listings = []
    
    for page in range(1, max_pages + 1):
        page_url = f"{url}?page={page}" if page > 1 else url
        
        try:
            req = urllib.request.Request(page_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                
                # Find all districts for this city
                districts = re.findall(rf'гр\.\s*{city},\s*([^<\-]+)', html)
                
                # Find all size-price pairs
                size_prices = re.findall(r'(\d+)\s*кв\.м\s*-\s*([\d\.]+)', html)
                
                # Match them up (they appear in order)
                for i, (size_str, price_sqm_str) in enumerate(size_prices):
                    try:
                        size = float(size_str)
                        price_sqm = float(price_sqm_str)
                        total_price = size * price_sqm
                        
                        district = districts[i].strip() if i < len(districts) else 'Unknown'
                        
                        listings.append({
                            'city': city,
                            'district': district,
                            'size_sqm': size,
                            'price_per_sqm': price_sqm,
                            'total_price_eur': total_price,
                            'source': 'olx.bg'
                        })
                    except:
                        pass
                        
        except Exception as e:
            print(f"  Error page {page}: {e}")
            break
    
    return listings

def init_market_db():
    """Initialize market DB"""
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(MARKET_DB)
    conn.execute("DROP TABLE IF EXISTS market_listings")
    conn.execute("""
        CREATE TABLE market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT, district TEXT, size_sqm REAL,
            price_per_sqm REAL, total_price_eur REAL, source TEXT,
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX idx_market_city ON market_listings(city)")
    conn.commit()
    return conn

def scrape_market():
    """Scrape market data"""
    conn = init_market_db()
    
    print(f"=== Market Scraper - {datetime.utcnow().isoformat()} ===\n")
    
    total = 0
    
    for city, url in OLX_URLS.items():
        print(f"Scraping {city}...", end=" ")
        sys.stdout.flush()
        
        listings = fetch_olx_listings(city, url, max_pages=5)
        
        for l in listings:
            conn.execute("""
                INSERT INTO market_listings (city, district, size_sqm, price_per_sqm, total_price_eur, source)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (l['city'], l['district'], l['size_sqm'], l['price_per_sqm'], l['total_price_eur'], l['source']))
        
        print(f"{len(listings)} listings")
        total += len(listings)
        conn.commit()
    
    print(f"\n{'='*50}")
    print(f"TOTAL: {total} market listings")
    print(f"{'='*50}")
    
    cursor = conn.cursor()
    print("\nMarket stats by city:")
    for row in cursor.execute("""
        SELECT city, COUNT(*), ROUND(AVG(price_per_sqm), 0), ROUND(MIN(price_per_sqm), 0), ROUND(MAX(price_per_sqm), 0)
        FROM market_listings GROUP BY city ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]:15}: {row[1]:3} listings, avg €{row[2]}/m² (€{row[3]}-{row[4]})")
    
    conn.close()
    print(f"\n✓ Saved to {MARKET_DB}")

def calculate_comparisons():
    """Compare auctions to market with neighborhood-aware price caps"""
    if not os.path.exists(MARKET_DB):
        print("Market DB not found. Run scrape first.")
        return
    
    # Import neighborhood caps
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from neighborhood_caps import get_price_cap
    
    auction_conn = sqlite3.connect(DB_PATH)
    market_conn = sqlite3.connect(MARKET_DB)
    
    auction_conn.execute("DROP TABLE IF EXISTS comparisons")
    auction_conn.execute("""
        CREATE TABLE comparisons (
            auction_id TEXT PRIMARY KEY, city TEXT, auction_price REAL,
            auction_size REAL, auction_price_sqm REAL, market_median_sqm REAL,
            market_mean_sqm REAL, market_count INTEGER, deviation_pct REAL,
            deviation_mean REAL, bargain_score INTEGER, price_capped INTEGER
        )
    """)
    
    print("\n=== Price Comparisons (with neighborhood caps) ===\n")
    
    auctions = auction_conn.execute("""
        SELECT id, city, address, price_eur, size_sqm FROM auctions 
        WHERE property_type = 'апартамент' AND size_sqm > 0 AND price_eur > 0
    """).fetchall()
    
    compared = 0
    bargains = []
    
    for auction in auctions:
        auction_id, city, address, price, size = auction
        city_clean = city.replace('гр. ', '').replace('с. ', '').strip() if city else ''
        
        # Get market data for similar sizes (±15 sqm)
        market = market_conn.execute("""
            SELECT price_per_sqm FROM market_listings 
            WHERE city = ? AND size_sqm BETWEEN ? AND ?
        """, (city_clean, size - 15, size + 15)).fetchall()
        
        # Get neighborhood price cap
        caps = get_price_cap(city or '', address or '')
        price_capped = 0
        
        if market:
            prices = sorted([r[0] for r in market])
            raw_median = prices[len(prices) // 2]
            raw_mean = sum(prices) / len(prices)
            
            # Apply cap if raw median is unrealistic
            if raw_median > caps['max']:
                median = caps['median']
                price_capped = 1
            elif raw_median < caps['min']:
                median = caps['median']
                price_capped = 1
            else:
                median = raw_median
            
            mean = min(raw_mean, caps['max'])  # Cap mean too
            
            auction_sqm = price / size
            dev_median = ((auction_sqm - median) / median) * 100
            dev_mean = ((auction_sqm - mean) / mean) * 100
            score = max(0, min(100, int(-dev_median)))
            
            auction_conn.execute("""
                INSERT OR REPLACE INTO comparisons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (auction_id, city, price, size, auction_sqm, median, mean, len(prices), dev_median, dev_mean, score, price_capped))
            
            compared += 1
            
            if score > 15:
                bargains.append((city, price, size, auction_sqm, median, dev_median, score, auction_id))
        else:
            # No market data - use neighborhood cap estimates
            auction_sqm = price / size
            median = caps['median']
            mean = caps['median']
            dev_median = ((auction_sqm - median) / median) * 100
            score = max(0, min(100, int(-dev_median)))
            
            auction_conn.execute("""
                INSERT OR REPLACE INTO comparisons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (auction_id, city, price, size, auction_sqm, median, mean, 0, dev_median, dev_median, score, 1))
            
            compared += 1
            
            if score > 15:
                bargains.append((city, price, size, auction_sqm, median, dev_median, score, auction_id))
    
    auction_conn.commit()
    
    print(f"Compared: {compared} auctions with market data\n")
    
    if bargains:
        print("🔥 BARGAINS (>15% below market):\n")
        bargains.sort(key=lambda x: -x[6])  # Sort by score
        
        for b in bargains[:15]:
            city, price, size, asqm, msqm, dev, score, aid = b
            print(f"  {city}: €{price:,.0f} ({size:.0f}m²)")
            print(f"    Auction: €{asqm:.0f}/m² vs Market: €{msqm:.0f}/m² ({dev:+.1f}%)")
            print(f"    Bargain Score: {score}/100")
            print(f"    URL: https://sales.bcpea.org/properties/{aid}")
            print()
    
    auction_conn.close()
    market_conn.close()

if __name__ == '__main__':
    scrape_market()
    calculate_comparisons()
