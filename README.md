# reload-prices

A public feed of South African shop prices for reloading components and factory ammo, used by the Reload Tracker app's Prices and Savings tabs.

- Feed: https://spectretactical.github.io/reload-prices/prices.json
- What's in it: shop names, product names, product links, prices (ZAR), stock status and a daily price history. **Shop prices only. No personal data.**
- What to track: `products.json` (fixed product page links).
- How it updates: the GitHub Actions workflow `.github/workflows/check-prices.yml` runs `check_prices.py` at about 06:00 and 16:00 SAST (and on demand via "Run workflow") and commits `prices.json` back to the repo with the built-in `GITHUB_TOKEN`. No other keys or secrets are used.
- If a shop can't be reached, its last known price is kept and the error is recorded on that item. The file is never emptied.
- Requests are polite: one page per product, 2 seconds apart, twice a day.

Prices are as shown on each shop's website at the time checked and may be out of date. Check the shop before you buy.
