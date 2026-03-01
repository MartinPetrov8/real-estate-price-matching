#!/usr/bin/env python3
"""
Migrate subscribers from SQLite to PostgreSQL.
Run once after setting up Railway Postgres.

Usage:
    DATABASE_URL=postgresql://... python scripts/migrate_to_postgres.py [sqlite_path]
"""

import sqlite3
import sys
import os

try:
    import psycopg2
except ImportError:
    print("Install psycopg2: pip install psycopg2-binary")
    sys.exit(1)

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("Set DATABASE_URL environment variable")
    sys.exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SQLITE_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/subscribers.db"

if not os.path.exists(SQLITE_PATH):
    print(f"SQLite DB not found at {SQLITE_PATH}")
    sys.exit(1)

# Connect
sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row
pg_conn = psycopg2.connect(DATABASE_URL)

print(f"SQLite: {SQLITE_PATH}")
print(f"Postgres: {DATABASE_URL[:40]}...")

# Read all subscribers
rows = sqlite_conn.execute("SELECT * FROM subscribers").fetchall()
print(f"Found {len(rows)} subscribers in SQLite")

if not rows:
    print("Nothing to migrate")
    sys.exit(0)

cur = pg_conn.cursor()

migrated = 0
skipped = 0

for row in rows:
    try:
        cur.execute("""
            INSERT INTO subscribers (email, cities, min_discount, verified, verify_token, 
                                     unsubscribe_token, created_at, verified_at, last_sent_at, last_deal_ids)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (email) DO NOTHING
        """, (
            row['email'],
            row['cities'],
            row['min_discount'],
            bool(row['verified']),
            row['verify_token'],
            row['unsubscribe_token'] if 'unsubscribe_token' in row.keys() else None,
            row['created_at'],
            row['verified_at'] if 'verified_at' in row.keys() else None,
            row['last_sent_at'] if 'last_sent_at' in row.keys() else None,
            row['last_deal_ids'] if 'last_deal_ids' in row.keys() else None,
        ))
        if cur.rowcount > 0:
            migrated += 1
        else:
            skipped += 1
    except Exception as e:
        print(f"  Error migrating {row['email']}: {e}")
        skipped += 1

pg_conn.commit()
cur.close()
pg_conn.close()
sqlite_conn.close()

print(f"\nDone: {migrated} migrated, {skipped} skipped (duplicates/errors)")
