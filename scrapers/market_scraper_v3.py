#!/usr/bin/env python3
"""
Production Market Scraper v3
===========================
Best practices implementation with:
- Human behavior mimicking (random delays, mouse patterns)
- Anti-blocking measures (rotating UAs, session persistence)
- Adaptive timeouts (no hard timeouts)
- Exponential backoff retry logic
- Rate limiting per domain
- Proper encoding handling

Sources: imot.bg, olx.bg, alo.bg
"""

import json
import os
import random
import re
import sqlite3
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse
import urllib.request
import urllib.error
import gzip
from io import BytesIO

# ============================================================================
# CONFIGURATION
# ============================================================================

DB_PATH = "scrapers/data/market.db"
OUTPUT_JSON = "scrapers/data/market_listings.json"

# Cities to scrape with URL patterns
# Note: OLX uses transliterated Bulgarian names (sofiya, not sofia)
# Note: alo.bg requires JS rendering - skipped for now
CITIES = {
    'София': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-sofiya/?tt=1',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/sofiya/',
    },
    'Пловдив': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-plovdiv/?tt=1',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/plovdiv/',
    },
    'Варна': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-varna/?tt=1',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/varna/',
    },
    'Бургас': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-burgas/?tt=1',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/burgas/',
    },
}

# Rotating User Agents (real browser fingerprints)
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
]

# Rate limiting: requests per domain
RATE_LIMITS = {
    'imot.bg': {'min_delay': 2.0, 'max_delay': 5.0, 'last_request': 0},
    'olx.bg': {'min_delay': 1.5, 'max_delay': 4.0, 'last_request': 0},
    'alo.bg': {'min_delay': 1.0, 'max_delay': 3.0, 'last_request': 0},
}

# ============================================================================
# ANTI-BLOCKING UTILITIES
# ============================================================================

def get_domain(url):
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc.replace('www.', '')

def human_delay(domain):
    """Implement human-like delays between requests."""
    limits = RATE_LIMITS.get(domain, {'min_delay': 1.0, 'max_delay': 3.0, 'last_request': 0})
    
    # Time since last request to this domain
    elapsed = time.time() - limits['last_request']
    
    # Random delay with slight variance (humans aren't perfectly random)
    base_delay = random.uniform(limits['min_delay'], limits['max_delay'])
    
    # Add occasional longer pauses (human distraction simulation)
    if random.random() < 0.1:  # 10% chance of longer pause
        base_delay += random.uniform(2.0, 5.0)
    
    # Wait if needed
    if elapsed < base_delay:
        time.sleep(base_delay - elapsed)
    
    # Update last request time
    limits['last_request'] = time.time()

def get_random_headers():
    """Generate realistic browser headers."""
    ua = random.choice(USER_AGENTS)
    
    headers = {
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'bg-BG,bg;q=0.9,en-US;q=0.8,en;q=0.7',
        # Note: Only accept gzip/deflate - we don't have brotli decoder
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }
    
    # Add random DNT header (some users have it)
    if random.random() < 0.3:
        headers['DNT'] = '1'
    
    return headers

