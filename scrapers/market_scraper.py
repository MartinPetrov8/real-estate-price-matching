#!/usr/bin/env python3
"""
Market Scraper v7 - RESILIENT with checkpoint/resume
=====================================================
- Checkpoint file saves progress after each city+source
- On interrupt (SIGTERM, timeout, crash), resumes from last checkpoint
- Data saved to DB incrementally (survives restarts)
- All-or-nothing validation: only exports when ALL sources pass
- Exit code 1 on failure, 0 on success

Usage:
  python3 market_scraper.py           # Fresh run (clears today's checkpoint)
  python3 market_scraper.py --resume  # Resume from last checkpoint
"""

import json
import logging
import os
import re
import signal
import sqlite3
import sys
import time
import random
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

import requests
from bs4 import BeautifulSoup

# Injection hardening (REG-037 / security scan 2026-02-26)
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', 'scripts'))
try:
    from sanitize_text import sanitize_text
except ImportError:
    def sanitize_text(t, **kw): return (t or "").strip()  # fallback no-op

# Neighborhood extraction (from project root)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
try:
    from neighborhood_matcher import extract_neighborhood, normalize_neighborhood
    _has_hood_matcher = True
except ImportError:
    _has_hood_matcher = False
    def extract_neighborhood(text): return None
    def normalize_neighborhood(text): return (text or '').lower().strip() or None

# ============================================================================
# CONFIG
# ============================================================================

DB_PATH = "data/market.db"
OUTPUT_JSON = "data/market_listings.json"
LOG_DIR = "data/logs"
CHECKPOINT_DIR = "data"
DATA_RETENTION_DAYS = 7
MIN_LISTINGS_PER_SOURCE = 5

# Graceful shutdown
SHUTDOWN_REQUESTED = False

def signal_handler(signum, frame):
    global SHUTDOWN_REQUESTED
    logging.warning(f"Received signal {signum}, requesting graceful shutdown...")
    SHUTDOWN_REQUESTED = True

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Neighborhoods not covered by OLX district filters — scraped via text search instead.
# Format: {city: [(neighborhood_label, search_slug), ...]}
# search_slug is the URL-encoded query string (Bulgarian text).
# IMPORTANT: these use /prodazhbi/ (sales) to exclude rentals.
OLX_SEARCH_SUPPLEMENTS = {
    'София': [
        ('сухата река', 'Сухата-река'),
        ('подуяне',     'Подуяне'),
        ('хиподрума',   'Хиподрума'),
    ],
    'Пловдив': [
        ('изгрев',      'Пловдив-Изгрев'),   # кв. Изгрев, район Източен (ул. Босилек)
    ],
    'Русе': [
        ('изток',         'Русе-Изток'),
        ('здравец-север', 'Здравец'),
    ],
    'Хасково': [
        ('орфей', 'Хасково-Орфей'),
    ],
}

# Cities with correct URL formats
CITIES = {
    'София': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-sofiya/',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/sofiya/',
    },
    'Пловдив': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-plovdiv/',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/plovdiv/',
    },
    'Варна': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-varna/',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/varna/',
    },
    'Бургас': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-burgas/',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/burgas/',
    },
    'Русе': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-ruse/',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/ruse/',
    },
    'Стара Загора': {
        'imot': 'https://www.imot.bg/obiavi/prodazhbi/grad-stara-zagora/',
        'olx': 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/stara-zagora/',
    },
}

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
]

