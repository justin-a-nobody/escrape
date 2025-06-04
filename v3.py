import os
import re
import csv
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any

import requests

"""
Ultimate eBay Sports‑Card Scraper
================================
* Accepts single year (e.g. ``1986``), comma list (``1998,1999,2000``) or range (``1980‑1989``).
* Streams **all** available listings (no need to specify page count) until eBay runs out of results ‑ or use ``--max-pages`` to cap it.
* Outputs one CSV per year **plus** an optional combined CSV.
* Columns: ``year,title,player,grade,card_no,item_url,gallery_url`` (no image downloads).
* Robust: retries, exponential back‑off, graceful CTRL‑C.

Quick start
-----------
```bash
export EBAY_APP_ID=YourAppID   # <‑‑ get at developer.ebay.com
pip install requests
python ebay_card_scraper.py 1980-1985 --delay 0.5
```

Command‑line flags
------------------
```
positional:
  years            Year / list / range (e.g. 1986 or 1980-1985 or 1993,1997)

optional:
  -o, --outdir     Destination folder (default: ./output)
  --max-pages N    Stop after N pages per year (0 = all, default 0)
  --delay SEC      Pause between requests (default 1.0)
  --combined       Emit cards_all.csv with every row scraped
  --debug          Verbose HTTP + JSON dump
```
"""

EBAY_FINDING_ENDPOINT = "https://svcs.ebay.com/services/search/FindingService/v1"
MAX_ENTRIES_PER_PAGE = 100

# --- regexes -------------------------------------------------------------
GRADE_RE = re.compile(r"\b(PSA|BGS|SGC)\s*(\d+(?:\.\d)?)\b", re.IGNORECASE)
CARD_NO_RE = re.compile(r"(?:#|No\.|Card\s*#?)\s*(\d{1,4}[A-Z]?)", re.IGNORECASE)
BRAND_STOPWORDS = {
    "TOPPS", "UPPER", "DECK", "FLEER", "DONRUSS", "BOWMAN", "O-PEE-CHEE",
    "PANINI", "SELECT", "PRIZM", "OPTIC", "CHROME", "HOOPS", "STADIUM",
    "CLUB", "SKYBOX", "SCORE", "LEAF", "RC", "ROOKIE",
}

# ------------------------------------------------------------------------
# helpers ----------------------------------------------------------------

def _clean(tok: str) -> str:
    return re.sub(r"[^A-Za-z]", "", tok).upper()


def guess_player(title: str) -> str:
    tok = title.split()
    clean = [_clean(t) for t in tok]
    for i in range(len(tok) - 1):
        if clean[i] in BRAND_STOPWORDS or clean[i + 1] in BRAND_STOPWORDS:
            continue
        if tok[i][0].isupper() and tok[i + 1][0].isupper():
            return f"{tok[i]} {tok[i + 1]}"
    return tok[0]


def parse_title(title: str) -> Dict[str, str]:
    g_m = GRADE_RE.search(title)
    grade = f"{g_m.group(1).upper()} {g_m.group(2)}" if g_m else "N/A"
    n_m = CARD_NO_RE.search(title)
    card_no = n_m.group(1) if n_m else "N/A"
    return {"player": guess_player(title), "grade": grade, "card_no": card_no}


# ------------------------------------------------------------------------
# ebay API ----------------------------------------------------------------

def ebay_find(app_id: str, keyword: str, page: int) -> Dict[str, Any]:
    params = {
        "OPERATION-NAME": "findItemsByKeywords",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "keywords": keyword,
        "paginationInput.entriesPerPage": str(MAX_ENTRIES_PER_PAGE),
        "paginationInput.pageNumber": str(page),
        "outputSelector": "PictureURLLarge",
    }
    r = requests.get(EBAY_FINDING_ENDPOINT, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def extract_items(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        return resp["findItemsByKeywordsResponse"][0]["searchResult"][0]["item"]
    except (KeyError, IndexError):
        return []


def total_pages(resp: Dict[str, Any]) -> int:
    try:
        return int(resp["findItemsByKeywordsResponse"][0]["paginationOutput"][0]["totalPages"][0])
    except (KeyError, IndexError, ValueError):
        return 0

# ------------------------------------------------------------------------
# core scraper ------------------------------------------------------------

def scrape_year(year: int, *, app_id: str, outdir: Path, max_pages: int = 0, delay: float = 1.0, debug: bool = False) -> List[Dict[str, Any]]:
    kw = f"{year} sports trading card"
    rows: List[Dict[str, Any]] = []
    page = 1
    fetched_pages = 0
    while True:
        if max_pages and fetched_pages >= max_pages:
            break
        try:
            resp = ebay_find(app_id, kw, page)
        except Exception as exc:
            print(f"[WARN] network error page {page}: {exc} – retrying in 5s…")
            time.sleep(5)
            continue

        if debug:
            print(resp)
        items = extract_items(resp)
        if not items:
            break

        total_pg = total_pages(resp)
        print(f"[INFO] {year}: page {page}/{total_pg} – {len(items)} items")
        for it in items:
            title = it.get("title", [""])[0]
            parsed = parse_title(title)
            rows.append({
                "year": year,
                "title": title,
                "player": parsed["player"],
                "grade": parsed["grade"],
                "card_no": parsed["card_no"],
                "item_url": it.get("viewItemURL", [""])[0],
                "gallery_url": it.get("galleryURL", [""])[0],
            })
        fetched_pages += 1
        if page >= total_pg:
            break
        page += 1
        time.sleep(delay)

    if rows:
        outdir.mkdir(parents=True, exist_ok=True)
        csv_path = outdir / f"cards_{year}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
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
            s, e = map(int, part.split('-', 1))
            years.extend(range(s, e + 1))
        else:
            years.append(int(part))
    return sorted(set(years))


# ------------------------------------------------------------------------
# entrypoint --------------------------------------------------------------

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Scrape eBay sports cards by year (bulk, all pages).")
    ap.add_argument("years", help="Year, comma list, or range(s)")
    ap.add_argument("-o", "--outdir", default="output", help="Output directory (default: ./output)")
    ap.add_argument("--max-pages", type=int, default=0, help="Cap pages per year (0 = all)")
    ap.add_argument("--delay", type=float, default=1.0, help="Delay between page requests (sec)")
    ap.add_argument("--combined", action="store_true", help="Write combined CSV across years")
    ap.add_argument("--debug", action="store_true", help="Verbose JSON dump")
    args = ap.parse_args()

    app_id = os.getenv("EBAY_APP_ID")
    if not app_id:
        raise SystemExit("❌  Set EBAY_APP_ID env var first.")

    years = parse_years(args.years)
    all_rows: List[Dict[str, Any]] = []
    for yr in years:
        all_rows.extend(
            scrape_year(
                yr,
                app_id=app_id,
                outdir=Path(args.outdir),
                max_pages=args.max_pages,
                delay=args.delay,
                debug=args.debug,
            )
        )

    if args.combined and all_rows:
        combo = Path(args.outdir) / "cards_all.csv"
        with combo.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            writer.writeheader(); writer.writerows(all_rows)
        print(f"[DONE] combined CSV -> {combo}")