def fetch_with_retry(url, max_retries=3, encoding='utf-8'):
    """
    Fetch URL with exponential backoff retry logic.
    No hard timeouts - uses adaptive approach.
    """
    domain = get_domain(url)
    
    for attempt in range(max_retries):
        try:
            # Human-like delay before request
            human_delay(domain)
            
            # Build request with realistic headers
            headers = get_random_headers()
            
            # Add referer for subsequent pages (looks more natural)
            if attempt > 0:
                headers['Referer'] = f"https://www.{domain}/"
            
            req = urllib.request.Request(url, headers=headers)
            
            # Adaptive timeout: increase with each retry
            timeout = 30 + (attempt * 15)
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                # Handle gzip encoding
                if response.info().get('Content-Encoding') == 'gzip':
                    buf = BytesIO(response.read())
                    with gzip.GzipFile(fileobj=buf) as f:
                        html = f.read()
                else:
                    html = response.read()
                
                # Decode with proper encoding
                try:
                    return html.decode(encoding, errors='ignore')
                except:
                    # Fallback encodings
                    for enc in ['windows-1251', 'utf-8', 'iso-8859-1']:
                        try:
                            return html.decode(enc, errors='ignore')
                        except:
                            continue
                    return html.decode('utf-8', errors='replace')
        
        except urllib.error.HTTPError as e:
            if e.code == 429:  # Rate limited
                wait_time = (2 ** attempt) * 10 + random.uniform(5, 15)
                print(f"    ⚠️ Rate limited, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
            elif e.code == 403:  # Blocked
                print(f"    ❌ Blocked (403), switching UA and waiting...")
                time.sleep(random.uniform(30, 60))
            elif e.code == 404:
                print(f"    ❌ Not found (404): {url}")
                return None
            else:
                print(f"    ⚠️ HTTP {e.code}, retry {attempt + 1}/{max_retries}")
                time.sleep((2 ** attempt) * 2)
        
        except urllib.error.URLError as e:
            print(f"    ⚠️ URL error: {e.reason}, retry {attempt + 1}/{max_retries}")
            time.sleep((2 ** attempt) * 3)
        
        except Exception as e:
            print(f"    ⚠️ Error: {e}, retry {attempt + 1}/{max_retries}")
            time.sleep((2 ** attempt) * 2)
    
    return None

# ============================================================================
# PARSERS - Site-specific extraction logic
# ============================================================================

def get_imot_listing_urls(html, max_listings=50):
    """Extract apartment listing URLs from imot.bg index page."""
    if not html:
        return []
    
    # Find apartment listings (exclude building projects)
    # Pattern: obiava-XXX-prodava-TYPE-apartament
    pattern = r'href="(//www\.imot\.bg/obiava[^"]+prodava-[^"]+apartament[^"#]*)"'
    links = re.findall(pattern, html)
    
    # Deduplicate while preserving order
    seen = set()
    unique_links = []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique_links.append('https:' + link)
    
    return unique_links[:max_listings]

def parse_imot_listing_page(html, city):
    """
    Parse a single imot.bg listing detail page.
    Returns listing dict or None.
    """
    if not html:
        return None
    
    try:
        # Extract price - look for numeric price followed by € or EUR
        # Pattern: ">148 000 €<" - digits with spaces, then currency symbol
        price_match = re.search(r'>\s*([\d][\d\s]*)\s*[€EUR]', html)
        
        if not price_match:
            return None
        
        price_str = price_match.group(1).replace(' ', '').replace('\xa0', '').strip()
        if not price_str or not price_str.isdigit():
            return None
        
        price_eur = float(price_str)
        
        # Extract size - look for sqm
        size_match = re.search(r'(\d+)\s*кв\.м', html)
        if not size_match:
            return None
        
        size_sqm = float(size_match.group(1))
        
        # Skip unrealistic values
        if size_sqm < 15 or size_sqm > 500:
            return None
        if price_eur < 5000 or price_eur > 5000000:
            return None
        
        price_sqm = price_eur / size_sqm
        
        # Skip unrealistic price per sqm
        if price_sqm < 200 or price_sqm > 15000:
            return None
        
        # Extract room type from URL or content
        rooms = extract_rooms(html)
        
        return {
            'city': city,
            'size_sqm': size_sqm,
            'price_eur': price_eur,
            'price_per_sqm': round(price_sqm, 2),
            'rooms': rooms,
            'source': 'imot.bg',
            'scraped_at': datetime.utcnow().isoformat(),
        }
    except Exception:
        return None

def scrape_imot_bg(index_url, city, max_listings=30):
    """
    Scrape imot.bg by:
    1. Getting listing URLs from index page
    2. Fetching individual listing pages
    3. Extracting price + size from each
    """
    listings = []
    
    # Step 1: Get index page
    html = fetch_with_retry(index_url, encoding='windows-1251')
    if not html:
        return listings
    
    # Step 2: Extract listing URLs
    urls = get_imot_listing_urls(html, max_listings=max_listings)
    if not urls:
        return listings
    
    print(f"found {len(urls)} listings, scraping...", end=" ", flush=True)
    
    # Step 3: Fetch each listing page
    for url in urls:
        listing_html = fetch_with_retry(url, encoding='windows-1251')
        listing = parse_imot_listing_page(listing_html, city)
        if listing:
            listings.append(listing)
    
    return listings

def parse_imot_bg(html, city):
    """
    Legacy parser for imot.bg index page.
    Note: Index pages don't show prices, so this won't find much.
    Use scrape_imot_bg() instead for proper scraping.
    """
    # This function is kept for compatibility but won't extract prices
    # because imot.bg index pages don't show individual listing prices
    return []

def parse_olx_bg(html, city):
    """
    Parse OLX.bg listings.
    Format: "XX кв.м - YYYY.YY" (size - price per sqm)
    """
    listings = []
    if not html:
        return listings
    
    # OLX format: "115 кв.м - 2982.61"
    pattern = re.compile(r'(\d+)\s*кв\.м\s*-\s*([\d\.,]+)')
    
    matches = pattern.findall(html)
    
    for size_str, price_sqm_str in matches:
        try:
            size_sqm = float(size_str)
            price_sqm = float(price_sqm_str.replace(',', '.'))
            
            # Skip unrealistic values
            if size_sqm < 15 or size_sqm > 500:
                continue
            if price_sqm < 200 or price_sqm > 10000:
                continue
            
            price_eur = size_sqm * price_sqm
            
            # Extract room type from nearby text (if possible)
            rooms = None  # OLX doesn't always show this in list view
            
            listings.append({
                'city': city,
                'size_sqm': size_sqm,
                'price_eur': price_eur,
                'price_per_sqm': price_sqm,
                'rooms': rooms,
                'source': 'olx.bg',
                'scraped_at': datetime.utcnow().isoformat(),
            })
        except:
            continue
    
    return listings

def parse_alo_bg(html, city):
    """
    Parse alo.bg listings.
    Very structured format with explicit fields:
    - Цена: XXX € 
    - за кв.м: XXXX €/кв.м
    - Квадратура: XX кв.м
    - Вид на имота: Type в City
    """
    listings = []
    if not html:
        return listings
    
    # Split by listing blocks (each starts with price)
    blocks = re.split(r'(?=Цена:\s*[\d\s]+\s*€)', html)
    
    for block in blocks[1:]:  # Skip first (before any listing)
        try:
            # Extract price
            price_match = re.search(r'Цена:\s*([\d\s]+)\s*€', block)
            if not price_match:
                continue
            price_eur = float(price_match.group(1).replace(' ', ''))
            
            # Extract price per sqm
            price_sqm_match = re.search(r'за кв\.м:\s*([\d\.,]+)\s*€', block)
            price_sqm = None
            if price_sqm_match:
                price_sqm = float(price_sqm_match.group(1).replace(',', '.'))
            
            # Extract size
            size_match = re.search(r'Квадратура:\s*([\d\.,]+)\s*кв\.м', block)
            size_sqm = None
            if size_match:
                size_sqm = float(size_match.group(1).replace(',', '.'))
            
            # Calculate missing values
            if size_sqm and price_eur and not price_sqm:
                price_sqm = price_eur / size_sqm
            elif price_sqm and price_eur and not size_sqm:
                size_sqm = price_eur / price_sqm
            
            # Skip if missing critical data
            if not size_sqm or not price_eur:
                continue
            
            # Skip unrealistic values
            if size_sqm < 15 or size_sqm > 500:
                continue
            if price_sqm and (price_sqm < 200 or price_sqm > 10000):
                continue
            
            # Extract property type and rooms
            type_match = re.search(r'Вид на имота:\s*(\w+)\s+апартамент', block)
            rooms = None
            if type_match:
                rooms = extract_rooms(type_match.group(1))
            
            listings.append({
                'city': city,
                'size_sqm': size_sqm,
                'price_eur': price_eur,
                'price_per_sqm': price_sqm,
                'rooms': rooms,
                'source': 'alo.bg',
                'scraped_at': datetime.utcnow().isoformat(),
            })
        except:
            continue
    
    return listings

def extract_rooms(text):
    """Extract room count from Bulgarian text."""
    if not text:
        return None
    
    text_lower = text.lower()
    
    patterns = [
        (r'\bедностаен', 1),
        (r'\bдвустаен', 2),
        (r'\bтристаен', 3),
        (r'\bчетиристаен', 4),
        (r'\bпетстаен', 5),
        (r'\bшестстаен', 6),
        (r'\bмногостаен', 4),
        (r'\bгарсониера', 1),
        (r'\bмезонет', 3),
        (r'\b(\d)\s*[-]?\s*ст(?:аен|\.)?', None),  # "2-стаен"
    ]
    
    for pattern, rooms in patterns:
        match = re.search(pattern, text_lower)
        if match:
            if rooms is None:  # Numeric pattern
                return int(match.group(1))
            return rooms
    
    return None

# ============================================================================
# DATABASE
# ============================================================================

def init_database():
    """Initialize SQLite database with proper schema."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    
    # Drop and recreate for fresh data
    conn.execute("DROP TABLE IF EXISTS market_listings")
    conn.execute("""
        CREATE TABLE market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            size_sqm REAL NOT NULL,
            price_eur REAL,
            price_per_sqm REAL,
            rooms INTEGER,
            source TEXT NOT NULL,
            scraped_at TEXT NOT NULL,
            UNIQUE(city, size_sqm, price_eur, source)
        )
    """)
    
    # Indexes for fast queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_city ON market_listings(city)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_size ON market_listings(size_sqm)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON market_listings(source)")
    
    conn.commit()
    return conn

def save_listings(conn, listings):
    """Save listings to database, skip duplicates."""
    saved = 0
    for listing in listings:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO market_listings 
                (city, size_sqm, price_eur, price_per_sqm, rooms, source, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                listing['city'],
                listing['size_sqm'],
                listing['price_eur'],
                listing['price_per_sqm'],
                listing['rooms'],
                listing['source'],
                listing['scraped_at'],
            ))
            if conn.total_changes:
                saved += 1
        except Exception as e:
            continue
    conn.commit()
    return saved

# ============================================================================
# MAIN SCRAPER
# ============================================================================

def scrape_city(city, urls, conn, imot_max=20):
    """Scrape all sources for a single city."""
    print(f"\n{'='*50}")
    print(f"📍 {city}")
    print(f"{'='*50}")
    
    total = 0
    
    # Scrape imot.bg (fetches individual listing pages)
    if 'imot' in urls:
        print(f"\n  🔍 imot.bg...", end=" ", flush=True)
        listings = scrape_imot_bg(urls['imot'], city, max_listings=imot_max)
        saved = save_listings(conn, listings)
        print(f"✓ {len(listings)} found, {saved} saved")
        total += saved
    
    # Scrape OLX (fast - single page scrape)
    if 'olx' in urls:
        print(f"  🔍 olx.bg...", end=" ", flush=True)
        html = fetch_with_retry(urls['olx'])
        listings = parse_olx_bg(html, city)
        saved = save_listings(conn, listings)
        print(f"✓ {len(listings)} found, {saved} saved")
        total += saved
    
    # Note: alo.bg skipped - requires JavaScript rendering
    
    return total

def export_to_json(conn):
    """Export all listings to JSON file."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM market_listings")
    columns = [desc[0] for desc in cursor.description]
    
    listings = []
    for row in cursor.fetchall():
        listings.append(dict(zip(columns, row)))
    
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)
    
    return len(listings)

