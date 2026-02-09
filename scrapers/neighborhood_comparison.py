#!/usr/bin/env python3
"""
Neighborhood-Based Market Comparison - NO HARDCODED CAPS
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = "data/auctions.db"
MARKET_DB = "data/market.db"

MIN_APARTMENT_SIZE = 35
MAX_APARTMENT_SIZE = 150


def is_valid_apartment(size_sqm, description=None, property_type=None):
    if size_sqm < MIN_APARTMENT_SIZE:
        return False, f"Too small ({size_sqm}m²)"
    if size_sqm > MAX_APARTMENT_SIZE:
        return False, f"Too large ({size_sqm}m²)"
    
    desc_lower = (description or '').lower()
    type_lower = (property_type or '').lower()
    
    if 'гараж' in desc_lower or 'гараж' in type_lower:
        return False, "Garage"
    if 'паркомясто' in desc_lower or 'паркинг' in desc_lower:
        return False, "Parking"
    if 'ид.ч' in desc_lower or 'идеални части' in desc_lower:
        return False, "Fractional share"
    
    return True, "OK"


def get_market_median_for_neighborhood(city, neighborhood, size_sqm, rooms=None, size_tolerance=15):
    """Get actual market median - NO HARDCODED CAPS"""
    if not os.path.exists(MARKET_DB):
        return None, 0, "No market DB"
    
    market_conn = sqlite3.connect(MARKET_DB)
    cursor = market_conn.cursor()
    
    city_clean = city.replace('гр. ', '').replace('с. ', '').strip() if city else ''
    size_min = size_sqm - size_tolerance
    size_max = size_sqm + size_tolerance
    
    # Try 1: District + size match
    cursor.execute("""
        SELECT price_per_sqm FROM market_listings 
        WHERE city = ? AND district = ?
        AND size_sqm BETWEEN ? AND ?
        AND price_per_sqm IS NOT NULL AND price_per_sqm > 0
    """, (city_clean, neighborhood, size_min, size_max))
    results = cursor.fetchall()
    
    if len(results) >= 3:
        prices = sorted([r[0] for r in results])
        median = prices[len(prices) // 2]
        market_conn.close()
        return median, len(results), f"Neighborhood ({neighborhood})"
    
    # Try 2: City-level + size match
    cursor.execute("""
        SELECT price_per_sqm FROM market_listings 
        WHERE city = ?
        AND size_sqm BETWEEN ? AND ?
        AND price_per_sqm IS NOT NULL AND price_per_sqm > 0
    """, (city_clean, size_min, size_max))
    results = cursor.fetchall()
    
    if len(results) >= 3:
        prices = sorted([r[0] for r in results])
        median = prices[len(prices) // 2]
        market_conn.close()
        return median, len(results), f"City ({city_clean})"
    
    market_conn.close()
    return None, len(results) if results else 0, "Insufficient data"


def calculate_comparisons():
    if not os.path.exists(MARKET_DB):
        print("Market DB not found. Run market scraper first.")
        return
    
    auction_conn = sqlite3.connect(DB_PATH)
    
    auction_conn.execute("DROP TABLE IF EXISTS comparisons")
    auction_conn.execute("""
        CREATE TABLE comparisons (
            auction_id TEXT PRIMARY KEY,
            city TEXT,
            neighborhood TEXT,
            auction_price REAL,
            auction_size REAL,
            auction_rooms INTEGER,
            auction_price_sqm REAL,
            market_median_sqm REAL,
            market_sample_size INTEGER,
            match_type TEXT,
            deviation_pct REAL,
            bargain_score INTEGER,
            bargain_rating TEXT
        )
    """)
    
    print(f"=== Neighborhood-Aware Price Comparisons ===")
    print(f"Generated: {datetime.utcnow().isoformat()}\n")
    
    auctions = auction_conn.execute("""
        SELECT id, city, neighborhood, address, price_eur, size_sqm, rooms, property_type 
        FROM auctions 
        WHERE property_type = 'апартамент' 
        AND size_sqm > 0 AND price_eur > 0
    """).fetchall()
    
    compared = 0
    skipped = 0
    bargains = []
    
    for auction in auctions:
        (auction_id, city, neighborhood, address, price, size, rooms, prop_type) = auction
        
        is_valid, reason = is_valid_apartment(size, address, prop_type)
        if not is_valid:
            skipped += 1
            continue
        
        median, sample_size, match_type = get_market_median_for_neighborhood(
            city or '', neighborhood or '', size, rooms
        )
        
        if median is None:
            auction_price_sqm = price / size
            auction_conn.execute("""
                INSERT INTO comparisons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (auction_id, city, neighborhood, price, size, rooms, auction_price_sqm,
                  None, sample_size, match_type, None, None, "NO_DATA"))
            continue
        
        auction_price_sqm = price / size
        deviation = ((auction_price_sqm - median) / median) * 100
        score = int(-deviation)
        
        if score >= 50:
            rating = "EXCELLENT"
        elif score >= 30:
            rating = "GOOD"
        elif score >= 15:
            rating = "FAIR"
        elif score >= 0:
            rating = "BELOW_MARKET"
        else:
            rating = "OVERPRICED"
        
        auction_conn.execute("""
            INSERT INTO comparisons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (auction_id, city, neighborhood, price, size, rooms, auction_price_sqm,
              median, sample_size, match_type, deviation, score, rating))
        
        compared += 1
        
        if score >= 15:
            bargains.append({
                'id': auction_id, 'city': city, 'neighborhood': neighborhood,
                'price': price, 'size': size, 'rooms': rooms,
                'auction_sqm': auction_price_sqm, 'market_sqm': median,
                'deviation': deviation, 'score': score, 'rating': rating,
                'match_type': match_type, 'sample_size': sample_size
            })
    
    auction_conn.commit()
    
    print(f"Total apartments: {len(auctions)}")
    print(f"Compared: {compared}")
    print(f"Skipped: {skipped}")
    print(f"No market data: {len(auctions) - compared - skipped}\n")
    
    print("Comparison breakdown:")
    for row in auction_conn.execute("""
        SELECT match_type, COUNT(*), ROUND(AVG(bargain_score), 0)
        FROM comparisons WHERE match_type IS NOT NULL
        GROUP BY match_type ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]}: {row[1]} listings, avg score {row[2] or 'N/A'}")
    
    if bargains:
        print(f"\n🔥 TOP BARGAINS (15%+ below market):\n")
        bargains.sort(key=lambda x: -x['score'])
        
        for b in bargains[:15]:
            room_str = f"{b['rooms']}-room" if b['rooms'] else "unknown"
            hood_str = f", {b['neighborhood']}" if b['neighborhood'] else ""
            print(f"  {b['city']}{hood_str}: €{b['price']:,.0f} ({b['size']:.0f}m², {room_str})")
            print(f"    Auction: €{b['auction_sqm']:.0f}/m² vs Market: €{b['market_sqm']:.0f}/m²")
            print(f"    Discount: {b['score']}% ({b['rating']})")
            print(f"    Match: {b['match_type']} (n={b['sample_size']})")
            print(f"    https://sales.bcpea.org/properties/{b['id']}\n")
    else:
        print("\nNo bargains found (15%+ below market).")
    
    auction_conn.close()
    print(f"✓ Comparisons saved to {DB_PATH}")


if __name__ == '__main__':
    calculate_comparisons()
