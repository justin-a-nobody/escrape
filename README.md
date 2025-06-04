set creds
export EBAY_APP_ID=YourAppIDHere
pip install requests
to run
python escraper.py  1956          # example year


The script:

Hits the eBay Finding API (100 items / page, up to 10 pages by default).

Heuristically parses each listing title for player, grade (PSA/BGS/SGC), and card #.

Saves each card’s hero image under images/<year>/…jpg.

Writes all metadata to cards_<year>.csv.

Tweak --pages or --delay as needed to stay under eBay’s call limits.
Need finer-grained control (sport, card brand, exact grading service)? Just adjust the keyword string near the top of scrape_year().

Ping me if you want bulk-year scraping, better title parsing, or translation to Selenium/Playwright instead of the official API.


escrape bulk1

Bulk-year support + smarter parsing shipped.

Usage examples

bash
Copy
# Single year
python ebay_card_scraper.py 1986

# Range
python ebay_card_scraper.py 1980-1985 --pages 5

# Comma list
python ebay_card_scraper.py 1993,1997,2001 --delay 0.5
Player names skip common brand words (Topps, Bowman, etc.).

Grade now captures “PSA 9.5”, “BGS 8”, “SGC 10”, etc.

Card number matches “#123”, “No. 45”, or “Card #7”.

Creates cards_<year>.csv and, when >1 year, a combined cards_all.csv.

tweaked


All-pages, no-image just url , maxed-out version



Copy
python scraper.py 1979-1982 --delay 0.5 --combined
Streams every page until eBay has nothing left (override with --max-pages N).

Saves per-year CSVs under ./output/ and, if --combined, a master cards_all.csv.

Columns: year | title | player | grade | card_no | item_url | gallery_url.

No images touched.

Handles network errors with automatic retries; CTRL-C exits cleanly.
