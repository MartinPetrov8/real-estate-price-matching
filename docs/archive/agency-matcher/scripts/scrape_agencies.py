#!/usr/bin/env python3
import argparse
import random
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "real_estate_matcher.db"
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:132.0) Gecko/20100101 Firefox/132.0",
]


def gaussian_delay(mean=1.8, std=0.6, min_val=0.5):
    return max(random.gauss(mean, std), min_val)


def decode_bg(content: bytes) -> str:
    for enc in ("cp1251", "windows-1251", "utf-8"):
        try:
            return content.decode(enc)
        except Exception:
            pass
    return content.decode("latin1", errors="ignore")


def clean_num(v: str) -> float | None:
    if not v:
        return None
    x = v.replace("\xa0", " ").replace(" ", "").replace(",", ".")
    x = re.sub(r"[^\d.]", "", x)
    if not x:
        return None
    try:
        return float(x)
    except ValueError:
        return None


def extract_listing_urls(page_html: str, subdomain: str) -> list[tuple[str, int]]:
    pattern = rf"https://{re.escape(subdomain)}\.imot\.bg/obiava-[^\"\s<]+"
    out = []
    seen = set()
    for m in re.finditer(pattern, page_html):
        u = m.group(0)
        if u in seen:
            continue
        if "-prodava-" in u and ("-grad-sofiya" in u or "-oblast-sofiya" in u):
            out.append((u, m.start()))
            seen.add(u)
    return out


@dataclass
class ParsedListing:
    listing_url: str
    listing_code: str | None
    title: str | None
    district: str | None
    property_type: str | None
    area_sqm: float | None
    floor_text: str | None
    construction_year: int | None
    price_eur: float | None
    price_bgn: float | None
    raw_text: str
    hash_signature: str | None