HEADERS = {
    'User-Agent': USER_AGENTS[0],  # default; rotated per session below
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'bg-BG,bg;q=0.9,en;q=0.8',
    # Note: intentionally omitting Accept-Encoding — imot.bg returns undecodable
    # compressed/obfuscated responses when br/gzip is advertised from datacenter IPs.
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# ============================================================================
# CHECKPOINT SYSTEM
# ============================================================================

class Checkpoint:
    """Save/load scraping progress to survive interruptions."""

    def __init__(self, checkpoint_dir: str = CHECKPOINT_DIR):
        self.date = datetime.utcnow().strftime('%Y-%m-%d')
        self.path = os.path.join(checkpoint_dir, f"checkpoint_{self.date}.json")
        self.completed: Dict[str, Dict[str, dict]] = {}
        # Structure: {city: {source: {success: bool, count: int, error: str}}}

    def load(self) -> bool:
        """Load checkpoint from disk. Returns True if loaded."""
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    data = json.load(f)
                if data.get('date') == self.date:
                    self.completed = data.get('completed', {})
                    logging.info(f"Loaded checkpoint: {len(self._completed_pairs())} city+source pairs done")
                    return True
                else:
                    logging.info("Checkpoint from different date, starting fresh")
            except (json.JSONDecodeError, KeyError) as e:
                logging.warning(f"Corrupt checkpoint, starting fresh: {e}")
        return False

    def save(self):
        """Save current progress to disk."""
        data = {
            'date': self.date,
            'updated_at': datetime.utcnow().isoformat(),
            'completed': self.completed,
        }
        # Atomic write: write to temp then rename
        tmp_path = self.path + '.tmp'
        with open(tmp_path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)

    def mark_done(self, city: str, source: str, success: bool, count: int, error: str = ""):
        """Mark a city+source as completed and save immediately."""
        if city not in self.completed:
            self.completed[city] = {}
        self.completed[city][source] = {
            'success': success,
            'count': count,
            'error': error,
            'completed_at': datetime.utcnow().isoformat(),
        }
        self.save()

    def is_done(self, city: str, source: str) -> bool:
        """Check if this city+source was already completed."""
        return city in self.completed and source in self.completed[city]

    def get_result(self, city: str, source: str) -> Optional[dict]:
        """Get previous result for a city+source."""
        if self.is_done(city, source):
            return self.completed[city][source]
        return None

    def _completed_pairs(self) -> List[str]:
        pairs = []
        for city, sources in self.completed.items():
            for source in sources:
                pairs.append(f"{city}/{source}")
        return pairs

    def has_failures(self) -> bool:
        """Check if any completed source failed."""
        for city, sources in self.completed.items():
            for source, result in sources.items():
                if not result['success']:
                    return True
        return False

    def all_cities_done(self) -> bool:
        """Check if all cities have both sources completed."""
        for city in CITIES:
            for source in ['imot.bg', 'olx.bg']:
                if not self.is_done(city, source):
                    return False
        return True

    def get_summary(self) -> str:
        """Human-readable summary."""
        lines = []
        for city in CITIES:
            lines.append(f"\n{city}:")
            for source in ['imot.bg', 'olx.bg']:
                result = self.get_result(city, source)
                if result:
                    status = "✓" if result['success'] else "✗"
                    line = f"  {status} {source}: {result['count']} listings"
                    if result.get('error'):
                        line += f" - ERROR: {result['error']}"
                    lines.append(line)
                else:
                    lines.append(f"  ⏳ {source}: pending")
        return "\n".join(lines)

    def get_total_listings(self) -> int:
        total = 0
        for city, sources in self.completed.items():
            for source, result in sources.items():
                if result['success']:
                    total += result['count']
        return total

    def cleanup(self):
        """Remove checkpoint file after successful completion."""
        if os.path.exists(self.path):
            os.remove(self.path)
            logging.info("Checkpoint cleaned up after successful run")

    @staticmethod
    def cleanup_old(checkpoint_dir: str = CHECKPOINT_DIR, keep_days: int = 2):
        """Remove checkpoint files older than keep_days."""
        cutoff = datetime.utcnow() - timedelta(days=keep_days)
        for f in os.listdir(checkpoint_dir):
            if f.startswith('checkpoint_') and f.endswith('.json'):
                try:
                    date_str = f.replace('checkpoint_', '').replace('.json', '')
                    file_date = datetime.strptime(date_str, '%Y-%m-%d')
                    if file_date < cutoff:
                        os.remove(os.path.join(checkpoint_dir, f))
                        logging.info(f"Cleaned up old checkpoint: {f}")
                except ValueError:
                    pass


# ============================================================================
# LOGGING
# ============================================================================

def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"market_{datetime.utcnow().strftime('%Y-%m-%d')}.log")

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ]
    )

