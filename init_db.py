#!/usr/bin/env python3
"""
Initialize SQLite database with schema and sample data from scraped sources
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = 'data/properties.db'

SCHEMA = """
-- Listings table
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT,
    title TEXT,
    city TEXT,
    district TEXT,
    address TEXT,
    property_type TEXT,
    price_eur REAL,
    price_bgn REAL,
    size_sqm REAL,
    price_per_sqm REAL,
    rooms INTEGER,
    floor INTEGER,
    total_floors INTEGER,
    year_built INTEGER,
    description TEXT,
    agency TEXT,
    phone TEXT,
    auction_date TEXT,
    auction_end TEXT,
    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Price history for tracking changes
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT NOT NULL,
    price_eur REAL,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (listing_id) REFERENCES listings(id)
);

-- Scrape runs log
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    listings_found INTEGER,
    listings_new INTEGER,
    listings_updated INTEGER,
    status TEXT,
    error TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_listings_city ON listings(city);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price_eur);
CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source);
CREATE INDEX IF NOT EXISTS idx_listings_scraped ON listings(scraped_at);
CREATE INDEX IF NOT EXISTS idx_price_history_listing ON price_history(listing_id);
"""

def init_db():
    """Initialize database with schema"""
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    print(f"✓ Database initialized at {DB_PATH}")
    return conn

def load_bcpea_data(conn):
    """Load BCPEA auction data"""
    bcpea_file = 'data/bcpea_sofia.json'
    if not os.path.exists(bcpea_file):
        print(f"✗ No BCPEA data found at {bcpea_file}")
        return 0
    
    with open(bcpea_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    cursor = conn.cursor()
    count = 0
    
    for listing in data.get('sofia_sample', []):
        listing_id = f"bcpea_{listing.get('id', count)}"
        cursor.execute("""
            INSERT OR REPLACE INTO listings 
            (id, source, url, city, address, price_eur, property_type, auction_date, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            listing_id,
            'BCPEA',
            listing.get('url'),
            listing.get('city', 'София'),
            listing.get('address'),
            listing.get('price_eur'),
            'auction',
            listing.get('announcement'),
            datetime.utcnow().isoformat()
        ))
        count += 1
    
    conn.commit()
    print(f"✓ Loaded {count} BCPEA listings")
    return count

def load_all_listings(conn):
    """Load all scraped listings"""
    all_file = 'data/all_listings.json'
    if not os.path.exists(all_file):
        print(f"✗ No combined data found at {all_file}")
        return 0
    
    with open(all_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    cursor = conn.cursor()
    count = 0
    
    for listing in data.get('listings', []):
        listing_id = f"{listing.get('source', 'unknown')}_{count}"
        
        # Calculate price per sqm if we have size
        price_per_sqm = None
        if listing.get('price_eur') and listing.get('size_sqm'):
            price_per_sqm = round(listing['price_eur'] / listing['size_sqm'], 2)
        
        cursor.execute("""
            INSERT OR REPLACE INTO listings 
            (id, source, city, district, property_type, price_eur, size_sqm, price_per_sqm, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            listing_id,
            listing.get('source'),
            listing.get('city', 'София'),
            listing.get('district'),
            listing.get('type'),
            listing.get('price_eur'),
            listing.get('size_sqm'),
            price_per_sqm or listing.get('price_per_sqm'),
            datetime.utcnow().isoformat()
        ))
        count += 1
    
    conn.commit()
    print(f"✓ Loaded {count} total listings")
    return count

def add_sample_imoti_data(conn):
    """Add sample imoti.net data from web_fetch results"""
    sample_data = [
        {"id": "imoti_1", "source": "imoti.net", "city": "София", "district": "Дружба 2", "property_type": "Офис", "price_eur": 3100000, "size_sqm": 2438, "price_per_sqm": 1271},
        {"id": "imoti_2", "source": "imoti.net", "city": "София", "district": "Витоша", "property_type": "Двустаен", "price_eur": 160583, "size_sqm": 71, "price_per_sqm": 2262},
        {"id": "imoti_3", "source": "imoti.net", "city": "София", "district": "Дружба 1", "property_type": "Тристаен", "price_eur": 230000, "size_sqm": 112, "price_per_sqm": 2054},
        {"id": "imoti_4", "source": "imoti.net", "city": "София", "district": "Горубляне", "property_type": "Парцел", "price_eur": 1206700, "size_sqm": 2912, "price_per_sqm": 414},
        {"id": "imoti_5", "source": "imoti.net", "city": "София", "district": "Кръстова Вада", "property_type": "Тристаен", "price_eur": 355000, "size_sqm": 115, "price_per_sqm": 3087},
        {"id": "imoti_6", "source": "imoti.net", "city": "София", "district": "Овча Купел", "property_type": "Тристаен", "price_eur": 272780, "size_sqm": 114, "price_per_sqm": 2393},
        {"id": "imoti_7", "source": "imoti.net", "city": "София", "district": "Оборище", "property_type": "Търговски обект", "price_eur": 1240000, "size_sqm": 304, "price_per_sqm": 4079},
        {"id": "imoti_8", "source": "imoti.net", "city": "София", "district": "Люлин 9", "property_type": "Тристаен", "price_eur": 239000, "size_sqm": 84, "price_per_sqm": 2845},
        {"id": "imoti_9", "source": "imoti.net", "city": "София", "district": "Банкя", "property_type": "Къща", "price_eur": 685000, "size_sqm": 380, "price_per_sqm": 1803},
        {"id": "imoti_10", "source": "imoti.net", "city": "София", "district": "Кръстова Вада", "property_type": "Двустаен", "price_eur": 160000, "size_sqm": 70, "price_per_sqm": 2286},
    ]
    
    cursor = conn.cursor()
    for listing in sample_data:
        cursor.execute("""
            INSERT OR REPLACE INTO listings 
            (id, source, city, district, property_type, price_eur, size_sqm, price_per_sqm, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            listing['id'],
            listing['source'],
            listing['city'],
            listing['district'],
            listing['property_type'],
            listing['price_eur'],
            listing['size_sqm'],
            listing['price_per_sqm'],
            datetime.utcnow().isoformat()
        ))
    
    conn.commit()
    print(f"✓ Added {len(sample_data)} sample imoti.net listings")
    return len(sample_data)

def main():
    print("=== Initializing Real Estate Database ===\n")
    
    conn = init_db()
    
    # Load data from various sources
    bcpea_count = load_bcpea_data(conn)
    all_count = load_all_listings(conn)
    sample_count = add_sample_imoti_data(conn)
    
    # Print summary
    cursor = conn.cursor()
    total = cursor.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    by_source = cursor.execute("SELECT source, COUNT(*) FROM listings GROUP BY source").fetchall()
    
    print(f"\n=== Database Summary ===")
    print(f"Total listings: {total}")
    print("By source:")
    for source, count in by_source:
        print(f"  {source}: {count}")
    
    conn.close()
    print(f"\n✓ Database ready at {DB_PATH}")

if __name__ == '__main__':
    main()
