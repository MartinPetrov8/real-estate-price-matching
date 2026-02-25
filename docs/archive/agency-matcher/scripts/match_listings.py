#!/usr/bin/env python3
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "real_estate_matcher.db"


def ratio(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def score_pair(a, b):
    # a,b = (id,agency,district,type,area,price,floor)
    _, ag_a, d_a, t_a, area_a, price_a, floor_a = a
    _, ag_b, d_b, t_b, area_b, price_b, floor_b = b

    if ag_a == ag_b:
        return 0.0, ["same_agency"]

    score = 0.0
    reasons = []

    d_sim = ratio(d_a, d_b)
    if d_sim > 0.80:
        score += 0.30
        reasons.append(f"district:{d_sim:.2f}")

    t_sim = ratio(t_a, t_b)
    if t_sim > 0.85:
        score += 0.20
        reasons.append(f"type:{t_sim:.2f}")

    if area_a and area_b:
        area_delta = abs(area_a - area_b) / max(area_a, area_b)
        if area_delta <= 0.05:
            score += 0.25
            reasons.append(f"area_delta:{area_delta:.3f}")
        elif area_delta <= 0.10:
            score += 0.15
            reasons.append(f"area_delta:{area_delta:.3f}")

    if price_a and price_b:
        price_delta = abs(price_a - price_b) / max(price_a, price_b)
        if price_delta <= 0.04:
            score += 0.20
            reasons.append(f"price_delta:{price_delta:.3f}")
        elif price_delta <= 0.08:
            score += 0.10
            reasons.append(f"price_delta:{price_delta:.3f}")

    f_sim = ratio(floor_a, floor_b)
    if f_sim > 0.75:
        score += 0.05
        reasons.append(f"floor:{f_sim:.2f}")

    return min(score, 1.0), reasons


def main(min_conf=0.65):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, agency_subdomain, district, property_type, area_sqm, price_eur, floor_text
            FROM listings
            WHERE is_active=1
              AND listing_url LIKE '%-prodava-%'
              AND (district IS NOT NULL OR area_sqm IS NOT NULL OR price_eur IS NOT NULL)
            """
        ).fetchall()

        conn.execute("DELETE FROM match_candidates")

        inserted = 0
        for i in range(len(rows)):
            a = rows[i]
            for j in range(i + 1, len(rows)):
                b = rows[j]
                s, reasons = score_pair(a, b)
                if s >= min_conf:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO match_candidates(listing_id_a, listing_id_b, confidence, reasons)
                        VALUES (?, ?, ?, ?)
                        """,
                        (a[0], b[0], s, ", ".join(reasons)),
                    )
                    inserted += 1

        conn.commit()

    print(f"Matching completed. Candidates: {inserted}")


if __name__ == "__main__":
    main()
