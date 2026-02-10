#!/usr/bin/env python3
"""Quick patch script to update auction_end dates for existing records."""

import sqlite3
import urllib.request
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

DB_PATH = "../data/auctions.db"
BASE_URL = "https://sales.bcpea.org"

SROK_PATTERN = re.compile(r'СРОК.*?до\s*(\d{2}\.\d{2}\.\d{4})', re.DOTALL | re.I)

def fetch_url(url):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode('utf-8')
    except:
        return None

def get_auction_end(prop_id):
    url = f"{BASE_URL}/properties/{prop_id}"
    html = fetch_url(url)
    if not html:
        return None, None
    
    match = SROK_PATTERN.search(html)
    if match:
        date_str = match.group(1)
        try:
            end_date = datetime.strptime(date_str, '%d.%m.%Y')
            is_expired = end_date < datetime.now()
            return date_str, is_expired
        except:
            return date_str, False
    return None, None

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get IDs without auction_end
    cursor.execute("SELECT id FROM auctions WHERE auction_end IS NULL")
    ids = [row[0] for row in cursor.fetchall()]
    print(f"Patching {len(ids)} records...")
    
    updated = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(get_auction_end, pid): pid for pid in ids}
        
        for i, future in enumerate(as_completed(futures)):
            pid = futures[future]
            try:
                date_str, is_expired = future.result()
                if date_str:
                    cursor.execute(
                        "UPDATE auctions SET auction_end = ?, is_expired = ? WHERE id = ?",
                        (date_str, int(is_expired) if is_expired is not None else 0, pid)
                    )
                    updated += 1
                    
                if (i + 1) % 50 == 0:
                    conn.commit()
                    print(f"  Progress: {i+1}/{len(ids)} ({updated} updated)")
            except Exception as e:
                pass
    
    conn.commit()
    print(f"\n✓ Updated {updated}/{len(ids)} records")
    
    # Show results
    cursor.execute("SELECT COUNT(*) FROM auctions WHERE auction_end IS NOT NULL")
    print(f"Total with auction_end: {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT COUNT(*) FROM auctions WHERE is_expired = 1")
    print(f"Marked expired: {cursor.fetchone()[0]}")
    
    conn.close()

if __name__ == "__main__":
    main()