# ============================================================================
# DATA MODEL
# ============================================================================

@dataclass
class Listing:
    city: str
    neighborhood: Optional[str]
    size_sqm: float
    price_eur: float
    price_per_sqm: float
    rooms: Optional[int]
    source: str
    scraped_at: str

# ============================================================================
# HTTP UTILS
# ============================================================================

def create_session() -> requests.Session:
    session = requests.Session()
    headers = dict(HEADERS)
    headers['User-Agent'] = random.choice(USER_AGENTS)
    session.headers.update(headers)
    return session

def fetch_page(session: requests.Session, url: str, encoding: str = 'utf-8', retries: int = 3,
               connect_timeout: int = 15, read_timeout: int = 45) -> Optional[str]:
    """
    Fetch a page with per-attempt connect+read timeouts and exponential backoff.
    
    connect_timeout: seconds to wait for TCP handshake (default 15s)
    read_timeout: seconds to wait for response bytes (default 45s) — generous for slow sites
    Total max per attempt: 60s. With 3 retries + backoff: max ~3.5 min per URL.
    
    Resilience notes (2026-03-26):
    - Use (connect, read) tuple instead of single timeout to prevent indefinite hangs
      on slow sites like imot.bg/OLX Стара Загора during off-peak hours
    - Exponential backoff (2^attempt) gives slow sites time to recover between retries
    - Caller gets None on failure; city is skipped, checkpoint records error but continues
    """
    for attempt in range(retries):
        if SHUTDOWN_REQUESTED:
            return None
        try:
            resp = session.get(url, timeout=(connect_timeout, read_timeout))
            resp.raise_for_status()
            if encoding == 'windows-1251':
                resp.encoding = 'windows-1251'
            return resp.text
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logging.debug(f"404: {url[:60]}...")
                return None
            logging.warning(f"HTTP {e.response.status_code} for {url[:60]}, retry {attempt+1}/{retries}")
            time.sleep(2 ** attempt)
        except requests.exceptions.Timeout:
            logging.warning(f"Timeout (connect={connect_timeout}s, read={read_timeout}s) for {url[:60]}, retry {attempt+1}/{retries}")
            time.sleep(2 ** attempt)
        except requests.exceptions.RequestException as e:
            logging.warning(f"Request error: {e}, retry {attempt+1}/{retries}")
            time.sleep(2 ** attempt)

    logging.error(f"Failed after {retries} retries: {url[:80]}")
    return None

# ============================================================================
# IMOT.BG SCRAPER
# ============================================================================

def scrape_imot_index(session: requests.Session, url: str) -> List[str]:
    html = fetch_page(session, url, encoding='windows-1251')
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'obiava' in href and 'prodava' in href and 'apartament' in href:
            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = 'https://www.imot.bg' + href
            clean_href = href.split('#')[0]
            if clean_href not in links:
                links.append(clean_href)

    return links[:30]

