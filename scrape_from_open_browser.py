"""
Scrape a restaurant menu from a browser tab YOU already opened.

Because you navigate the site in your real browser, bot-protection (Cloudflare/
Akamai) is passed as a human — this tool just attaches to that tab and reads the
already-loaded menu. No automation fingerprint, no evasion.

SETUP (one time per session):
  1. Quit Chrome completely (Cmd+Q).
  2. Relaunch with remote debugging:
       /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
         --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-cdp
  3. In that window, navigate to the restaurant's ordering menu, pick the store,
     scroll so all items render.

USAGE:
  python scrape_from_open_browser.py <place_id>            # PREVIEW (no write)
  python scrape_from_open_browser.py <place_id> --merge    # write into menus_data.json
  python scrape_from_open_browser.py <place_id> --url chipotle   # pick tab by URL substring
  python scrape_from_open_browser.py <place_id> --merge --by Dean  # attribute the verification
"""
import asyncio
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MENUS = os.path.join(HERE, "menus_data.json")
CDP = "http://localhost:9222"


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# Generic menu extractor: for each name-ish element, find the nearest price /
# description / image within its surrounding card. Works across most ordering
# platforms; refine per-site if a particular menu comes back sparse.
EXTRACT_JS = r"""
() => {
  function priceOf(text) {
    const m = (text || '').match(/\$?\s?(\d{1,3}(?:\.\d{2}))/);
    return m ? parseFloat(m[1]) : 0;
  }
  const NAME_SEL = 'h2,h3,h4,[class*="name" i],[class*="title" i],[class*="itemName" i],[class*="headerText" i],[data-testid*="name" i]';
  const out = [];
  const seen = new Set();
  for (const el of document.querySelectorAll(NAME_SEL)) {
    const name = (el.innerText || '').trim().split('\n')[0];
    if (!name || name.length < 2 || name.length > 60) continue;
    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    // walk up to a container that has a price and/or image
    let card = el, price = 0, img = '', desc = '', hops = 0;
    while (card && hops < 6) {
      if (!price) price = priceOf(card.innerText);
      if (!img) { const im = card.querySelector('img'); if (im) { const s = im.src || im.getAttribute('data-src') || ''; if (s.startsWith('http')) img = s; } }
      if (!img) { for (const ch of (card ? card.querySelectorAll('*') : [])) { const bg = getComputedStyle(ch).backgroundImage; if (bg && bg !== 'none' && bg.includes('url(')) { const s = bg.replace(/^url\(["']?/,'').replace(/["']?\)$/,''); if (s.startsWith('http')) { img = s; break; } } } }
      if (price || img) break;
      card = card.parentElement; hops++;
    }
    card = card || el;
    const d = card.querySelector('[class*="desc" i],[class*="description" i],[class*="ingredient" i],p');
    if (d) { const t = (d.innerText || '').trim(); if (t && t !== name) desc = t.slice(0, 160); }
    seen.add(key);
    out.push({ name, price, description: desc, image_url: img });
  }
  return out;
}
"""


# Card-aware extractor for SPA ordering platforms (thanx, some chains) where the
# generic heading-based extractor above misses items. Finds each price *leaf*
# (a node whose own text is just "$X.XX"), ascends to the enclosing item card,
# and reads the first non-price, non-allergen line as the name.
CARD_EXTRACT_JS = r"""
() => {
  // Leading price, optionally trailed by " · 550 cals" etc. Length-capped so a
  // description paragraph that happens to contain a price isn't treated as one.
  const priceRe = /^\$\s?(\d{1,3}(?:\.\d{2})?)\b/;
  const anyPrice = /\$\s?\d/;
  const items = []; const seen = new Set();
  for (const el of document.querySelectorAll('span,div,p,b,strong')) {
    let own=''; for (const nd of el.childNodes) if (nd.nodeType===3) own+=nd.textContent;
    own = own.trim();
    const pm = own.match(priceRe); if (!pm || own.length > 20) continue;
    const price = parseFloat(pm[1]);
    let card = el;
    for (let i=0;i<6 && card;i++){
      const lines = (card.innerText||'').split('\n').map(s=>s.trim()).filter(Boolean);
      const nameLine = lines.find(l => !anyPrice.test(l) && l.length>=2 && l.length<=60
          && !/^contains/i.test(l)
          && !/^(egg|milk|soy|wheat|fish|tree|peanut|sesame|shellfish|eggs|soybeans)/i.test(l)
          && !/^(skip to|enable access|open the access|main content)/i.test(l));
      if (nameLine){
        const key=nameLine.toLowerCase();
        if(!seen.has(key)){ seen.add(key);
          const desc=lines.find(l=>l!==nameLine && !anyPrice.test(l) && !/^contains/i.test(l) && l.length>15);
          items.push({name:nameLine, price, description:desc||'', image_url:''});
        }
        break;
      }
      card=card.parentElement;
    }
  }
  return items;
}
"""


