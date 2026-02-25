#!/usr/bin/env python3
"""Test OLX district scraping for Varna (small, fast)"""
import requests, re
import sys; sys.path.insert(0, 'scrapers')
from bs4 import BeautifulSoup
from market_scraper import get_olx_districts, scrape_olx_district, USER_AGENTS, create_session
import random

session = create_session()
city = 'Варна'
url = 'https://www.olx.bg/nedvizhimi-imoti/prodazhbi/apartamenti/varna/'

print(f"Discovering {city} districts...")
districts = get_olx_districts(session, url)
print(f"Found: {len(districts)} districts")
for did, name in list(districts.items())[:8]:
    print(f"  {did}: {name}")

print(f"\nScraping first 5 districts...")
all_listings = []
for i, (did, dname) in enumerate(list(districts.items())[:5]):
    listings = scrape_olx_district(session, url, city, did, dname)
    all_listings.extend(listings)
    print(f"  District {i+1} ({dname}): {len(listings)} listings")

print(f"\nTotal: {len(all_listings)} listings from 5 districts")
print("Sample neighborhoods:")
for L in all_listings[:10]:
    print(f"  {L.neighborhood}: {L.size_sqm}m² @ {L.price_per_sqm}EUR/m²")
