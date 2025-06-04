import os
import re
import csv
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any

import requests

"""
Bulk-year eBay sports-card scraper
=================================
*   Accepts single year (e.g. 1986), comma-separated list ("1989,1990,1991"), or range ("1980-1985").
*   Grabs up to N pages (100 items/page) via eBay *Finding* API.
*   Heuristic parsing extracts **player**, **grading slab** (PSA/BGS/SGC + grade), and **card #**.
*   Downloads hero images under `images/<year>/` and stores CSV per year (and a combined CSV if more than one year).

❗  Requires env var `EBAY_APP_ID` (get one free at developer.ebay.com).

```bash
pip install requests
python ebay_card_scraper.py 1986-1990 --pages 5 --delay 0.5
```
"""

EBAY_FINDING_ENDPOINT = "https://svcs.ebay.com/services/search/FindingService/v1"

# --- regexes -------------------------------------------------------------
GRADE_RE = re.compile(r"\b(PSA|BGS|SGC)\s*(\d+(?:\.\d)?)\b", re.IGNORECASE)
CARD_NO_RE = re.compile(r"(?:#|No\.|Card\s*#?)\s*(\d{1,4}[A-Z]?)", re.IGNORECASE)
# Common card-brand keywords to ignore when guessing player name
BRAND_STOPWORDS = {
    "TOPPS", "UPPER", "DECK", "FLEER", "DONRUSS", "BOWMAN", "O-PEE-CHEE",
    "PANINI", "SELECT", "PRIZM", "OPTIC", "CHROME", "HOOPS", "STADIUM",
    "CLUB", "SKYBOX", "SCORE", "LEAF", "KOBE", "RC", "ROOKIE",
}

# ------------------------------------------------------------------------

def ebay_find_items(app_id: str, keyword: str, entries_per_page: int = 100, page_num: int = 1) -> List[Dict[str, Any]]:
    params = {
        "OPERATION-NAME": "findItemsByKeywords",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "keywords": keyword,
        "paginationInput.entriesPerPage": str(entries_per_page),
        "paginationInput.pageNumber": str(page_num),
        "outputSelector": "PictureURLLarge",
    }
    resp = requests.get(EBAY_FINDING_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["findItemsByKeywordsResponse"][0]["searchResult"][0]["item"]
    except (KeyError, IndexError):
        return []


# ------------------------------------------------------------------------
# heuristics --------------------------------------------------------------

def clean_token(tok: str) -> str:
    return re.sub(r"[^A-Za-z]", "", tok).upper()


def guess_player(title: str) -> str:
    """Return the first two consecutive capitalized words not in BRAND_STOPWORDS."""
    tokens = title.split()
    cleaned = [clean_token(t) for t in tokens]
    for i in range(len(tokens) - 1):
        if cleaned[i] in BRAND_STOPWORDS or cleaned[i + 1] in BRAND_STOPWORDS:
            continue
        if tokens[i][0].isupper() and tokens[i + 1][0].isupper():
            return f"{tokens[i]} {tokens[i + 1]}"
    # fallback to first token
    return tokens[0]


def parse_title(title: str) -> Dict[str, str]:
    grade_m = GRADE_RE.search(title)
    grade = f"{grade_m.group(1).upper()} {grade_m.group(2)}" if grade_m else "N/A"
    card_no_m = CARD_NO_RE.search(title)
    card_no = card_no_m.group(1) if card_no_m else "N/A"
    player = guess_player(title)
    return {"player": player, "grade": grade, "card_no": card_no}

# ------------------------------------------------------------------------


def download_image(url: str, dest_path: Path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(r.content)
    except Exception as e:
        print(f"[WARN] img {url[:50]}… -> {e}")


# ------------------------------------------------------------------------
# main worker -------------------------------------------------------------

def scrape_year(year: int, app_id: str, max_pages: int = 10, delay: float = 1.0) -> List[Dict[str, Any]]:
    keyword = f"{year} sports trading card"
    rows: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        items = ebay_find_items(app_id, keyword, page_num=page)
        if not items:
            break
        print(f"[INFO] {year}: page {page} ({len(items)} items)")
        for it in items:
            title = it.get("title", [""])[0]
            gallery = it.get("galleryURL", [""])[0]
            item_id = it.get("itemId", [""])[0]
            parsed = parse_title(title)

            img_name = f"{parsed['player'].replace(' ', '_')}_{parsed['card_no']}_{parsed['grade']}_{item_id}.jpg"
            img_path = Path("images") / str(year) / img_name
            if gallery:
                download_image(gallery, img_path)

            rows.append({
                "year": year,
                "title": title,
                "player": parsed["player"],
                "grade": parsed["grade"],
                "card_no": parsed["card_no"],
                "image_file": str(img_path),
                "item_url": it.get("viewItemURL", [""])[0],
            })
        time.sleep(delay)
    # write per-year CSV
    if rows:
        csv_path = Path(f"cards_{year}.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader(); writer.writerows(rows)
        print(f"[DONE] {year}: {len(rows)} rows -> {csv_path}")
    return rows

# ------------------------------------------------------------------------
# utilities ---------------------------------------------------------------

def parse_years(arg: str) -> List[int]:
    years: List[int] = []
    for part in arg.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start, end = map(int, part.split('-', 1))
            years.extend(range(start, end + 1))
        else:
            years.append(int(part))
    return sorted(set(years))


# ------------------------------------------------------------------------
# entrypoint --------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Scrape eBay sports cards by year (bulk supported).")
    ap.add_argument("years", help="Year, comma list, or range (e.g. 1986 or 1980-1985 or 1989,1990)")
    ap.add_argument("--pages", type=int, default=10, help="Max pages (100 items each) per year")
    ap.add_argument("--delay", type=float, default=1.0, help="Delay between page requests (sec)")
    args = ap.parse_args()

    app_id = os.getenv("EBAY_APP_ID")
    if not app_id:
        raise SystemExit("❌  Set EBAY_APP_ID env var first.")

    years = parse_years(args.years)
    all_rows: List[Dict[str, Any]] = []
    for yr in years:
        all_rows.extend(scrape_year(yr, app_id, max_pages=args.pages, delay=args.delay))

    if len(years) > 1 and all_rows:
        combined_csv = Path("cards_all.csv")
        with open(combined_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            writer.writeheader(); writer.writerows(all_rows)
        print(f"[DONE] Combined CSV -> {combined_csv}")
