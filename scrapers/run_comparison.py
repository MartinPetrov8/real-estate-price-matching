#!/usr/bin/env python3
"""
Run Market Comparison - Fixed version
Compares auction prices to market medians for apartments in target cities
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = "data/auctions.db"
MARKET_DB = "data/market.db"

# Target cities
TARGET_CITIES = ['гр. София', 'гр. Пловдив', 'гр. Варна', 'гр. Бургас']

# Validation
MIN_APT_SIZE = 35
MAX_APT_SIZE = 150


def get_market_median(city, size_sqm, rooms=None, size_tolerance=15):
    """Get market median from scraped data."""
    if not os.path.exists(MARKET_DB):
        return None, 0, "No market DB"
    
    market_conn = sqlite3.connect(MARKET_DB)
    cursor = market_conn.cursor()
    
    # Clean city name for market DB (remove гр. prefix)
    city_clean = city.replace('гр. ', '').replace('с. ', '').strip() if city else ''
    size_min = size_sqm - size_tolerance
    size_max = size_sqm + size_tolerance
    
    # Try city + size match
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
    
    # Fallback: city only (no size filter)
    cursor.execute("""
        SELECT price_per_sqm FROM market_listings 
        WHERE city = ?
        AND price_per_sqm IS NOT NULL AND price_per_sqm > 0
    """, (city_clean,))
    results = cursor.fetchall()
    
    if len(results) >= 3:
        prices = sorted([r[0] for r in results])
        median = prices[len(prices) // 2]
        market_conn.close()
        return median, len(results), f"City-wide ({city_clean})"
    
    market_conn.close()
    return None, len(results) if results else 0, "Insufficient data"


def run_comparison():
    """Compare apartments in target cities to market prices."""
    
    auction_conn = sqlite3.connect(DB_PATH)
    
    # Create comparisons table
    auction_conn.execute("DROP TABLE IF EXISTS comparisons")
    auction_conn.execute("""
        CREATE TABLE comparisons (
            auction_id INTEGER PRIMARY KEY,
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
            bargain_rating TEXT,
            is_partial_ownership INTEGER
        )
    """)
    
    print(f"\n=== Market Comparison for Target Cities ===")
    print(f"Cities: {', '.join([c.replace('гр. ', '') for c in TARGET_CITIES])}")
    print(f"Generated: {datetime.utcnow().isoformat()}\n")
    
    # Get apartments from target cities
    placeholders = ','.join(['?' for _ in TARGET_CITIES])
    auctions = auction_conn.execute(f"""
        SELECT id, city, neighborhood, address, price_eur, size_sqm, rooms, property_type, is_partial_ownership
        FROM auctions 
        WHERE is_expired = 0
        AND city IN ({placeholders})
        AND (property_type LIKE '%апартамент%' OR property_type LIKE '%Апартамент%')
        AND size_sqm > 0 AND price_eur > 0
    """, TARGET_CITIES).fetchall()
    
    compared = 0
    no_data = 0
    skipped = 0
    bargains = []
    
    for auction in auctions:
        (auction_id, city, neighborhood, address, price, size, rooms, prop_type, is_partial) = auction
        
        # Skip invalid sizes
        if size < MIN_APT_SIZE or size > MAX_APT_SIZE:
            skipped += 1
            continue
        
        # Get market median
        median, sample_size, match_type = get_market_median(city, size, rooms)
        
        auction_price_sqm = price / size
        
        if median is None:
            # No market data
            auction_conn.execute("""
                INSERT INTO comparisons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (auction_id, city, neighborhood, price, size, rooms, auction_price_sqm,
                  None, sample_size, match_type, None, None, "NO_DATA", is_partial))
            no_data += 1
            continue
        
        # Calculate deviation (negative = below market = good deal)
        deviation = ((auction_price_sqm - median) / median) * 100
        score = int(-deviation)  # Score is positive when below market
        
        # Rating
        if is_partial:
            rating = "PARTIAL_OWNERSHIP"
        elif score >= 50:
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
            INSERT INTO comparisons VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (auction_id, city, neighborhood, price, size, rooms, auction_price_sqm,
              median, sample_size, match_type, deviation, score, rating, is_partial))
        
        compared += 1
        
        # Track bargains (15%+ below market, not partial ownership)
        if score >= 15 and not is_partial:
            bargains.append({
                'id': auction_id,
                'city': city,
                'neighborhood': neighborhood or '',
                'price': price,
                'size': size,
                'rooms': rooms,
                'auction_sqm': auction_price_sqm,
                'market_sqm': median,
                'score': score,
                'rating': rating,
                'match_type': match_type,
                'sample_size': sample_size
            })
    
    auction_conn.commit()
    
    # Stats
    print(f"Apartments in target cities: {len(auctions)}")
    print(f"Compared with market data: {compared}")
    print(f"No market data: {no_data}")
    print(f"Skipped (size out of range): {skipped}\n")
    
    # By city
    print("By city:")
    for row in auction_conn.execute("""
        SELECT city, COUNT(*), SUM(CASE WHEN bargain_rating IN ('EXCELLENT','GOOD','FAIR') THEN 1 ELSE 0 END)
        FROM comparisons
        GROUP BY city ORDER BY COUNT(*) DESC
    """):
        city_clean = row[0].replace('гр. ', '') if row[0] else 'Unknown'
        print(f"  {city_clean}: {row[1]} total, {row[2] or 0} bargains")
    
    # Partial ownership count
    partial_count = auction_conn.execute("""
        SELECT COUNT(*) FROM comparisons WHERE is_partial_ownership = 1
    """).fetchone()[0]
    print(f"\n⚠️ Partial ownership (excluded from bargains): {partial_count}")
    
    # Bargains
    if bargains:
        print(f"\n🔥 TOP BARGAINS (15%+ below market):\n")
        bargains.sort(key=lambda x: -x['score'])
        
        for b in bargains[:10]:
            city_clean = b['city'].replace('гр. ', '')
            hood_str = f", {b['neighborhood']}" if b['neighborhood'] else ""
            room_str = f"{b['rooms']}-стаен" if b['rooms'] else ""
            print(f"  {city_clean}{hood_str}: €{b['price']:,.0f} ({b['size']:.0f}m², {room_str})")
            print(f"    Тръжна: €{b['auction_sqm']:.0f}/m² vs Пазарна: €{b['market_sqm']:.0f}/m²")
            print(f"    Отстъпка: {b['score']}% ({b['rating']})")
            print(f"    https://sales.bcpea.org/property/{b['id']}\n")
    else:
        print("\nNo bargains found (15%+ below market).")
    
    auction_conn.close()
    print(f"✓ Comparisons saved to {DB_PATH}")
    return len(bargains)


if __name__ == '__main__':
    run_comparison()
