"""
Automated live-test runner for fill_cart_* functions.
Patches _keep_browser_alive to a 3-second pause so the script exits cleanly.
Output is machine-readable for iterative CI use.

Usage: python run_live_test.py <place_id> [--headless]
"""
import asyncio
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Patch before any fill_cart function is called (Python late-binds module globals)
import autoorder

async def _short_wait(page):
    await page.wait_for_timeout(3000)

autoorder._keep_browser_alive = _short_wait

from autoorder import SUPPORTED_RESTAURANTS, consolidate_orders  # noqa: E402

TEST_ORDERS: dict = {
    "seed-starbird": {
        "Dean":   [{"item": "Classic Tender Box", "qty": 1, "notes": "buffalo sauce", "price": 12.95}],
        "Cooper": [{"item": "Nashville Hotbird",  "qty": 1, "notes": "no pickles",   "price": 13.95}],
        "Evan":   [{"item": "Classic Tender Box", "qty": 1, "notes": "",             "price": 12.95}],
        "Parth":  [{"item": "Fries",              "qty": 2, "notes": "",             "price":  4.25}],
    },
    "seed-ike-s-love-sandwiches": {
        # 5-item repro: structured choices from the Orders form.
        "Dean":   [{"item": "Menage a Trois", "qty": 1, "notes": "Dutch Crunch, Lettuce, Tomato, Add Avocado (+$2.50)", "price": 11.25}],
        "Parth":  [{"item": "Steve Young",    "qty": 1, "notes": "Sourdough, No Dirty Sauce",                          "price": 10.75}],
        "Cooper": [{"item": "Menage a Trois", "qty": 1, "notes": "French, Jalapenos",                                  "price": 11.25}],
        "Evan":   [{"item": "Matt Cain",      "qty": 1, "notes": "Whole Wheat, Lettuce",                               "price": 13.50}],
        "Aaron":  [{"item": "Hunter Pence",   "qty": 1, "notes": "Dutch Crunch",                                       "price": 13.50}],
    },
    "seed-sweetgreen": {
        "Dean":   [{"item": "Harvest Bowl",       "qty": 1, "notes": "",             "price": 13.95}],
        "Aaron":  [{"item": "Crispy Rice Bowl",   "qty": 1, "notes": "",             "price": 13.95}],
        "Cooper": [{"item": "Kale Caesar",        "qty": 1, "notes": "",             "price": 12.95}],
    },
    "seed-mendocino-farms": {
        "Dean":   [{"item": '"Not So Fried" Chicken', "qty": 1, "notes": "no onions", "price": 14.50}],
        "Parth":  [{"item": "The Farm Club",          "qty": 1, "notes": "",          "price": 14.95}],
        "Cooper": [{"item": "Heirloom BLT",           "qty": 2, "notes": "",          "price": 13.50}],
    },
    "seed-eureka-mountain-view": {
        "Dean":   [{"item": "Napa Chicken Sandwich",  "qty": 1, "notes": "no onions", "price": 21.50}],
        "Parth":  [{"item": "Truffle Cheese Fries",   "qty": 1, "notes": "",          "price": 13.75}],
        "Cooper": [{"item": "Nachos",                 "qty": 1, "notes": "",          "price": 13.25}],
    },
    "seed-chipotle-mexican-grill": {
        "Dean":   [{"item": "Chicken Burrito Bowl", "qty": 1,
                    "notes": "White Rice, Black Beans, Corn Salsa (Medium), Sour Cream, Cheese",
                    "price": 11.35}],
        "Parth":  [{"item": "Steak Burrito",        "qty": 1,
                    "notes": "Brown Rice, Pinto Beans, Tomato Salsa (Mild), Cheese, Lettuce",
                    "price": 12.45}],
        "Evan":   [{"item": "Chips & Guacamole",    "qty": 1, "notes": "", "price": 5.20}],
    },
}


async def run(place_id: str, headless: bool = False) -> None:
    filler = SUPPORTED_RESTAURANTS.get(place_id)
    if not filler:
        print(f"[SKIP] No filler for '{place_id}'")
        return

    orders = TEST_ORDERS.get(place_id)
    if not orders:
        print(f"[SKIP] No test orders for '{place_id}'")
        return

    items = consolidate_orders(orders)
    print(f"\n{'='*60}")
    print(f"TEST: {place_id}")
    print(f"Items ({len(items)}):")
    for it in items:
        print(f"  {it['qty']}x {it['item']!r}  notes={it['notes']!r}")
    print(f"{'='*60}")

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=80,
            # Always pass the stealth flag — some storefronts (e.g. Toast/Eureka)
            # won't hydrate their menu for a plain headless browser.
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 390, "height": 844},
        )
        page = await context.new_page()
        try:
            await filler(page, items)
        finally:
            await browser.close()
    print(f"\n[DONE] {place_id}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    headless = "--headless" in sys.argv
    asyncio.run(run(sys.argv[1], headless=headless))
