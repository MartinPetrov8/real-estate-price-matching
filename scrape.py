#!/usr/bin/env python3
"""
Real Estate Scraper - Main Entry Point
Run this with browser snapshots to populate the database

Usage (from Cookie/agent):
  1. Navigate browser to imot.bg listing page
  2. Take snapshot
  3. Pass snapshot text to this script
"""

import sys
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / 'data' / 'properties.db'

def init_db():
    """Initialize database"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            external_id TEXT,
            url TEXT,
            property_type TEXT,
            city TEXT,
            district TEXT,
            price_eur INTEGER,
            price_bgn INTEGER,
            size_sqm INTEGER,
            price_per_sqm REAL,
            floor TEXT,
            year_built TEXT,
            heating TEXT,
            description TEXT,
            agency TEXT,
            phone TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source, external_id)
        );
        
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER,
            price_eur INTEGER,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (listing_id) REFERENCES listings(id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_listings_city ON listings(city);
        CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price_eur);
    ''')
    conn.commit()
    return conn

def parse_imot_bg_listing(block):
    """Parse a single listing block from imot.bg snapshot"""
    listing = {'source': 'imot.bg'}
    
    # Extract URL and ID
    url_match = re.search(r'url:\s*//www\.imot\.bg/(obiava-[^\s\]]+)', block)
    if url_match:
        listing['url'] = f"https://www.imot.bg/{url_match.group(1)}"
        id_match = re.search(r'obiava-([a-z0-9]+)', url_match.group(1))
        if id_match:
            listing['external_id'] = id_match.group(1)
    
    # Extract property type and location from link text
    type_loc_match = re.search(r'Продава\s+([^,]+),\s*град\s+([^,]+),\s*([^">\]]+)', block, re.IGNORECASE)
    if type_loc_match:
        listing['property_type'] = type_loc_match.group(1).strip()
        listing['city'] = type_loc_match.group(2).strip()
        listing['district'] = type_loc_match.group(3).strip()
    
    # Extract price EUR
    price_match = re.search(r'(\d[\d\s]*)\s*€', block)
    if price_match:
        price_str = price_match.group(1).replace(' ', '').replace('\xa0', '')
        try:
            listing['price_eur'] = int(price_str)
        except:
            pass
    
    # Extract size
    size_match = re.search(r'(\d+)\s*кв\.?м', block)
    if size_match:
        listing['size_sqm'] = int(size_match.group(1))
    
    # Calculate price per sqm
    if listing.get('price_eur') and listing.get('size_sqm'):
        listing['price_per_sqm'] = round(listing['price_eur'] / listing['size_sqm'], 2)
    
    # Extract floor
    floor_match = re.search(r'(\d+)-[а-яти]+\s*ет\.?\s*от\s*(\d+)', block, re.IGNORECASE)
    if floor_match:
        listing['floor'] = f"{floor_match.group(1)}/{floor_match.group(2)}"
    
    # Extract year
    year_match = re.search(r'(\d{4})\s*г\.', block)
    if year_match:
        listing['year_built'] = year_match.group(1)
    
    # Extract heating
    if 'ТЕЦ' in block:
        listing['heating'] = 'ТЕЦ'
    elif 'Газ' in block:
        listing['heating'] = 'Газ'
    
    # Extract phone
    phone_match = re.search(r'тел\.?:?\s*([\d\s]+)', block)
    if phone_match:
        listing['phone'] = phone_match.group(1).strip()
    
    # Extract agency
    agency_match = re.search(r'link\s+"лого\s+([^"]+)"', block)
    if not agency_match:
        agency_match = re.search(r'link\s+"([A-ZА-Я][A-ZА-Яа-я\s]+)"[^}]*url:\s*//[a-z]+\.imot\.bg', block)
    if agency_match:
        listing['agency'] = agency_match.group(1).strip()
    
    return listing

def parse_snapshot(snapshot_text, city=None, property_type=None):
    """Parse full browser snapshot and extract all listings"""
    listings = []
    
    # Split by listing blocks - each starts with 'link "status Обява Продава'
    blocks = re.split(r'(?=link\s+"status\s+Обява\s+Продава)', snapshot_text)
    
    for block in blocks:
        if 'Продава' not in block or 'obiava-' not in block:
            continue
            
        listing = parse_imot_bg_listing(block)
        
        # Override city/type if provided
        if city:
            listing['city'] = city
        if property_type:
            listing['property_type'] = property_type
            
        # Only add if we got essential data
        if listing.get('external_id') and listing.get('price_eur'):
            listings.append(listing)
    
    return listings

def save_listings(conn, listings):
    """Save listings to database"""
    cursor = conn.cursor()
    new_count = 0
    updated_count = 0
    
    for listing in listings:
        # Check if exists
        cursor.execute('''
            SELECT id, price_eur FROM listings 
            WHERE source = ? AND external_id = ?
        ''', (listing.get('source'), listing.get('external_id')))
        
        existing = cursor.fetchone()
        
        if existing:
            listing_id, old_price = existing
            new_price = listing.get('price_eur')
            
            # Update
            cursor.execute('''
                UPDATE listings SET
                    price_eur = ?, price_bgn = ?, size_sqm = ?,
                    price_per_sqm = ?, scraped_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (
                listing.get('price_eur'),
                listing.get('price_bgn'),
                listing.get('size_sqm'),
                listing.get('price_per_sqm'),
                listing_id
            ))
            
            # Track price change
            if new_price and old_price and new_price != old_price:
                cursor.execute('''
                    INSERT INTO price_history (listing_id, price_eur)
                    VALUES (?, ?)
                ''', (listing_id, new_price))
            
            updated_count += 1
        else:
            # Insert new
            cursor.execute('''
                INSERT INTO listings (
                    source, external_id, url, property_type, city, district,
                    price_eur, price_bgn, size_sqm, price_per_sqm,
                    floor, year_built, heating, description, agency, phone
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                listing.get('source'),
                listing.get('external_id'),
                listing.get('url'),
                listing.get('property_type'),
                listing.get('city'),
                listing.get('district'),
                listing.get('price_eur'),
                listing.get('price_bgn'),
                listing.get('size_sqm'),
                listing.get('price_per_sqm'),
                listing.get('floor'),
                listing.get('year_built'),
                listing.get('heating'),
                listing.get('description'),
                listing.get('agency'),
                listing.get('phone')
            ))
            new_count += 1
    
    conn.commit()
    return new_count, updated_count

def get_stats(conn):
    """Get database statistics"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT city) as cities,
            ROUND(AVG(price_eur), 0) as avg_price,
            ROUND(AVG(price_per_sqm), 0) as avg_sqm
        FROM listings
        WHERE price_eur IS NOT NULL
    ''')
    return cursor.fetchone()

if __name__ == '__main__':
    conn = init_db()
    
    if len(sys.argv) > 1:
        # Read snapshot from file
        with open(sys.argv[1], 'r') as f:
            snapshot = f.read()
        
        city = sys.argv[2] if len(sys.argv) > 2 else None
        prop_type = sys.argv[3] if len(sys.argv) > 3 else None
        
        listings = parse_snapshot(snapshot, city, prop_type)
        new, updated = save_listings(conn, listings)
        
        print(f"Parsed {len(listings)} listings")
        print(f"New: {new}, Updated: {updated}")
    else:
        # Just show stats
        stats = get_stats(conn)
        print(f"Database: {DB_PATH}")
        print(f"Total listings: {stats[0]}")
        print(f"Cities: {stats[1]}")
        print(f"Avg price: €{stats[2]}")
        print(f"Avg €/m²: €{stats[3]}")
