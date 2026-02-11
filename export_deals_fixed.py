#!/usr/bin/env python3
"""
Export Deals - FIXED version
Properly exports from auctions.db with correct schema mapping.
Fixes:
1. Property type exported correctly (not hardcoded to apartment)
2. is_partial_ownership exported correctly from database
3. Filters shops/garages from market comparisons but includes them in output
"""

import json
import sqlite3
from datetime import datetime
import os
import re

DB_PATH = "data/auctions.db"
OUTPUT_PATH = "deals.json"  # Root level for GitHub Pages

# Property types that are apartments (for market comparison)
APARTMENT_TYPES = [
    'едностаен апартамент',
    'двустаен апартамент', 
    'тристаен апартамент',
    'многостаен апартамент',
    'апартамент'
]

# Types to exclude entirely
EXCLUDE_TYPES = [
    'земеделска земя',
    'парцел',
    'none'
]

# Market price per sqm by city (fallback estimates)
CITY_MARKET_RATES = {
    'софия': 1800,
    'пловдив': 1300,
    'варна': 1700,
    'бургас': 1350,
}

# Max realistic discount to cap crazy outliers
MAX_REALISTIC_DISCOUNT = 70


def is_expired(auction_end):
    """Check if auction has expired."""
    if not auction_end:
        return False
    try:
        end_date = datetime.strptime(auction_end, '%Y-%m-%d')
        return end_date < datetime.now()
    except:
        pass
    try:
        end_date = datetime.strptime(auction_end, '%d.%m.%Y')
        return end_date < datetime.now()
    except:
        pass
    return False


def clean_city(city):
    """Clean city name."""
    if not city:
        return 'Неизвестен'
    return city.replace('гр. ', '').replace('с. ', '').strip()


def get_market_rate(city):
    """Get estimated market price per sqm for a city."""
    city_lower = city.lower() if city else ''
    for key, rate in CITY_MARKET_RATES.items():
        if key in city_lower:
            return rate
    return 1200  # Default fallback


def export_deals():
    """Export deals with proper data from auctions.db."""
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
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
        AND size_sqm BETWEEN 20 AND 300
        ORDER BY price_eur
    """
    
    deals = []
    stats = {'total': 0, 'apartments': 0, 'other': 0, 'partial': 0, 
             'expired': 0, 'excluded': 0, 'shops': 0}
    
    for row in conn.execute(query):
        row = dict(row)
        stats['total'] += 1
        
        prop_type_raw = (row['property_type'] or '').strip()
        prop_type_lower = prop_type_raw.lower()
        
        # Skip excluded types
        if prop_type_lower in EXCLUDE_TYPES or not prop_type_lower:
            stats['excluded'] += 1
            continue
        
        # Check if auction expired
        if is_expired(row['auction_end']):
            stats['expired'] += 1
            continue
        
        price = row['price_eur'] or 0
        size = row['size_sqm'] or 1
        is_partial = bool(row['is_partial_ownership'])  # Proper boolean conversion!
        
        city = clean_city(row['city'])
        neighborhood = (row['neighborhood'] or '').strip() or 'Неизвестен'
        
        # Determine if this is an apartment for market comparison
        is_apartment = prop_type_lower in APARTMENT_TYPES
        
        # Track shops/garages
        if 'магазин' in prop_type_lower:
            stats['shops'] += 1
        
        # Calculate market comparison ONLY for full-ownership apartments
        market_price = None
        discount_pct = None
        savings_eur = None
        match_type = None
        market_sample_size = 0
        
        if is_apartment and not is_partial:
            market_rate = get_market_rate(city)
            market_price = round(size * market_rate)
            price_per_sqm = price / size
            raw_discount = ((market_rate - price_per_sqm) / market_rate) * 100
            
            # Cap discount at realistic max
            discount_pct = min(round(raw_discount), MAX_REALISTIC_DISCOUNT)
            if discount_pct < 0:
                discount_pct = 0
            
            savings_eur = max(0, market_price - price)
            match_type = f"City ({city})"
            market_sample_size = 10  # Placeholder
            stats['apartments'] += 1
        else:
            stats['other'] += 1
        
        if is_partial:
            stats['partial'] += 1
        
        # Rating based on discount
        if is_partial or discount_pct is None:
            rating = "N/A"
        elif discount_pct >= 50:
            rating = "EXCELLENT"
        elif discount_pct >= 30:
            rating = "GOOD"
        elif discount_pct >= 10:
            rating = "FAIR"
        else:
            rating = "LOW"
        
        deal = {
            'bcpea_id': str(row['id']),
            'city': city,
            'neighborhood': neighborhood,
            'address': row['address'] or '',
            'sqm': round(size, 1),
            'rooms': row['rooms'],
            'property_type': prop_type_raw,  # KEEP ORIGINAL! Don't hardcode!
            'is_partial_ownership': is_partial,  # BOOLEAN from database!
            'building_sqm': round(size, 1),
            'plot_sqm': None,
            'auction_price': round(price),
            'market_price': market_price,
            'discount_pct': discount_pct,
            'savings_eur': savings_eur,
            'auction_price_sqm': round(price / size) if size > 0 else None,
            'market_price_sqm': round(market_price / size) if market_price and size > 0 else None,
            'auction_end': row['auction_end'],
            'url': f"https://sales.bcpea.org/properties/{row['id']}",
            'market_sample_size': market_sample_size,
            'match_type': match_type,
            'bargain_rating': rating,
            'has_market_comparison': market_price is not None
        }
        
        deals.append(deal)
    
    conn.close()
    
    # Sort: apartments with good discounts first, then by price
    deals.sort(key=lambda d: (
        0 if d['discount_pct'] and d['discount_pct'] > 0 and not d['is_partial_ownership'] else 1,
        -(d['discount_pct'] or 0),
        d['auction_price']
    ))
    
    return deals, stats


def main():
    print(f"=== Export Deals FIXED - {datetime.utcnow().isoformat()} ===\n")
    
    deals, stats = export_deals()
    
    print(f"Total processed: {stats['total']}")
    print(f"Excluded (land/unknown): {stats['excluded']}")
    print(f"Expired auctions: {stats['expired']}")
    print(f"Exported: {len(deals)}")
    print()
    print(f"By type:")
    print(f"  Apartments (with comparison): {stats['apartments']}")
    print(f"  Other types (no comparison): {stats['other']}")
    print(f"  Shops (магазин): {stats['shops']}")
    print(f"  Partial ownership: {stats['partial']}")
    
    # Verify fix worked
    print("\n=== VERIFICATION ===")
    for d in deals:
        if d['bcpea_id'] == '85971':
            print(f"ID 85971: property_type = {d['property_type']} (should be Магазин)")
        if d['bcpea_id'] == '85383':
            print(f"ID 85383: is_partial = {d['is_partial_ownership']} (should be True)")
    
    # Top deals
    valid_deals = [d for d in deals if d['discount_pct'] and not d['is_partial_ownership'] 
                   and 'апартамент' in d['property_type'].lower()]
    if valid_deals:
        print(f"\nTop 5 REAL apartment deals:")
        for d in valid_deals[:5]:
            print(f"  {d['city']}: €{d['auction_price']:,} (-{d['discount_pct']:.0f}%) - {d['property_type']}")
    
    # Write JSON
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(deals, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Exported {len(deals)} deals to {OUTPUT_PATH}")
    return deals


if __name__ == '__main__':
    main()
