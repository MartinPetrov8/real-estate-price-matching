#!/usr/bin/env python3
"""
Export deals to frontend-compatible JSON format.

Joins auctions with comparisons and outputs to frontend/deals.json
"""

import json
import re
import sqlite3
from datetime import datetime
import os

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
    
    # Join auctions with comparisons - filter for quality
    query = """
        SELECT 
            a.id, a.url, a.city, a.address, a.district,
            a.property_type, a.size_sqm, a.rooms, a.auction_end,
            c.auction_price, c.market_median_sqm, c.market_count,
            c.deviation_pct, c.bargain_score
        FROM auctions a
        JOIN comparisons c ON a.id = c.auction_id
        WHERE c.bargain_score >= ?
          AND c.auction_price >= ?
          AND c.market_count >= ?
        ORDER BY c.bargain_score DESC
    """
    
    deals = []
    for row in conn.execute(query, (min_score, min_price, min_comparables)):
        row = dict(row)
        
        # Calculate prices
        auction_price = row['auction_price'] or 0
        size = row['size_sqm'] or 1
        market_sqm = row['market_median_sqm'] or 0
        market_price = size * market_sqm
        savings = market_price - auction_price
        discount = abs(row['deviation_pct']) if row['deviation_pct'] else 0
        
        # Clean city name
        city = (row['city'] or '').replace('гр. ', '').replace('с. ', '').strip()
        
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
            'market_price': round(market_price),
            'discount_pct': round(discount),
            'savings_eur': round(savings),
            'auction_end': auction_end,
            'market_url': None,  # Could link to OLX search
            'comparables_count': row['market_count']
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
