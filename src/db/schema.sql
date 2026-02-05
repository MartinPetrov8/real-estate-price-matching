-- КЧСИ Auction Properties
CREATE TABLE IF NOT EXISTS kchsi_properties (
    id INTEGER PRIMARY KEY,
    bcpea_id TEXT UNIQUE NOT NULL,
    price_eur REAL,
    city TEXT,
    address TEXT,
    description TEXT,
    sqm REAL,
    rooms INTEGER,
    floor INTEGER,
    property_type TEXT,
    auction_start DATE,
    auction_end DATE,
    announcement_date DATETIME,
    court TEXT,
    executor TEXT,
    cadastral_id TEXT,
    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Market Listings
CREATE TABLE IF NOT EXISTS market_listings (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,  -- 'imot.bg', 'imot.net', 'alo.bg'
    source_id TEXT,
    price_eur REAL,
    price_bgn REAL,
    city TEXT,
    neighborhood TEXT,
    address TEXT,
    sqm REAL,
    rooms INTEGER,
    floor INTEGER,
    total_floors INTEGER,
    property_type TEXT,
    construction_type TEXT,
    year_built INTEGER,
    price_per_sqm REAL,
    url TEXT,
    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Matches (auction vs market)
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY,
    kchsi_id INTEGER NOT NULL,
    market_id INTEGER NOT NULL,
    similarity_score REAL,
    price_difference_eur REAL,
    price_difference_pct REAL,
    matched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (kchsi_id) REFERENCES kchsi_properties(id),
    FOREIGN KEY (market_id) REFERENCES market_listings(id),
    UNIQUE(kchsi_id, market_id)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_kchsi_city ON kchsi_properties(city);
CREATE INDEX IF NOT EXISTS idx_kchsi_sqm ON kchsi_properties(sqm);
CREATE INDEX IF NOT EXISTS idx_market_city ON market_listings(city);
CREATE INDEX IF NOT EXISTS idx_market_sqm ON market_listings(sqm);
CREATE INDEX IF NOT EXISTS idx_market_source ON market_listings(source);
CREATE INDEX IF NOT EXISTS idx_matches_kchsi ON matches(kchsi_id);
CREATE INDEX IF NOT EXISTS idx_matches_diff ON matches(price_difference_pct);
