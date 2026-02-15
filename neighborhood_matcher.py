#!/usr/bin/env python3
"""
Neighborhood/District Matcher for Real Estate Price Matching

Key functions:
- normalize_neighborhood(text) - Normalizes neighborhood names
- extract_neighborhood(address) - Extracts district from address strings
- neighborhood_similarity(hood1, hood2) - Calculates similarity score (0.0-1.0)
"""

import re


# Canonical neighborhood aliases (handles variations)
NEIGHBORHOOD_ALIASES = {
    # Sofia
    'люлин': ['люлин', 'lyulin'],
    'младост': ['младост', 'mladost'],
    'лозенец': ['лозенец', 'lozenec'],
    'дружба': ['дружба', 'druzhba'],
    'надежда': ['надежда', 'nadezhda'],
    'красно село': ['красно село', 'krasno selo'],
    'студентски': ['студентски', 'studentski'],
    'овча купел': ['овча купел', 'ovcha kupel'],
    'витоша': ['витоша', 'vitosha'],
    'банишора': ['банишора', 'banishora'],
    'хиподрума': ['хиподрума', 'hipodruma'],
    'илинден': ['илинден', 'ilinden'],
    'подуяне': ['подуяне', 'poduyane'],
    'хаджи димитър': ['хаджи димитър', 'hadji dimitar'],
    'център': ['център', 'center', 'centar'],
    
    # Plovdiv
    'тракия': ['тракия', 'trakia'],
    'кючук париж': ['кючук париж', 'kyuchuk parizh'],
    'смирненски': ['смирненски', 'smirnenski'],
    
    # Varna
    'чайка': ['чайка', 'chaika'],
    'владиславово': ['владиславово', 'vladislavovo'],
    'левски': ['левски', 'levski'],
    
    # Black Sea resorts
    'слънчев бряг': ['слънчев бряг', 'sunny beach'],
    'несебър': ['несебър', 'nessebar'],
    'равда': ['равда', 'ravda'],
    'свети влас': ['свети влас', 'sveti vlas'],
}


def normalize_neighborhood(text):
    """
    Normalize neighborhood name for comparison.
    Removes numbers (block numbers), standardizes case, strips prefixes.
    """
    if not text:
        return None
    
    # Lowercase and clean
    text = text.lower().strip()
    
    # Remove common prefixes
    text = re.sub(r'^(ж\.?\s*к\.?|жк\.?|кв\.?|район|квартал|местност)\s*', '', text)
    
    # Remove block/entrance numbers (e.g., "Люлин 9" -> "Люлин")
    text = re.sub(r'\s*\d+\s*$', '', text)
    text = re.sub(r'\s*бл\.?\s*\d+', '', text)
    text = re.sub(r'\s*вх\.?\s*[а-яa-z]', '', text)
    
    # Remove quotes
    text = text.replace('"', '').replace("'", '').strip()
    
    # Check aliases
    for canonical, aliases in NEIGHBORHOOD_ALIASES.items():
        if text in aliases or text.startswith(canonical):
            return canonical
    
    return text if text else None


def extract_neighborhood(address):
    """
    Extract neighborhood/district from Bulgarian address string.
    
    Handles patterns like:
    - ж.к. Люлин
    - жк Младост 1
    - кв. Лозенец
    - район Триадица
    """
    if not address:
        return None
    
    addr_lower = address.lower()
    
    # Patterns in order of specificity
    patterns = [
        r'ж\.?\s*к\.?\s*["\']?([а-яА-Я\s\d-]+)',  # ж.к. X
        r'жк\.?\s*["\']?([а-яА-Я\s\d-]+)',         # жк X
        r'кв\.?\s*["\']?([а-яА-Я\s\d-]+)',         # кв. X
        r'квартал\s*["\']?([а-яА-Я\s-]+)',         # квартал X
        r'район\s*["\']?([а-яА-Я\s-]+)',           # район X
        r'местност\s*["\']?([а-яА-Я\s-]+)',        # местност X
        r'ул\.\s*["\']?([а-яА-Я\s\d-]+)',          # ул. X (street)
    ]
    
    for pattern in patterns:
        match = re.search(pattern, addr_lower)
        if match:
            hood = match.group(1).strip()
            return normalize_neighborhood(hood)
    
    return None


def neighborhood_similarity(hood1, hood2):
    """
    Calculate similarity score between two neighborhoods (0.0 to 1.0).
    
    Returns:
        1.0: Exact match after normalization
        0.8: Same base neighborhood (e.g., Люлин 1 vs Люлин 7)
        0.5: Partial match
        0.0: No match
    """
    if not hood1 or not hood2:
        return 0.0
    
    norm1 = normalize_neighborhood(hood1)
    norm2 = normalize_neighborhood(hood2)
    
    if not norm1 or not norm2:
        return 0.0
    
    # Exact match
    if norm1 == norm2:
        return 1.0
    
    # Check if one contains the other (e.g., "младост 1" matches "младост")
    if norm1 in norm2 or norm2 in norm1:
        return 0.8
    
    # Check canonical aliases
    for canonical, aliases in NEIGHBORHOOD_ALIASES.items():
        if (norm1 == canonical or norm1 in aliases) and \
           (norm2 == canonical or norm2 in aliases):
            return 0.9
    
    # Levenshtein-like similarity for close matches
    # (simplified - just check prefix matching)
    min_len = min(len(norm1), len(norm2))
    if min_len >= 3:
        common_prefix = 0
        for i in range(min_len):
            if norm1[i] == norm2[i]:
                common_prefix += 1
            else:
                break
        if common_prefix >= 3:
            return 0.5 * (common_prefix / min_len)
    
    return 0.0


if __name__ == '__main__':
    # Test cases
    test_addresses = [
        'гр. София, ж.к. "Люлин 9", бл. 123',
        'София, кв. Лозенец, ул. Черни връх 15',
        'гр. Варна, район Приморски, ул. Морска',
        'ж.к. Младост 1, бл. 45, вх. А',
        'гр. Пловдив, жк Тракия, бл. 200',
    ]
    
    print("=== Neighborhood Extraction Tests ===\n")
    for addr in test_addresses:
        hood = extract_neighborhood(addr)
        print(f"  {addr[:50]}...")
        print(f"    → {hood}")
        print()
    
    print("=== Similarity Tests ===\n")
    pairs = [
        ('Люлин 9', 'Люлин 7'),
        ('ж.к. Младост', 'Младост 1'),
        ('Лозенец', 'Център'),
        ('кв. Тракия', 'жк Тракия'),
    ]
    for h1, h2 in pairs:
        sim = neighborhood_similarity(h1, h2)
        print(f"  {h1} vs {h2}: {sim:.2f}")
