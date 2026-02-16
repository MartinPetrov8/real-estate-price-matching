#!/usr/bin/env python3
"""Initialize subscribers database"""
import sqlite3
import os

DB_PATH = "data/subscribers.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            cities TEXT NOT NULL,
            min_discount INTEGER DEFAULT 20,
            verified BOOLEAN DEFAULT 0,
            verify_token TEXT,
            unsubscribe_token TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            verified_at TEXT,
            last_sent_at TEXT,
            last_deal_ids TEXT
        )
    ''')
    
    c.execute('CREATE INDEX IF NOT EXISTS idx_email ON subscribers(email)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_verified ON subscribers(verified)')
    
    conn.commit()
    print(f"✅ Created {DB_PATH}")
    return conn

if __name__ == "__main__":
    init_db()
