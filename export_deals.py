#!/usr/bin/env python3
"""Export deals to frontend-compatible JSON format.

Outputs to deals.json (root) for GitHub Pages
Uses deal_matches when available, falls back to neighborhood estimates.
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


def get_market_rate(city, address):
    """Get estimated market price per sqm for a city/neighborhood."""
    city_lower = city.lower() if city else ''
    
    # Try specific neighborhood caps first
    caps = get_price_cap(city, address)
    if caps['median'] != 1200:  # Default value was changed
        return caps['median']
    
    # Fall back to city average
    for key, rate in CITY_MARKET_RATES.items():
        if key in city_lower:
            return rate
    
    # Default fallback
    return 1000


def column_exists(conn, table, column):
    """Check if a column exists in a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def export_deals(min_price=10000):
    """Export deals - includes only FULL ownership properties with market estimates.
    
    Args:
        min_price: Minimum auction price in EUR
    """
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Check if partial_ownership column exists
    has_partial_column = column_exists(conn, 'kchsi_properties', 'partial_ownership')
    
    # Get all KCHSI properties with their match data (if available)
    # EXCLUDE partial ownership properties
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
              AND k.sqm BETWEEN 30 AND 200
              AND k.partial_ownership IS NULL
            GROUP BY k.id
            ORDER BY avg_savings_pct DESC
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
              AND k.sqm BETWEEN 30 AND 200
            GROUP BY k.id
            ORDER BY avg_savings_pct DESC
        """
    
    deals = []
    excluded_count = 0
    excluded_partial = []
    
    for row in conn.execute(query, (min_price,)):
        row = dict(row)
        
        auction_price = row['price_eur'] or 0
        size = row['sqm'] or 1
        description = row['description'] or ''
        
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
        else:
            # Fallback: use neighborhood/city estimates
            market_sqm = get_market_rate(city, address)
            market_price = size * market_sqm
            savings = market_price - auction_price
            discount = ((market_price - auction_price) / market_price * 100) if market_price > 0 else 0
        
        # Cap discount at realistic level
        discount = min(discount, MAX_REALISTIC_DISCOUNT)
        
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
            'property_type': 'апартамент',  # Default for now
            'auction_price': round(auction_price),
            'market_price': round(market_price),
            'discount_pct': round(discount, 1),
            'savings_eur': round(max(0, savings)),
            'price_per_sqm': round(auction_sqm),
            'auction_end': auction_end,
            'url': f"https://sales.bcpea.org/properties/{row['bcpea_id']}",
            'comparables_count': comparables,
            'partial_ownership': partial_ownership  # Will be None for included properties
        }
        
        deals.append(deal)
    
    conn.close()
    return deals, excluded_count, excluded_partial


def main():
    print(f"=== Exporting Deals - {datetime.utcnow().isoformat()} ===\n")
    
    deals, excluded_count, excluded_partial = export_deals(min_price=5000)
    
    print(f"Found {len(deals)} deals (excluded {excluded_count} partial ownership properties)\n")
    
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
        discounts = []
        for d in deals:
            cities[d['city']] = cities.get(d['city'], 0) + 1
            if d['discount_pct'] > 0:
                discounts.append(d['discount_pct'])
        
        print("By city:")
        for city, count in sorted(cities.items(), key=lambda x: -x[1]):
            print(f"  {city}: {count}")
        
        avg_discount = sum(discounts) / len(discounts) if discounts else 0
        print(f"\nAverage discount: {avg_discount:.1f}%")
        
        print(f"\nTop 5 bargains:")
        for d in sorted(deals, key=lambda x: -x['discount_pct'])[:5]:
            print(f"  {d['city']}, {d['neighborhood']}: €{d['auction_price']:,} (-{d['discount_pct']}%)")
    
    # Write JSON to root directory
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(deals, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Exported {len(deals)} deals to {OUTPUT_PATH}")
    if excluded_count > 0:
        print(f"✓ Excluded {excluded_count} partial ownership properties")
    
    return deals


if __name__ == '__main__':
    main()
