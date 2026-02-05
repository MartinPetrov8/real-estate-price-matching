#!/usr/bin/env python3
"""
Real Estate Scraper Service
Production-grade scraper for Bulgarian property sites
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

# Database setup
DB_PATH = Path(__file__).parent.parent / 'data' / 'properties.db'

def init_db():
    """Initialize SQLite database"""
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
        
        CREATE TABLE IF NOT EXISTS scrape_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            city TEXT,
            property_type TEXT,
            pages_scraped INTEGER,
            listings_found INTEGER,
            new_listings INTEGER,
            updated_listings INTEGER,
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_listings_city ON listings(city);
        CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price_eur);
        CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source);
    ''')
    conn.commit()
    return conn

def parse_imot_listing(text_block, url=None):
    """Parse listing data from imot.bg snapshot text"""
    listing = {
        'source': 'imot.bg',
        'url': url,
        'scraped_at': datetime.utcnow().isoformat()
    }
    
    # Extract external ID from URL
    if url:
        id_match = re.search(r'obiava-([^\-/]+)', url)
        if id_match:
            listing['external_id'] = id_match.group(1)
    
    # Extract price in EUR
    price_match = re.search(r'([\d\s]+)\s*€', text_block)
    if price_match:
        price_str = price_match.group(1).replace(' ', '').replace('\xa0', '')
        try:
            listing['price_eur'] = int(price_str)
        except ValueError:
            pass
    
    # Extract price in BGN
    bgn_match = re.search(r'([\d\s,.]+)\s*лв\.', text_block)
    if bgn_match:
        bgn_str = bgn_match.group(1).replace(' ', '').replace(',', '').replace('.', '')
        try:
            # Handle decimal separator
            listing['price_bgn'] = int(float(bgn_str) / 100) if len(bgn_str) > 6 else int(bgn_str)
        except ValueError:
            pass
    
    # Extract size
    size_match = re.search(r'(\d+)\s*кв\.?м', text_block)
    if size_match:
        listing['size_sqm'] = int(size_match.group(1))
    
    # Calculate price per sqm
    if listing.get('price_eur') and listing.get('size_sqm'):
        listing['price_per_sqm'] = round(listing['price_eur'] / listing['size_sqm'], 2)
    
    # Extract floor
    floor_match = re.search(r'(\d+)-[тиоейрв]+\s*ет\.?\s*от\s*(\d+)', text_block)
    if floor_match:
        listing['floor'] = f"{floor_match.group(1)}/{floor_match.group(2)}"
    
    # Extract year
    year_match = re.search(r'(\d{4})\s*г\.', text_block)
    if year_match:
        listing['year_built'] = year_match.group(1)
    
    # Extract heating
    if 'ТЕЦ' in text_block:
        listing['heating'] = 'ТЕЦ'
    elif 'Газ' in text_block:
        listing['heating'] = 'Газ'
    elif 'Лок.отопл' in text_block:
        listing['heating'] = 'Локално'
    
    # Extract phone
    phone_match = re.search(r'тел\.?:?\s*([\d\s]+)', text_block)
    if phone_match:
        listing['phone'] = phone_match.group(1).strip()
    
    return listing

def save_listing(conn, listing):
    """Save or update listing in database"""
    cursor = conn.cursor()
    
    # Check if listing exists
    cursor.execute('''
        SELECT id, price_eur FROM listings 
        WHERE source = ? AND external_id = ?
    ''', (listing.get('source'), listing.get('external_id')))
    
    existing = cursor.fetchone()
    
    if existing:
        listing_id, old_price = existing
        new_price = listing.get('price_eur')
        
        # Update listing
        cursor.execute('''
            UPDATE listings SET
                price_eur = ?,
                price_bgn = ?,
                size_sqm = ?,
                price_per_sqm = ?,
                scraped_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (
            listing.get('price_eur'),
            listing.get('price_bgn'),
            listing.get('size_sqm'),
            listing.get('price_per_sqm'),
            listing_id
        ))
        
        # Record price change if different
        if new_price and old_price and new_price != old_price:
            cursor.execute('''
                INSERT INTO price_history (listing_id, price_eur)
                VALUES (?, ?)
            ''', (listing_id, new_price))
        
        return 'updated'
    else:
        # Insert new listing
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
        
        return 'new'

def get_market_stats(conn, city=None, property_type=None):
    """Get market statistics"""
    query = '''
        SELECT 
            COUNT(*) as total,
            AVG(price_eur) as avg_price,
            AVG(price_per_sqm) as avg_price_sqm,
            MIN(price_eur) as min_price,
            MAX(price_eur) as max_price,
            AVG(size_sqm) as avg_size
        FROM listings
        WHERE price_eur IS NOT NULL
    '''
    params = []
    
    if city:
        query += ' AND city = ?'
        params.append(city)
    if property_type:
        query += ' AND property_type = ?'
        params.append(property_type)
    
    cursor = conn.cursor()
    cursor.execute(query, params)
    row = cursor.fetchone()
    
    return {
        'total': row[0],
        'avg_price': round(row[1], 2) if row[1] else 0,
        'avg_price_sqm': round(row[2], 2) if row[2] else 0,
        'min_price': row[3],
        'max_price': row[4],
        'avg_size': round(row[5], 1) if row[5] else 0
    }

def export_to_json(conn, output_path):
    """Export all listings to JSON"""
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM listings ORDER BY scraped_at DESC')
    columns = [desc[0] for desc in cursor.description]
    
    listings = []
    for row in cursor.fetchall():
        listings.append(dict(zip(columns, row)))
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'exported_at': datetime.utcnow().isoformat(),
            'total': len(listings),
            'listings': listings
        }, f, ensure_ascii=False, indent=2)
    
    return len(listings)

if __name__ == '__main__':
    conn = init_db()
    print(f"Database initialized at {DB_PATH}")
    
    # Test with sample data
    test_listing = {
        'source': 'imot.bg',
        'external_id': 'test123',
        'city': 'София',
        'district': 'Банишора',
        'price_eur': 125000,
        'size_sqm': 50,
        'price_per_sqm': 2500
    }
    
    result = save_listing(conn, test_listing)
    conn.commit()
    print(f"Test listing: {result}")
    
    stats = get_market_stats(conn)
    print(f"Stats: {stats}")
