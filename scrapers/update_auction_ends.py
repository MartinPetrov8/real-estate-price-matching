#!/usr/bin/env python3
"""Update auction_end dates for properties that don't have them."""

import sqlite3
import urllib.request
import re
import time
from datetime import datetime

DB_PATH = "/host-workspace/real-estate-price-matching/data/auctions.db"
BASE_URL = "https://sales.bcpea.org"

SROK_PATTERN = re.compile(r'СРОК.*?до\s*(\d{2}\.\d{2}\.\d{4})', re.DOTALL | re.I)

def fetch_url(url):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode('utf-8')
    except Exception as e:
        return None

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM auctions WHERE auction_end IS NULL LIMIT 100")
    ids = [row[0] for row in cursor.fetchall()]
    
    print(f"Updating {len(ids)} properties...")
    updated = 0
    
    for pid in ids:
        url = f"{BASE_URL}/properties/{pid}"
        html = fetch_url(url)
        
        if html:
            match = SROK_PATTERN.search(html)
            if match:
                date_str = match.group(1)
                try:
                    end_date = datetime.strptime(date_str, '%d.%m.%Y')
                    is_expired = 1 if end_date < datetime.now() else 0
                except:
                    is_expired = 0
                
                cursor.execute(
                    "UPDATE auctions SET auction_end = ?, is_expired = ? WHERE id = ?",
                    (date_str, is_expired, pid)
                )
                updated += 1
        
        time.sleep(0.3)  # Rate limiting
    
    conn.commit()
    
    cursor.execute("SELECT COUNT(*) FROM auctions WHERE auction_end IS NOT NULL")
    total_with = cursor.fetchone()[0]
    
    print(f"Updated {updated} records. Total with auction_end: {total_with}")
    conn.close()

if __name__ == "__main__":
    main()
