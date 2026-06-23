"""
Scrape MJ Sushi item images from their MenuSifu ordering page using a headless browser.
"""
import asyncio
import json
import os
import re
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
MENUS_PATH = os.path.join(HERE, "menus_data.json")


async def find_order_url(page) -> str | None:
    """Navigate to MJ Sushi homepage and find the real order link."""
    print("Finding order URL from MJ Sushi homepage...")
    await page.goto("https://www.mjsushipaloalto.com", timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    # Look for any link containing 'order', 'mealkeyway', 'menusifu', etc.
    links = await page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href]'))
            .map(a => a.href)
            .filter(h => h && (
                h.includes('order') || h.includes('mealkeyway') ||
                h.includes('menusifu') || h.includes('chownow') ||
                h.includes('toast') || h.includes('olo.com')
            ))
    """)
    print(f"  Found candidate links: {links}")
    return links[0] if links else None


async def scrape_menusifu(page, url: str) -> dict[str, str]:
    """Scrape a MenuSifu ordering page for item name → image URL pairs."""
    results: dict[str, str] = {}

    print(f"Loading ordering page: {url}")
    try:
        await page.goto(url, timeout=45000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"  Load error: {e}")
        return results

    # Wait for React to render the menu
    print("  Waiting for menu to render...")
    await page.wait_for_timeout(5000)

    # Scroll through the page to trigger lazy loading
    for _ in range(10):
        await page.evaluate("window.scrollBy(0, 400)")
        await page.wait_for_timeout(400)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(1000)

    # Save full HTML for inspection
    html = await page.content()
    with open(os.path.join(HERE, "mj_debug2.html"), "w") as f:
        f.write(html)
    print(f"  Page HTML saved ({len(html)} chars)")

    # Extract all img srcs from the page
    all_imgs = await page.evaluate("""
        () => Array.from(document.querySelectorAll('img'))
            .map(img => ({
                src: img.src || img.getAttribute('data-src') || img.getAttribute('data-lazy-src') || '',
                alt: img.alt || '',
                width: img.naturalWidth || img.width || 0,
                height: img.naturalHeight || img.height || 0,
            }))
            .filter(i => i.src && i.src.startsWith('http') && i.width > 50)
    """)
    print(f"  Found {len(all_imgs)} images in DOM")

    # Extract items: look for MenuSifu-specific class patterns
    items = await page.evaluate("""
        () => {
            const results = [];
            const seen = new Set();

            // MenuSifu uses class names like 'item-card', 'food-item', 'dish-item', etc.
            const containers = document.querySelectorAll(
                '[class*="item"], [class*="product"], [class*="dish"], [class*="food"], [class*="menu"]'
            );

            containers.forEach(el => {
                const img = el.querySelector('img');
                if (!img || !img.src || !img.src.startsWith('http')) return;

                // Try various name selectors
                const nameSelectors = [
                    '[class*="name"]', '[class*="title"]',
                    'h1', 'h2', 'h3', 'h4', 'p',
                ];
                let name = '';
                for (const sel of nameSelectors) {
                    const nameEl = el.querySelector(sel);
                    if (nameEl && nameEl.innerText?.trim().length > 1) {
                        name = nameEl.innerText.trim();
                        break;
                    }
                }

                if (name && !seen.has(name) && img.naturalWidth > 50) {
                    seen.add(name);
                    results.push({ name, image_url: img.src });
                }
            });
            return results;
        }
    """)

    print(f"  DOM extraction: {len(items)} name+image pairs found")
    for it in items[:5]:
        print(f"    {it['name'][:40]}: {it['image_url'][:60]}")

    for it in items:
        if it.get("name") and it.get("image_url"):
            results[it["name"]] = it["image_url"]

    # Also extract from raw HTML — MenuSifu often has JSON in script tags
    img_name_pairs = re.findall(
        r'"name"\s*:\s*"([^"]{3,60})".{0,300}?"image(?:Url|URL|url|_url)?"\s*:\s*"(https://[^"]+(?:jpg|jpeg|png|webp)[^"]*)"',
        html, re.DOTALL
    )
    for name, img_url in img_name_pairs:
        if name not in results:
            results[name] = img_url
            print(f"    JSON extract: {name[:40]}: {img_url[:60]}")

    if img_name_pairs:
        print(f"  JSON regex: {len(img_name_pairs)} additional pairs")

    return results


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 390, "height": 844},  # Mobile viewport — MenuSifu is mobile-first
        )
        page = await context.new_page()

        # Step 1: find the real order URL
        order_url = await find_order_url(page)
        if not order_url:
            print("No order link found on homepage. Trying known MenuSifu pattern...")
            # Try to find it in the page source
            html = await page.content()
            matches = re.findall(r'https://[^"\']*(?:mealkeyway|menusifu)[^"\']*', html)
            print(f"  Found in source: {matches}")
            order_url = matches[0] if matches else "https://order.mealkeyway.com/merchant/a3d34b67e1644b3ea4b9e18cf7ad88a1/main"

        print(f"Order URL: {order_url}")

        # Step 2: scrape the ordering page
        items = await scrape_menusifu(page, order_url)
        await browser.close()

    print(f"\nTotal items found: {len(items)}")

    if not items:
        print("No items scraped. Check mj_debug2.html for page content.")
        return

    # Patch menus_data.json
    with open(MENUS_PATH) as f:
        data = json.load(f)

    mj = next((r for r in data if r["id"] == "seed-mj-sushi"), None)
    if not mj:
        print("seed-mj-sushi not found")
        return

    added = 0
    for cat in mj["categories"]:
        for item in cat["items"]:
            if item.get("image_url"):
                continue
            item_lower = item["name"].lower().strip()
            for scraped_name, img_url in items.items():
                scraped_lower = scraped_name.lower().strip()
                if scraped_lower == item_lower or scraped_lower in item_lower or item_lower in scraped_lower:
                    item["image_url"] = img_url
                    print(f"  Matched: '{item['name']}' ← '{scraped_name}'")
                    added += 1
                    break

    print(f"\nPatched {added} new image_url fields")
    with open(MENUS_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print("Saved menus_data.json")


if __name__ == "__main__":
    asyncio.run(main())