async def main(place_id, do_merge, url_hint, verified_by="live scrape", extract_js=EXTRACT_JS):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP)
        except Exception as e:
            print(f"Could not connect to Chrome at {CDP}.\n"
                  f"Did you launch Chrome with --remote-debugging-port=9222 ?\n  {e}")
            return

        # gather all open tabs across contexts
        pages = [pg for ctx in browser.contexts for pg in ctx.pages]
        if not pages:
            print("No open tabs found in the debug browser.")
            return
        # Scan every tab AND every sub-frame (Chipotle's order menu lives in an
        # embedded frame). Score each by how many items have a PRICE — that's the
        # real ordering menu, not a marketing/nav page.
        def score(rows):
            return (sum(1 for r in rows if r["price"]), len(rows))

        target_url, best_rows, best_score = None, [], (0, 0)
        for pg in pages:
            if url_hint and url_hint.lower() not in (pg.url or "").lower():
                continue
            frames = pg.frames  # includes the main frame
            for fr in frames:
                try:
                    rows = await fr.evaluate(extract_js)
                except Exception:
                    rows = []
                sc = score(rows)
                if sc > best_score:
                    target_url, best_rows, best_score = (fr.url or pg.url), rows, sc

        if not best_rows:
            print("Open tabs:")
            for pg in pages:
                print("  ", (pg.url or "")[:90])
            print("\nNo menu-looking content found. Make sure you're on the ORDER menu "
                  "(store selected, prices visible) and scrolled, or pass --url <substring>.")
            return

        rows = best_rows
        print(f"\nSource: {(target_url or '')[:90]}")
        show = rows if "--all" in sys.argv else [r for r in rows if r["price"]][:60]
        print(f"Extracted {len(rows)} candidate items. Showing {len(show)}:")
        for r in show:
            pr = f"${r['price']}" if r["price"] else "(no price)"
            print(f"   {pr:>9}  {r['name'][:40]}" + (f"  — {r['description'][:28]}" if r['description'] else ""))

        if not do_merge:
            n_priced = sum(1 for r in rows if r["price"])
            print(f"\nPREVIEW only — {n_priced}/{len(rows)} have a price. "
                  f"Re-run with --merge to write into menus_data.json.")
            return

        # merge by fuzzy name into the stored menu
        data = json.load(open(MENUS))
        by_norm = {}
        for r in rows:
            k = _norm(r["name"])
            if k:
                by_norm[k] = r
        pr_n = de_n = im_n = matched = 0
        for rec in data:
            if rec["id"] != place_id:
                continue
            for cat in rec.get("categories", []):
                for it in cat.get("items", []):
                    sc = by_norm.get(_norm(it["name"]))
                    if not sc:
                        continue
                    matched += 1
                    if sc.get("price"):
                        it["price"] = sc["price"]; pr_n += 1
                    if sc.get("description"):
                        it["description"] = sc["description"]; de_n += 1
                    if sc.get("image_url") and not it.get("image_url"):
                        it["image_url"] = sc["image_url"]; im_n += 1
            rec["prices_verified"] = True  # confirmed against the live (human) session
            rec["prices_verified_at"] = datetime.date.today().isoformat()
            rec["prices_verified_by"] = verified_by
        # indent=2 + default ensure_ascii=True + no trailing newline keeps the
        # on-disk format byte-identical (minimal diff) — see menus.py.
        json.dump(data, open(MENUS, "w"), indent=2)
        print(f"\nMerged into {place_id}: matched {matched} items — "
              f"+{pr_n} prices, +{de_n} descriptions, +{im_n} images. "
              f"prices_verified=True, at={datetime.date.today().isoformat()} by={verified_by}.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    pid = sys.argv[1]
    merge = "--merge" in sys.argv
    hint = ""
    if "--url" in sys.argv:
        i = sys.argv.index("--url")
        if i + 1 < len(sys.argv):
            hint = sys.argv[i + 1]
    who = "live scrape"
    if "--by" in sys.argv:
        i = sys.argv.index("--by")
        if i + 1 < len(sys.argv):
            who = sys.argv[i + 1]
    extractor = CARD_EXTRACT_JS if "--cards" in sys.argv else EXTRACT_JS
    asyncio.run(main(pid, merge, hint, who, extractor))
