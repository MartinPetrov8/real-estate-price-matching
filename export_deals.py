#!/usr/bin/env python3
"""
Export Deals v4 - Complete QA fixes
- Includes all property types (not just apartments)
- Properly handles partial ownership (no discount shown)
- Filters expired auctions
- Classifies property types correctly
"""

import json
import sqlite3
from datetime import datetime
import os
import re
import sys
sys.path.insert(0, 'src/matching')
from neighborhood_matcher import extract_neighborhood, normalize_neighborhood

DB_PATH = "data/auctions.db"
MARKET_DB = "data/market.db"
OUTPUT_PATH = "frontend/deals.json"

# Property types that are apartments (for market comparison)
APARTMENT_TYPES = [
    'едностаен апартамент',
    'двустаен апартамент', 
    'тристаен апартамент',
    'многостаен апартамент',
    'апартамент'
]

# Property types to exclude entirely (land, etc.)
EXCLUDE_TYPES = [
    'земеделска земя',
    'парцел',
    'none'
]

# Map property types to frontend categories
TYPE_MAP = {
    'едностаен апартамент': 'apartment',
    'двустаен апартамент': 'apartment',
    'тристаен апартамент': 'apartment',
    'многостаен апартамент': 'apartment',
    'къща': 'house',
    'къща с парцел': 'house',
    'етаж от къща': 'house',
    'вила': 'house',
    'парцел с къща': 'house',
    'гараж': 'garage',
    'магазин': 'commercial',
    'офис': 'commercial',
    'склад': 'commercial',
    'ателие, таван': 'other',
}


