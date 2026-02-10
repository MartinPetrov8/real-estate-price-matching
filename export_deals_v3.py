#!/usr/bin/env python3
"""
Export Deals v3 - Uses comparisons from auctions.db
Outputs in format compatible with frontend app.js
"""

import json
import sqlite3
from datetime import datetime
import os

DB_PATH = "data/auctions.db"
OUTPUT_PATH = "frontend/deals.json"


def export_deals():
    """Export deals from comparisons table."""
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Join auctions with comparisons
    query = """
        SELECT 
            a.id,
            a.city,
            a.neighborhood,
            a.address,
            a.size_sqm,
            a.rooms,
            a.auction_start,
            a.auction_end,
            a.property_type,
            a.is_partial_ownership,
            c.auction_price,
            c.auction_price_sqm,
            c.market_median_sqm,
            c.market_sample_size,
            c.match_type,
            c.bargain_score,
            c.bargain_rating
        FROM auctions a
        INNER JOIN comparisons c ON a.id = c.auction_id
        WHERE c.market_median_sqm IS NOT NULL
        ORDER BY c.bargain_score DESC
    """
    
    deals = []
    cursor = conn.execute(query)
    
    for row in cursor:
        row = dict(row)
        
        price = row['auction_price'] or 0
        size = row['size_sqm'] or 1
        market_sqm = row['market_median_sqm'] or 0
        is_partial = row['is_partial_ownership']
        score = row['bargain_score'] or 0
        
        # Clean city name
        city = (row['city'] or '').replace('гр. ', '').replace('с. ', '').strip()
        if not city:
            city = 'Неизвестен'
        
        # Clean neighborhood
        neighborhood = (row['neighborhood'] or '').lower().strip()
        if not neighborhood or neighborhood == 'неизвестен':
            neighborhood = ''
        
        # Determine partial ownership string
        partial_str = None
        if is_partial:
            partial_str = "Дробна собственост"
        
        # Score for frontend (1-5 stars)
        if score >= 50:
            stars = 5
        elif score >= 40:
            stars = 5
        elif score >= 30:
            stars = 4
        elif score >= 20:
            stars = 3
        elif score >= 10:
            stars = 2
        else:
            stars = 1
        
        deal = {
            'id': str(row['id']),
            'city': city,
            'neighborhood': neighborhood,
            'address': row['address'] or '',
            'price': round(price),
            'effective_price': round(price),  # Same as price for now
            'sqm': round(size, 1),
            'price_per_sqm': round(row['auction_price_sqm']) if row['auction_price_sqm'] else None,
            'market_avg': round(market_sqm),
            'discount': round(max(0, score), 1),  # Use bargain_score as discount %
            'rooms': row['rooms'],
            'property_type': 'apartment',
            'auction_start': row['auction_start'],
            'auction_end': row['auction_end'],
            'url': f"https://sales.bcpea.org/properties/{row['id']}",
            'partial_ownership': partial_str,
            'score': stars
        }
        
        deals.append(deal)
    
    conn.close()
    return deals


def main():
    print(f"=== Exporting Deals v3 - {datetime.utcnow().isoformat()} ===\n")
    
    deals = export_deals()
    
    # Stats
    valid_deals = [d for d in deals if not d.get('partial_ownership')]
    partial_deals = [d for d in deals if d.get('partial_ownership')]
    bargain_deals = [d for d in valid_deals if d['discount'] >= 15]
    
    print(f"Total apartments with market data: {len(deals)}")
    print(f"Valid (not partial): {len(valid_deals)}")
    print(f"Partial ownership: {len(partial_deals)}")
    print(f"Bargains (15%+ discount): {len(bargain_deals)}\n")
    
    if valid_deals:
        # Stats by city
        print("By city:")
        cities = {}
        for d in deals:
            cities[d['city']] = cities.get(d['city'], 0) + 1
        for city, count in sorted(cities.items(), key=lambda x: -x[1]):
            print(f"  {city}: {count}")
        
        # Top bargains
        print(f"\nTop 5 bargains (not partial):")
        count = 0
        for d in deals:
            if d.get('partial_ownership'):
                continue
            if count >= 5:
                break
            print(f"  {d['city']}: €{d['price']:,} (-{d['discount']:.0f}%)")
            count += 1
    
    # Write JSON
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(deals, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Exported {len(deals)} deals to {OUTPUT_PATH}")
    return deals


if __name__ == '__main__':
    main()
