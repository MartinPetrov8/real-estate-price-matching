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
    'красно село': ['красно село', 'krasno selo', 'красна поляна'],  # р-н Красна поляна contains кв. Красно село
    'студентски': ['студентски', 'studentski', 'студентски град'],
    'овча купел': ['овча купел', 'ovcha kupel'],
    'витоша': ['витоша', 'vitosha'],
    'банишора': ['банишора', 'banishora'],
    'хиподрума': ['хиподрума', 'hipodruma', 'красна поляна'],  # also р-н Красна поляна
    'илинден': ['илинден', 'ilinden'],
    'подуяне': ['подуяне', 'poduyane', 'слатина'],  # р-н Слатина contains подуяне
    'хаджи димитър': ['хаджи димитър', 'hadji dimitar'],
    'сухата река': ['сухата река', 'suha reka'],
    'гео милев': ['гео милев', 'geo milev'],
    'слатина': ['слатина'],
    'изгрев': ['изгрев', 'izgrev'],
    'изток': ['изток', 'iztok'],
    'оборище': ['оборище', 'oborishte'],
    'яворов': ['яворов', 'yavorov'],
    'център': ['център', 'center', 'centar'],
    
    # Plovdiv
    'тракия': ['тракия', 'trakia'],
    'кючук париж': ['кючук париж', 'kyuchuk parizh'],
    'смирненски': ['смирненски', 'smirnenski'],
    
    # Varna
    'чайка': ['чайка', 'chaika'],
    'владиславово': ['владиславово', 'vladislavovo'],
    'левски': ['левски', 'levski'],
    'цветен квартал': ['цветен квартал', 'цветен', 'tsveten kvartal'],
    'владислав варненчик': ['владислав варненчик', 'владиславов', 'вл. варненчик'],
    'трошево': ['трошево', 'troshevo'],
    
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

    Handles:
    - ж.к. Люлин / жк Младост / кв. Лозенец / район X / местност X
    - imot.bg title pattern: "... в град София, Кръстова вада - ..."
    - imot.bg URL slug: "grad-sofiya-lyulin-9-ul-..."
    - Street names (lowest priority, often wrong)
    """
    if not address:
        return None

    addr_lower = address.lower()

    # Patterns in order of specificity (explicit prefixes first)
    patterns = [
        r'ж\.?\s*к\.?\s*["\u201e\u201c]?([а-яА-Я\s\d-]+)',   # ж.к. X
        r'жк\.?\s*["\u201e\u201c]?([а-яА-Я\s\d-]+)',          # жк X
        r'кв\.?\s*(?!м)(?!м²)["\u201e\u201c]?([а-яА-Я\s\d-]+)',  # кв. X (not кв.м)
        r'квартал\s*["\u201e\u201c]?([а-яА-Я\s-]+)',          # квартал X
        r'р-н\s*["\u201e\u201c]?([а-яА-Я\s-]+)',              # р-н X (short for район)
        r'район\s*["\u201e\u201c„]?([а-яА-Я\s-]+)',           # район X / район „X"
        r'местност\s*["\u201e\u201c]?([а-яА-Я\s-]+)',         # местност X
    ]

    for pattern in patterns:
        match = re.search(pattern, addr_lower)
        if match:
            hood = match.group(1).strip()
            result = normalize_neighborhood(hood)
            if result and len(result) > 2:
                return result

    # imot.bg title/H1 pattern: "... град [City], [Neighborhood]\n" or "... в [City], [Hood] -"
    # e.g. "Продава 2-СТАЕН в град София, Кръстова вада - 79 кв.м"
    city_comma = re.search(
        r'(?:град|гр\.)\s+[а-яА-Я]+,\s*([А-Яа-я][а-яА-Я\s\d]+?)(?:\s*[-\n,]|\s+кв\.?|\s+м²|\s*$)',
        address
    )
    if city_comma:
        hood = city_comma.group(1).strip()
        result = normalize_neighborhood(hood)
        if result and len(result) > 2:
            return result

    # imot.bg URL slug: extract segment after city slug
    # e.g. "grad-sofiya-lyulin-9-ul-asen-yordanov" -> "lyulin"
    # Known city slugs to skip
    _city_slugs = {'sofiya', 'plovdiv', 'varna', 'burgas', 'ruse', 'stara-zagora', 'pleven'}
    slug_match = re.search(r'grad-([a-z]+(?:-[a-z]+)?)-', address)
    if slug_match:
        after_city = address[slug_match.end():]
        # First hyphen-separated segment after city slug is usually the neighborhood
        seg_match = re.match(r'([a-z][a-z-]+?)(?:-ul-|-bul-|-bl-|-\d+|-[a-z]{1,2}-|\s|$)', after_city)
        if seg_match:
            slug_hood = seg_match.group(1).replace('-', ' ')
            # Transliterate common BG neighborhoods from Latin slugs
            _slug_map = {
                'lyulin': 'люлин', 'mladost': 'младост', 'lozenets': 'лозенец',
                'druzhba': 'дружба', 'nadezhda': 'надежда', 'krasno selo': 'красно село',
                'studentski': 'студентски', 'ovcha kupel': 'овча купел',
                'vitosha': 'витоша', 'banishora': 'банишора', 'hipodruma': 'хиподрума',
                'ilinden': 'илинден', 'poduyane': 'подуяне',
                'trakia': 'тракия', 'chaika': 'чайка', 'vladislavovo': 'владиславово',
                'levski': 'левски', 'krastova vada': 'кръстова вада',
                'geo milev': 'гео милев', 'borovo': 'борово', 'iztok': 'изток',
                'izgrev': 'изгрев', 'manastirski livadi': 'манастирски ливади',
                'gotse delchev': 'гоце делчев', 'red light': None,  # skip bad matches
            }
            canonical = _slug_map.get(slug_hood)
            if canonical:
                return canonical
            if len(slug_hood) > 3 and slug_hood not in _city_slugs:
                return normalize_neighborhood(slug_hood)

    # Street → neighborhood lookup (for addresses with no ж.к./кв./район prefix)
    # City-scoped to avoid false matches (ул. Македония exists in many Bulgarian cities).
    # Format: (street_fragment, neighborhood, [city_fragments_that_must_match])
    # city_fragments=[] means any city (street is sufficiently unique)
    _street_hood_map = [
        # Sofia — unique enough, unscoped
        ('патриарх евтимий',        'центъра',              ['софия']),
        ('витошка',                 'центъра',              ['софия']),
        ('цар освободител',         'центъра',              ['софия']),
        ('александър стамболийски', 'красно село',          ['софия']),
        ('ивайло петров',           'люлин',                ['софия']),
        ('светлоструй',             'красно село',          ['софия']),
        ('роден кът',               'овча купел',           ['софия']),
        # Varna — scoped to варна
        ('паско желев',             'владислав варненчик',  ['варна']),
        ('скопие',                  'владислав варненчик',  ['варна']),
        ('ростов',                  'младост',              ['варна']),
        ('д-р аршинкова',           'победа',               ['варна']),
        # Varna — Цветен квартал (streets named after flowers)
        # Source: OSM street directory for Цветен квартал suburb
        # Note: BGMaps labels these as "жк Васил Левски" formally, but
        # real estate market uses "Цветен квартал". Cluster fallback to Левски.
        ('роза',                    'цветен квартал',       ['варна']),
        ('люляк',                   'цветен квартал',       ['варна']),
        ('нарцис',                  'цветен квартал',       ['варна']),
        ('иглика',                  'цветен квартал',       ['варна']),
        ('карамфил',                'цветен квартал',       ['варна']),
        ('кокиче',                  'цветен квартал',       ['варна']),
        ('незабравка',              'цветен квартал',       ['варна']),
        ('трендафил',               'цветен квартал',       ['варна']),
        ('тинтява',                 'цветен квартал',       ['варна']),
        ('лотос',                   'цветен квартал',       ['варна']),
        ('ружа',                    'цветен квартал',       ['варна']),
        ('синчец',                  'цветен квартал',       ['варна']),
        ('еделвайс',               'цветен квартал',       ['варна']),
        ('момина сълза',            'цветен квартал',       ['варна']),
        ('бял крем',                'цветен квартал',       ['варна']),
        ('зеленика',                'цветен квартал',       ['варна']),
        ('белите лилии',            'цветен квартал',       ['варна']),
        ('детелина',                'цветен квартал',       ['варна']),
        # Plovdiv — scoped to пловдив
        ('стефан стамболов',        'южен',                 ['пловдив']),
        ('македония',               'южен',                 ['пловдив']),
        ('босилек',                 'изгрев',               ['пловдив']),
        ('лотос',                   'изгрев',               ['пловдив']),
        # Ruse — scoped to русе
        ('рени',                    'широк център',         ['русе']),
        ('панайот волов',           'широк център',         ['русе']),
    ]
    for street_fragment, hood, city_scope in _street_hood_map:
        if street_fragment in addr_lower:
            if not city_scope or any(c in addr_lower for c in city_scope):
                return normalize_neighborhood(hood)

    return None


# Neighborhood clusters — groups of adjacent neighborhoods with similar price levels.
# When exact neighborhood match has too few comps, we fall back to cluster comps.
# Similarity within a cluster scores 0.75 (above the 0.7 threshold used in export_deals.py).
NEIGHBORHOOD_CLUSTERS = {
    'софия_център': {'център', 'оборище', 'яворов', 'изток', 'изгрев', 'лозенец', 'докторски паметник'},
    'софия_южен': {'витоша', 'бояна', 'драгалевци', 'симеоново', 'кръстова вада', 'гоце делчев', 'борово', 'манастирски ливади', 'бъкстон'},
    'софия_запад': {'люлин', 'красно село', 'хиподрума', 'овча купел', 'банишора', 'илинден'},
    'софия_изток': {'младост', 'дружба', 'мусагеница', 'дървеница', 'студентски'},
    'софия_север': {'надежда', 'подуяне', 'хаджи димитър', 'сухата река', 'военна рампа'},
    'софия_ср_център': {'гео милев', 'слатина', 'редута', 'разсадника'},
    # Varna — Цветен квартал is within the larger жк Васил Левски / Базар Левски area
    'варна_левски': {'цветен квартал', 'левски', 'базар левски'},
}


def neighborhood_similarity(hood1, hood2):
    """
    Calculate similarity score between two neighborhoods (0.0 to 1.0).
    
    Returns:
        1.0: Exact match after normalization
        0.8: Same base neighborhood (e.g., Люлин 1 vs Люлин 7)
        0.75: Same cluster (e.g., Оборище vs Център)
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
    
    # Check neighborhood clusters (adjacent areas with similar pricing)
    for cluster_name, members in NEIGHBORHOOD_CLUSTERS.items():
        if norm1 in members and norm2 in members:
            return 0.75
    
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
