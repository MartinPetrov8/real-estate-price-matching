#!/usr/bin/env python3
"""
Simple market data collector using web_fetch results
"""

import re
import sqlite3
from datetime import datetime
import os

DB_PATH = "data/market_listings.db"

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


def olx_from_text(text):
    """Parse OLX text"""
    listings = []
    # Match: гр. София, District - text - size кв.м - price
    pattern = r'гр\.\s*([^,]+),\s*([^-\n]+).*?(\d+)\s*кв\.м\s*-\s*([\d\.]+)'
    matches = re.findall(pattern, text)
    seen = set()
    for city, district, size_str, price_sqm_str in matches:
        key = (city, size_str, price_sqm_str)
        if key in seen:
            continue
        seen.add(key)
        try:
            size = float(size_str)
            price_per_sqm = float(price_sqm_str)
            total = size * price_per_sqm
            if size >= 30 and price_per_sqm >= 300:
                listings.append({
                    'city': city.strip(), 'district': district.strip(),
                    'size_sqm': size, 'price_eur': round(total, 2),
                    'price_per_sqm': round(price_per_sqm, 2), 'source': 'olx.bg'
                })
        except:
            continue
    return listings


def alo_from_text(text):
    """Parse alo.bg text"""
    listings = []
    # Split by Цена:
    parts = text.split('Цена:')[1:]
    for part in parts:
        # Price
        pm = re.search(r'([\d\s]+)\s*€', part)
        if not pm:
            continue
        try:
            price = float(pm.group(1).replace(' ', ''))
        except:
            continue
        
        # Price per sqm
        ppsm = re.search(r'за кв\.м:\s*([\d\.]+)\s*€/кв\.м', part)
        price_per_sqm = float(ppsm.group(1)) if ppsm else None
        
        # Size
        sm = re.search(r'Квадратура:(\d+)\s*кв\.м', part)
        if not sm:
            continue
        try:
            size = float(sm.group(1))
        except:
            continue
        
        # City from "в City"
        cm = re.search(r'в\s+(София|Пловдив|Варна|Бургас)', part)
        city = cm.group(1) if cm else None
        
        if size > 30 and price > 5000:
            if not price_per_sqm:
                price_per_sqm = round(price / size, 2)
            listings.append({
                'city': city, 'size_sqm': size, 'price_eur': price,
                'price_per_sqm': price_per_sqm, 'source': 'alo.bg'
            })
    return listings


def homes_from_text(text, default_city=None):
    """Parse homes.bg text"""
    listings = []
    # Look for: room_type, size, price, price_per_sqm patterns
    blocks = re.findall(r'(\w+стаен),\s*(\d+)m².*?([\d,]+)\s*EUR\s*([\d,]+)EUR/m²', text, re.DOTALL)
    for room_type, size_str, price_str, price_sqm_str in blocks:
        try:
            size = float(size_str)
            price = float(price_str.replace(',', ''))
            price_per_sqm = float(price_sqm_str.replace(',', ''))
            if size > 30 and price > 5000:
                listings.append({
                    'city': default_city, 'size_sqm': size, 'price_eur': price,
                    'price_per_sqm': round(price_per_sqm, 2), 'source': 'homes.bg'
                })
        except:
            continue
    return listings


def imot_from_text(text):
    """Parse imot.bg text"""
    listings = []
    # Find Цена: price euro ... size кв.м
    prices = list(re.finditer(r'Цена:\s*([\d\s]+)\s*euro', text, re.IGNORECASE))
    for pm in prices:
        try:
            price = float(pm.group(1).replace(' ', ''))
        except:
            continue
        nearby = text[pm.end():pm.end()+300]
        sm = re.search(r'(\d+)\s*кв\.м', nearby)
        if sm:
            try:
                size = float(sm.group(1))
                if price > 5000 and size > 30:
                    listings.append({
                        'city': None, 'size_sqm': size, 'price_eur': price,
                        'price_per_sqm': round(price / size, 2), 'source': 'imot.bg'
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
    
    print(f"\n{'='*60}")