def parse_detail(url: str, html: str) -> ParsedListing:
    # Fallback parser when/if we fetch detail page.
    title = None
    mt = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    if mt:
        title = re.sub(r"<.*?>", "", mt.group(1)).strip()

    text = re.sub(r"<script.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    slug = url.split("/obiava-")[-1]
    listing_code = slug.split("-")[0] if slug else None

    district = None
    m_d = re.search(r"-grad-sofiya-([a-z0-9-]+)$", slug)
    if not m_d:
        m_d = re.search(r"-oblast-sofiya-([a-z0-9-]+)$", slug)
    if m_d:
        district = m_d.group(1)

    property_type = None
    m_t = re.search(r"-prodava-([a-z0-9-]+?)-grad-sofiya", slug)
    if not m_t:
        m_t = re.search(r"-prodava-([a-z0-9-]+?)-oblast-sofiya", slug)
    if m_t:
        property_type = m_t.group(1)

    eur = None
    bgn = None
    m_e = re.search(r"(\d[\d\s\.,]*)\s*€", text)
    if m_e:
        eur = clean_num(m_e.group(1))
    m_b = re.search(r"(\d[\d\s\.,]*)\s*лв", text)
    if m_b:
        bgn = clean_num(m_b.group(1))

    area = None
    m_a = re.search(r"(\d+[\.,]?\d*)\s*кв\.?м", text, re.I)
    if m_a:
        area = clean_num(m_a.group(1))

    floor_text = None
    m_f = re.search(r"(\d+\s*-?\s*ти\s*ет\.?[^,\.]*)", text, re.I)
    if m_f:
        floor_text = m_f.group(1).strip()

    year = None
    m_y = re.search(r"(19\d{2}|20\d{2})\s*г", text)
    if m_y:
        year = int(m_y.group(1))

    sig_parts = [
        (district or "na").strip(),
        (property_type or "na").strip(),
        str(int(round(area or 0))),
        str(int(round(eur or 0))),
    ]
    hash_signature = "|".join(sig_parts)

    return ParsedListing(
        listing_url=url,
        listing_code=listing_code,
        title=title,
        district=district,
        property_type=property_type,
        area_sqm=area,
        floor_text=floor_text,
        construction_year=year,
        price_eur=eur,
        price_bgn=bgn,
        raw_text=text[:5000],
        hash_signature=hash_signature,
    )


def parse_from_page_context(url: str, page_html: str, pos: int) -> ParsedListing:
    window = page_html[max(0, pos - 220): pos + 1400]
    window_txt = re.sub(r"<[^>]+>", " ", window)
    window_txt = re.sub(r"\s+", " ", window_txt).strip()

    base = parse_detail(url, window)

    m_e = re.search(r"(\d[\d\s\.,]*)\s*€", window_txt)
    m_b = re.search(r"(\d[\d\s\.,]*)\s*лв", window_txt)
    m_a = re.search(r"(\d+[\.,]?\d*)\s*кв\.?м", window_txt, re.I)
    m_f = re.search(r"(\d+\s*-?\s*ти\s*ет\.?[^,\.]*)", window_txt, re.I)
    m_y = re.search(r"(19\d{2}|20\d{2})\s*г", window_txt)

    eur = clean_num(m_e.group(1)) if m_e else base.price_eur
    bgn = clean_num(m_b.group(1)) if m_b else base.price_bgn
    area = clean_num(m_a.group(1)) if m_a else base.area_sqm

    # Sanity correction for parser bleed from nearby text blocks.
    if eur and eur > 2_000_000 and bgn:
        eur = round(bgn / 1.95583, 2)
    floor = m_f.group(1).strip() if m_f else base.floor_text
    year = int(m_y.group(1)) if m_y else base.construction_year

    sig_parts = [
        (base.district or "na").strip(),
        (base.property_type or "na").strip(),
        str(int(round(area or 0))),
        str(int(round(eur or 0))),
    ]

    return ParsedListing(
        listing_url=url,
        listing_code=base.listing_code,
        title=f"{base.property_type or 'listing'} {base.district or ''}".strip(),
        district=base.district,
        property_type=base.property_type,
        area_sqm=area,
        floor_text=floor,
        construction_year=year,
        price_eur=eur,
        price_bgn=bgn,
        raw_text=window_txt[:2000],
        hash_signature="|".join(sig_parts),
    )


def get(session: requests.Session, url: str, timeout=30, retries=3) -> str | None:
    for i in range(retries):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return decode_bg(resp.content)
            if resp.status_code in (403, 429):
                time.sleep((2 ** i) + random.uniform(0.2, 1.0))
                continue
        except requests.RequestException:
            time.sleep((2 ** i) + random.uniform(0.2, 1.0))
    return None


def upsert_listing(conn: sqlite3.Connection, agency_sub: str, p: ParsedListing) -> bool:
    cur = conn.execute(
        """
        INSERT INTO listings(
          source, agency_subdomain, listing_code, listing_url, title, district, property_type,
          area_sqm, floor_text, construction_year, price_eur, price_bgn, raw_text, hash_signature
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, listing_url) DO UPDATE SET
          title=excluded.title,
          district=excluded.district,
          property_type=excluded.property_type,
          area_sqm=excluded.area_sqm,
          floor_text=excluded.floor_text,
          construction_year=excluded.construction_year,
          price_eur=excluded.price_eur,
          price_bgn=excluded.price_bgn,
          raw_text=excluded.raw_text,
          hash_signature=excluded.hash_signature,
          last_seen_at=CURRENT_TIMESTAMP,
          is_active=1
        """,
        (
            "imot.bg",
            agency_sub,
            p.listing_code,
            p.listing_url,
            p.title,
            p.district,
            p.property_type,
            p.area_sqm,
            p.floor_text,
            p.construction_year,
            p.price_eur,
            p.price_bgn,
            p.raw_text,
            p.hash_signature,
        ),
    )
    return cur.rowcount > 0


def scrape_agency(session: requests.Session, conn: sqlite3.Connection, subdomain: str, max_pages: int, run_id: int):
    pages_scraped = 0
    listings_seen = 0
    listings_saved = 0
    errors = 0

    for page in range(1, max_pages + 1):
        page_url = f"https://{subdomain}.imot.bg/obiavi" if page == 1 else f"https://{subdomain}.imot.bg/obiavi/p-{page}"
        html = get(session, page_url)
        if not html:
            errors += 1
            continue

        pages_scraped += 1
        listing_urls = extract_listing_urls(html, subdomain)
        if not listing_urls:
            if page > 2:
                break
            continue

        for url, pos in listing_urls:
            listings_seen += 1
            try:
                parsed = parse_from_page_context(url, html, pos)
                if upsert_listing(conn, subdomain, parsed):
                    listings_saved += 1
            except Exception:
                errors += 1
            time.sleep(gaussian_delay())

        if page % 8 == 0:
            time.sleep(random.uniform(8, 20))

    conn.execute(
        """
        UPDATE scrape_runs
        SET pages_scraped = pages_scraped + ?,
            listings_seen = listings_seen + ?,
            listings_saved = listings_saved + ?,
            error_count = error_count + ?
        WHERE id = ?
        """,
        (pages_scraped, listings_seen, listings_saved, errors, run_id),
    )
    conn.commit()


def iter_agencies(conn: sqlite3.Connection, selected: str | None) -> Iterable[str]:
    if selected:
        yield selected
        return
    rows = conn.execute("SELECT subdomain FROM agencies WHERE active=1 ORDER BY id").fetchall()
    for (sub,) in rows:
        yield sub


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agency", help="Single agency subdomain")
    parser.add_argument("--max-pages", type=int, default=8)
    args = parser.parse_args()

    with sqlite3.connect(DB_PATH) as conn:
        run_id = conn.execute(
            "INSERT INTO scrape_runs(source, status, notes) VALUES(?, ?, ?)",
            ("imot.bg", "running", f"max_pages={args.max_pages}, agency={args.agency or 'all'}"),
        ).lastrowid
        conn.commit()

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": random.choice(UA_POOL),
                "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.8",
            }
        )

        try:
            for subdomain in iter_agencies(conn, args.agency):
                scrape_agency(session, conn, subdomain, args.max_pages, run_id)
                time.sleep(gaussian_delay(mean=3.0, std=1.2))
            conn.execute(
                "UPDATE scrape_runs SET status='ok', finished_at=CURRENT_TIMESTAMP WHERE id=?", (run_id,)
            )
        except Exception as e:
            conn.execute(
                "UPDATE scrape_runs SET status='failed', finished_at=CURRENT_TIMESTAMP, notes=COALESCE(notes,'') || ? WHERE id=?",
                (f" | error={e}", run_id),
            )
            raise
        finally:
            conn.commit()

    print(f"Scrape completed. Run id: {run_id}")


if __name__ == "__main__":
    main()
