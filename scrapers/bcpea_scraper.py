#!/usr/bin/env python3
"""
КЧСИ Scraper v6 - Smart Listing-Based Scraper

LOGIC:
1. First run (--full): Scrape ALL active auctions from court listing pages
2. Daily runs (--incremental): Only fetch NEW properties, mark EXPIRED ones
3. NO ID range guessing - we scrape what exists on the website
"""

import json
import re
import html
import sqlite3
import urllib.request
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

_db_lock = threading.Lock()
import os
import sys
import socket
import time

BASE_URL = "https://sales.bcpea.org"
DB_PATH = "data/auctions.db"

REQUEST_TIMEOUT = 25
MAX_RETRIES = 2
MAX_WORKERS = 4  # Reduced for rate limiting

COURTS = {
    1: "Благоевград", 2: "Бургас", 3: "Варна", 4: "Велико Търново",
    5: "Видин", 6: "Враца", 7: "Габрово", 8: "Добрич",
    9: "Кърджали", 10: "Кюстендил", 11: "Ловеч", 12: "Монтана",
    13: "Пазарджик", 14: "Перник", 15: "Плевен", 16: "Пловдив",
    17: "Разград", 18: "Русе", 19: "Силистра", 20: "Сливен",
    21: "Смолян", 22: "Стара Загора", 23: "Търговище", 24: "Хасково",
    25: "Шумен", 26: "Ямбол", 27: "София окръг", 28: "София град",
}

# Pre-compiled regex patterns (thread-safe)
SROK_PATTERN = re.compile(r'СРОК.*?до\s*(\d{2}\.\d{2}\.\d{4})', re.DOTALL | re.I)
KRAI_PATTERN = re.compile(r'Край[^:]*:?\s*(\d{2}\.\d{2}\.\d{4})')

def log(msg):
    print(msg)
    sys.stdout.flush()

def fetch_url(url, retries=0):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        })
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read().decode('utf-8')
    except Exception as e:
        if retries < MAX_RETRIES:
            time.sleep(1)
            return fetch_url(url, retries + 1)
        return None


def extract_property_ids_from_listing(court_id):
    url = f"{BASE_URL}/properties?court={court_id}&perpage=500"
    html_content = fetch_url(url)
    if not html_content:
        return []
    ids = re.findall(r'href="/properties/(\d+)"', html_content)
    return list(set(int(id) for id in ids))


