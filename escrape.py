import os
import re
import csv
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any

import requests

EBAY_FINDING_ENDPOINT = "https://svcs.ebay.com/services/search/FindingService/v1"

# Regex patterns for extracting data from listing titles
GRADE_RE = re.compile(r"\b(?:PSA|BGS|SGC)\s*(?:\d+(?:\.\d)?)\b", re.IGNORECASE)
CARD_NO_RE = re.compile(r"#?\s*(\d{1,4}[A-Z]?)\b")


def ebay_find_items(app_id: str, keyword: str, entries_per_page: int = 100, page_num: int = 1) -> List[Dict[str, Any]]:
    """Call eBay Finding API and return a list of items."""
    params = {
        "OPERATION-NAME": "findItemsByKeywords",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "keywords": keyword,
        "paginationInput.entriesPerPage": str(entries_per_page),
        "paginationInput.pageNumber": str(page_num),
        "outputSelector": "PictureURLLarge"
    }
    resp = requests.get(EBAY_FINDING_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    try:
        items = data["findItemsByKeywordsResponse"][0]["searchResult"][0]["item"]
    except (KeyError, IndexError):
        return []
    return items


def parse_title(title: str) -> Dict[str, str]:
    """Heuristically parse the listing title for player, grade, and card number."""
    parts = title.split(" ")
    # Assume player name is first two tokens
    player = " ".join(parts[:2]) if len(parts) >= 2 else parts[0]

    grade_match = GRADE_RE.search(title)
    grade = grade_match.group(0).upper() if grade_match else "N/A"

    card_no_match = CARD_NO_RE.search(title)
    card_no = card_no_match.group(1) if card_no_match else "N/A"

    return {"player": player, "grade": grade, "card_no": card_no}


def download_image(url: str, dest_path: Path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(r.content)
    except Exception as e:
        print(f"[WARN] Could not download image {url}: {e}")


def scrape_year(year: int, app_id: str, max_pages: int = 10, delay: float = 1.0):
    keyword = f"{year} sports trading card"
    all_rows = []

    for page in range(1, max_pages + 1):
        items = ebay_find_items(app_id, keyword, page_num=page)
        if not items:
            break
        print(f"[INFO] Page {page}: {len(items)} items")
        for item in items:
            title = item.get("title", [""])[0]
            gallery = item.get("galleryURL", [""])[0]
            item_id = item.get("itemId", [""])[0]
            parsed = parse_title(title)

            filename = f"{parsed['player'].replace(' ', '_')}_{parsed['card_no']}_{parsed['grade']}_{item_id}.jpg"
            image_path = Path("images") / str(year) / filename
            if gallery:
                download_image(gallery, image_path)

            row = {
                "year": year,
                "title": title,
                "player": parsed["player"],
                "grade": parsed["grade"],
                "card_no": parsed["card_no"],
                "image_file": str(image_path),
                "item_url": item.get("viewItemURL", [""])[0]
            }
            all_rows.append(row)
        time.sleep(delay)

    # Save CSV
    csv_path = Path(f"cards_{year}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"[DONE] Saved {len(all_rows)} records to {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape sports trading cards from eBay by year.")
    parser.add_argument("year", type=int, help="Target card year, e.g., 1986")
    parser.add_argument("--pages", type=int, default=10, help="Max pages to fetch (100 items each)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between pages to avoid rate limits (sec)")
    args = parser.parse_args()

    app_id = os.getenv("EBAY_APP_ID")
    if not app_id:
        raise EnvironmentError("Set EBAY_APP_ID environment variable with your eBay developer App ID.")

    scrape_year(args.year, app_id, max_pages=args.pages, delay=args.delay)