def parse_imot_listing(session: requests.Session, url: str, city: str) -> Optional[Listing]:
    html = fetch_page(session, url, encoding='windows-1251')
    if not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')

    try:
        price_eur = None
        for text in soup.stripped_strings:
            match = re.search(r'(\d[\d\s]*\d)\s*[€EUR]', text)
            if match:
                price_str = match.group(1).replace(' ', '').replace('\xa0', '')
                if price_str.isdigit():
                    price_eur = float(price_str)
                    if price_eur > 5000:
                        break

        if not price_eur:
            return None

        size_sqm = None
        for text in soup.stripped_strings:
            match = re.search(r'(\d+)\s*кв\.?\s*м', text)
            if match:
                size_sqm = float(match.group(1))
                if 15 <= size_sqm <= 500:
                    break

        if not size_sqm:
            return None

        price_per_sqm = round(price_eur / size_sqm, 2)
        if not (200 <= price_per_sqm <= 15000):
            return None

        rooms = None
        url_lower = url.lower()
        if 'ednostaen' in url_lower:
            rooms = 1
        elif 'dvustaen' in url_lower:
            rooms = 2
        elif 'tristaen' in url_lower:
            rooms = 3
        elif 'chetiristaen' in url_lower or 'mnogostaen' in url_lower:
            rooms = 4

        # Extract neighborhood from page title or breadcrumb
        neighborhood = None
        title_tag = soup.find('title')
        title_text = title_tag.get_text() if title_tag else ''
        # Also check H1 and breadcrumb elements
        for candidate in [title_text] + [el.get_text() for el in soup.select('h1, .breadcrumb, #breadcrumb, .location, .adress')]:
            hood = extract_neighborhood(candidate)
            if hood:
                neighborhood = hood
                break

        return Listing(
            neighborhood=neighborhood, city=city, size_sqm=size_sqm,
            price_eur=price_eur, price_per_sqm=price_per_sqm,
            rooms=rooms, source='imot.bg',
            scraped_at=datetime.utcnow().isoformat()
        )

    except (ValueError, TypeError, AttributeError) as e:
        logging.debug(f"Parse error for {url[:60]}: {e}")
        return None

def scrape_imot_city(session: requests.Session, url: str, city: str) -> Tuple[List[Listing], bool, str]:
    """Returns (listings, success, error_msg)"""
    listings = []
    urls = scrape_imot_index(session, url)
    if not urls:
        return [], False, "Failed to fetch index page or no listings found"

    logging.info(f"  imot.bg: found {len(urls)} links, scraping...")
    print(f"found {len(urls)}, scraping...", end=" ", flush=True)

    for listing_url in urls:
        if SHUTDOWN_REQUESTED:
            logging.warning("Shutdown requested mid-imot scrape")
            return listings, False, "Interrupted by shutdown signal"
        listing = parse_imot_listing(session, listing_url, city)
        if listing:
            listings.append(listing)
        time.sleep(0.5 + random.random())

    if len(listings) < MIN_LISTINGS_PER_SOURCE:
        return listings, False, f"Too few listings: {len(listings)} < {MIN_LISTINGS_PER_SOURCE}"

    return listings, True, ""

# ============================================================================
# OLX.BG SCRAPER
# ============================================================================

def get_olx_districts(session: requests.Session, city_url: str) -> Dict[str, str]:
    """
    Discover OLX district filter IDs from a city listing page.
    Returns {district_id: district_name} dict.
    """
    html = fetch_page(session, city_url)
    if not html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    districts = {}
    for a in soup.find_all('a', href=True):
        href = a['href']
        m = re.search(r'district_id%5D=(\d+)', href)
        if m:
            did = m.group(1)
            # Label is the link text, strip listing count in parens
            label = re.sub(r'\s*\(\d+\)\s*$', '', a.get_text().strip())
            if label and did not in districts:
                districts[did] = label
    return districts


