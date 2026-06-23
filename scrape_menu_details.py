"""
Enrich menus_data.json with item IMAGES and INGREDIENT DESCRIPTIONS scraped from
each restaurant's live ordering site. Card-level scrape (no per-item clicking).

Matches scraped items to existing menu items by normalized name and fills in
`image_url` and `description` without disturbing names/prices/categories.

Usage:
    python scrape_menu_details.py <place_id>        # one restaurant
    python scrape_menu_details.py --all             # all reachable restaurants

Reachable platforms only — bot-blocked sites (Mendocino, Panda, Pizza My Heart,
Five Guys) are skipped automatically.
"""
import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from playwright.async_api import async_playwright  # noqa: E402
import autoorder  # noqa: E402

MENUS_PATH = os.path.join(HERE, "menus_data.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _norm(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ── Per-restaurant scrape configs ───────────────────────────────────────────────
# Each returns a JS function that yields [{name, image_url, description}] from the
# fully-rendered, scrolled menu page.

async def _setup_ikes(page):
    try:
        sb = page.locator('button.submit-button').first
        if await sb.is_visible(timeout=3000):
            await sb.click()
            await page.wait_for_timeout(1500)
    except Exception:
        pass


async def _setup_menusifu(page):
    for sel in ['.GA_lp_startorder', '.GA_Ordertypepop_PickupOrder']:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=3000):
                await el.click()
                await page.wait_for_timeout(1500)
        except Exception:
            pass


async def _setup_starbird(page):
    for sel in ['#btn-cookie-banner-accept-2', '.cookie-banner__accept-btn',
                'button:has-text("Accept all")', 'button:has-text("Accept")']:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.click()
                await page.wait_for_timeout(1000)
                break
        except Exception:
            continue


