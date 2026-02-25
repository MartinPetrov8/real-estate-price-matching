#!/usr/bin/env python3
"""
One-time backfill: re-fetch addresses for active auctions that have bad/missing address data.
Targets records where address IS NULL, empty, or looks like garbage (no Cyrillic, too short).
Uses 4 threads for speed. Run once, then geocode_neighborhoods.py takes over.
"""

import sqlite3
import sys
import os
import re
import html
import time
import urllib.request
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'auctions.db')
_db_lock = threading.Lock()


def extract_address_from_html(html_content: str) -> str | None:
    addr_match = re.search(
        r'<div[^>]*class="label"[^>]*>\s*Адрес\s*</div>\s*<div[^>]*class="info"[^>]*>(.*?)</div>',
        html_content, re.DOTALL | re.IGNORECASE
    )
    if addr_match:
        addr_raw = re.sub(r'<[^>]+>', '', addr_match.group(1))
        addr_raw = html.unescape(addr_raw).strip()
        if re.search(r'[А-Яа-я]', addr_raw) and len(addr_raw) > 3:
            return addr_raw
    return None


def fetch_and_update(auction_id: int, url: str) -> tuple[int, str | None]:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode('utf-8', errors='replace')
        address = extract_address_from_html(content)
        return auction_id, address
    except Exception as e:
        return auction_id, None


def main():
    db = sqlite3.connect(DB_PATH)

    # Target: active auctions with missing or clearly bad address
    rows = db.execute("""
        SELECT id, url FROM auctions
        WHERE is_expired = 0
          AND property_type NOT IN ('Земеделска земя', 'Парцел', 'none')
          AND (
            address IS NULL
            OR address = ''
            OR (LENGTH(address) < 5 AND address NOT GLOB '*[А-Яа-я]*')
          )
        ORDER BY id
    """).fetchall()

    db.close()
    total = len(rows)
    print(f"Auctions with missing/bad address: {total}")
    print("Re-fetching from BCPEA...\n")

    updated = 0
    found = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_and_update, row[0], row[1]): row[0] for row in rows}
        for i, future in enumerate(as_completed(futures)):
            auction_id, address = future.result()
            if address:
                found += 1
                # Write to DB (thread-safe)
                db2 = sqlite3.connect(DB_PATH)
                with _db_lock:
                    db2.execute("UPDATE auctions SET address = ? WHERE id = ?", (address, auction_id))
                    db2.commit()
                db2.close()
                updated += 1
            else:
                errors += 1

            if (i + 1) % 50 == 0:
                print(f"  Progress: {i+1}/{total} | Found: {found} | Errors: {errors}")

    print(f"\nDone. Updated {updated}/{total} records with real addresses.")


if __name__ == '__main__':
    main()
