#!/usr/bin/env python3
"""Diagnose site structure for market scrapers"""

import os
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/host-workspace/.browsers'

from playwright.sync_api import sync_playwright
import re

def diagnose_imot(page):
    """Check imot.bg structure"""
    print("\n=== IMOT.BG DIAGNOSIS ===")
    url = 'https://www.imot.bg/pcgi/imot.cgi?act=3&session_id=&f1=1&f2=1&f3=1&f4=1&f5=1'
    page.goto(url, wait_until='networkidle', timeout=30000)
    
    # Save screenshot
    page.screenshot(path='/host-workspace/real-estate-price-matching/scrapers/data/imot_screenshot.png')
    print("Screenshot saved: data/imot_screenshot.png")
    
    # Get page content
    content = page.content()
    with open('/host-workspace/real-estate-price-matching/scrapers/data/imot_page.html', 'w') as f:
        f.write(content)
    print("HTML saved: data/imot_page.html")
    
    # Check for price patterns
    eur_prices = re.findall(r'([\d\s]+)\s*(?:EUR|€|euro)', content, re.IGNORECASE)
    print(f"EUR prices found: {len(eur_prices)}")
    if eur_prices[:5]:
        print(f"  Samples: {eur_prices[:5]}")
    
    sqm_patterns = re.findall(r'(\d+)\s*(?:кв\.?\s*м|m²)', content)
    print(f"Sqm patterns found: {len(sqm_patterns)}")
    if sqm_patterns[:5]:
        print(f"  Samples: {sqm_patterns[:5]}")
    
    # Check listing selectors
    for selector in ['.lnk1', '.lnk2', '.photoLink', '.adBox', 'a[href*="properties"]']:
        els = page.query_selector_all(selector)
        print(f"  Selector '{selector}': {len(els)} elements")


def diagnose_olx(page):
    """Check OLX structure"""
    print("\n=== OLX.BG DIAGNOSIS ===")
    url = 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/sofia/'
    page.goto(url, wait_until='networkidle', timeout=30000)
    
    page.screenshot(path='/host-workspace/real-estate-price-matching/scrapers/data/olx_screenshot.png')
    print("Screenshot saved: data/olx_screenshot.png")
    
    content = page.content()
    with open('/host-workspace/real-estate-price-matching/scrapers/data/olx_page.html', 'w') as f:
        f.write(content)
    print("HTML saved: data/olx_page.html")
    
    # Get a card and print its text
    cards = page.query_selector_all('[data-cy="l-card"]')
    print(f"Cards found: {len(cards)}")
    
    if cards:
        sample_text = cards[0].inner_text()
        print(f"\nSample card text:\n{sample_text[:500]}")
        
        # Check price patterns in card
        eur_match = re.search(r'([\d\s]+)\s*(?:EUR|€)', sample_text)
        bgn_match = re.search(r'([\d\s]+)\s*лв', sample_text)
        sqm_match = re.search(r'(\d+)\s*(?:кв\.?\s*м|m²)', sample_text)
        
        print(f"\nIn card - EUR: {eur_match}, BGN: {bgn_match}, SQM: {sqm_match}")


def diagnose_alo(page):
    """Check alo.bg structure"""
    print("\n=== ALO.BG DIAGNOSIS ===")
    url = 'https://www.alo.bg/obiavi/imoti-prodajbi/apartamenti-stai/?city_id=1'
    page.goto(url, wait_until='networkidle', timeout=30000)
    
    page.screenshot(path='/host-workspace/real-estate-price-matching/scrapers/data/alo_screenshot.png')
    print("Screenshot saved: data/alo_screenshot.png")
    
    content = page.content()
    with open('/host-workspace/real-estate-price-matching/scrapers/data/alo_page.html', 'w') as f:
        f.write(content)
    print("HTML saved: data/alo_page.html")
    
    # Check various selectors
    for selector in ['.ads-list-item', '.listing-item', '.classified', 'article', '.card', '[class*="listing"]', '[class*="ad"]']:
        els = page.query_selector_all(selector)
        print(f"  Selector '{selector}': {len(els)} elements")
    
    # Get page text snippet
    text = page.inner_text('body')[:2000]
    print(f"\nPage text sample:\n{text[:1000]}")


def main():
    os.makedirs('/host-workspace/real-estate-price-matching/scrapers/data', exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='bg-BG'
        )
        page = context.new_page()
        
        try:
            diagnose_imot(page)
        except Exception as e:
            print(f"imot.bg error: {e}")
        
        try:
            diagnose_olx(page)
        except Exception as e:
            print(f"olx.bg error: {e}")
        
        try:
            diagnose_alo(page)
        except Exception as e:
            print(f"alo.bg error: {e}")
        
        browser.close()
    
    print("\n=== DIAGNOSIS COMPLETE ===")
    print("Check screenshots and HTML files in scrapers/data/")


if __name__ == '__main__':
    main()
