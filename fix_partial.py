import re

# Better partial ownership detection
# Should match: "1/6 ид.ч от апартамент", "1/2 идеална част от имота"
# Should NOT match: "идеални части от общите части на сградата"

test_cases = [
    ("4,3490 % идеални части от общите части на сградата", False),  # Common area share
    ("1/6 ид.ч. от апартамента", True),  # Actual partial ownership
    ("1/2 идеална част от имота", True),  # Actual partial ownership
    ("притежава 1/3 идеална част", True),  # Actual partial ownership
    ("8,5% идеални части от общите части", False),  # Common area share
    ("3,45 % идеални части от правото на строеж", False),  # Building rights share
]

# Better patterns - look for fraction followed by ownership indication
# but NOT if it's about common parts
better_patterns = [
    r'притежава\s+\d+/\d+',  # "owns 1/2"
    r'\d+/\d+\s*(ид\.?\s*ч\.?|идеална\s+част)\s*(от|на)\s*(апартамент|имот|жилище)',  # "1/6 ид.ч от апартамент"
    r'\d+/\d+\s*ид\.?\s*ч\.?\s*$',  # Ends with fraction + ид.ч.
]

# Patterns that indicate it's NOT partial ownership (common area shares)
exclude_patterns = [
    r'идеални части от общите части',
    r'идеални части от правото на строеж',
    r'%\s*идеални части',
]

for text, expected in test_cases:
    text_lower = text.lower()
    
    # Check exclude patterns first
    is_excluded = any(re.search(p, text_lower) for p in exclude_patterns)
    
    # Check if matches partial ownership
    is_partial = not is_excluded and any(re.search(p, text_lower) for p in better_patterns)
    
    status = "✓" if is_partial == expected else "✗"
    print(f"{status} '{text[:60]}...' => partial={is_partial} (expected={expected})")
