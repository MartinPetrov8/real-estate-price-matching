#!/usr/bin/env python3
"""
КЧСИ Scraper v5 - With proper timeouts and neighborhood extraction
- Adds socket timeouts to prevent hanging
- Extracts neighborhoods from addresses (ж.к., кв. patterns)
- Better error handling
- NEW: Configurable property type filters (--include-houses, --include-garages, --include-small-towns)
- NEW: Configurable sqm filters (--min-sqm, --max-sqm)
- NEW: Configurable city filtering (--min-population)
"""

import json
import re
import html
import sqlite3
import urllib.request
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys
import socket

BASE_URL = "https://sales.bcpea.org"
DB_PATH = "data/auctions.db"

REQUEST_TIMEOUT = 25
SOCKET_TIMEOUT = 30
MAX_RETRIES = 2

# Major Bulgarian cities with population > 50k (2024 estimates)
MAJOR_CITIES = {
    'софия': 1250000,
    'пловдив': 375000,
    'варна': 325000,
    'бургас': 210000,
    'русе': 145000,
    'стара загора': 140000,
    'плевен': 95000,
    'сливен': 85000,
    'добрич': 80000,
    'шумен': 75000,
    'перник': 70000,
    'хасково': 70000,
    'ямбол': 70000,
    'пазарджик': 65000,
    'благоевград': 65000,
    'велико търново': 65000,
    'враца': 55000,
    'асеновград': 55000,
    'габрово': 50000,
    'кърджали': 55000,
    'кюстендил': 50000,
    'монтана': 50000,
    'търговище': 50000,
}


def is_small_city(city_name, min_population=50000):
    """Check if a city has population below threshold."""
    if not city_name:
        return True  # Unknown cities treated as small
    
    city_clean = city_name.lower().replace('гр. ', '').replace('с. ', '').replace('село ', '').strip()
    
    # Check for exact match
    if city_clean in MAJOR_CITIES:
        return MAJOR_CITIES[city_clean] < min_population
    
    # Check for partial match
    for major_city, pop in MAJOR_CITIES.items():
        if major_city in city_clean or city_clean in major_city:
            return pop < min_population
    
    # Not in major cities list = small town/village
    return True


def extract_neighborhood_from_address(address):
    if not address:
        return None
    addr_lower = address.lower()
    
    jk_patterns = [
        r'ж\.\s*к\.\s*["\']?([а-яА-Я\s\d-]+?)(?:[,;\s]|$)',
        r'жк\s+["\']?([а-яА-Я\s\d-]+?)(?:[,;\s]|$)',
    ]
    
    for pattern in jk_patterns:
        match = re.search(pattern, addr_lower)
        if match:
            hood = match.group(1).strip()
            hood = re.sub(r'\s*бл\.?\s*\d+.*$', '', hood).strip()
            hood = re.sub(r'\s+\d+\s*$', '', hood).strip()
            return hood.capitalize() if hood else None
    
    kv_patterns = [
        r'кв\.\s*["\']?([а-яА-Я\s\d-]+?)(?:[,;\s]|$)',
        r'кв\s+["\']?([а-яА-Я\s\d-]+?)(?:[,;\s]|$)',
    ]
    
    for pattern in kv_patterns:
        match = re.search(pattern, addr_lower)
        if match:
            hood = match.group(1).strip()
            return hood.capitalize() if hood else None
    
    rayon_match = re.search(r'район\s+["\']?([а-яА-Я\s-]+?)(?:[,;\s]|$)', addr_lower)
    if rayon_match:
        return rayon_match.group(1).strip().capitalize()
    
    return None


