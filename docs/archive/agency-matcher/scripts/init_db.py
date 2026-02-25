#!/usr/bin/env python3
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "real_estate_matcher.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

schema = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS agencies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  subdomain TEXT NOT NULL UNIQUE,
  base_url TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scrape_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  pages_scraped INTEGER NOT NULL DEFAULT 0,
  listings_seen INTEGER NOT NULL DEFAULT 0,
  listings_saved INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  agency_subdomain TEXT NOT NULL,
  listing_code TEXT,
  listing_url TEXT NOT NULL,
  title TEXT,
  district TEXT,
  property_type TEXT,
  area_sqm REAL,
  floor_text TEXT,
  construction_year INTEGER,
  price_eur REAL,
  price_bgn REAL,
  raw_text TEXT,
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  is_active INTEGER NOT NULL DEFAULT 1,
  hash_signature TEXT,
  UNIQUE(source, listing_url)
);

CREATE INDEX IF NOT EXISTS idx_listings_agency ON listings(agency_subdomain);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price_eur);
CREATE INDEX IF NOT EXISTS idx_listings_area ON listings(area_sqm);
CREATE INDEX IF NOT EXISTS idx_listings_district ON listings(district);

CREATE TABLE IF NOT EXISTS match_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id_a INTEGER NOT NULL,
  listing_id_b INTEGER NOT NULL,
  confidence REAL NOT NULL,
  reasons TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(listing_id_a, listing_id_b)
);
"""

AGENCIES = [
    ("BULGARIAN PROPERTIES", "newbulprop"),
    ("ADDRESS", "address"),
    ("OLIMP-UV", "olimp-uv"),
    ("UNIQUE ESTATES", "uniqueestates"),
    ("LUXIMMO", "luximmo"),
    ("SUPRIMMO OFFICES", "superimotibg"),
    ("BUILDING BOX", "buildingbox"),
    ("HOME CENTER", "home_center"),
    ("STONEHARD BG", "stonehardbg"),
    ("YAVLENA", "yavlena"),
    ("EX NVD", "exnvd"),
    ("STONEHARD SOFIA", "stonehard"),
    ("IMOTEKA", "imoteka"),
    ("GLOBAL SERVICES", "globalservices"),
    ("SUPRIMMO HQ", "superimoti"),
    ("MIRELA", "mirela"),
    ("EKOLIT", "ekolit"),
    ("BULGARIAN PROPERTIES SOFIA", "novostroitelstvo"),
    ("TITAN PROPERTIES", "titanproperties"),
    ("ARCO", "arcoimoti"),
]

with sqlite3.connect(DB_PATH) as conn:
    conn.executescript(schema)
    for name, sub in AGENCIES:
        conn.execute(
            """
            INSERT OR IGNORE INTO agencies(name, subdomain, base_url)
            VALUES (?, ?, ?)
            """,
            (name, sub, f"https://{sub}.imot.bg"),
        )
    conn.commit()

print(f"Initialized DB: {DB_PATH}")
