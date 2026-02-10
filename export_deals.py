#!/usr/bin/env python3
"""Export deals to frontend-compatible JSON format.

Outputs to deals.json (root) for GitHub Pages
Uses deal_matches when available, falls back to neighborhood estimates.
Handles properties with no market comparison data gracefully.
"""

import json
import re
import sqlite3
from datetime import datetime
import os
import sys

# Add scrapers to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scrapers'))
try:
    from neighborhood_caps import get_price_cap, MAX_REALISTIC_DISCOUNT
except ImportError:
    # Fallback if module not available
    def get_price_cap(city, address):
        return {'min': 800, 'max': 2000, 'median': 1200}
    MAX_REALISTIC_DISCOUNT = 60

DB_PATH = "data/properties.db"
OUTPUT_PATH = "deals.json"  # Root level for GitHub Pages

# Market price per sqm by city (fallback estimates)
CITY_MARKET_RATES = {
    'софия': 1800,
    'пловдив': 1300,
    'варна': 1400,
    'бургас': 1200,
    'русе': 900,
    'стара загора': 1000,
    'плевен': 850,
}

# Property type multipliers (relative to apartment base price)
PROPERTY_TYPE_MULTIPLIERS = {
    'апартамент': 1.0,
    'къща': 0.8,      # Houses often lower per sqm but larger
    'гараж': 0.3,     # Garages much cheaper per sqm
    'магазин': 1.2,   # Commercial higher
    'офис': 1.1,
    'склад': 0.6,
    'търговски': 1.2,
    'земя': 0.2,      # Land priced differently
    'друго': 0.8,
}

# Partial ownership detection patterns
PARTIAL_OWNERSHIP_PATTERNS = [
    # (regex pattern, fraction)
    (r'½|1\s*/\s*2|една\s+втора|половин\s+идеална\s+част', '1/2'),
    (r'1\s*/\s*3|една\s+трета', '1/3'),
    (r'¼|1\s*/\s*4|една\s+четвърт', '1/4'),
    (r'1\s*/\s*5|една\s+пета', '1/5'),
    (r'1\s*/\s*6|една\s+шеста', '1/6'),
    (r'1\s*/\s*8|една\s+осма', '1/8'),
    (r'2\s*/\s*3|две\s+трети', '2/3'),
    (r'3\s*/\s*4|три\s+четвърти', '3/4'),
    (r'идеална\s+част', 'unknown'),  # Generic pattern - catch-all
]


def detect_partial_ownership(description):
    """Detect partial ownership fractions from property description.
    
    Returns fraction string like "1/6", "1/4", "1/2", "1/3" or None if full ownership.
    """
    if not description:
        return None
    
    desc_lower = description.lower()
    
    for pattern, fraction in PARTIAL_OWNERSHIP_PATTERNS:
        if re.search(pattern, desc_lower, re.IGNORECASE):
            return fraction
    
    return None


def extract_neighborhood(address, city):
    """Extract neighborhood/district from Bulgarian address."""
    if not address:
        return None
    
    addr_lower = address.lower()
    
    # Common patterns: ж.к. X, жк X, кв. X, район X, кв X
    patterns = [
        r'ж\.?\s*к\.?\s*["\']?([а-яА-Я\s\d-]+)',  # ж.к. Люлин
        r'кв\.?\s*["\']?([а-яА-Я\s\d-]+)',        # кв. Лозенец
        r'район\s*["\']?([а-яА-Я\s-]+)',          # район Триадица
        r'местност\s*["\']?([а-яА-Я\s-]+)',       # местност X
    ]
    
    for pattern in patterns:
        match = re.search(pattern, addr_lower)
        if match:
            hood = match.group(1).strip()
            # Clean up trailing numbers for housing complexes
            hood = re.sub(r'\s*\d+\s*$', '', hood).strip()
            # Capitalize first letter
            return hood.capitalize() if hood else None
    
    return None


def get_market_rate(city, address, property_type='апартамент'):
    """Get estimated market price per sqm for a city/neighborhood/property type."""
    city_lower = city.lower() if city else ''
    
    # Get base rate from neighborhood or city
    # Try specific neighborhood caps first
    caps = get_price_cap(city, address)
    base_rate = caps['median']
    
    # If neighborhood caps returned default, try city averages
    if base_rate == 1200:  # Default value was returned
        for key, rate in CITY_MARKET_RATES.items():
            if key in city_lower:
                base_rate = rate
                break
    
    # Apply property type multiplier
    multiplier = PROPERTY_TYPE_MULTIPLIERS.get(property_type, 0.8)
    adjusted_rate = base_rate * multiplier
    
    return adjusted_rate


