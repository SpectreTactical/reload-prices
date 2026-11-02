#!/usr/bin/env python3
"""Reload Tracker price feed: reads products.json, writes prices.json (public, no personal data).
Usage: python3 check_prices.py [products.json] [prices.json]
Each product: {"id","vendor","kind":"bullets|primers|powder|brass|factory","label","packSize","unit":"pieces|grams|rounds","caliber"?,
               "url": product page  OR  "search": term (+ optional "match": regex on product name)}
Adapters: WooCommerce Store API, Magento product/search pages, generic JSON-LD / og:price fallback.
"""
import os, json, re, sys, time, html, urllib.request, urllib.error, urllib.parse, datetime
UA = "Mozilla/5.0 (X11; Linux x86_64) ReloadTrackerPriceCheck/1.0 (+twice-daily; github.com/SpectreTactical/reload-prices)"
VENDORS = {  # host -> platform
  "shootingstuff.co.za": "magento", "safarioutdoor.co.za": "magento",
  "chsguns.co.za": "woo", "www.rhinoarms.co.za": "woo", "rhinoarms.co.za": "woo",
  "zimbi.co.za": "woo", "www.zimbi.co.za": "woo",
}
def get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json"})
    for attempt in range(3):  # retry transient errors (shops sometimes answer 400/429/5xx under load)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r: return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if attempt == 2 or e.code == 404: raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2: raise
        time.sleep(6 * (attempt + 1))
def host(u): return urllib.parse.urlparse(u).netloc.lower()
def base(u): p = urllib.parse.urlparse(u); return p.scheme + "://" + p.netloc

def woo(p):
    b = base(p.get("url") or p["vendorUrl"])
    if p.get("url"):
        slug = urllib.parse.urlparse(p["url"]).path.strip("/").split("/")[-1]
        q = "slug=" + urllib.parse.quote(slug)
    else: q = "search=" + urllib.parse.quote(p["search"]) + "&per_page=20"
    items = json.loads(get(b + "/wp-json/wc/store/v1/products?" + q))
    items = pick(items, p, lambda x: html.unescape(x["name"]))
    if not items: raise LookupError("no matching product")
    x = items[0]; pr = x["prices"]; m = int(pr.get("currency_minor_unit", 2))
    return {"name": html.unescape(x["name"]), "url": x["permalink"], "price": int(pr["price"]) / 10 ** m,
            "inStock": bool(x.get("is_in_stock")), "currency": pr.get("currency_code", "ZAR")}

def page_price(h):
    for rx in [r'product:price:amount"\s+content="([0-9.]+)"', r'itemprop="price"\s+content="([0-9.]+)"', r'data-price-amount="([0-9.]+)"', r'"price"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)']:
        m = re.search(rx, h)
        if m: return float(m.group(1))
    return None
def page_stock(h):
    if re.search(r'InStock|>\s*In stock\s*<', h, re.I): return True
    if re.search(r'OutOfStock|>\s*Out of stock\s*<', h, re.I): return False
    return None
def magento(p):
    url = p.get("url")
    if not url:
        h = get(base(p["vendorUrl"]) + "/catalogsearch/result/?q=" + urllib.parse.quote_plus(p["search"]))
        links = [(m.group(1), html.unescape(m.group(2)).strip()) for m in re.finditer(r'class="product-item-link"\s+href="([^"]+)"[^>]*>\s*(.*?)\s*</a>', h, re.S)]
        links = pick(links, p, lambda x: x[1])
        if not links: raise LookupError("no matching product")
        url = links[0][0]
    return generic(dict(p, url=url))
def generic(p):
    h = get(p["url"]); pr = page_price(h)
    if pr is None: raise LookupError("no price on page (blocked or rendered by JavaScript)")
    t = re.search(r'<title>\s*(.*?)\s*</title>', h, re.S)
    return {"name": html.unescape(t.group(1)).strip()[:120] if t else p.get("label", ""), "url": p["url"], "price": pr, "inStock": page_stock(h), "currency": "ZAR"}
def pick(items, p, name):
    if p.get("match"): items = [x for x in items if re.search(p["match"], name(x), re.I)]
    return items

def check(p):
    h = host(p.get("url") or p.get("vendorUrl", ""))
    plat = p.get("platform") or VENDORS.get(h, "generic")
    return {"woo": woo, "magento": magento}.get(plat, generic)(p)

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "products.json"; out = sys.argv[2] if len(sys.argv) > 2 else "prices.json"
    prods = json.load(open(src))["products"]  # a broken products.json stops here, before prices.json is touched
    try: old = {x["id"]: x for x in json.load(open(out))["items"]}
    except Exception: old = {}
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"); day = now[:10]
    items = []
    for p in prods:
        prev = old.get(p["id"], {}); hist = prev.get("history", [])
        it = {k: p.get(k) for k in ("id", "vendor", "kind", "brand", "label", "packSize", "unit", "caliber")}
        if p.get("default"): it["default"] = True
        if p.get("benchmark"): it["benchmark"] = True
        try:
            r = check(p)
            if not isinstance(r.get("price"), (int, float)) or r["price"] <= 0: raise ValueError("no price found on the page")
            it.update(r); it["checked"] = now; it["error"] = None
            pt = {"d": day, "p": r["price"], "s": r["inStock"]}
            if hist and hist[-1]["d"] == day: hist[-1] = pt
            else: hist.append(pt)
        except Exception as e:
            it.update({k: prev.get(k) for k in ("name", "url", "price", "inStock", "currency", "checked")})
            it["url"] = it.get("url") or p.get("url"); it["error"] = str(e)[:160]
        nm = it.get("name") or ""; it["name"] = nm.split(" | ")[0]
        m = re.search(r"[\[(]\s*([0-9][0-9 ]*)\s*[\])]\s*$", it["name"])
        it["detectedPack"] = int(m.group(1).replace(" ", "")) if m else None
        lb = re.search(r"([0-9.]+)\s*(lb|kg|g)\b", it["name"], re.I)
        if lb and it.get("kind") == "powder":
            n = float(lb.group(1)); u = lb.group(2).lower(); it["detectedPack"] = round(n * (453.59237 if u == "lb" else 1000 if u == "kg" else 1))
        it["history"] = hist[-400:]; items.append(it)
        time.sleep(2)  # be polite
    if not items: sys.exit("no products, leaving " + out + " untouched")
    tmp = out + ".tmp"
    with open(tmp, "w") as fh: json.dump({"schema": 1, "generated": now, "currency": "ZAR", "items": items}, fh, indent=1)
    os.replace(tmp, out)  # atomic: a crash never leaves a half-written or empty feed
    print(json.dumps([{k: i.get(k) for k in ("id", "price", "inStock", "error")} for i in items], indent=0))
if __name__ == "__main__": main()
