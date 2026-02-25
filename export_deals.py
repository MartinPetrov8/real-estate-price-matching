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
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src', 'matching'))
from neighborhood_matcher import extract_neighborhood, normalize_neighborhood, neighborhood_similarity

DB_PATH = "data/auctions.db"
MARKET_DB = "data/market.db"


def _title_hood(name):
    """Title-case a neighborhood name, handling hyphens: 'здравец-север' → 'Здравец-Север'."""
    if not name:
        return name
    return '-'.join(
        ' '.join(w.capitalize() for w in part.split())
        for part in name.strip().split('-')
    )
OUTPUT_PATH = "deals.json"

# Property types that are apartments (for market comparison)
APARTMENT_TYPES = [
    'Едностаен апартамент',
    'Двустаен апартамент',
    'Тристаен апартамент',
    'Многостаен апартамент',
    'Апартамент'
]

# Property types to exclude entirely (land, etc.)
EXCLUDE_TYPES = [
    'Земеделска земя',
    'Парцел',
    'none'
]

# Map property types to frontend categories
TYPE_MAP = {
    'Едностаен апартамент': 'apartment',
    'Двустаен апартамент': 'apartment',
    'Тристаен апартамент': 'apartment',
    'Многостаен апартамент': 'apartment',
    'Къща': 'house',
    'Къща с парцел': 'house',
    'Етаж от къща': 'house',
    'Вила': 'house',
    'Парцел с къща': 'house',
    'Гараж': 'garage',
    'Магазин': 'commercial',
    'Офис': 'commercial',
    'Склад': 'commercial',
    'Ателие, Таван': 'other',
}


