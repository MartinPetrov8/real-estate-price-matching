#!/usr/bin/env python3
"""
QA Test Suite for Real Estate Scraper v2
"""

import os
import sys
import sqlite3
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scrapers'))

DB_PATH = "data/auctions.db"
MARKET_DB = "data/market.db"


def test_neighborhood_extraction():
    """Test neighborhood extraction from addresses."""
    print("Testing neighborhood extraction...")
    
    from bcpea_v5 import extract_neighborhood_from_address
    
    test_cases = [
        ("гр. София, ж.к. Люлин, бл.883", "Люлин"),
        ("гр. София, кв. Лозенец", "Лозенец"),
        ("София, жк Младост 1", "Младост"),
        ("Варна, кв. Чайка", "Чайка"),
        ("гр. Пловдив, ж.к. Тракия", "Тракия"),
        ("Бургас", None),
        ("", None),
    ]
    
    passed = 0
    for address, expected in test_cases:
        result = extract_neighborhood_from_address(address)
        if result == expected:
            passed += 1
        else:
            print(f"  ⚠️  Expected '{expected}', got '{result}' for: {address}")
    
    print(f"  Passed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_no_hardcoded_caps():
    """Verify no hardcoded price caps in comparison logic."""
    print("Testing NO hardcoded caps...")
    
    # Read the comparison file
    with open('scrapers/neighborhood_comparison.py', 'r') as f:
        content = f.read()
    
    # Check for forbidden patterns
    forbidden = ['get_price_cap', 'price_cap', 'max_price', 'min_price']
    found = [p for p in forbidden if p in content.lower()]
    
    if found:
        print(f"  ❌ Found hardcoded cap references: {found}")
        return False
    
    # Check it uses actual market data queries
    required = ['market_listings', 'SELECT price_per_sqm', 'median']
    missing = [p for p in required if p not in content]
    
    if missing:
        print(f"  ❌ Missing market data patterns: {missing}")
        return False
    
    print("  ✓ No hardcoded caps found, uses real market data")
    return True


def test_db_schema():
    """Test database has neighborhood column."""
    print("Testing database schema...")
    
    if not os.path.exists(DB_PATH):
        print("  ⚠️  No database yet (run scraper first)")
        return True
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(auctions)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'neighborhood' not in columns:
        print("  ❌ Missing 'neighborhood' column in auctions table")
        conn.close()
        return False
    
    conn.close()
    print("  ✓ Database has neighborhood column")
    return True


def test_market_db_schema():
    """Test market DB has neighborhood column."""
    print("Testing market DB schema...")
    
    if not os.path.exists(MARKET_DB):
        print("  ⚠️  No market DB yet (run market scraper first)")
        return True
    
    conn = sqlite3.connect(MARKET_DB)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(market_listings)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'neighborhood' not in columns:
        print("  ❌ Missing 'neighborhood' column in market_listings table")
        conn.close()
        return False
    
    conn.close()
    print("  ✓ Market DB has neighborhood column")
    return True


def test_comparison_has_match_type():
    """Test comparisons table has match_type field."""
    print("Testing comparison schema...")
    
    if not os.path.exists(DB_PATH):
        print("  ⚠️  No database yet")
        return True
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(comparisons)")
    columns = {row[1] for row in cursor.fetchall()}
    
    required = {'match_type', 'market_sample_size', 'bargain_score'}
    if not required.issubset(columns):
        missing = required - columns
        print(f"  ❌ Missing columns: {missing}")
        conn.close()
        return False
    
    conn.close()
    print("  ✓ Comparisons table has required fields")
    return True


def test_export_has_new_fields():
    """Test export_deals_v2 has new fields."""
    print("Testing export script...")
    
    with open('export_deals_v2.py', 'r') as f:
        content = f.read()
    
    required = ['match_type', 'market_sample_size', 'auction_price_sqm', 'market_price_sqm']
    missing = [f for f in required if f not in content]
    
    if missing:
        print(f"  ❌ Missing fields in export: {missing}")
        return False
    
    print("  ✓ Export has all new fields")
    return True


def test_timeout_implementation():
    """Test bcpea_v5 has proper timeouts."""
    print("Testing timeout implementation...")
    
    with open('scrapers/bcpea_v5.py', 'r') as f:
        content = f.read()
    
    required = ['socket.setdefaulttimeout', 'urllib.request.urlopen.*timeout']
    
    # Check for socket timeout
    if 'socket.setdefaulttimeout' not in content:
        print("  ❌ Missing socket.setdefaulttimeout")
        return False
    
    # Check for urlopen timeout
    if 'timeout=' not in content or 'REQUEST_TIMEOUT' not in content:
        print("  ❌ Missing urlopen timeout")
        return False
    
    print("  ✓ Proper timeouts implemented")
    return True


def main():
    print("="*60)
    print("REAL ESTATE SCRAPER v2 - QA TEST SUITE")
    print("="*60)
    print()
    
    os.chdir('/workspace/real-estate-price-matching')
    
    tests = [
        ("Neighborhood Extraction", test_neighborhood_extraction),
        ("No Hardcoded Caps", test_no_hardcoded_caps),
        ("Database Schema", test_db_schema),
        ("Market DB Schema", test_market_db_schema),
        ("Comparison Schema", test_comparison_has_match_type),
        ("Export Fields", test_export_has_new_fields),
        ("Timeout Implementation", test_timeout_implementation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results.append((name, False))
        print()
    
    print("="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for name, result in results:
        status = "✓ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    print()
    print(f"Result: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED - Ready for production!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed - Review before production")
        return 1


if __name__ == '__main__':
    sys.exit(main())