def extract_rooms(text_lower):
    word_patterns = [
        (r'\bедностаен', 1), (r'\bдвустаен', 2), (r'\bтристаен', 3),
        (r'\bчетиристаен', 4), (r'\bпетстаен', 5), (r'\bшестстаен', 6),
        (r'\bмногостаен', 4), (r'\bгарсониера', 1), (r'\bмезонет', 3),
    ]
    
    for pattern, rooms in word_patterns:
        if re.search(pattern, text_lower):
            return rooms
    
    numeric_match = re.search(r'\b(\d)\s*[-]?\s*ст(?:аен|айн|\.?)', text_lower)
    if numeric_match:
        return int(numeric_match.group(1))
    
    return None


def fetch_detail_with_timeout(prop_id, retries=0):
    try:
        url = f"{BASE_URL}/properties/{prop_id}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(SOCKET_TIMEOUT)
        
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                return parse_detail(prop_id, resp.read().decode('utf-8', errors='ignore'), url)
        finally:
            socket.setdefaulttimeout(old_timeout)
            
    except (socket.timeout, urllib.error.URLError, urllib.error.HTTPError) as e:
        if retries < MAX_RETRIES:
            return fetch_detail_with_timeout(prop_id, retries + 1)
        return None
    except Exception as e:
        return None


def parse_detail(prop_id, html_text, url):
    decoded = html.unescape(html_text)
    
    data = {
        'id': str(prop_id),
        'url': url,
        'scraped_at': datetime.utcnow().isoformat()
    }
    
    price_match = re.search(r'Начална цена</div>.*?<div class="price">([\d\s\xa0,\.]+)', decoded, re.DOTALL)
    if price_match:
        try:
            price_str = price_match.group(1).replace(' ', '').replace('\xa0', '').replace(',', '.')
            price = float(price_str)
            if price > 500:
                data['price_eur'] = price
        except:
            pass
    
    if 'price_eur' not in data:
        return None
    
    city_match = re.search(r'Населено място</div>\s*<div class="info">([^<]+)', decoded)
    if city_match:
        data['city'] = city_match.group(1).strip()
    
    addr_match = re.search(r'Адрес</div>\s*<div class="info">([^<]+)', decoded)
    if addr_match:
        data['address'] = addr_match.group(1).strip()[:300]
    
    # Extract main size (plot/land size for УПИ, total area for apartments)
    size_match = re.search(r'ПЛОЩ</div>\s*<div class="info">([\d\s\.,]+)\s*кв', decoded, re.IGNORECASE)
    if not size_match:
        size_match = re.search(r'class="info">([\d\s\.,]+)\s*кв\.?\s*м', decoded, re.IGNORECASE)
    if size_match:
        try:
            data['size_sqm'] = float(size_match.group(1).replace(' ', '').replace(',', '.'))
        except:
            pass
    
    # For houses with plots (УПИ): extract building size (разгъната застроена площ)
    building_match = re.search(r'разгъната застроена площ.*?([\d\s\.,]+)\s*кв\.?\s*м', decoded, re.IGNORECASE)
    if not building_match:
        building_match = re.search(r'застроена площ.*?([\d\s\.,]+)\s*кв\.?\s*м', decoded, re.IGNORECASE)
    if building_match:
        try:
            data['building_sqm'] = float(building_match.group(1).replace(' ', '').replace(',', '.'))
        except:
            pass
    
    # Extract plot/land size for УПИ (площ по нотариален акт)
    plot_match = re.search(r'площ по нотариален акт.*?([\d\s\.,]+)\s*кв\.?\s*м', decoded, re.IGNORECASE)
    if plot_match:
        try:
            plot_size = float(plot_match.group(1).replace(' ', '').replace(',', '.'))
            data['plot_sqm'] = plot_size
            # For УПИ, use plot as main size if current size is smaller
            if data.get('size_sqm', 0) < plot_size:
                data['size_sqm'] = plot_size
        except:
            pass
    
    court_match = re.search(r'ОКРЪЖЕН СЪД</div>\s*<div class="info">([^<]+)', decoded)
    if court_match:
        data['court'] = court_match.group(1).strip()
    
    period_match = re.search(r'от\s*(\d{2}\.\d{2}\.\d{4})\s*до\s*(\d{2}\.\d{2}\.\d{4})', decoded)
    if period_match:
        data['auction_start'] = period_match.group(1)
        data['auction_end'] = period_match.group(2)
    
    if 'address' in data:
        data['neighborhood'] = extract_neighborhood_from_address(data['address'])
    
    # Detect partial ownership (1/6 ид.ч, 1/2, etc.) - can't compare prices accurately
    text_for_ownership_check = (data.get('address', '') + ' ' + decoded).lower()
    partial_patterns = [
        r'1/\d+\s*ид\.?\s*ч', r'идеална част', r'идеални части',
        r'\d+/\d+\s*ид\.?\s*ч', r'\d+/\d+\s*идеална'
    ]
    data['is_partial_ownership'] = any(re.search(p, text_for_ownership_check) for p in partial_patterns)
    
    text_lower = decoded.lower()
    rooms = extract_rooms(text_lower)
    if rooms:
        data['rooms'] = rooms
    
    # PRIORITY: Check for houses FIRST (before apartments)
    # "еднофамилна" = single-family house, "упи" = regulated plot with house
    if any(x in text_lower for x in ['еднофамилна', 'самостоятелна къща', 'семейна къща', 'къща с двор', 'къща с парцел']):
        data['property_type'] = 'къща'
    elif any(x in text_lower for x in ['упи', 'урегулиран поземлен имот']) and any(x in text_lower for x in ['сграда', 'къща', 'жилищна']):
        data['property_type'] = 'къща'
    elif any(x in text_lower for x in ['жилищна сграда', 'къща', 'вила']):
        data['property_type'] = 'къща'
    elif any(x in text_lower for x in ['самостоятелен обект', 'жилищен етаж', 'жилище,', 'жилище ']):
        data['property_type'] = 'апартамент'
    elif 'апартамент' in text_lower:
        data['property_type'] = 'апартамент'
    elif any(x in text_lower for x in ['гараж', 'паркомясто', 'паркинг']):
        data['property_type'] = 'гараж'
    elif any(x in text_lower for x in ['магазин', 'търговски']):
        data['property_type'] = 'магазин'
    elif any(x in text_lower for x in ['офис', 'кантора']):
        data['property_type'] = 'офис'
    elif any(x in text_lower for x in ['склад', 'складов']):
        data['property_type'] = 'склад'
    elif any(x in text_lower for x in ['хотел', 'ресторант', 'заведение']):
        data['property_type'] = 'търговски'
    elif any(x in text_lower for x in ['поземлен имот', 'земеделска', 'нива', 'парцел']):
        data['property_type'] = 'земя'
    else:
        data['property_type'] = 'друго'
    
    return data