def print_stats(conn):
    """Print scraping statistics."""
    cursor = conn.cursor()
    
    print(f"\n{'='*60}")
    print("📊 SCRAPING STATISTICS")
    print(f"{'='*60}")
    
    # By source
    print("\nBy source:")
    for row in cursor.execute("""
        SELECT source, COUNT(*), ROUND(AVG(price_per_sqm), 0) as avg_price
        FROM market_listings 
        WHERE price_per_sqm IS NOT NULL
        GROUP BY source
        ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]}: {row[1]} listings, avg €{row[2]}/m²")
    
    # By city
    print("\nBy city:")
    for row in cursor.execute("""
        SELECT city, COUNT(*), ROUND(AVG(price_per_sqm), 0) as avg_price
        FROM market_listings 
        WHERE price_per_sqm IS NOT NULL
        GROUP BY city
        ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]}: {row[1]} listings, avg €{row[2]}/m²")
    
    # Total
    cursor.execute("SELECT COUNT(*) FROM market_listings")
    total = cursor.fetchone()[0]
    print(f"\n{'='*60}")
    print(f"TOTAL: {total} listings")
    print(f"{'='*60}")

def main():
    """Main scraper entry point."""
    print("🏠 Market Data Scraper v3")
    print(f"⏰ Started: {datetime.utcnow().isoformat()}")
    print(f"📁 Database: {DB_PATH}")
    
    # Initialize database
    conn = init_database()
    
    # Scrape all cities
    grand_total = 0
    for city, urls in CITIES.items():
        grand_total += scrape_city(city, urls, conn)
    
    # Export to JSON
    exported = export_to_json(conn)
    print(f"\n📤 Exported {exported} listings to {OUTPUT_JSON}")
    
    # Print stats
    print_stats(conn)
    
    conn.close()
    print(f"\n✅ Completed: {datetime.utcnow().isoformat()}")

if __name__ == '__main__':
    main()