def scrape_olx_district(session: requests.Session, city_url: str, city: str,
                         district_id: str, district_name: str) -> List[Listing]:
    """Scrape one OLX district, returning listings with neighborhood pre-tagged."""
    listings = []
    neighborhood = normalize_neighborhood(district_name)
    if not neighborhood:
        neighborhood = district_name.lower().strip()

    for page in range(1, 3):  # 2 pages per district (40-80 listings, enough)
        if SHUTDOWN_REQUESTED:
            break
        sep = '&' if '?' in city_url else '?'
        page_url = f"{city_url}{sep}search%5Bdistrict_id%5D={district_id}"
        if page > 1:
            page_url += f"&page={page}"

        html = fetch_page(session, page_url)
        if not html:
            break

        soup = BeautifulSoup(html, 'html.parser')
        pattern = re.compile(r'(\d+)\s*кв\.м\s*-\s*([\d\.,]+)')
        cards = soup.select('[data-cy="l-card"], .offer-wrapper, article')

        items = cards if cards else [soup]  # fallback to full page
        for item in items:
            text = item.get_text()
            match = pattern.search(text)
            if not match:
                continue
            try:
                size_sqm = float(match.group(1))
                price_per_sqm = float(match.group(2).replace(',', '.'))
                if not (15 <= size_sqm <= 500) or not (200 <= price_per_sqm <= 15000):
                    continue
                price_eur = round(size_sqm * price_per_sqm, 2)
                listings.append(Listing(
                    neighborhood=neighborhood, city=city, size_sqm=size_sqm,
                    price_eur=price_eur, price_per_sqm=price_per_sqm,
                    rooms=None, source='olx.bg',
                    scraped_at=datetime.utcnow().isoformat()
                ))
            except (ValueError, TypeError):
                continue

        time.sleep(0.4)

    return listings


def scrape_olx_search(session: requests.Session, city: str,
                       neighborhood_label: str, search_slug: str) -> List[Listing]:
    """
    Scrape OLX via text search for a neighborhood not covered by district filters.
    Uses /nedvizhimi-imoti/prodazhbi/ (sales only — excludes rentals).
    search_slug: Bulgarian text as it appears in the OLX search URL, e.g. 'Сухата-река'.
    """
    listings = []
    neighborhood = normalize_neighborhood(neighborhood_label) or neighborhood_label.lower().strip()
    base_url = f"https://www.olx.bg/nedvizhimi-imoti/prodazhbi/q-{search_slug}/"

    for page_num in range(1, 3):  # 2 pages max
        if SHUTDOWN_REQUESTED:
            break
        page_url = base_url if page_num == 1 else f"{base_url}?page={page_num}"
        html = fetch_page(session, page_url)
        if not html:
            break

        soup = BeautifulSoup(html, 'html.parser')
        pattern = re.compile(r'(\d+)\s*кв\.м\s*-\s*([\d\.,]+)')
        cards = soup.select('[data-cy="l-card"], .offer-wrapper, article')
        items = cards if cards else [soup]

        for item in items:
            text = item.get_text()
            # Skip rental listings: they show monthly prices (very low total EUR amount)
            # Sales listings are always > 10000 EUR; rentals are 200-2000 EUR/month
            # The price_per_sqm filter (200-15000) handles this, but double-check total price
            match = pattern.search(text)
            if not match:
                continue
            try:
                size_sqm = float(match.group(1))
                price_per_sqm = float(match.group(2).replace(',', '.'))
                if not (15 <= size_sqm <= 500) or not (200 <= price_per_sqm <= 15000):
                    continue
                price_eur = round(size_sqm * price_per_sqm, 2)
                # Hard floor: anything under 15000 EUR total is a rental leaking through
                if price_eur < 15000:
                    continue
                listings.append(Listing(
                    neighborhood=neighborhood, city=city, size_sqm=size_sqm,
                    price_eur=price_eur, price_per_sqm=price_per_sqm,
                    rooms=None, source='olx.bg',
                    scraped_at=datetime.utcnow().isoformat()
                ))
            except (ValueError, TypeError):
                continue

        time.sleep(0.4)

    return listings


