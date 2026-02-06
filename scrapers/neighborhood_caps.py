#!/usr/bin/env python3
"""
Neighborhood-based price caps for Sofia properties.
Panel block areas have MUCH lower prices than city center.

Prices in EUR/m² (as of Feb 2026)
"""

# Sofia neighborhoods by tier (EUR/m²)
SOFIA_PRICE_CAPS = {
    # Panel block neighborhoods (ж.к.) - €700-1200/m²
    'люлин': {'min': 600, 'max': 1200, 'median': 900},
    'младост': {'min': 800, 'max': 1400, 'median': 1100},
    'дружба': {'min': 600, 'max': 1100, 'median': 850},
    'надежда': {'min': 600, 'max': 1100, 'median': 850},
    'обеля': {'min': 600, 'max': 1000, 'median': 800},
    'връбница': {'min': 600, 'max': 1100, 'median': 850},
    'сухата река': {'min': 600, 'max': 1000, 'median': 800},
    'хаджи димитър': {'min': 700, 'max': 1200, 'median': 950},
    'подуяне': {'min': 700, 'max': 1200, 'median': 950},
    'левски': {'min': 800, 'max': 1300, 'median': 1050},
    'красна поляна': {'min': 600, 'max': 1100, 'median': 850},
    'захарна фабрика': {'min': 600, 'max': 1000, 'median': 800},
    'фондови жилища': {'min': 600, 'max': 1000, 'median': 800},
    'овча купел': {'min': 700, 'max': 1200, 'median': 950},
    'горубляне': {'min': 700, 'max': 1200, 'median': 950},
    'дианабад': {'min': 900, 'max': 1500, 'median': 1200},
    'слатина': {'min': 800, 'max': 1300, 'median': 1050},
    'гео милев': {'min': 900, 'max': 1500, 'median': 1200},
    'редута': {'min': 800, 'max': 1300, 'median': 1050},
    'света троица': {'min': 700, 'max': 1200, 'median': 950},
    'банишора': {'min': 700, 'max': 1200, 'median': 950},
    'хиподрума': {'min': 800, 'max': 1400, 'median': 1100},
    'борово': {'min': 900, 'max': 1500, 'median': 1200},
    'манастирски ливади': {'min': 1000, 'max': 1600, 'median': 1300},
    'стрелбище': {'min': 900, 'max': 1500, 'median': 1200},
    
    # Better neighborhoods - €1200-2000/m²
    'изток': {'min': 1500, 'max': 2500, 'median': 2000},
    'лозенец': {'min': 1800, 'max': 3000, 'median': 2400},
    'докторски паметник': {'min': 1500, 'max': 2500, 'median': 2000},
    'център': {'min': 1500, 'max': 3000, 'median': 2200},
    'иван вазов': {'min': 1400, 'max': 2200, 'median': 1800},
    'яворов': {'min': 1400, 'max': 2200, 'median': 1800},
    
    # Premium areas - €2000-4000/m²
    'витоша': {'min': 2000, 'max': 4000, 'median': 2800},
    'бояна': {'min': 2000, 'max': 4000, 'median': 2800},
    'драгалевци': {'min': 1500, 'max': 3000, 'median': 2200},
    'симеоново': {'min': 1500, 'max': 2500, 'median': 2000},
}

# Default for unknown Sofia neighborhoods
SOFIA_DEFAULT = {'min': 800, 'max': 1500, 'median': 1100}

# Other Bulgarian cities - rough estimates
CITY_DEFAULTS = {
    'варна': {'min': 800, 'max': 2000, 'median': 1200},
    'бургас': {'min': 600, 'max': 1500, 'median': 900},
    'пловдив': {'min': 600, 'max': 1500, 'median': 900},
    'русе': {'min': 400, 'max': 1000, 'median': 600},
    'стара загора': {'min': 400, 'max': 900, 'median': 550},
    'плевен': {'min': 300, 'max': 800, 'median': 450},
    'банско': {'min': 600, 'max': 1500, 'median': 900},
    'несебър': {'min': 800, 'max': 2000, 'median': 1200},
    'свети влас': {'min': 800, 'max': 2000, 'median': 1200},
    'слънчев бряг': {'min': 500, 'max': 1200, 'median': 700},
}

# Fallback for unknown cities
UNKNOWN_DEFAULT = {'min': 400, 'max': 1200, 'median': 700}


def extract_neighborhood(address):
    """Extract neighborhood from address string."""
    if not address:
        return None
    
    addr_lower = address.lower()
    
    # Check for ж.к. pattern
    import re
    jk_match = re.search(r'ж\.?\s*к\.?\s*["\']?([а-яА-Я\s\d-]+)', addr_lower)
    if jk_match:
        hood = jk_match.group(1).strip()
        # Remove trailing block numbers
        hood = re.sub(r'[\s,]*бл\.?\s*\d+.*$', '', hood).strip()
        return hood
    
    # Check for кв. pattern
    kv_match = re.search(r'кв\.?\s*["\']?([а-яА-Я\s-]+)', addr_lower)
    if kv_match:
        return kv_match.group(1).strip()
    
    return None


def get_price_cap(city, address):
    """Get realistic price cap for a property based on location.
    
    Returns dict with min, max, median EUR/m² estimates.
    """
    city_lower = city.lower().replace('гр. ', '').replace('с. ', '').strip()
    
    # Check if Sofia
    if 'софия' in city_lower or 'sofia' in city_lower:
        # Try to extract neighborhood
        hood = extract_neighborhood(address)
        
        if hood:
            # Check against known neighborhoods
            for key, caps in SOFIA_PRICE_CAPS.items():
                if key in hood.lower():
                    return caps
        
        # Unknown Sofia neighborhood
        return SOFIA_DEFAULT
    
    # Other cities
    for city_key, caps in CITY_DEFAULTS.items():
        if city_key in city_lower:
            return caps
    
    return UNKNOWN_DEFAULT


def apply_cap(estimated_sqm, city, address):
    """Apply realistic cap to an estimated price per sqm.
    
    Returns (capped_price, was_capped, cap_info)
    """
    caps = get_price_cap(city, address)
    
    if estimated_sqm > caps['max']:
        return caps['median'], True, caps
    elif estimated_sqm < caps['min']:
        return caps['median'], True, caps
    else:
        return estimated_sqm, False, caps


if __name__ == '__main__':
    # Test cases
    test_cases = [
        ('гр. София', 'ж.к. Люлин, бл.883, вх.3, ет.9'),
        ('гр. София', 'кв. Лозенец, ул. Златен рог 15'),
        ('гр. София', 'жк Младост 1, бл. 45'),
        ('гр. Бургас', 'ул. Александровска 25'),
        ('с. Кранево', 'някакъв адрес'),
    ]
    
    for city, addr in test_cases:
        hood = extract_neighborhood(addr)
        caps = get_price_cap(city, addr)
        print(f"{city}, {addr}")
        print(f"  → Neighborhood: {hood}")
        print(f"  → Price cap: €{caps['min']}-{caps['max']}/m², median €{caps['median']}/m²")
        print()