def get_market_median(city, size_sqm, address=None, size_tolerance=15):
    """Get market median from scraped data with neighborhood matching."""
    if not os.path.exists(MARKET_DB):
        return None, 0, None
    
    market_conn = sqlite3.connect(MARKET_DB)
    cursor = market_conn.cursor()
    
    city_clean = city.replace('гр. ', '').replace('с. ', '').strip() if city else ''
    size_min = size_sqm - size_tolerance
    size_max = size_sqm + size_tolerance
    
    # Extract neighborhood from auction address
    auction_hood = extract_neighborhood(address) if address else None
    matched_neighborhood = None
    
    # Try city + neighborhood + size match first (most precise)
    if auction_hood:
        cursor.execute("""
            SELECT price_per_sqm, neighborhood FROM market_listings 
            WHERE city = ? AND neighborhood = ? AND size_sqm BETWEEN ? AND ?
            AND price_per_sqm IS NOT NULL AND price_per_sqm > 0
        """, (city_clean, auction_hood, size_min, size_max))
        results = cursor.fetchall()
        
        if len(results) >= 3:
            prices = sorted([r[0] for r in results])
            median = prices[len(prices) // 2]
            market_conn.close()
            return median, len(results), auction_hood
    
    # Fallback: city + size match (no neighborhood)
    cursor.execute("""
        SELECT price_per_sqm FROM market_listings 
        WHERE city = ? AND size_sqm BETWEEN ? AND ?
        AND price_per_sqm IS NOT NULL AND price_per_sqm > 0
    """, (city_clean, size_min, size_max))
    results = cursor.fetchall()
    
    if len(results) >= 3:
        prices = sorted([r[0] for r in results])
        median = prices[len(prices) // 2]
        market_conn.close()
        return median, len(results), None
    
    # Final fallback: city only
    cursor.execute("""
        SELECT price_per_sqm FROM market_listings 
        WHERE city = ? AND price_per_sqm IS NOT NULL AND price_per_sqm > 0
    """, (city_clean,))
    results = cursor.fetchall()
    
    if len(results) >= 3:
        prices = sorted([r[0] for r in results])
        median = prices[len(prices) // 2]
        market_conn.close()
        return median, len(results), None
    
    market_conn.close()
    return None, 0, None


def is_expired(auction_end):
    """Check if auction has expired."""
    if not auction_end:
        return False  # Can't determine, assume active
    
    try:
        # Try DD.MM.YYYY format
        end_date = datetime.strptime(auction_end, '%d.%m.%Y')
        return end_date < datetime.now()
    except:
        pass
    
    try:
        # Try YYYY-MM-DD format
        end_date = datetime.strptime(auction_end, '%Y-%m-%d')
        return end_date < datetime.now()
    except:
        pass
    
    return False


def export_deals():
    """Export all properties with proper classification."""
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return [], {}
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Get all non-expired, non-excluded properties in target cities
    query = """
        SELECT 
            id, city, neighborhood, address, 
            price_eur, size_sqm, rooms,
            property_type, is_partial_ownership,
            auction_start, auction_end, is_expired
        FROM auctions 
        WHERE is_expired = 0
        AND city IN ('гр. София', 'гр. Пловдив', 'гр. Варна', 'гр. Бургас')
        AND size_sqm > 0 AND price_eur > 0
        ORDER BY price_eur
    """
    
    deals = []
    stats = {'total': 0, 'apartments': 0, 'houses': 0, 'garages': 0, 'other': 0, 
             'partial': 0, 'expired': 0, 'excluded': 0}
    
    cursor = conn.execute(query)
    
    for row in cursor:
        row = dict(row)
        stats['total'] += 1
        
        prop_type = (row['property_type'] or '').lower().strip()
        
        # Skip excluded types (land, plots)
        if prop_type in EXCLUDE_TYPES or not prop_type:
            stats['excluded'] += 1
            continue
        
        # Check if expired
        if is_expired(row['auction_end']):
            stats['expired'] += 1
            continue
        
        price = row['price_eur'] or 0
        size = row['size_sqm'] or 1
        is_partial = row['is_partial_ownership']
        
        # Clean city name
        city = (row['city'] or '').replace('гр. ', '').replace('с. ', '').strip()
        
        # Determine frontend type
        frontend_type = TYPE_MAP.get(prop_type, 'other')
        is_apartment = prop_type in APARTMENT_TYPES
        
        # Get market data only for apartments
        market_avg = None
        discount = None
        
        if is_apartment and not is_partial:
            market_median, sample_size, matched_hood = get_market_median(city, size, row['address'])
            if market_median and sample_size >= 3:
                market_avg = round(market_median)
                price_per_sqm = price / size
                discount = round(((market_median - price_per_sqm) / market_median) * 100, 1)
                if discount < 0:
                    discount = 0  # Don't show negative discounts
            elif market_median:
                # Not enough comparables for reliable discount
                market_avg = round(market_median)
                discount = None  # Don't show unreliable discount
        
        # Build deal object
        deal = {
            'id': str(row['id']),
            'city': city,
            'neighborhood': (row['neighborhood'] or '').lower().strip() or None,
            'address': row['address'] or '',
            'price': round(price),
            'effective_price': round(price),
            'sqm': round(size, 1),
            'price_per_sqm': round(price / size) if size > 0 else None,
            'market_avg': market_avg,
            'market_price': round(market_avg * size) if market_avg and size else None,
            'savings_eur': round((market_avg * size) - price) if market_avg and size and price else None,
            'comparables_count': sample_size if market_avg else 0,
            'discount': discount if not is_partial else None,
            'rooms': row['rooms'],
            'property_type': frontend_type,
            'property_type_bg': row['property_type'],
            'auction_start': row['auction_start'],
            'auction_end': row['auction_end'],
            'url': f"https://sales.bcpea.org/properties/{row['id']}",
            'partial_ownership': 'Дробна собственост' if is_partial else None,
            'score': 0  # Will calculate below
        }
        
        # Calculate score (1-5 stars)
        if is_partial:
            deal['score'] = 0
        elif discount and discount >= 40:
            deal['score'] = 5
        elif discount and discount >= 30:
            deal['score'] = 4
        elif discount and discount >= 20:
            deal['score'] = 3
        elif discount and discount >= 10:
            deal['score'] = 2
        elif discount:
            deal['score'] = 1
        else:
            deal['score'] = 0  # No market comparison available
        
        # Update stats
        if is_partial:
            stats['partial'] += 1
        if frontend_type == 'apartment':
            stats['apartments'] += 1
        elif frontend_type == 'house':
            stats['houses'] += 1
        elif frontend_type == 'garage':
            stats['garages'] += 1
        else:
            stats['other'] += 1
        
        deals.append(deal)
    
    conn.close()
    
    # Sort: apartments with discounts first, then others by price
    deals.sort(key=lambda d: (
        0 if d['discount'] and d['discount'] > 0 else 1,
        -(d['discount'] or 0),
        d['price']
    ))
    
    return deals, stats


def main():
    print(f"=== Exporting Deals v4 - {datetime.utcnow().isoformat()} ===\n")
    
    deals, stats = export_deals()
    
    print(f"Total processed: {stats['total']}")
    print(f"Excluded (land/plots): {stats['excluded']}")
    print(f"Expired auctions: {stats['expired']}")
    print(f"Exported: {len(deals)}")
    print()
    print(f"By type:")
    print(f"  Apartments: {stats['apartments']}")
    print(f"  Houses: {stats['houses']}")
    print(f"  Garages: {stats['garages']}")
    print(f"  Other: {stats['other']}")
    print(f"  Partial ownership: {stats['partial']}")
    
    # Top deals
    valid_deals = [d for d in deals if d['discount'] and not d['partial_ownership']]
    if valid_deals:
        print(f"\nTop 5 deals (apartments, not partial):")
        for d in valid_deals[:5]:
            print(f"  {d['city']}: €{d['price']:,} (-{d['discount']:.0f}%)")
    
    # Write JSON
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(deals, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Exported {len(deals)} deals to {OUTPUT_PATH}")
    return deals


if __name__ == '__main__':
    main()