def scrape_olx(session: requests.Session, url: str, city: str) -> Tuple[List[Listing], bool, str]:
    """
    Scrape OLX per-district for 100% neighborhood coverage.
    Discovers district IDs dynamically from the city page, then scrapes each.
    Supplements with text-search scraping for neighborhoods not in district filters.
    Falls back to city-level scrape if district discovery fails.
    """
    # Step 1: discover districts
    districts = get_olx_districts(session, url)
    if not districts:
        logging.warning(f"  OLX district discovery failed for {city}, falling back to city-level")
        return _scrape_olx_city_fallback(session, url, city)

    logging.info(f"  OLX: {len(districts)} districts found for {city}")
    all_listings = []

    for did, dname in districts.items():
        if SHUTDOWN_REQUESTED:
            break
        district_listings = scrape_olx_district(session, url, city, did, dname)
        all_listings.extend(district_listings)
        logging.debug(f"    District {dname!r}: {len(district_listings)} listings")

    # Step 2: supplement with search-based scraping for unlisted neighborhoods
    supplements = OLX_SEARCH_SUPPLEMENTS.get(city, [])
    if supplements:
        district_names_lower = {n.lower() for n in districts.values()}
        for hood_label, search_slug in supplements:
            if SHUTDOWN_REQUESTED:
                break
            # Skip if this neighborhood is already covered by a district filter
            if hood_label.lower() in district_names_lower:
                logging.debug(f"  OLX search supplement skipped (already in districts): {hood_label}")
                continue
            search_listings = scrape_olx_search(session, city, hood_label, search_slug)
            all_listings.extend(search_listings)
            logging.info(f"  OLX search supplement '{hood_label}': {len(search_listings)} listings")

    if len(all_listings) < MIN_LISTINGS_PER_SOURCE:
        return all_listings, False, f"Too few listings after district scrape: {len(all_listings)}"

    return all_listings, True, ""


def _scrape_olx_city_fallback(session: requests.Session, url: str, city: str) -> Tuple[List[Listing], bool, str]:
    """Original city-level OLX scrape without neighborhood tagging (fallback only)."""
    listings = []
    for page in range(1, 4):
        if SHUTDOWN_REQUESTED:
            return listings, False, "Interrupted by shutdown signal"
        page_url = url if page == 1 else f"{url}?page={page}"
        html = fetch_page(session, page_url)
        if not html:
            if page == 1:
                return [], False, "Failed to fetch page 1"
            break
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()
        pattern = re.compile(r'(\d+)\s*кв\.м\s*-\s*([\d\.,]+)')
        for match in pattern.finditer(text):
            try:
                size_sqm = float(match.group(1))
                price_per_sqm = float(match.group(2).replace(',', '.'))
                if not (15 <= size_sqm <= 500) or not (200 <= price_per_sqm <= 15000):
                    continue
                listings.append(Listing(
                    neighborhood=None, city=city, size_sqm=size_sqm,
                    price_eur=round(size_sqm * price_per_sqm, 2),
                    price_per_sqm=price_per_sqm, rooms=None, source='olx.bg',
                    scraped_at=datetime.utcnow().isoformat()
                ))
            except (ValueError, TypeError):
                continue
        if page < 3:
            time.sleep(0.5)
    if len(listings) < MIN_LISTINGS_PER_SOURCE:
        return listings, False, f"Too few listings: {len(listings)}"
    return listings, True, ""

# ============================================================================
# DATABASE
# ============================================================================