SCRAPE_CONFIGS = {
    "seed-ike-s-love-sandwiches": {
        "url": autoorder.IKES_URL,
        "wait": 7000,
        "setup": _setup_ikes,
        "count_sel": ".item-card",
        "cat_sel": ".category-name",
        "js": """() => {
            const out=[];
            for (const c of document.querySelectorAll('.item-card')) {
                const name=(c.querySelector('.item-card-name')||{}).innerText||'';
                const img=c.querySelector('img');
                const desc=c.querySelector('.item-card-description, [class*="description"], [class*="desc"]');
                // Price is in .menuitem-price, rendered WITHOUT a $ (e.g. "15.95").
                const pEl=c.querySelector('.menuitem-price, [class*="price"]');
                let price=0;
                if (pEl) { const m=(pEl.innerText||'').match(/(\\d+(?:\\.\\d+)?)/); if (m) price=parseFloat(m[1]); }
                if (name.trim()) out.push({
                    name: name.trim(),
                    image_url: img ? (img.getAttribute('src')||img.getAttribute('data-src')||'') : '',
                    description: desc ? (desc.innerText||'').trim() : '',
                    price: price,
                });
            }
            return out;
        }""",
    },
    "seed-mj-sushi": {
        "url": autoorder.MJ_SUSHI_URL,
        "wait": 5000,
        "setup": _setup_menusifu,
        "count_sel": "[class*='itemName']",
        # MenuSifu shows all categories in one scroll (no collapsed sections).
        "js": """() => {
            const out=[];
            for (const el of document.querySelectorAll('[class*="itemName"]')) {
                const card = el.closest('[class*="itemInfo"]') || el.parentElement;
                const row = card ? card.parentElement : null;
                const desc = card ? card.querySelector('[class*="itemDescription"]') : null;
                let img='';
                const imgEl = (row && row.querySelector('img')) || (card && card.querySelector('img'));
                if (imgEl) { const s=imgEl.getAttribute('src')||imgEl.getAttribute('data-src')||'';
                             if (s.startsWith('http')) img=s; }
                const pe = card ? card.querySelector('[class*="itemPrice"], [class*="itemDisplayPrice"]') : null;
                let price=0;
                if (pe) { const m=(pe.innerText||'').match(/(\\d+(?:\\.\\d+)?)/); if (m) price=parseFloat(m[1]); }
                const name=(el.innerText||'').trim();
                if (name) out.push({name, image_url: img, price: price,
                                    description: desc ? (desc.innerText||'').trim() : ''});
            }
            return out;
        }""",
    },
    "seed-sweetgreen": {
        "url": autoorder.SWEETGREEN_URL,
        "wait": 6000,
        "setup": autoorder._dismiss_onetrust,  # consent overlay blocks the menu
        "count_sel": "a[href*='/palo-alto/']",
        "js": """() => {
            const out=[];
            for (const a of document.querySelectorAll('a[href*="/palo-alto/"]')) {
                const nameEl=a.querySelector('h3,h4,[class*="name"],[class*="title"]')||a;
                const name=(nameEl.innerText||'').trim().split('\\n')[0];
                if (!name || name.length>40) continue;
                let price=0; const m=(a.innerText||'').match(/\\$\\s?(\\d+\\.\\d{2})/); if (m) price=parseFloat(m[1]);
                out.push({name, image_url:'', description:'', price});
            }
            return out;
        }""",
    },
    # Toast menu — price lives in span.price inside .priceAvailability (sibling of .itemHeader, not inside it)
    "seed-oren-s-hummus-shop": {
        "url": autoorder.ORENS_URL,
        "wait": 8000,
        "wait_for": "span.headerText",
        "count_sel": ".itemInfo",
        "js": """() => {
            const out=[];
            for (const card of document.querySelectorAll('.itemInfo')) {
                const nameEl = card.querySelector('span.headerText');
                const priceEl = card.querySelector('span.price');
                const descEl = card.querySelector('.itemDescription');
                const imgEl = card.querySelector('img');
                const name = nameEl ? nameEl.innerText.trim() : '';
                if (!name) continue;
                const m = (priceEl ? priceEl.innerText : '').match(/\\$(\\d+\\.\\d{2})/);
                const price = m ? parseFloat(m[1]) : 0;
                let img='';
                if (imgEl) { const s=imgEl.getAttribute('src')||imgEl.getAttribute('data-src')||'';
                             if (s.startsWith('http')) img=s; }
                out.push({name, price, image_url: img,
                          description: descEl ? descEl.innerText.trim() : ''});
            }
            return out;
        }""",
    },
    # Toast menu — same DOM as Oren's
    "seed-roost-roast": {
        "url": autoorder.ROOST_ROAST_URL,
        "wait": 8000,
        "wait_for": "span.headerText",
        "count_sel": ".itemInfo",
        "js": """() => {
            const out=[];
            for (const card of document.querySelectorAll('.itemInfo')) {
                const nameEl = card.querySelector('span.headerText');
                const priceEl = card.querySelector('span.price');
                const descEl = card.querySelector('.itemDescription');
                const imgEl = card.querySelector('img');
                const name = nameEl ? nameEl.innerText.trim() : '';
                if (!name) continue;
                const m = (priceEl ? priceEl.innerText : '').match(/\\$(\\d+\\.\\d{2})/);
                const price = m ? parseFloat(m[1]) : 0;
                let img='';
                if (imgEl) { const s=imgEl.getAttribute('src')||imgEl.getAttribute('data-src')||'';
                             if (s.startsWith('http')) img=s; }
                out.push({name, price, image_url: img,
                          description: descEl ? descEl.innerText.trim() : ''});
            }
            return out;
        }""",
    },
    # SpotOn menu — Chakra UI
    "seed-asian-box": {
        "url": autoorder.ASIAN_BOX_URL,
        "wait": 8000,
        "wait_for": "[data-testid='menu-item-card-name']",
        "count_sel": "[data-testid='menu-item-card-name']",
        "js": """() => {
            const out=[];
            for (const card of document.querySelectorAll('[data-testid="menu-item-card"]')) {
                const nameEl = card.querySelector('[data-testid="menu-item-card-name"]');
                const name = nameEl ? nameEl.innerText.trim() : '';
                if (!name) continue;
                const imgEl = card.querySelector('img');
                let img='';
                if (imgEl) { const s=imgEl.getAttribute('src')||imgEl.getAttribute('data-src')||'';
                             if (s.startsWith('http')) img=s; }
                const priceEl = card.querySelector('[data-testid="menu-item-card-price"], [class*="price"]');
                let price=0;
                if (priceEl) { const m=(priceEl.innerText||'').match(/(\\d+(?:\\.\\d+)?)/); if (m) price=parseFloat(m[1]); }
                const descEl = card.querySelector('[data-testid="menu-item-card-description"], [class*="description"]');
                out.push({name, price, image_url: img,
                          description: descEl ? descEl.innerText.trim() : ''});
            }
            return out;
        }""",
    },
    # Square online ordering
    "seed-zareen-s": {
        "url": autoorder.ZAREEN_URL,
        "wait": 8000,
        "wait_for": "[aria-label^='Select ']",
        "count_sel": "[aria-label^='Select ']",
        "js": """() => {
            const out=[];
            for (const btn of document.querySelectorAll('[aria-label^="Select "]')) {
                const raw = (btn.getAttribute('aria-label')||'').replace(/^Select\\s+/,'').trim();
                const name = raw.replace(/\\s*\\$[\\d.]+.*$/, '').trim();
                if (!name) continue;
                const imgEl = btn.querySelector('img') || btn.closest('li,article,[class]')?.querySelector('img');
                let img='';
                if (imgEl) { const s=imgEl.getAttribute('src')||imgEl.getAttribute('data-src')||'';
                             if (s.startsWith('http')) img=s; }
                const priceEl = btn.querySelector('[class*="price"],[class*="Price"]');
                let price=0;
                if (priceEl) { const m=(priceEl.innerText||'').match(/(\\d+(?:\\.\\d+)?)/); if (m) price=parseFloat(m[1]); }
                const descEl = btn.querySelector('[class*="desc"],[class*="Desc"],[class*="caption"]');
                out.push({name, price, image_url: img,
                          description: descEl ? descEl.innerText.trim() : ''});
            }
            // dedupe by name
            const seen=new Set(), deduped=[];
            for (const r of out) { if (!seen.has(r.name)) { seen.add(r.name); deduped.push(r); } }
            return deduped;
        }""",
    },
    # DoorDash — almost certainly bot-blocked; included for completeness
    "seed-poke-house": {
        "url": autoorder.POKE_HOUSE_URL,
        "wait": 8000,
        "count_sel": "[data-anchor-id='MenuItem']",
        "js": """() => {
            const out=[];
            for (const card of document.querySelectorAll('[data-anchor-id="MenuItem"]')) {
                const nameEl = card.querySelector('span[data-anchor-id="MenuItemName"]') ||
                               card.querySelector('[class*="sc-"][class*="name"], h3, h4');
                const name = nameEl ? nameEl.innerText.trim() : '';
                if (!name) continue;
                const imgEl = card.querySelector('img');
                let img='';
                if (imgEl) { const s=imgEl.getAttribute('src')||imgEl.getAttribute('data-src')||'';
                             if (s.startsWith('http')) img=s; }
                const priceEl = card.querySelector('[data-anchor-id="MenuItemPrice"], [class*="price"]');
                let price=0;
                if (priceEl) { const m=(priceEl.innerText||'').match(/(\\d+(?:\\.\\d+)?)/); if (m) price=parseFloat(m[1]); }
                out.push({name, price, image_url: img, description:''});
            }
            return out;
        }""",
    },
    "seed-starbird": {
        "url": autoorder.STARBIRD_URL,
        "wait": 6000,
        "setup": _setup_starbird,
        "count_sel": ".c-button__title",
        "cat_sel": ".category-name",
        "js": """() => {
            const out=[];
            for (const el of document.querySelectorAll('.c-button__title, [class*="c-button__title"]')) {
                const card = el.closest('.c-button, [class*="c-button"], [class*="menuItem"], li, article') || el.parentElement;
                let img='';
                const imgEl = card ? card.querySelector('img') : null;
                if (imgEl) { const s=imgEl.getAttribute('src')||imgEl.getAttribute('data-src')||'';
                             if (s.startsWith('http')) img=s; }
                const desc = card ? card.querySelector('[class*="desc"], [class*="Desc"], [class*="caption"], p') : null;
                // Price ("$ 12.97") lives in an ancestor outside the card — walk up.
                let price=0, n=el;
                for (let i=0;i<6 && n;i++) { const m=(n.innerText||'').match(/\\$\\s?(\\d+\\.\\d{2})/);
                    if (m) { price=parseFloat(m[1]); break; } n=n.parentElement; }
                const name=(el.innerText||'').trim();
                if (name) out.push({name, image_url: img, price: price,
                                    description: desc ? (desc.innerText||'').trim() : ''});
            }
            return out;
        }""",
    },
}


