#!/usr/bin/env python3
"""
Export Deals v2 - Uses neighborhood-aware comparisons
Exports to deals.json for GitHub Pages frontend
Includes properties WITHOUT market data (flagged as "no comparison available")
"""

import json
import sqlite3
from datetime import datetime
import os

DB_PATH = "data/auctions.db"
OUTPUT_PATH = "deals.json"


def format_auction_end(date_str):
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, '%d.%m.%Y')
        return dt.strftime('%Y-%m-%d')
    except:
        pass
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return date_str
    except:
        pass
    return str(date_str) if date_str else None


def export_deals():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Include ALL properties, even without market comparison data
    query = """
        SELECT 
            a.id as bcpea_id,
            a.city,
            a.neighborhood,
            a.address,
            a.size_sqm,
            a.rooms,
            a.auction_end,
            a.property_type,
            c.auction_price,
            c.auction_price_sqm,
            c.market_median_sqm,
            c.market_sample_size,
            c.match_type,
            c.deviation_pct,
            c.bargain_score,
            c.bargain_rating
        FROM auctions a
        LEFT JOIN comparisons c ON a.id = c.auction_id
        WHERE a.property_type = 'апартамент'
        AND a.size_sqm BETWEEN 20 AND 500
        ORDER BY 
            CASE WHEN c.bargain_score IS NOT NULL THEN c.bargain_score ELSE -999 END DESC,
            a.price_eur DESC
    """
    
    deals = []
    cursor = conn.execute(query)
    
    for row in cursor:
        row = dict(row)
        
        auction_price = row['auction_price'] or 0
        size = row['size_sqm'] or 1
        market_sqm = row['market_median_sqm']
        has_market_data = market_sqm is not None
        
        if has_market_data:
            market_price = market_sqm * size
            discount = row['bargain_score'] or 0
            savings = market_price - auction_price
            match_type = row['match_type'] or 'Unknown'
            bargain_rating = row['bargain_rating'] or 'NO_DATA'
        else:
            # No market data available
            market_price = None
            discount = 0
            savings = 0
            match_type = 'Няма данни за пазара'
            bargain_rating = 'NO_COMPARISON'
        
        city = (row['city'] or '').replace('гр. ', '').replace('с. ', '').strip()
        if not city:
            city = 'Неизвестен'
        
        deal = {
            'bcpea_id': str(row['bcpea_id']),
            'city': city,
            'neighborhood': row['neighborhood'] or 'Неизвестен',
            'address': row['address'] or '',
            'sqm': round(size, 1),
            'rooms': row['rooms'],
            'property_type': row['property_type'] or 'апартамент',
            'auction_price': round(auction_price),
            'market_price': round(market_price) if market_price else None,
            'discount_pct': round(discount, 1),
            'savings_eur': round(max(0, savings)) if savings else 0,
            'auction_price_sqm': round(row['auction_price_sqm'], 0) if row['auction_price_sqm'] else None,
            'market_price_sqm': round(market_sqm, 0) if market_sqm else None,
            'auction_end': format_auction_end(row['auction_end']),
            'url': f"https://sales.bcpea.org/properties/{row['bcpea_id']}",
            'market_sample_size': row['market_sample_size'] or 0,
            'match_type': match_type,
            'bargain_rating': bargain_rating,
            'has_market_comparison': has_market_data
        }
        
        deals.append(deal)
    
    conn.close()
    return deals


def main():
    print(f"=== Exporting Deals v2 - {datetime.utcnow().isoformat()} ===\n")
    
    deals = export_deals()
    
    deals_with_data = [d for d in deals if d['has_market_comparison']]
    deals_without_data = [d for d in deals if not d['has_market_comparison']]
    
    print(f"Total apartments: {len(deals)}")
    print(f"With market data: {len(deals_with_data)}")
    print(f"Without market data: {len(deals_without_data)}")
    
    if deals_with_data:
        print("\nBy city (with market data):")
        cities = {}
        for d in deals_with_data:
            cities[d['city']] = cities.get(d['city'], 0) + 1
        for city, count in sorted(cities.items(), key=lambda x: -x[1]):
            print(f"  {city}: {count}")
        
        print(f"\nTop bargains (with market data):")
        for d in deals_with_data[:5]:
            hood_str = f", {d['neighborhood']}" if d['neighborhood'] != 'Неизвестен' else ""
            print(f"  {d['city']}{hood_str}: €{d['auction_price']:,} (-{d['discount_pct']}%, {d['match_type']})")
    
    if deals_without_data:
        print(f"\nProperties without market comparison:")
        cities_no_data = {}
        for d in deals_without_data:
            cities_no_data[d['city']] = cities_no_data.get(d['city'], 0) + 1
        for city, count in sorted(cities_no_data.items(), key=lambda x: -x[1])[:10]:
            print(f"  {city}: {count}")
    
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(deals, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Exported {len(deals)} deals to {OUTPUT_PATH}")
    return deals


if __name__ == '__main__':
    main()
