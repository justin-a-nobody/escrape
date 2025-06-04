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