def parse_property_detail(html_content, prop_id):
    if not html_content:
        return None
    
    data = {
        'id': prop_id,
        'url': f"{BASE_URL}/properties/{prop_id}",
        'scraped_at': datetime.utcnow().isoformat(),
    }
    
    # Price
    price_match = re.search(r'<div class="price">([\d\s&;nbsp\.]+)\s*(EUR|лв)', html_content)
    if price_match:
        price_str = re.sub(r'&nbsp;|\s', '', price_match.group(1))
        try:
            price = float(price_str)
            if 'лв' in price_match.group(2):
                price = round(price / 1.96, 2)
            data['price_eur'] = price
        except (ValueError, TypeError):
            pass
    
    # Property type - look after </ul> to skip dropdown options
    # The property type appears in the detail section, after the search form
    type_match = re.search(r'</ul>\s*</div>\s*<div class="title">([^<]+)</div>\s*<div class="date">', html_content, re.DOTALL)
    if type_match:
        data['property_type'] = type_match.group(1).strip()
    else:
        # Fallback: look for property type near "Публикувано"
        type_match = re.search(r'<div class="title">([^<]*(?:апартамент|къща|гараж|вила|парцел|земя|магазин|офис|ателие|склад|земеделска)[^<]*)</div>\s*<div class="(?:date|category)">', html_content, re.I)
        if type_match:
            data['property_type'] = type_match.group(1).strip()
    
    # City
    city_match = re.search(r'(гр\.\s*[А-Яа-я\s-]+|с\.\s*[А-Яа-я\s-]+)', html_content)
    if city_match:
        data['city'] = city_match.group(1).strip().rstrip(',').rstrip('<')
    
    # Address - extract clean address, reject HTML/URLs
    addr_match = re.search(r'Адрес[^:]*:\s*([^<]+)', html_content)
    if addr_match:
        addr_raw = html.unescape(addr_match.group(1).strip())
        # Validate: must contain Cyrillic, reject URLs and garbage
        if re.search(r'[А-Яа-я]', addr_raw) and not re.search(r'https?://', addr_raw) and len(addr_raw) > 2:
            data['address'] = addr_raw
        else:
            data['address'] = None
    
    # Size
    size_match = re.search(r'(\d+(?:[,\.]\d+)?)\s*(?:кв\.?\s*м|м2|m2)', html_content, re.I)
    if size_match:
        data['size_sqm'] = float(size_match.group(1).replace(',', '.'))
    
    # Floor - extract from description/address only (not navigation/forms)
    # Look for "ет.X" pattern in the info/description div
    desc_section = re.search(r'<div class="info">(.*?)</div>', html_content, re.DOTALL)
    if desc_section:
        floor_match = re.search(r'(?:ет\.\s*|етаж\s+)(\d{1,2})(?!\d)', desc_section.group(1), re.I)
        if floor_match:
            floor_val = int(floor_match.group(1))
            if 0 < floor_val <= 30:  # Sanity check
                data['floor'] = floor_val
    # Rooms
    rooms_match = re.search(r'(\d+)\s*(?:-?стаен|стаи|стая)', html_content, re.I)
    if rooms_match:
        data['rooms'] = int(rooms_match.group(1))
    
    # Auction end - look for "СРОК" section with "от DD.MM.YYYY до DD.MM.YYYY"
    # The end date is after "до"
    srok_match = SROK_PATTERN.search(html_content)
    if srok_match:
        data['auction_end'] = srok_match.group(1)
        try:
            end_date = datetime.strptime(srok_match.group(1), '%d.%m.%Y')
            data['is_expired'] = end_date < datetime.now()
        except:
            data['is_expired'] = False
    else:
        # Fallback: try "Край" pattern
        end_match = KRAI_PATTERN.search(html_content)
        if end_match:
            data['auction_end'] = end_match.group(1)
            try:
                end_date = datetime.strptime(end_match.group(1), '%d.%m.%Y')
                data['is_expired'] = end_date < datetime.now()
            except ValueError:
                data['is_expired'] = False
        else:
            data['is_expired'] = False
    
    # Partial ownership
    data['is_partial_ownership'] = bool(re.search(
        r'¼|½|¾|⅓|⅔|\d+/\d+\s*(?:ид|ід)|идеална\s*част|ідеална\s*част', 
        html_content, re.I
    ))
    
    return data


def fetch_property_detail(prop_id):
    url = f"{BASE_URL}/properties/{prop_id}"
    html_content = fetch_url(url)
    if not html_content:
        return None
    return parse_property_detail(html_content, prop_id)