def get_market_median(city, size_sqm, address=None, db_neighborhood=None, size_tolerance=15):
    """Get market median from scraped data with neighborhood matching.
    Returns (median, count, matched_hood, match_level) where match_level is 'hood', 'city_size', or 'city'.
    """
    if not os.path.exists(MARKET_DB):
        return None, 0, None, None
    
    market_conn = sqlite3.connect(MARKET_DB)
    cursor = market_conn.cursor()
    
    city_clean = city.replace('гр. ', '').replace('с. ', '').strip() if city else ''
    size_min = size_sqm - size_tolerance
    size_max = size_sqm + size_tolerance
    
    # Use DB neighborhood (from geocoding) first, fallback to text extraction from address
    auction_hood = db_neighborhood or (extract_neighborhood(address) if address else None)
    matched_neighborhood = None
    
    # Try city + neighborhood + size match (fuzzy)
    # Strategy: try strict size first, then widen to all sizes in neighborhood.
    # Neighborhood-level data at any size > city-wide data at matching size.
    if auction_hood:
        SIMILARITY_THRESHOLD = 0.7
        
        # Pass 1: neighborhood + size match (best: same area, same size)
        cursor.execute("""
            SELECT price_per_sqm, neighborhood FROM market_listings 
            WHERE city = ? AND neighborhood IS NOT NULL AND size_sqm BETWEEN ? AND ?
            AND price_per_sqm IS NOT NULL AND price_per_sqm > 200 AND price_per_sqm < 5000
        """, (city_clean, size_min, size_max))
        all_hood_results = cursor.fetchall()

        matched_prices = []
        for price_per_sqm, market_hood in all_hood_results:
            sim = neighborhood_similarity(auction_hood, market_hood)
            if sim >= SIMILARITY_THRESHOLD:
                matched_prices.append(price_per_sqm)

        if len(matched_prices) >= 3:
            prices = sorted(matched_prices)
            median = prices[len(prices) // 2]
            market_conn.close()
            return median, len(matched_prices), auction_hood, 'hood'
        
        # Pass 2: neighborhood match, ANY size (still better than city-wide)
        cursor.execute("""
            SELECT price_per_sqm, neighborhood FROM market_listings 
            WHERE city = ? AND neighborhood IS NOT NULL
            AND price_per_sqm IS NOT NULL AND price_per_sqm > 200 AND price_per_sqm < 5000
        """, (city_clean,))
        all_hood_any_size = cursor.fetchall()

        matched_prices_wide = []
        for price_per_sqm, market_hood in all_hood_any_size:
            sim = neighborhood_similarity(auction_hood, market_hood)
            if sim >= SIMILARITY_THRESHOLD:
                matched_prices_wide.append(price_per_sqm)

        if len(matched_prices_wide) >= 3:
            prices = sorted(matched_prices_wide)
            median = prices[len(prices) // 2]
            market_conn.close()
            return median, len(matched_prices_wide), auction_hood, 'hood'
    
    # Fallback: city + size match (no neighborhood)
    cursor.execute("""
        SELECT price_per_sqm FROM market_listings 
        WHERE city = ? AND size_sqm BETWEEN ? AND ?
        AND price_per_sqm IS NOT NULL AND price_per_sqm > 200 AND price_per_sqm < 5000
    """, (city_clean, size_min, size_max))
    results = cursor.fetchall()
    
    if len(results) >= 3:
        prices = sorted([r[0] for r in results])
        median = prices[len(prices) // 2]
        market_conn.close()
        return median, len(results), None, 'city_size'
    
    # Final fallback: city only (with outlier filtering)
    cursor.execute("""
        SELECT price_per_sqm FROM market_listings 
        WHERE city = ? AND price_per_sqm IS NOT NULL AND price_per_sqm > 200 AND price_per_sqm < 5000
    """, (city_clean,))
    results = cursor.fetchall()
    
    if len(results) >= 3:
        prices = sorted([r[0] for r in results])
        median = prices[len(prices) // 2]
        market_conn.close()
        return median, len(results), None, 'city'
    
    market_conn.close()
    return None, 0, None, None


def is_expired(auction_end):
    """Check if auction has expired."""
    if not auction_end:
        return False  # Can't determine, assume active
    
    try:
        # Try DD.MM.YYYY format
        end_date = datetime.strptime(auction_end, '%d.%m.%Y')
        return end_date < datetime.now()
    except ValueError:
        pass
    
    try:
        # Try YYYY-MM-DD format
        end_date = datetime.strptime(auction_end, '%Y-%m-%d')
        return end_date < datetime.now()
    except ValueError:
        pass
    
    return False


def export_deals():
    """Export all properties with proper classification."""
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return [], {}
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Ensure composite index exists for market queries
    if os.path.exists(MARKET_DB):
        try:
            mconn = sqlite3.connect(MARKET_DB)
            mconn.execute('CREATE INDEX IF NOT EXISTS idx_city_size ON market_listings(city, size_sqm)')
            mconn.commit()
            mconn.close()
        except Exception:
            pass
    
    # Get all non-expired, non-excluded properties in target cities
    query = """
        SELECT 
            id, city, neighborhood, address, 
            price_eur, size_sqm, floor,
            property_type, is_partial_ownership,
            auction_start, auction_end, is_expired
        FROM auctions 
        WHERE is_expired = 0
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
        
        prop_type = (row['property_type'] or '').strip()
        
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
        matched_hood = None
        match_level = None
        
        if is_apartment and not is_partial:
            market_median, sample_size, matched_hood, match_level = get_market_median(
                city, size, row['address'], db_neighborhood=row.get('neighborhood')
            )
            if market_median and sample_size >= 3:
                market_avg = round(market_median)
                price_per_sqm = price / size
                discount = round(((market_median - price_per_sqm) / market_median) * 100, 1)
                if discount < 0:
                    discount = None  # Negative = overpriced, don't show unreliable discount
            elif market_median:
                # Not enough comparables for reliable discount
                market_avg = round(market_median)
                discount = None  # Don't show unreliable discount
        
        # Build deal object
        deal = {
            'id': str(row['id']),
            'city': city,
            'neighborhood': _title_hood((row['neighborhood'] or '').strip()) or None,
            'address': row['address'] or '',
            'price': round(price),
            'effective_price': round(price),
            'sqm': round(size, 1),
            'price_per_sqm': round(price / size) if size > 0 else None,
            'market_avg': market_avg,
            'market_price': round(market_avg * size) if market_avg and size else None,
            'savings_eur': round((market_avg * size) - price) if market_avg and size and price else None,
            'comparables_count': sample_size if market_avg else 0,
            'comparables_level': match_level,  # 'hood', 'city_size', 'city', or None
            'discount': discount if not is_partial else None,
            'property_type': frontend_type,
            'floor': row.get('floor'),
            'property_type_bg': row['property_type'],
            'auction_start': row['auction_start'],
            'auction_end': row['auction_end'],
            'url': f"https://sales.bcpea.org/properties/{row['id']}",
            'matched_neighborhood': _title_hood(matched_hood) if matched_hood else None,
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
