"""
Live test harness for fill_cart_* functions.
Opens a real browser with hardcoded test orders — no DB needed.

Usage:
    python test_autoorder.py <place_id>

Available place IDs:
    seed-mj-sushi
    seed-starbird
    seed-ike-s-love-sandwiches
    seed-five-guys
    seed-sweetgreen
    seed-chipotle-mexican-grill

Examples:
    python test_autoorder.py seed-starbird
    python test_autoorder.py seed-chipotle-mexican-grill
"""
import asyncio
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from playwright.async_api import async_playwright
from autoorder import SUPPORTED_RESTAURANTS, consolidate_orders

# ── Test orders per restaurant ─────────────────────────────────────────────────
# Use real menu item names. Notes for Chipotle must be comma-separated ingredients
# matching the chipotle_options in menus_data.json.

TEST_ORDERS: dict = {
    "seed-starbird": {
        "Dean":   [{"item": "3-Piece Tenders",  "qty": 1, "notes": "buffalo sauce",    "price": 12.95}],
        "Cooper": [{"item": "Chicken Sandwich",  "qty": 1, "notes": "no pickles",       "price": 13.95}],
        "Evan":   [{"item": "3-Piece Tenders",   "qty": 1, "notes": "",                 "price": 12.95}],
        "Parth":  [{"item": "Fries",             "qty": 2, "notes": "",                 "price":  4.25}],
    },
    "seed-ike-s-love-sandwiches": {
        "Dean":   [{"item": "Menage a Trois",    "qty": 1, "notes": "no onions",        "price": 11.25}],
        "Parth":  [{"item": "Pilgrim",           "qty": 1, "notes": "",                 "price": 10.75}],
        "Cooper": [{"item": "Menage a Trois",    "qty": 1, "notes": "",                 "price": 11.25}],
    },
    "seed-five-guys": {
        "Dean":   [{"item": "Little Hamburger",  "qty": 1, "notes": "lettuce, ketchup", "price":  6.19}],
        "Cooper": [{"item": "Cheeseburger",      "qty": 1, "notes": "",                 "price":  9.29}],
        "Evan":   [{"item": "Little Cheeseburger","qty": 1,"notes": "",                 "price":  7.19}],
        "Parth":  [{"item": "Fries (Regular)",   "qty": 1, "notes": "",                 "price":  4.69}],
    },
    "seed-sweetgreen": {
        "Dean":   [{"item": "Harvest Bowl",      "qty": 1, "notes": "",                 "price": 13.95}],
        "Aaron":  [{"item": "Crispy Rice Bowl",  "qty": 1, "notes": "",                 "price": 13.95}],
        "Cooper": [{"item": "Garden Cobb",       "qty": 1, "notes": "",                 "price": 12.95}],
    },
    "seed-chipotle-mexican-grill": {
        "Dean":   [{"item": "Chicken Burrito Bowl", "qty": 1,
                    "notes": "White Rice, Black Beans, Corn Salsa (Medium), Sour Cream, Cheese",
                    "price": 11.35}],
        "Parth":  [{"item": "Steak Burrito",        "qty": 1,
                    "notes": "Brown Rice, Pinto Beans, Tomato Salsa (Mild), Cheese, Lettuce",
                    "price": 12.45}],
        "Evan":   [{"item": "Chips & Guacamole",    "qty": 1, "notes": "", "price": 5.20}],
        "Cooper": [{"item": "Chicken Burrito Bowl", "qty": 1,
                    "notes": "Brown Rice, Black Beans, Green Tomatillo (Hot), Sour Cream, Guacamole (+$2)",
                    "price": 11.35}],
    },
    "seed-mj-sushi": {
        "Dean":   [{"item": "Edamame",           "qty": 1, "notes": "",                 "price":  4.99}],
        "Cooper": [{"item": "Dragon Roll",       "qty": 1, "notes": "no unagi sauce",   "price": 14.00}],
        "Evan":   [{"item": "Salmon Avocado Roll","qty": 1, "notes": "",                "price":  8.04}],
    },
}


async def run_test(place_id: str) -> None:
    filler = SUPPORTED_RESTAURANTS.get(place_id)
    if not filler:
        print(f"No filler registered for '{place_id}'.")
        print(f"Available: {list(SUPPORTED_RESTAURANTS)}")
        return

    orders_by_person = TEST_ORDERS.get(place_id)
    if not orders_by_person:
        print(f"No test orders defined for '{place_id}'.")
        return

    items = consolidate_orders(orders_by_person)
    print(f"\n🧪  LIVE TEST — {place_id}")
    print(f"    {len(items)} item(s) after consolidation:")
    for it in items:
        notes_str = f"  notes={it['notes']!r}" if it["notes"] else ""
        print(f"    • {it['qty']}× {it['item']}{notes_str}")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=120)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 390, "height": 844},
        )
        page = await context.new_page()
        await filler(page, items)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(run_test(sys.argv[1]))