def init_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_listings (
            id INTEGER PRIMARY KEY,
            city TEXT NOT NULL,
            neighborhood TEXT,
            size_sqm REAL NOT NULL,
            price_eur REAL,
            price_per_sqm REAL,
            rooms INTEGER,
            source TEXT NOT NULL,
            scraped_at TEXT,
            UNIQUE(city, size_sqm, price_eur, source)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_city ON market_listings(city)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON market_listings(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_size ON market_listings(size_sqm)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scraped ON market_listings(scraped_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_neighborhood ON market_listings(neighborhood)")

    cutoff = (datetime.utcnow() - timedelta(days=DATA_RETENTION_DAYS)).isoformat()
    cursor = conn.execute("DELETE FROM market_listings WHERE scraped_at < ?", (cutoff,))
    if cursor.rowcount > 0:
        logging.info(f"Purged {cursor.rowcount} listings older than {DATA_RETENTION_DAYS} days")

    conn.commit()
    return conn

def save_listings(conn: sqlite3.Connection, listings: List[Listing]) -> int:
    saved = 0
    for l in listings:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO market_listings
                (city, neighborhood, size_sqm, price_eur, price_per_sqm, rooms, source, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (l.city, l.neighborhood, l.size_sqm, l.price_eur, l.price_per_sqm, l.rooms, l.source, l.scraped_at))
            saved += 1
        except sqlite3.Error as e:
            logging.warning(f"DB insert error: {e}")
    conn.commit()
    return saved

def export_json(conn: sqlite3.Connection) -> int:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT city, size_sqm, price_eur, price_per_sqm, rooms, source, scraped_at
        FROM market_listings
        ORDER BY city, price_per_sqm
    """)

    listings = []
    for row in cursor.fetchall():
        listings.append({
            'city': row[0], 'size_sqm': row[1], 'price_eur': row[2],
            'price_per_sqm': row[3], 'rooms': row[4], 'source': row[5],
            'scraped_at': row[6]
        })

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)

    return len(listings)

# ============================================================================
# MAIN
# ============================================================================

def main():
    setup_logging()

    resume_mode = '--resume' in sys.argv

    logging.info("🏠 Market Scraper v7 (RESILIENT)")
    print("🏠 Market Scraper v7 (RESILIENT)")
    print(f"⏰ {datetime.utcnow().isoformat()}")
    print(f"Mode: {'RESUME' if resume_mode else 'FRESH'}")
    print("=" * 60)

    # Initialize checkpoint
    checkpoint = Checkpoint()
    Checkpoint.cleanup_old()  # Remove old checkpoint files

    if resume_mode:
        loaded = checkpoint.load()
        if loaded:
            print(f"📂 Resuming: {len(checkpoint._completed_pairs())} pairs already done")
            # Check if already fully complete
            if checkpoint.all_cities_done():
                print("✅ All cities already completed in checkpoint!")
                if checkpoint.has_failures():
                    print("⚠️  But there were failures - re-run without --resume to retry")
                    sys.exit(1)
                # Just need to export
                conn = init_db()
                exported = export_json(conn)
                conn.close()
                print(f"📤 Exported {exported} to {OUTPUT_JSON}")
                checkpoint.cleanup()
                sys.exit(0)
        else:
            print("📂 No checkpoint found, starting fresh")
    else:
        # Fresh run: clear any existing checkpoint for today
        if os.path.exists(checkpoint.path):
            os.remove(checkpoint.path)
            print("🗑️  Cleared existing checkpoint (fresh run)")

    conn = init_db()
    session = create_session()

    total = 0
    cities_completed = 0
    interrupted = False

    for city, urls in CITIES.items():
        if SHUTDOWN_REQUESTED:
            logging.warning(f"Shutdown requested, stopping after {cities_completed} cities")
            print(f"\n⚠️  Shutdown after {cities_completed}/{len(CITIES)} cities")
            interrupted = True
            break

        print(f"\n📍 {city}")

        # === IMOT.BG ===
        if checkpoint.is_done(city, 'imot.bg'):
            prev = checkpoint.get_result(city, 'imot.bg')
            status = "✓" if prev['success'] else "✗"
            print(f"  ⏭️  imot.bg: skipped (checkpoint: {status} {prev['count']} listings)")
        else:
            print(f"  🔍 imot.bg... ", end="", flush=True)
            listings, success, error = scrape_imot_city(session, urls['imot'], city)

            if SHUTDOWN_REQUESTED and not success:
                # Interrupted mid-scrape - save what we got to DB but don't mark complete
                if listings:
                    save_listings(conn, listings)
                    print(f"💾 {len(listings)} saved (interrupted, will retry)")
                else:
                    print("interrupted")
                interrupted = True
                break

            saved = save_listings(conn, listings)
            checkpoint.mark_done(city, 'imot.bg', success, len(listings), error)
            print(f"{'✓' if success else '✗'} {len(listings)} → {saved} saved")
            total += saved

        if SHUTDOWN_REQUESTED:
            interrupted = True
            break

        # === OLX.BG ===
        if checkpoint.is_done(city, 'olx.bg'):
            prev = checkpoint.get_result(city, 'olx.bg')
            status = "✓" if prev['success'] else "✗"
            print(f"  ⏭️  olx.bg: skipped (checkpoint: {status} {prev['count']} listings)")
        else:
            print(f"  🔍 olx.bg... ", end="", flush=True)
            listings, success, error = scrape_olx(session, urls['olx'], city)

            if SHUTDOWN_REQUESTED and not success:
                if listings:
                    save_listings(conn, listings)
                    print(f"💾 {len(listings)} saved (interrupted, will retry)")
                else:
                    print("interrupted")
                interrupted = True
                break

            saved = save_listings(conn, listings)
            checkpoint.mark_done(city, 'olx.bg', success, len(listings), error)
            print(f"{'✓' if success else '✗'} {len(listings)} → {saved} saved")
            total += saved

        cities_completed += 1

    # === RESULTS ===
    print("\n" + "=" * 60)
    print("SCRAPING RESULTS PER SOURCE")
    print("=" * 60)
    print(checkpoint.get_summary())

    # Stats from DB
    print("\n" + "=" * 60)
    print("📊 DATABASE STATISTICS")
    print("=" * 60)

    cursor = conn.cursor()

    print("\nBy source:")
    for row in cursor.execute("""
        SELECT source, COUNT(*), ROUND(AVG(price_per_sqm), 0)
        FROM market_listings WHERE price_per_sqm IS NOT NULL
        GROUP BY source
    """):
        print(f"  {row[0]}: {row[1]} listings, avg €{row[2]}/m²")

    print("\nBy city:")
    for row in cursor.execute("""
        SELECT city, COUNT(*), ROUND(AVG(price_per_sqm), 0)
        FROM market_listings WHERE price_per_sqm IS NOT NULL
        GROUP BY city ORDER BY COUNT(*) DESC
    """):
        print(f"  {row[0]}: {row[1]} listings, avg €{row[2]}/m²")

    # === FINAL VERDICT ===
    print(f"\n{'=' * 60}")

    if interrupted:
        print(f"⏸️  INTERRUPTED - checkpoint saved at {checkpoint.path}")
        print(f"   Resume with: python3 market_scraper.py --resume")
        conn.close()
        logging.warning(f"Interrupted: {len(checkpoint._completed_pairs())} pairs done, checkpoint saved")
        print(f"\n⏸️  Done: {datetime.utcnow().isoformat()} [INTERRUPTED - RESUMABLE]")
        sys.exit(2)  # EXIT CODE 2 = INTERRUPTED (resumable)

    if not checkpoint.all_cities_done():
        print(f"❌ INCOMPLETE: Not all cities scraped")
        conn.close()
        sys.exit(1)

    if checkpoint.has_failures():
        print(f"❌ FAILED: Some sources did not return enough data")
        print(f"Total successful listings: {checkpoint.get_total_listings()}")
        conn.close()
        logging.error("Done: FAILED (insufficient data)")
        print(f"\n❌ Done: {datetime.utcnow().isoformat()} [FAILED]")
        sys.exit(1)  # EXIT CODE 1 = SCRAPER FAILURE

    # All good - export
    exported = export_json(conn)
    print(f"✅ SUCCESS: {exported} listings, all {len(CITIES)} cities complete")
    print(f"{'=' * 60}")

    conn.close()
    checkpoint.cleanup()  # Remove checkpoint on success

    logging.info(f"Done: {exported} listings, {len(CITIES)} cities, SUCCESS")
    print(f"\n✅ Done: {datetime.utcnow().isoformat()} [SUCCESS]")
    sys.exit(0)


if __name__ == '__main__':
    main()