async def scrape(place_id: str) -> list:
    cfg = SCRAPE_CONFIGS.get(place_id)
    if not cfg:
        print(f"[SKIP] no scrape config for {place_id} (bot-blocked or unsupported)")
        return []
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = await b.new_context(viewport={"width": 390, "height": 844}, user_agent=UA)
        page = await ctx.new_page()
        try:
            await page.goto(cfg["url"], timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(cfg["wait"])
            if cfg.get("wait_for"):  # SPA hydration: wait for real menu nodes
                try:
                    await page.wait_for_selector(cfg["wait_for"], timeout=25000)
                    await page.wait_for_timeout(1500)
                except Exception:
                    print("  (menu did not hydrate — site may be throttling)")
            if cfg.get("setup"):
                await cfg["setup"](page)
            # Paytronix/Toast menus VIRTUALIZE long lists — only ~40 cards live in
            # the DOM at once, so we must extract-and-accumulate as we step-scroll
            # down (dedupe by normalized name), not extract once at the end.
            count_sel = cfg.get("count_sel", ".item-card")
            acc = {}

            async def harvest():
                rows = await page.evaluate(cfg["js"])
                for r in rows:
                    k = _norm(r["name"])
                    if k and (k not in acc or (not acc[k].get("description") and r.get("description"))):
                        acc[k] = r

            # Menus with collapsed category sections (Paytronix) only render the
            # active category's cards. Click through each category header to load
            # them all; harvest after each. cat_sel="" disables this for flat menus.
            cat_sel = cfg.get("cat_sel")
            if cat_sel:
                n_cats = await page.evaluate("(s) => document.querySelectorAll(s).length", cat_sel)
                for i in range(n_cats):
                    try:
                        await page.evaluate(
                            """([s, i]) => { const els=document.querySelectorAll(s);
                                if (els[i]) els[i].scrollIntoView({block:'start'}); }""",
                            [cat_sel, i],
                        )
                        await page.wait_for_timeout(250)
                        await page.evaluate(
                            """([s, i]) => { const els=document.querySelectorAll(s);
                                if (els[i]) els[i].click(); }""",
                            [cat_sel, i],
                        )
                        await page.wait_for_timeout(700)
                        await harvest()
                    except Exception:
                        continue

            # Then step-scroll the whole page to catch anything lazy-rendered.
            stagnant = 0
            for _ in range(60):
                await harvest()
                before = len(acc)
                await page.evaluate(
                    """(sel) => { const c=document.querySelectorAll(sel);
                        if (c.length) c[c.length-1].scrollIntoView({block:'end'}); }""",
                    count_sel,
                )
                await page.wait_for_timeout(400)
                stagnant = stagnant + 1 if len(acc) == before else 0
                if stagnant >= 4:
                    break
            rows = list(acc.values())
        finally:
            await b.close()
    print(f"  scraped {len(rows)} items from {place_id}")
    return rows


def merge(place_id: str, rows: list) -> tuple:
    with open(MENUS_PATH) as f:
        data = json.load(f)
    by_norm = {}
    for r in rows:
        by_norm[_norm(r["name"])] = r
    img_n = desc_n = price_n = 0
    for rec in data:
        if rec["id"] != place_id:
            continue
        for cat in rec.get("categories", []):
            for it in cat.get("items", []):
                scraped = by_norm.get(_norm(it["name"]))
                if not scraped:
                    continue
                if scraped.get("image_url") and not it.get("image_url"):
                    it["image_url"] = scraped["image_url"]
                    img_n += 1
                if scraped.get("description"):
                    it["description"] = scraped["description"]
                    desc_n += 1
                if scraped.get("price"):
                    it["price"] = scraped["price"]
                    price_n += 1
    with open(MENUS_PATH, "w") as f:
        json.dump(data, f, indent=2)
    return img_n, desc_n, price_n


async def run(place_id: str):
    print(f"\n→ {place_id}")
    rows = await scrape(place_id)
    if rows:
        img_n, desc_n, price_n = merge(place_id, rows)
        print(f"  merged: +{img_n} images, {desc_n} descriptions, {price_n} prices updated")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "--all":
        for pid in SCRAPE_CONFIGS:
            asyncio.run(run(pid))
    else:
        asyncio.run(run(sys.argv[1]))