def column_exists(conn, table, column):
    """Check if a column exists in a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def get_comparison_status(match_count, has_market_estimate, property_type):
    """
    Determine comparison status for a property.
    
    Returns dict with:
    - status: 'matched', 'estimated', or 'no_comparison'
    - label: Human-readable label
    - confidence: 'high', 'medium', or 'low'
    """
    if match_count and match_count > 0:
        return {
            'status': 'matched',
            'label': 'Based on market comparables',
            'confidence': 'high',
            'has_data': True
        }
    elif has_market_estimate:
        return {
            'status': 'estimated',
            'label': 'Based on neighborhood estimates',
            'confidence': 'medium',
            'has_data': True
        }
    else:
        return {
            'status': 'no_comparison',
            'label': 'No comparison available',
            'confidence': 'low',
            'has_data': False
        }


def export_deals(min_price=10000, include_no_comparison=True):
    """Export deals - includes FULL ownership properties with market estimates.
    
    Args:
        min_price: Minimum auction price in EUR
        include_no_comparison: Include properties even without market comparison data
    """
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Check if partial_ownership column exists
    has_partial_column = column_exists(conn, 'kchsi_properties', 'partial_ownership')
    
    # Build query based on available columns
    if has_partial_column:
        query = """
            SELECT 
                k.id,
                k.bcpea_id,
                k.city,
                k.address,
                k.district,
                k.property_type,
                k.sqm,
                k.rooms,
                k.floor,
                k.price_eur,
                k.auction_end,
                k.description,
                k.partial_ownership,
                COUNT(d.id) as match_count,
                AVG(d.market_price_eur) as avg_market_price,
                AVG(d.savings_pct) as avg_savings_pct,
                AVG(d.savings_eur) as avg_savings_eur
            FROM kchsi_properties k
            LEFT JOIN deal_matches d ON k.bcpea_id = d.kchsi_id
            WHERE k.price_eur >= ?
            GROUP BY k.id
            ORDER BY 
                CASE WHEN avg_savings_pct IS NULL THEN 0 ELSE 1 END DESC,
                avg_savings_pct DESC
        """
    else:
        # Fallback for older database schema
        query = """
            SELECT 
                k.id,
                k.bcpea_id,
                k.city,
                k.address,
                k.district,
                k.property_type,
                k.sqm,
                k.rooms,
                k.floor,
                k.price_eur,
                k.auction_end,
                k.description,
                NULL as partial_ownership,
                COUNT(d.id) as match_count,
                AVG(d.market_price_eur) as avg_market_price,
                AVG(d.savings_pct) as avg_savings_pct,
                AVG(d.savings_eur) as avg_savings_eur
            FROM kchsi_properties k
            LEFT JOIN deal_matches d ON k.bcpea_id = d.kchsi_id
            WHERE k.price_eur >= ?
            GROUP BY k.id
            ORDER BY 
                CASE WHEN avg_savings_pct IS NULL THEN 0 ELSE 1 END DESC,
                avg_savings_pct DESC
        """
    
    deals = []
    excluded_count = 0
    excluded_partial = []
    no_comparison_count = 0
    
    for row in conn.execute(query, (min_price,)):
        row = dict(row)
        
        auction_price = row['price_eur'] or 0
        size = row['sqm'] or 1
        description = row['description'] or ''
        property_type = row['property_type'] or 'апартамент'
        
        # Double-check for partial ownership in description (safety net)
        partial_ownership = row['partial_ownership'] or detect_partial_ownership(description)
        
        if partial_ownership:
            excluded_count += 1
            excluded_partial.append({
                'id': row['bcpea_id'],
                'city': row['city'],
                'fraction': partial_ownership,
                'price': auction_price
            })
            continue  # SKIP this property - it's partial ownership
        
        # Clean city name
        city = (row['city'] or '').replace('гр. ', '').replace('с. ', '').strip()
        address = row['address'] or ''
        
        # Get market price
        raw_market_price = row['avg_market_price']
        comparables = row['match_count'] or 0
        
        if raw_market_price and raw_market_price > 0:
            # Use actual market data from matches
            market_price = raw_market_price
            savings = row['avg_savings_eur'] or (market_price - auction_price)
            discount = row['avg_savings_pct'] or ((market_price - auction_price) / market_price * 100)
            has_market_estimate = True
        else:
            # Fallback: use neighborhood/city estimates
            market_sqm = get_market_rate(city, address, property_type)
            market_price = size * market_sqm
            savings = market_price - auction_price
            discount = ((market_price - auction_price) / market_price * 100) if market_price > 0 else 0
            has_market_estimate = True  # We have an estimate
        
        # Cap discount at realistic level
        discount = min(discount, MAX_REALISTIC_DISCOUNT)
        
        # Skip if no meaningful market data and include_no_comparison is False
        comparison_info = get_comparison_status(comparables, has_market_estimate, property_type)
        
        if not comparison_info['has_data'] and not include_no_comparison:
            no_comparison_count += 1
            continue
        
        if not comparison_info['has_data']:
            # Still include but flag appropriately
            market_price = None
            savings = None
            discount = None
            no_comparison_count += 1
        
        # Calculate price per sqm
        auction_sqm = auction_price / size if size > 0 else 0
        
        # Extract neighborhood
        neighborhood = row['district'] or extract_neighborhood(row['address'], city)
        
        # Format auction end date
        auction_end = None
        if row['auction_end']:
            try:
                if isinstance(row['auction_end'], str):
                    # Try parsing various formats
                    for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y']:
                        try:
                            dt = datetime.strptime(row['auction_end'], fmt)
                            auction_end = dt.strftime('%Y-%m-%d')
                            break
                        except:
                            continue
                else:
                    auction_end = row['auction_end'].strftime('%Y-%m-%d')
            except:
                auction_end = str(row['auction_end']) if row['auction_end'] else None
        
        deal = {
            'bcpea_id': str(row['bcpea_id']),
            'city': city or 'Неизвестен',
            'neighborhood': neighborhood or 'Неизвестен',
            'address': address,
            'sqm': round(size, 1) if size else None,
            'rooms': row['rooms'],
            'floor': row['floor'],
            'property_type': property_type,
            'auction_price': round(auction_price),
            'market_price': round(market_price) if market_price else None,
            'discount_pct': round(discount, 1) if discount is not None else None,
            'savings_eur': round(max(0, savings)) if savings is not None else None,
            'price_per_sqm': round(auction_sqm),
            'auction_end': auction_end,
            'url': f"https://sales.bcpea.org/properties/{row['bcpea_id']}",
            'comparables_count': comparables,
            'comparison_status': comparison_info['status'],
            'comparison_label': comparison_info['label'],
            'comparison_confidence': comparison_info['confidence'],
            'partial_ownership': partial_ownership  # Will be None for included properties
        }
        
        deals.append(deal)
    
    conn.close()
    return deals, excluded_count, excluded_partial, no_comparison_count


def main():
    print(f"=== Exporting Deals - {datetime.utcnow().isoformat()} ===\n")
    
    deals, excluded_count, excluded_partial, no_comparison_count = export_deals(
        min_price=5000, 
        include_no_comparison=True
    )
    
    print(f"Found {len(deals)} deals")
    print(f"  - Excluded: {excluded_count} partial ownership properties")
    print(f"  - No comparison data: {no_comparison_count} properties\n")
    
    if excluded_count > 0:
        print("Excluded partial ownership properties:")
        for ex in excluded_partial[:10]:  # Show first 10
            print(f"  ID {ex['id']}: {ex['city']} - {ex['fraction']} - €{ex['price']:,.0f}")
        if len(excluded_partial) > 10:
            print(f"  ... and {len(excluded_partial) - 10} more")
        print()
    
    if deals:
        # Stats
        cities = {}
        property_types = {}
        comparison_statuses = {}
        discounts = []
        
        for d in deals:
            cities[d['city']] = cities.get(d['city'], 0) + 1
            property_types[d['property_type']] = property_types.get(d['property_type'], 0) + 1
            comparison_statuses[d['comparison_status']] = comparison_statuses.get(d['comparison_status'], 0) + 1
            if d['discount_pct'] is not None and d['discount_pct'] > 0:
                discounts.append(d['discount_pct'])
        
        print("By city:")
        for city, count in sorted(cities.items(), key=lambda x: -x[1])[:10]:
            print(f"  {city}: {count}")
        
        print("\nBy property type:")
        for ptype, count in sorted(property_types.items(), key=lambda x: -x[1]):
            print(f"  {ptype}: {count}")
        
        print("\nBy comparison status:")
        for status, count in sorted(comparison_statuses.items(), key=lambda x: -x[1]):
            label = {
                'matched': 'Based on comparables',
                'estimated': 'Based on estimates',
                'no_comparison': 'No comparison available'
            }.get(status, status)
            print(f"  {label}: {count}")
        
        if discounts:
            avg_discount = sum(discounts) / len(discounts)
            print(f"\nAverage discount (with data): {avg_discount:.1f}%")
        
        # Show sample deals
        print(f"\nTop 5 bargains (with market data):")
        deals_with_data = [d for d in deals if d['discount_pct'] is not None]
        for d in sorted(deals_with_data, key=lambda x: -(x['discount_pct'] or 0))[:5]:
            print(f"  {d['city']}, {d['neighborhood']}: €{d['auction_price']:,} (-{d['discount_pct']}%)")
        
        if no_comparison_count > 0:
            print(f"\nSample properties with no comparison data:")
            no_data_deals = [d for d in deals if d['comparison_status'] == 'no_comparison']
            for d in no_data_deals[:3]:
                print(f"  {d['city']}, {d['neighborhood']}: €{d['auction_price']:,} - {d['comparison_label']}")
    
    # Write JSON to root directory
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(deals, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Exported {len(deals)} deals to {OUTPUT_PATH}")
    if excluded_count > 0:
        print(f"✓ Excluded {excluded_count} partial ownership properties")
    if no_comparison_count > 0:
        print(f"✓ Included {no_comparison_count} properties flagged as 'no comparison available'")
    
    return deals


if __name__ == '__main__':
    main()