def should_include_property(data, args):
    """
    Determine if a property should be included based on filters.
    Returns (should_include, reason_if_excluded)
    """
    property_type = data.get('property_type', 'друго')
    city = data.get('city', '')
    size_sqm = data.get('size_sqm', 0) or 0
    
    # Check property type filters
    if property_type == 'къща' and not args.include_houses:
        return False, f"House excluded (use --include-houses to include)"
    
    if property_type == 'гараж' and not args.include_garages:
        return False, f"Garage excluded (use --include-garages to include)"
    
    # Check small towns filter
    if not args.include_small_towns:
        if is_small_city(city, min_population=args.min_population):
            return False, f"Small town/village excluded (use --include-small-towns to include)"
    
    # Check size filters
    if size_sqm > 0:
        if size_sqm < args.min_sqm:
            return False, f"Too small ({size_sqm}m² < {args.min_sqm}m²)"
        if size_sqm > args.max_sqm:
            return False, f"Too large ({size_sqm}m² > {args.max_sqm}m²)"
    
    return True, None


def init_db():
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DROP TABLE IF EXISTS auctions")
    conn.execute("""
        CREATE TABLE auctions (
            id TEXT PRIMARY KEY, url TEXT, price_eur REAL, city TEXT, district TEXT,
            neighborhood TEXT, address TEXT, property_type TEXT, size_sqm REAL, building_sqm REAL, plot_sqm REAL, 
            rooms INTEGER, court TEXT, auction_start TEXT, auction_end TEXT, scraped_at DATETIME,
            excluded BOOLEAN DEFAULT 0,
            exclusion_reason TEXT,
            is_partial_ownership BOOLEAN DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX idx_city ON auctions(city)")
    conn.execute("CREATE INDEX idx_type ON auctions(property_type)")
    conn.execute("CREATE INDEX idx_neighborhood ON auctions(neighborhood)")
    conn.execute("CREATE INDEX idx_excluded ON auctions(excluded)")
    conn.commit()
    return conn


def scrape_range(start_id=85000, end_id=85100, workers=10, args=None):
    conn = init_db()
    
    # Track filter settings
    filter_info = {
        'include_houses': args.include_houses if args else False,
        'include_garages': args.include_garages if args else False,
        'include_small_towns': args.include_small_towns if args else False,
        'min_sqm': args.min_sqm if args else 35,
        'max_sqm': args.max_sqm if args else 150,
        'min_population': args.min_population if args else 50000,
    }
    
    print(f"=== КЧСИ Scraper v5 - {datetime.utcnow().isoformat()} ===")
    print(f"Range: {start_id} to {end_id}")
    print(f"Timeouts: Request={REQUEST_TIMEOUT}s, Socket={SOCKET_TIMEOUT}s")
    print(f"Workers: {workers}")
    print(f"\nFilters:")
    print(f"  - Houses: {'included' if filter_info['include_houses'] else 'EXCLUDED'}")
    print(f"  - Garages: {'included' if filter_info['include_garages'] else 'EXCLUDED'}")
    print(f"  - Small towns (<{filter_info['min_population']:,} pop): {'included' if filter_info['include_small_towns'] else 'EXCLUDED'}")
    print(f"  - Size range: {filter_info['min_sqm']}-{filter_info['max_sqm']}m²")
    print()
    
    all_data = []
    included_count = 0
    excluded_count = 0
    excluded_by_reason = {}
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_detail_with_timeout, pid): pid for pid in range(start_id, end_id + 1)}
        
        done = 0
        success = 0
        neighborhoods_found = 0
        
        for future in as_completed(futures):
            done += 1
            
            try:
                data = future.result()
                if data and data.get('price_eur'):
                    all_data.append(data)
                    success += 1
                    
                    if data.get('neighborhood'):
                        neighborhoods_found += 1
                    
                    # Apply filters
                    should_include, exclusion_reason = should_include_property(data, args)
                    
                    if should_include:
                        included_count += 1
                        excluded_flag = 0
                    else:
                        excluded_count += 1
                        excluded_flag = 1
                        excluded_by_reason[exclusion_reason] = excluded_by_reason.get(exclusion_reason, 0) + 1
                    
                    conn.execute("""
                        INSERT OR REPLACE INTO auctions 
                        (id, url, price_eur, city, district, neighborhood, address, property_type, 
                         size_sqm, building_sqm, plot_sqm, rooms, is_partial_ownership, court, auction_start, auction_end, scraped_at, excluded, exclusion_reason)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data.get('id'), data.get('url'), data.get('price_eur'),
                        data.get('city'), data.get('district'), data.get('neighborhood'),
                        data.get('address'), data.get('property_type'), data.get('size_sqm'), 
                        data.get('building_sqm'), data.get('plot_sqm'), data.get('rooms'), data.get('is_partial_ownership', False), data.get('court'), data.get('auction_start'), 
                        data.get('auction_end'), data.get('scraped_at'),
                        excluded_flag, exclusion_reason
                    ))
            except Exception as e:
                pass
            
            if done % 20 == 0:
                conn.commit()
                print(f"  Progress: {done}/{end_id-start_id+1} scanned, {success} valid, {included_count} included, {excluded_count} excluded")
                sys.stdout.flush()
    
    conn.commit()
    
    print(f"\nSCRAPED: {success} listings")
    print(f"  → Included: {included_count}")
    print(f"  → Excluded: {excluded_count}")
    print(f"  → Neighborhoods extracted: {neighborhoods_found}")
    
    if excluded_count > 0:
        print("\nExcluded by reason:")
        for reason, count in sorted(excluded_by_reason.items(), key=lambda x: -x[1]):
            print(f"  - {reason}: {count}")
    
    cursor = conn.cursor()
    
    print("\nBy property type (included only):")
    for row in cursor.execute("""
        SELECT property_type, COUNT(*), ROUND(AVG(price_eur), 0), ROUND(AVG(size_sqm), 0)
        FROM auctions WHERE excluded = 0 GROUP BY property_type ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]:15} : {row[1]:3} listings")
    
    print("\nBy property type (excluded):")
    for row in cursor.execute("""
        SELECT property_type, COUNT(*), ROUND(AVG(price_eur), 0)
        FROM auctions WHERE excluded = 1 GROUP BY property_type ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]:15} : {row[1]:3} listings")
    
    print("\nTop neighborhoods (included only):")
    for row in cursor.execute("""
        SELECT neighborhood, city, COUNT(*), ROUND(AVG(price_eur), 0)
        FROM auctions WHERE neighborhood IS NOT NULL AND excluded = 0
        GROUP BY neighborhood ORDER BY COUNT(*) DESC LIMIT 10
    """):
        print(f"  {row[0]:20} ({row[1]}): {row[2]:3} listings")
    
    conn.close()
    
    with open('data/bcpea_v5.json', 'w', encoding='utf-8') as f:
        json.dump({
            'scraped_at': datetime.utcnow().isoformat(),
            'filters': filter_info,
            'count': len(all_data),
            'included': included_count,
            'excluded': excluded_count,
            'listings': all_data
        }, f, ensure_ascii=False)
    
    print(f"\n✓ Saved to {DB_PATH}")
    print(f"✓ Summary saved to data/bcpea_v5.json")
    return success, neighborhoods_found, included_count, excluded_count