def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auctions (
            id INTEGER PRIMARY KEY,
            url TEXT,
            price_eur REAL,
            city TEXT,
            neighborhood TEXT,
            address TEXT,
            property_type TEXT,
            size_sqm REAL,
            rooms INTEGER,
            floor INTEGER,
            is_partial_ownership INTEGER DEFAULT 0,
            is_expired INTEGER DEFAULT 0,
            court TEXT,
            auction_start TEXT,
            auction_end TEXT,
            scraped_at TEXT,
            first_seen_at TEXT,
            last_updated_at TEXT
        )
    """)
    conn.commit()
    return conn


def run_full_scan():
    log("=== КЧСИ Scraper v6 - Full Scan ===")
    log(f"Started: {datetime.utcnow().isoformat()}")
    
    # Step 1: Collect IDs
    log("\nStep 1: Collecting property IDs...")
    all_ids = set()
    
    for court_id, court_name in COURTS.items():
        ids = extract_property_ids_from_listing(court_id)
        all_ids.update(ids)
        if ids:
            log(f"  Court {court_id} ({court_name}): {len(ids)}")
    
    log(f"\nTotal: {len(all_ids)} properties")
    
    # Step 2: Fetch and save
    log("\nStep 2: Fetching details...")
    conn = init_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM auctions")
    conn.commit()
    
    now = datetime.utcnow().isoformat()
    fetched = 0
    active = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_property_detail, pid): pid for pid in all_ids}
        
        for future in as_completed(futures):
            try:
                data = future.result()
                if data:
                    fetched += 1
                    if not data.get('is_expired'):
                        active += 1
                    
                    with _db_lock:
                        cursor.execute("""
                            INSERT INTO auctions 
                            (id, url, price_eur, city, address, property_type, size_sqm, rooms, floor,
                             is_partial_ownership, is_expired, auction_end, scraped_at, first_seen_at, last_updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            data['id'], data.get('url'), data.get('price_eur'), data.get('city'),
                            data.get('address'), data.get('property_type'), data.get('size_sqm'),
                            data.get('rooms'), data.get('floor'), int(data.get('is_partial_ownership', False)),
                            int(data.get('is_expired', False)), data.get('auction_end'), now, now, now
                        ))
                        
                        # Commit every 50 records
                        if fetched % 50 == 0:
                            conn.commit()
                    if fetched % 50 == 0:
                        log(f"  Progress: {fetched}/{len(all_ids)} ({active} active)")
            except Exception as e:
                log(f"  Error processing property {futures[future]}: {e}")
    
    conn.commit()
    
    # Summary
    log(f"\n=== Summary ===")
    cursor.execute("SELECT COUNT(*) FROM auctions WHERE is_expired = 0")
    log(f"Active: {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT property_type, COUNT(*) FROM auctions WHERE is_expired = 0 GROUP BY property_type ORDER BY COUNT(*) DESC")
    log("\nBy type:")
    for row in cursor.fetchall():
        log(f"  {row[0] or 'Unknown'}: {row[1]}")
    
    cursor.execute("SELECT city, COUNT(*) FROM auctions WHERE is_expired = 0 GROUP BY city ORDER BY COUNT(*) DESC LIMIT 10")
    log("\nBy city:")
    for row in cursor.fetchall():
        log(f"  {row[0] or 'Unknown'}: {row[1]}")
    
    conn.close()
    log(f"\n✓ Saved to {DB_PATH}")


def run_incremental_scan():
    log("=== КЧСИ v6 - Incremental ===")
    
    conn = init_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM auctions WHERE is_expired = 0")
    existing = set(row[0] for row in cursor.fetchall())
    log(f"Tracking: {len(existing)} active")
    
    # Get current
    current = set()
    for court_id in COURTS:
        current.update(extract_property_ids_from_listing(court_id))
    log(f"Website: {len(current)} properties")
    
    new_ids = current - existing
    expired_ids = existing - current
    log(f"New: {len(new_ids)} | Expired: {len(expired_ids)}")
    
    now = datetime.utcnow().isoformat()
    
    # Fetch new
    if new_ids:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for future in as_completed({executor.submit(fetch_property_detail, pid): pid for pid in new_ids}):
                data = future.result()
                if data and not data.get('is_expired'):
                    with _db_lock:
                        cursor.execute("""
                            INSERT INTO auctions 
                            (id, url, price_eur, city, address, property_type, size_sqm, rooms, floor,
                             is_partial_ownership, is_expired, auction_end, scraped_at, first_seen_at, last_updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            data['id'], data.get('url'), data.get('price_eur'), data.get('city'),
                            data.get('address'), data.get('property_type'), data.get('size_sqm'),
                            data.get('rooms'), data.get('floor'), int(data.get('is_partial_ownership', False)), 0,
                            data.get('auction_end'), now, now, now
                        ))
    
    # Mark expired
    for pid in expired_ids:
        cursor.execute("UPDATE auctions SET is_expired = 1, last_updated_at = ? WHERE id = ?", (now, pid))
    
    conn.commit()
    
    cursor.execute("SELECT COUNT(*) FROM auctions WHERE is_expired = 0")
    log(f"Active now: {cursor.fetchone()[0]}")
    conn.close()
    log("✓ Done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--incremental", action="store_true")
    args = parser.parse_args()
    
    os.makedirs("data", exist_ok=True)
    
    if args.full:
        run_full_scan()
    else:
        run_incremental_scan()
