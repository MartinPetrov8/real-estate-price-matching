#!/usr/bin/env python3
"""
Geocode neighborhood for КЧСИ auction properties.

Strategy:
1. For each active auction with address but no neighborhood:
   - Try extract_neighborhood() from address text first (fast, free)
   - If that fails, query Photon API (OSM-based, no key, ~5 req/sec)
   - Extract suburb/quarter/neighbourhood from Photon response
   - Cache result in auctions.db neighborhood column
2. Designed to be idempotent — skips rows where neighborhood already set
3. Run once for backfill, then nightly for new properties only

Usage:
  python3 scripts/geocode_neighborhoods.py          # Process all NULL neighborhoods
  python3 scripts/geocode_neighborhoods.py --dry-run  # Show what would be done
"""

import argparse
import sqlite3
import sys
import os
import time
import json
import re
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from neighborhood_matcher import extract_neighborhood, normalize_neighborhood

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'auctions.db')
NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
REQUEST_DELAY = 1.1    # Nominatim ToS: max 1 req/sec
NOMINATIM_TIMEOUT = 10


def clean_address_for_geocoding(address: str, city: str) -> str | None:
    """
    Strip noise and build a clean geocoding query.
    Rejects time fragments, JS blobs, and non-address garbage.
    Returns query string or None if address is unusable.
    """
    # Reject known garbage patterns
    if not address or len(address) < 4:
        return None
    if re.search(r'\d+\s*часа', address):  # "03 часа" = countdown timer
        return None
    if re.search(r'document\.createElement|cdn-cgi|challenge-platform', address):
        return None
    if not re.search(r'[А-Яа-я]', address):
        return None

    # Truncate very long addresses (keep first meaningful part)
    clean = address.split('.')[0] if len(address) > 150 else address
    clean = re.sub(r'\s+', ' ', clean).strip()

    city_clean = re.sub(r'^(гр\.|с\.)\s*', '', city).strip()
    return f"{clean}, {city_clean}, България"


def nominatim_geocode(address: str, city: str) -> str | None:
    """
    Query Nominatim (OSM) and extract neighborhood/suburb.
    Returns normalized neighborhood string or None.
    """
    query = clean_address_for_geocoding(address, city)
    if not query:
        return None

    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={'q': query, 'format': 'json', 'limit': 1,
                    'addressdetails': 1, 'countrycodes': 'bg'},
            timeout=NOMINATIM_TIMEOUT,
            headers={'User-Agent': 'kchsi-neighborhood-matcher/1.0 (real-estate-price-matching)'}
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    Nominatim error: {e}")
        return None

    if not data:
        return None

    addr = data[0].get('address', {})

    # OSM field priority: suburb > quarter > neighbourhood > city_district
    for key in ['suburb', 'quarter', 'neighbourhood', 'city_district']:
        val = addr.get(key)
        if val:
            normalized = normalize_neighborhood(val)
            if normalized and len(normalized) > 2:
                return normalized

    return None


def extract_from_address(address: str) -> str | None:
    """Try to extract neighborhood from raw address text."""
    if not address:
        return None
    result = extract_neighborhood(address)
    # Filter out garbage results (single chars, numbers)
    if result and len(result) > 2 and not result.isdigit():
        return result
    return None


def main():
    parser = argparse.ArgumentParser(description='Geocode neighborhoods for КЧСИ auctions')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done, no DB writes')
    parser.add_argument('--limit', type=int, default=0, help='Max records to process (0 = all)')
    parser.add_argument('--city', type=str, default='', help='Only process specific city')
    args = parser.parse_args()

    db = sqlite3.connect(DB_PATH)

    # Build query for auctions needing neighborhood
    query = """
        SELECT id, address, city, property_type FROM auctions
        WHERE is_expired = 0
          AND (neighborhood IS NULL OR neighborhood = '')
          AND property_type NOT IN ('Земеделска земя', 'Парцел', 'none')
    """
    params = []
    if args.city:
        query += " AND city LIKE ?"
        params.append(f"%{args.city}%")
    query += " ORDER BY city, id"
    if args.limit:
        query += f" LIMIT {args.limit}"

    rows = db.execute(query, params).fetchall()
    total = len(rows)
    print(f"Auctions needing geocoding: {total}")
    if args.dry_run:
        print("DRY RUN — no writes")
    print()

    stats = {'text_match': 0, 'photon_match': 0, 'no_match': 0, 'no_address': 0}
    updated = 0

    for i, (auction_id, address, city, prop_type) in enumerate(rows):
        if not address or len(address) < 4:
            stats['no_address'] += 1
            continue

        neighborhood = None
        method = None

        # Step 1: Try text extraction (fast, no network)
        neighborhood = extract_from_address(address)
        if neighborhood:
            method = 'text'
            stats['text_match'] += 1
        else:
            # Step 2: Nominatim geocoding
            neighborhood = nominatim_geocode(address, city)
            if neighborhood:
                method = 'nominatim'
                stats['photon_match'] += 1
            else:
                stats['no_match'] += 1

        # Progress output
        if (i + 1) % 20 == 0 or neighborhood:
            print(f"  [{i+1}/{total}] {city} | {address[:50]!r} -> {neighborhood!r} ({method})")

        if neighborhood and not args.dry_run:
            db.execute(
                "UPDATE auctions SET neighborhood = ? WHERE id = ?",
                (neighborhood, auction_id)
            )
            updated += 1
            if updated % 50 == 0:
                db.commit()

        # Rate limit only when using Nominatim (ToS: 1 req/sec)
        if method == 'nominatim':
            time.sleep(REQUEST_DELAY)

    if not args.dry_run:
        db.commit()

    print()
    print("=== RESULTS ===")
    print(f"  Total processed: {total}")
    print(f"  Text match:      {stats['text_match']}")
    print(f"  Nominatim match: {stats['photon_match']}")
    print(f"  No match:        {stats['no_match']}")
    print(f"  No address:      {stats['no_address']}")
    if not args.dry_run:
        print(f"  DB updated:      {updated}")

    # Show neighborhood coverage after
    if not args.dry_run:
        total_active = db.execute("SELECT COUNT(*) FROM auctions WHERE is_expired=0").fetchone()[0]
        with_hood = db.execute(
            "SELECT COUNT(*) FROM auctions WHERE is_expired=0 AND neighborhood IS NOT NULL AND neighborhood != ''"
        ).fetchone()[0]
        print(f"\nCoverage after: {with_hood}/{total_active} ({100*with_hood//total_active}%)")

        print("\nTop neighborhoods per city:")
        for city_row in ['гр. София', 'гр. Пловдив', 'гр. Варна', 'гр. Бургас', 'гр. Русе', 'гр. Стара Загора']:
            hoods = db.execute("""
                SELECT neighborhood, COUNT(*) cnt FROM auctions
                WHERE city LIKE ? AND is_expired=0 AND neighborhood IS NOT NULL
                GROUP BY neighborhood ORDER BY cnt DESC LIMIT 5
            """, (f"%{city_row.split()[-1]}%",)).fetchall()
            if hoods:
                hood_str = ', '.join(f"{r[0]}({r[1]})" for r in hoods)
                print(f"  {city_row}: {hood_str}")

    db.close()


if __name__ == '__main__':
    main()
