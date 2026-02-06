#!/usr/bin/env python3
"""
Export deals to frontend-compatible JSON format.

Joins auctions with comparisons and outputs to frontend/deals.json
Uses neighborhood-aware pricing caps for accurate estimates.
"""

import json
import re
import sqlite3
from datetime import datetime
import os
import sys

# Add scrapers to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scrapers'))
from neighborhood_caps import get_price_cap, extract_neighborhood as extract_hood, is_valid_apartment, MAX_REALISTIC_DISCOUNT

DB_PATH = "data/auctions.db"
OUTPUT_PATH = "frontend/deals.json"


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


def export_deals(min_score=15, min_price=10000, min_comparables=3):
    """Export deals with bargain score >= min_score.
    
    Args:
        min_score: Minimum bargain score (% below market)
        min_price: Minimum auction price in EUR (filters out rural junk)
        min_comparables: Minimum number of market comparables for validity
    """
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Join auctions with comparisons - filter for quality and realistic discounts
    query = """
        SELECT 
            a.id, a.url, a.city, a.address, a.district,
            a.property_type, a.size_sqm, a.rooms, a.auction_end,
            c.auction_price, c.market_median_sqm, c.market_count,
            c.deviation_pct, c.bargain_score
        FROM auctions a
        JOIN comparisons c ON a.id = c.auction_id
        WHERE c.bargain_score >= ?
          AND c.bargain_score <= ?
          AND c.auction_price >= ?
          AND a.size_sqm BETWEEN 35 AND 150
        ORDER BY c.bargain_score DESC
    """
    
    deals = []
    for row in conn.execute(query, (min_score, MAX_REALISTIC_DISCOUNT, min_price)):
        row = dict(row)
        
        # Calculate prices with neighborhood-aware caps
        auction_price = row['auction_price'] or 0
        size = row['size_sqm'] or 1
        raw_market_sqm = row['market_median_sqm'] or 0
        
        # Clean city name
        city = (row['city'] or '').replace('гр. ', '').replace('с. ', '').strip()
        address = row['address'] or ''
        
        # Get realistic price cap for this neighborhood
        caps = get_price_cap(row['city'] or '', address)
        
        # Apply cap if market estimate is unrealistic
        if raw_market_sqm > caps['max']:
            market_sqm = caps['median']  # Use neighborhood median
            price_capped = True
        elif raw_market_sqm < caps['min']:
            market_sqm = caps['median']  # Use neighborhood median
            price_capped = True
        else:
            market_sqm = raw_market_sqm
            price_capped = False
        
        market_price = size * market_sqm
        savings = market_price - auction_price
        auction_sqm = auction_price / size if size > 0 else 0
        
        # Recalculate discount based on capped price, and cap at MAX_REALISTIC_DISCOUNT
        raw_discount = ((market_sqm - auction_sqm) / market_sqm * 100) if market_sqm > 0 else 0
        discount = min(raw_discount, MAX_REALISTIC_DISCOUNT)
        
        # Extract neighborhood
        neighborhood = row['district'] or extract_neighborhood(row['address'], city)
        
        # Format auction end date
        auction_end = None
        if row['auction_end']:
            try:
                # Parse Bulgarian date format DD.MM.YYYY
                dt = datetime.strptime(row['auction_end'], '%d.%m.%Y')
                auction_end = dt.strftime('%Y-%m-%dT23:59:59Z')
            except:
                auction_end = row['auction_end']
        
        deal = {
            'bcpea_id': str(row['id']),
            'city': city or 'Неизвестен',
            'neighborhood': neighborhood or 'Неизвестен',
            'sqm': round(size, 1) if size else None,
            'rooms': row['rooms'],
            'floor': None,  # Not in current schema
            'property_type': row['property_type'] or 'Имот',
            'auction_price': round(auction_price),
            'auction_price_sqm': round(auction_sqm),
            'market_price': round(market_price),
            'market_price_sqm': round(market_sqm),
            'discount_pct': round(discount),
            'savings_eur': round(max(0, savings)),  # Don't show negative savings
            'auction_end': auction_end,
            'market_url': None,  # Could link to OLX search
            'comparables_count': row['market_count'],
            'price_capped': price_capped,  # True if we used neighborhood cap
            'neighborhood_range': f"€{caps['min']}-{caps['max']}/m²"
        }
        
        deals.append(deal)
    
    conn.close()
    return deals


def main():
    print(f"=== Exporting Deals - {datetime.utcnow().isoformat()} ===\n")
    
    deals = export_deals(min_score=15)
    
    print(f"Found {len(deals)} deals with score >= 15%\n")
    
    if deals:
        # Stats
        cities = {}
        for d in deals:
            cities[d['city']] = cities.get(d['city'], 0) + 1
        
        print("By city:")
        for city, count in sorted(cities.items(), key=lambda x: -x[1])[:10]:
            print(f"  {city}: {count}")
        
        print(f"\nTop 5 bargains:")
        for d in deals[:5]:
            print(f"  {d['city']}, {d['neighborhood']}: €{d['auction_price']:,} (-{d['discount_pct']}%)")
    
    # Ensure frontend directory exists
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    
    # Write JSON
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(deals, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Exported {len(deals)} deals to {OUTPUT_PATH}")
    
    return deals


if __name__ == '__main__':
    main()