def main():
    parser = argparse.ArgumentParser(
        description='КЧСИ Property Scraper v5 - With configurable filters',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: apartments only, major cities only, 35-150m²
  python bcpea_v5.py
  
  # Include houses and garages
  python bcpea_v5.py --include-houses --include-garages
  
  # Include small towns (under 50k population)
  python bcpea_v5.py --include-small-towns
  
  # Custom size range
  python bcpea_v5.py --min-sqm 20 --max-sqm 200
  
  # Include everything
  python bcpea_v5.py --include-houses --include-garages --include-small-towns
        """
    )
    
    parser.add_argument('--start-id', type=int, default=85000,
                        help='Start property ID (default: 85000)')
    parser.add_argument('--end-id', type=int, default=86000,
                        help='End property ID (default: 85100)')
    parser.add_argument('--workers', type=int, default=10,
                        help='Number of parallel workers (default: 10)')
    
    # Property type filters
    parser.add_argument('--include-houses', action='store_true',
                        help='Include houses (къщи) in results')
    parser.add_argument('--include-garages', action='store_true',
                        help='Include garages and parking (гаражи, паркоместа) in results')
    
    # City population filter
    parser.add_argument('--include-small-towns', action='store_true',
                        help='Include small towns and villages (under --min-population)')
    parser.add_argument('--min-population', type=int, default=50000,
                        help='Minimum city population to include (default: 50000)')
    
    # Size filters
    parser.add_argument('--min-sqm', type=int, default=35,
                        help='Minimum property size in m² (default: 35)')
    parser.add_argument('--max-sqm', type=int, default=150,
                        help='Maximum property size in m² (default: 150)')
    
    args = parser.parse_args()
    
    scrape_range(
        start_id=args.start_id,
        end_id=args.end_id,
        workers=args.workers,
        args=args
    )


if __name__ == '__main__':
    main()
