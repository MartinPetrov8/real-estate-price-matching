#!/usr/bin/env python3
"""
Bulgarian Real Estate Multi-Source Scraper
Sources: КЧСИ (bcpea.org), imoti.net, alo.bg
"""

import json
import re
import urllib.request
import urllib.error
from datetime import datetime
from html.parser import HTMLParser

# Simple HTML to text converter
class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, data):
        self.text.append(data)
    def get_text(self):
        return ' '.join(self.text)

def fetch_url(url):
    """Fetch URL content"""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8', errors='ignore')

def parse_price_eur(text):
    """Extract EUR price from text"""
    match = re.search(r'([\d\s,.]+)\s*(?:EUR|€)', text)
    if match:
        price = match.group(1).replace(' ', '').replace(',', '')
        try:
            return float(price)
        except:
            pass
    return None

def scrape_bcpea(pages=10):
    """Scrape КЧСИ auctions"""
    listings = []
    for page in range(1, pages + 1):
        try:
            html = fetch_url(f'https://sales.bcpea.org/properties?page={page}')
            parser = HTMLTextExtractor()
            parser.feed(html)
            text = parser.get_text()
            
            # Find Sofia properties with prices
            blocks = re.split(r'EUR\s+Начална цена', text)
            for i, block in enumerate(blocks[:-1]):
                price_match = re.search(r'([\d\s,.]+)\s*$', blocks[i-1] if i > 0 else '')
                if 'София' in block:
                    price = parse_price_eur(block + ' EUR')
                    addr_match = re.search(r'Адрес\s+([^\n]+)', block)
                    listings.append({
                        'source': 'BCPEA',
                        'price_eur': price,
                        'city': 'София',
                        'address': addr_match.group(1) if addr_match else None,
                        'type': 'auction'
                    })
            print(f'BCPEA page {page}: {len(listings)} Sofia listings total')
        except Exception as e:
            print(f'BCPEA page {page} error: {e}')
    return listings

def scrape_imoti_net(pages=5):
    """Scrape imoti.net Sofia listings"""
    listings = []
    base_url = 'https://www.imoti.net/bg/obiavi/r/prodava/sofia/'
    
    try:
        html = fetch_url(base_url)
        
        # Extract listings - pattern from actual HTML structure
        # Find property cards with price and details
        # Look for: [TYPE], [SIZE] м2 ... [PRICE] EUR
        blocks = re.findall(r'продава\s+([\w\s]+),\s*(\d+)\s*м2[^€E]+?([\d\s]+)\s*EUR', html, re.IGNORECASE)
        
        for prop_type, size, price in blocks:
            try:
                price_clean = float(price.replace(' ', '').replace(',', ''))
                size_int = int(size)
                listings.append({
                    'source': 'imoti.net',
                    'price_eur': price_clean,
                    'city': 'София',
                    'type': prop_type.strip(),
                    'size_sqm': size_int,
                    'price_per_sqm': round(price_clean / size_int, 2)
                })
            except:
                pass
        
        # Alternative: look for price patterns directly
        if not listings:
            prices = re.findall(r'([\d\s]+)\s*EUR\s*([\d\s]+)\s*BGN', html)
            for eur, bgn in prices[:20]:  # Limit to first 20
                try:
                    listings.append({
                        'source': 'imoti.net',
                        'price_eur': float(eur.replace(' ', '')),
                        'city': 'София',
                        'type': 'property'
                    })
                except:
                    pass
        
        print(f'imoti.net: {len(listings)} Sofia listings')
    except Exception as e:
        print(f'imoti.net error: {e}')
    return listings

def scrape_alo_bg():
    """Scrape alo.bg Sofia listings"""
    listings = []
    try:
        html = fetch_url('https://www.alo.bg/obiavi/imoti-prodajbi/?region=sofia')
        parser = HTMLTextExtractor()
        parser.feed(html)
        text = parser.get_text()
        
        # Extract prices and locations
        # Pattern: [PRICE] € ([BGN])от днес URL [TITLE] [LOCATION]
        matches = re.findall(r'([\d\s]+)\s*€[^С]*София', text)
        for price in matches:
            listings.append({
                'source': 'alo.bg',
                'price_eur': float(price.replace(' ', '')),
                'city': 'София',
                'type': 'listing'
            })
        print(f'alo.bg: {len(listings)} Sofia listings')
    except Exception as e:
        print(f'alo.bg error: {e}')
    return listings

def main():
    print(f"=== Bulgarian Real Estate Scraper - {datetime.utcnow().isoformat()} ===\n")
    
    all_listings = []
    
    # Scrape all sources
    all_listings.extend(scrape_bcpea(pages=5))
    all_listings.extend(scrape_imoti_net())
    all_listings.extend(scrape_alo_bg())
    
    # Summary
    print(f"\n=== SUMMARY ===")
    print(f"Total listings: {len(all_listings)}")
    
    by_source = {}
    for l in all_listings:
        by_source[l['source']] = by_source.get(l['source'], 0) + 1
    print(f"By source: {by_source}")
    
    prices = [l['price_eur'] for l in all_listings if l.get('price_eur')]
    if prices:
        print(f"Price range: €{min(prices):,.0f} - €{max(prices):,.0f}")
        print(f"Average: €{sum(prices)/len(prices):,.0f}")
    
    # Save results
    output = {
        'scraped_at': datetime.utcnow().isoformat(),
        'summary': {
            'total': len(all_listings),
            'by_source': by_source,
            'price_min': min(prices) if prices else None,
            'price_max': max(prices) if prices else None,
            'price_avg': sum(prices)/len(prices) if prices else None
        },
        'listings': all_listings
    }
    
    with open('data/all_listings.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to data/all_listings.json")

if __name__ == '__main__':
    main()
