#!/usr/bin/env python3
"""
Fetch market data from all sources and save to SQLite
"""

import sqlite3
import re
from datetime import datetime
import os

DB_PATH = "data/market_listings.db"

# HTML samples for testing - will be populated by actual fetches
SAMPLE_OLX_SOFIA = """гр. София, Зона Б-5-3 - Обновено на 06 февруари 2026 г.46 кв.м - 3621.74
гр. София, Витоша - Обновено на 06 февруари 2026 г.112 кв.м - 2500
гр. София, Сердика - 04 февруари 2026 г.65 кв.м - 2292.31
гр. София, Зона Б-19 - Обновено на 04 февруари 2026 г.72 кв.м - 3319.44
гр. София, Център - Обновено на 04 февруари 2026 г.72 кв.м - 3319.44
гр. София, Малинова долина - Обновено на 01 февруари 2026 г.146 кв.м - 1835.62
гр. София, Малинова долина - Обновено на 05 февруари 2026 г.146 кв.м - 3390.41
гр. София, Сердика - 04 февруари 2026 г.112 кв.м - 2356.07
гр. София, Дружба 1 - Обновено на 30 януари 2026 г.62 кв.м - 3209.68
гр. София, Младост 1 - 09 януари 2026 г.51 кв.м - 3529.41"""

def init_db():
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS market_listings")
    c.execute("""
        CREATE TABLE market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, city TEXT, district TEXT,
            property_type TEXT DEFAULT 'апартамент', size_sqm REAL, price_eur REAL, 
            price_per_sqm REAL, rooms INTEGER, source TEXT, 
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("CREATE INDEX idx_city ON market_listings(city)")
    c.execute("CREATE INDEX idx_source ON market_listings(source)")
    conn.commit()
    return conn


def save_listings(conn, listings):
    c = conn.cursor()
    for l in listings:
        c.execute("""
            INSERT INTO market_listings (city, district, size_sqm, price_eur, price_per_sqm, source)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (l.get('city'), l.get('district'), l.get('size_sqm'),
              l.get('price_eur'), l.get('price_per_sqm'), l.get('source')))
    conn.commit()


def parse_olx_text(text, city_name=None):
    """Parse OLX text format: гр. City, District ... size кв.м - price_per_sqm"""
    listings = []
    # Pattern matches: гр. City, District - ... size кв.м - price
    pattern = r'гр\.\s*([^,]+),\s*([^-\n]+).*?(\d+)\s*кв\.м\s*-\s*([\d\.]+)'
    matches = re.findall(pattern, text)
    
    seen = set()
    for city, district, size_str, price_sqm_str in matches:
        key = (size_str, price_sqm_str)
        if key in seen:
            continue
        seen.add(key)
        try:
            size = float(size_str)
            price_per_sqm = float(price_sqm_str)
            total = size * price_per_sqm
            if size >= 25 and price_per_sqm >= 200:
                listings.append({
                    'city': city.strip(),
                    'district': district.strip(),
                    'size_sqm': size,
                    'price_eur': round(total, 2),
                    'price_per_sqm': round(price_per_sqm, 2),
                    'source': 'olx.bg'
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
    
    print("\nBy source:")
    c.execute("SELECT source, COUNT(*), ROUND(AVG(price_per_sqm), 0) FROM market_listings GROUP BY source ORDER BY COUNT(*) DESC")
    for row in c.fetchall():
        print(f"  {row[0]:15}: {row[1]:4} listings, avg €{row[2]}/m²")
    
    print("\nBy city:")
    c.execute("SELECT city, COUNT(*), ROUND(AVG(price_per_sqm), 0) FROM market_listings WHERE city IS NOT NULL GROUP BY city ORDER BY COUNT(*) DESC")
    for row in c.fetchall():
        print(f"  {row[0]:15}: {row[1]:4} listings, avg €{row[2]}/m²")
    
    print("\nBy district (Sofia top 10):")
    c.execute("""
        SELECT district, COUNT(*), ROUND(AVG(price_per_sqm), 0) 
        FROM market_listings 
        WHERE city = 'София' AND district IS NOT NULL 
        GROUP BY district 
        ORDER BY COUNT(*) DESC 
        LIMIT 10
    """)
    for row in c.fetchall():
        print(f"  {row[0][:25]:25}: {row[1]:3} listings, avg €{row[2]}/m²")
    
    print(f"\n{'='*60}")


def main():
    print(f"=== Market Data Parser - {datetime.utcnow().isoformat()} ===\n")
    
    conn = init_db()
    
    # For now, use sample data
    # In production, this would read from web_fetch results
    listings = parse_olx_text(SAMPLE_OLX_SOFIA, 'София')
    print(f"Parsed {len(listings)} listings from sample data")
    
    save_listings(conn, listings)
    print_stats(conn)
    conn.close()


if __name__ == '__main__':
    main()
