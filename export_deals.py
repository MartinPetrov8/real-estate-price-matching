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


# Size band boundaries derived from auction property_type distributions.
# Used to restrict market comparables to the same room-count tier.
# Slightly wider than the raw avg to avoid dropping too many listings.
ROOM_TYPE_SIZE_BANDS = {
    'едностаен':   (15,  55),   # 1-bed
    'двустаен':    (40,  90),   # 2-bed
    'тристаен':    (65, 130),   # 3-bed
    'четиристаен': (100, 200),  # 4-bed
    'многостаен':  (100, 600),  # 4+ bed
}

def _room_type_band(property_type_bg: str):
    """Return (min_sqm, max_sqm) size band for a Bulgarian property type string, or None."""
    if not property_type_bg:
        return None
    pt = property_type_bg.lower()
    for key, band in ROOM_TYPE_SIZE_BANDS.items():
        if key in pt:
            return band
    return None


def get_market_median(city, size_sqm, address=None, db_neighborhood=None,
                      size_tolerance=10, property_type_bg=None):
    """Get market median from scraped data with neighborhood matching.
    
    Matching priority:
      1. Hood + size ±10sqm + room-type band  (tightest)
      2. Hood + size ±10sqm                   (no room filter)
      3. Hood + room-type band                (any size in neighborhood)
      4. Hood + any size                      (neighborhood only)
      5. City + size ±10sqm + room-type band  (city fallback, still typed)
      6. City + size ±10sqm                   (city fallback)

    Returns (median, count, matched_hood, match_level)
    match_level: 'hood' | 'city_size' | 'city'
    """
    if not os.path.exists(MARKET_DB):
        return None, 0, None, None

    market_conn = sqlite3.connect(MARKET_DB)
    cursor = market_conn.cursor()

    city_clean = city.replace('гр. ', '').replace('с. ', '').strip() if city else ''
    size_min = size_sqm - size_tolerance
    size_max = size_sqm + size_tolerance
    room_band = _room_type_band(property_type_bg)  # (min_sqm, max_sqm) or None
    
    # Use DB neighborhood (from geocoding) first, fallback to text extraction from address
    # Prepend city for city-scoped street→neighborhood rules (e.g. flower streets → Цветен квартал in Varna)
    auction_hood = db_neighborhood or (
        extract_neighborhood(f"{city}, {address}") if address and city
        else extract_neighborhood(address) if address
        else None
    )

    SIMILARITY_THRESHOLD = 0.7
    MIN_COMPS = 3

    def _fetch_hood(size_clause, size_params):
        """Fetch all market listings for this city with a neighborhood, apply size filter."""
        cursor.execute(f"""
            SELECT price_per_sqm, neighborhood FROM market_listings
            WHERE city = ? AND neighborhood IS NOT NULL
            AND price_per_sqm IS NOT NULL AND price_per_sqm > 200 AND price_per_sqm < 5000
            {size_clause}
        """, [city_clean] + size_params)
        return cursor.fetchall()

    def _match_hood(rows):
        """Filter rows by neighborhood similarity, return matched prices."""
        return [pps for pps, mhood in rows
                if neighborhood_similarity(auction_hood, mhood) >= SIMILARITY_THRESHOLD]

    def _median(prices):
        s = sorted(prices)
        return s[len(s) // 2]

    def _stats(prices):
        """Return (median, min, max) for a price list."""
        s = sorted(prices)
        return s[len(s) // 2], s[0], s[-1]

    if auction_hood:
        # Pass 1: hood + size ±10sqm + room-type band (tightest — all three constraints)
        if room_band:
            band_min = max(size_min, room_band[0])
            band_max = min(size_max, room_band[1])
            rows = _fetch_hood("AND size_sqm BETWEEN ? AND ?", [band_min, band_max])
            prices = _match_hood(rows)
            if len(prices) >= MIN_COMPS:
                market_conn.close()
                return _median(prices), len(prices), auction_hood, 'hood'

        # Pass 2: hood + size ±10sqm (no room filter)
        rows = _fetch_hood("AND size_sqm BETWEEN ? AND ?", [size_min, size_max])
        prices = _match_hood(rows)
        if len(prices) >= MIN_COMPS:
            market_conn.close()
            return _median(prices), len(prices), auction_hood, 'hood'

        # Pass 3: hood + room-type band, any size in neighborhood
        if room_band:
            rows = _fetch_hood("AND size_sqm BETWEEN ? AND ?", list(room_band))
            prices = _match_hood(rows)
            if len(prices) >= MIN_COMPS:
                market_conn.close()
                return _median(prices), len(prices), auction_hood, 'hood'

        # Pass 4: hood + any size (neighborhood signal is still better than city-wide)
        rows = _fetch_hood("", [])
        prices = _match_hood(rows)
        if len(prices) >= MIN_COMPS:
            market_conn.close()
            return _median(prices), len(prices), auction_hood, 'hood'

    # Pass 5: city + size ±10sqm + room-type band (city fallback, typed)
    if room_band:
        band_min = max(size_min, room_band[0])
        band_max = min(size_max, room_band[1])
        cursor.execute("""
            SELECT price_per_sqm FROM market_listings
            WHERE city = ? AND size_sqm BETWEEN ? AND ?
            AND price_per_sqm IS NOT NULL AND price_per_sqm > 200 AND price_per_sqm < 5000
        """, (city_clean, band_min, band_max))
        results = [r[0] for r in cursor.fetchall()]
        if len(results) >= MIN_COMPS:
            market_conn.close()
            return _median(results), len(results), None, 'city_size'

    # Pass 6: city + size ±10sqm
    cursor.execute("""
        SELECT price_per_sqm FROM market_listings
        WHERE city = ? AND size_sqm BETWEEN ? AND ?
        AND price_per_sqm IS NOT NULL AND price_per_sqm > 200 AND price_per_sqm < 5000
    """, (city_clean, size_min, size_max))
    results = [r[0] for r in cursor.fetchall()]
    if len(results) >= MIN_COMPS:
        market_conn.close()
        return _median(results), len(results), None, 'city_size'

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
        
        market_min_sqm = None
        market_max_sqm = None
        
        if is_apartment and not is_partial:
            market_median, sample_size, matched_hood, match_level = get_market_median(
                city, size, row['address'], db_neighborhood=row.get('neighborhood'),
                property_type_bg=row.get('property_type')
            )
            if market_median and sample_size >= 3:
                market_avg = round(market_median)
                price_per_sqm = price / size
                discount = round(((market_median - price_per_sqm) / market_median) * 100, 1)
                if discount < 0:
                    discount = None  # Negative = overpriced, don't show unreliable discount
                # Get min/max from same comparables (quick re-query)
                try:
                    _mconn = sqlite3.connect(MARKET_DB)
                    _mc = _mconn.cursor()
                    city_c = city.replace('гр. ', '').replace('с. ', '').strip()
                    _mc.execute("""
                        SELECT MIN(price_per_sqm), MAX(price_per_sqm) FROM market_listings
                        WHERE city = ? AND price_per_sqm IS NOT NULL AND price_per_sqm > 200 AND price_per_sqm < 5000
                        AND size_sqm BETWEEN ? AND ?
                    """, (city_c, size - 10, size + 10))
                    _r = _mc.fetchone()
                    if _r and _r[0]:
                        market_min_sqm = round(_r[0])
                        market_max_sqm = round(_r[1])
                    _mconn.close()
                except Exception:
                    pass
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
            'market_min_sqm': market_min_sqm,
            'market_max_sqm': market_max_sqm,
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
    
    # Write JSON — include metadata for UI trust signals
    output = {
        'generated_at': datetime.utcnow().strftime('%d.%m.%Y'),
        'sources': ['imot.bg', 'olx.bg'],
        'deals': deals,
    }
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Exported {len(deals)} deals to {OUTPUT_PATH}")
    return deals


if __name__ == '__main__':
    main()
