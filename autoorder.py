"""
Auto-order: opens a visible browser and fills the restaurant's cart with today's team orders.
Run as a subprocess from Streamlit (asyncio.run() can't run inside Streamlit's event loop).

Usage (automatic via Order Station page, or manual):
    python autoorder.py
"""
import asyncio
import json
import os
import sys

# NOTE: Playwright is imported lazily inside _run() (the only place that needs
# the browser). Importing it at module top would make `from autoorder import
# SUPPORTED_RESTAURANTS` (used by the Streamlit vote/order pages) crash the whole
# page in any environment where Playwright isn't installed.

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import db  # noqa: E402

# ── Ordering URLs ──────────────────────────────────────────────────────────────


MJ_SUSHI_URL   ="https://order.mealkeyway.com/customer/release/index?mid=59486559764f684f70534b5a534f72434479487744773d3d#/main"
STARBIRD_URL   = "https://order.starbirdchicken.com/venue/?id=3223&order-type=6"
IKES_URL       = "https://ikesloveandsandwiches.orderexperience.net/60902b6895b701063f8b457e/menu"
SWEETGREEN_URL = "https://order.sweetgreen.com/palo-alto/menu"
MENDOCINO_URL  = "https://order.mendocinofarms.com/menu/palo-alto"  # Olo (direct store URL)
ORENS_URL      = "https://order.toasttab.com/online/orens-hummus-palo-alto"  # Toast
ROOST_ROAST_URL = "https://order.toasttab.com/online/roost-and-roast"           # Toast
ASIAN_BOX_URL   = "https://order.spoton.com/asian-box-962/palo-alto-ca/65b13a4621728ea769f7f0b2/welcome"  # SpotOn
ZAREEN_URL      = "https://orderingatzareens.square.site/"                       # Square
POKE_HOUSE_URL  = "https://www.doordash.com/store/poke-house-palo-alto-458519/" # DoorDash (bot-blocked)
CHIPOTLE_URL         = "https://www.chipotle.com/order"
CHIPOTLE_BOWL_URL    = "https://www.chipotle.com/order/build/burrito-bowl"
CHIPOTLE_BURRITO_URL = "https://www.chipotle.com/order/build/burrito"
CHIPOTLE_TACO_URL    = "https://www.chipotle.com/order/build/tacos"
CHIPOTLE_SALAD_URL   = "https://www.chipotle.com/order/build/salad"
CHIPOTLE_QUESADILLA_URL = "https://www.chipotle.com/order/build/quesadilla"

OFFICE_ZIP = "94304"

# ── MenuSifu selectors (confirmed from live DOM inspection Jun 2026) ───────────

SEL_START_ORDER  = '.GA_lp_startorder'
SEL_PICKUP       = '.GA_Ordertypepop_PickupOrder'
SEL_ITEM_NAME    = '[class*="itemName"]'
SEL_ITEM_CARD    = '.GA_Menu_AddtoOrder'          # item card — click to open detail panel
SEL_PANEL_PLUS   = '[class*="GA_Item_detail_+"]'  # qty + inside the detail panel
SEL_PANEL_NOTES  = '.GA_Item_detail_Instructions' # special instructions textarea
SEL_PANEL_ADD    = '.GA_Item_detail_AddtoOrder'   # "Add N to cart" button in panel
SEL_VIEW_CART    = '.GA_Cart_ViewOrder, .shoppingCartBtn'


# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_items(order_text: str) -> list:
    if not order_text:
        return []
    try:
        parsed = json.loads(order_text)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return [{"item": order_text, "qty": 1, "notes": "", "price": 0.0}]


def consolidate_orders(orders_by_person: dict) -> list:
    """
    Flatten all per-person orders into a single list.
    Only merges items that share the same name AND the same customization note.
    Items with different notes stay as separate cart entries so the restaurant
    can fulfill each customization independently.
    """
    consolidated: dict = {}
    for person, items in orders_by_person.items():
        for it in items:
            name = (it.get("item") or "").strip()
            if not name:
                continue  # skip malformed/empty items rather than abort the run
            note = it.get("notes", "").strip()
            key = (name.lower(), note.lower())
            if key in consolidated:
                consolidated[key]["qty"] += it.get("qty", 1)
            else:
                consolidated[key] = {
                    "item": name,
                    "qty": it.get("qty", 1),
                    "notes": note,
                }
    return list(consolidated.values())


def _normalize(s: str) -> str:
    import re
    # Strip everything except letters and digits so "Foo (10 Pcs)" == "Foo(10 pcs)"
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _fuzzy_match(canonical: str, scraped: str) -> bool:
    c, s = _normalize(canonical), _normalize(scraped)
    if not c or not s:
        return False
    return c == s or c in s or s in c


# ── MenuSifu cart filler ───────────────────────────────────────────────────────

async def fill_cart_menusifu(page, items: list) -> None:
    print(f"\n→ Navigating to MJ Sushi ordering page...")
    try:
        await page.goto(MJ_SUSHI_URL, timeout=45000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"  Load error: {e}")
        return

    print("  Waiting for page to render...")
    await page.wait_for_timeout(5000)

    # Click "Start Order" if the landing page is showing
    try:
        start_btn = page.locator(SEL_START_ORDER).first
        if await start_btn.is_visible(timeout=3000):
            print("  Clicking 'Start Order'...")
            await start_btn.click()
            await page.wait_for_timeout(2000)
    except Exception:
        pass  # Already on the menu page

    # Dismiss the order-type dialog — select Pickup / ASAP
    try:
        pickup_btn = page.locator('.GA_Ordertypepop_PickupOrder').first
        if await pickup_btn.is_visible(timeout=3000):
            print("  Selecting 'Pickup Order' (ASAP)...")
            await pickup_btn.click()
            await page.wait_for_timeout(1500)
    except Exception:
        pass  # Dialog already dismissed or not shown

    # Scroll to trigger lazy loading
    for _ in range(10):
        await page.evaluate("window.scrollBy(0, 400)")
        await page.wait_for_timeout(300)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(1000)

    added: list = []
    skipped: list = []

    for order_item in items:
        item_name = order_item["item"]
        qty = order_item.get("qty", 1)
        notes = order_item.get("notes", "").strip()

        print(f"\n  Adding: {item_name} ×{qty}" + (f"  notes: {notes}" if notes else ""))

        # Find and scroll to item by name
        found = await page.evaluate(
            """(args) => {
                const [canonical, sel] = args;
                function norm(s) { return s.toLowerCase().replace(/[^a-z0-9]/g,''); }
                const c = norm(canonical);
                const nameEls = document.querySelectorAll(sel);
                for (const el of nameEls) {
                    const s = norm(el.innerText || el.textContent || '');
                    if (c === s || s.includes(c) || c.includes(s)) {
                        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        return true;
                    }
                }
                return false;
            }""",
            [item_name, SEL_ITEM_NAME],
        )

        if not found:
            print(f"    ✗ Not found in menu — will need to add manually")
            skipped.append(item_name)
            continue

        await page.wait_for_timeout(700)

        # Click the item card to open its detail panel
        try:
            clicked = await page.evaluate(
                """(args) => {
                    const [canonical, sel] = args;
                    function norm(s) { return s.toLowerCase().replace(/[^a-z0-9]/g,''); }
                    const c = norm(canonical);
                    const nameEls = document.querySelectorAll(sel);
                    for (const el of nameEls) {
                        const s = norm(el.innerText || el.textContent || '');
                        if (c === s || s.includes(c) || c.includes(s)) {
                            const card = el.closest('[class*="itemBody"], [class*="GA_Menu_AddtoOrder"]')
                                      || el.parentElement?.parentElement
                                      || el.parentElement;
                            if (card) { card.click(); return true; }
                        }
                    }
                    return false;
                }""",
                [item_name, SEL_ITEM_NAME],
            )
            if not clicked:
                raise Exception("no clickable card found")
        except Exception as e:
            print(f"    ✗ Click failed: {e}")
            skipped.append(item_name)
            continue

        # Wait for detail panel to open
        await page.wait_for_timeout(1500)

        # Set quantity using the panel's + button
        for _ in range(qty - 1):
            try:
                plus_btn = page.locator(SEL_PANEL_PLUS).first
                await plus_btn.click(timeout=2000)
                await page.wait_for_timeout(300)
            except Exception:
                break

        # Fill special instructions
        if notes:
            try:
                notes_field = page.locator(SEL_PANEL_NOTES).first
                await notes_field.fill(notes, timeout=2000)
            except Exception:
                pass

        # Click "Add N to cart" in the detail panel
        try:
            add_btn = page.locator(SEL_PANEL_ADD).first
            await add_btn.click(timeout=4000)
            # Wait for the detail panel to fully close before moving to next item
            try:
                await page.locator('#comboPanelOut .comboPanel_show__2fgV9').wait_for(
                    state="hidden", timeout=3000
                )
            except Exception:
                await page.wait_for_timeout(1200)
            print(f"    ✓ Added")
            added.append(item_name)
        except Exception as e:
            print(f"    ✗ Could not click 'Add to cart': {e}")
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(800)
            skipped.append(item_name)

    await _finalize(page, added, skipped, [SEL_VIEW_CART])


# ── Shared helpers for new restaurants ────────────────────────────────────────

async def _scroll_to_load(page, scrolls: int = 10) -> None:
    for _ in range(scrolls):
        await page.evaluate("window.scrollBy(0, 500)")
        await page.wait_for_timeout(250)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(800)


async def _find_scroll(page, item_name: str, name_sel: str) -> bool:
    return await page.evaluate(
        """([canonical, sel]) => {
            function norm(s) { return s.toLowerCase().replace(/[^a-z0-9]/g,''); }
            const c = norm(canonical);
            if (!c) return false;
            for (const el of document.querySelectorAll(sel)) {
                const s = norm(el.innerText || el.textContent || '');
                if (s && (c === s || s.includes(c) || c.includes(s))) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    return true;
                }
            }
            return false;
        }""",
        [item_name, name_sel],
    )


async def _click_card(page, item_name: str, name_sel: str, card_sel: str) -> bool:
    return await page.evaluate(
        """([canonical, nameSel, cardSel]) => {
            function norm(s) { return s.toLowerCase().replace(/[^a-z0-9]/g,''); }
            const c = norm(canonical);
            if (!c) return false;
            for (const el of document.querySelectorAll(nameSel)) {
                const s = norm(el.innerText || el.textContent || '');
                if (s && (c === s || s.includes(c) || c.includes(s))) {
                    const card = el.closest(cardSel) || el.parentElement?.parentElement || el.parentElement;
                    if (card) { card.click(); return true; }
                }
            }
            return false;
        }""",
        [item_name, name_sel, card_sel],
    )


async def _auto_select_required_modifiers(page) -> None:
    """Click first option in any required modifier group with no selection made.

    Handles radio-button groups (Olo, MenuSifu) via JS evaluate.
    For Paytronix checkbox groups (Ike's) call _ikes_select_required_modifiers instead.
    """
    try:
        await page.evaluate("""() => {
            const radioGroups = document.querySelectorAll(
                '[class*="modifier"], [class*="Modifier"], [data-testid*="modifier"], ' +
                '[class*="option-group"], [class*="OptionGroup"], [class*="customization"]'
            );
            for (const group of radioGroups) {
                const radios = group.querySelectorAll('input[type="radio"]');
                if (radios.length > 0 && !Array.from(radios).some(r => r.checked)) {
                    radios[0].click();
                }
            }
        }""")
        await page.wait_for_timeout(400)
    except Exception:
        pass


async def _ikes_select_required_modifiers(page) -> None:
    """Paytronix / Ike's: click the first label in each required .option-form
    that has zero selections.  Must use Playwright's native click (not JS evaluate)
    so React's synthetic onChange fires and the 'Add to Order' button enables.

    On 2nd+ items the sidebar reuses the same DOM — checked inputs from the
    previous item may still be present.  We detect groups that are VISUALLY
    shown in the current panel by checking that the group element is visible
    (offsetParent !== null), then treat any visible required group as needing
    a selection regardless of leftover checked state.
    """
    try:
        # Hide any stale modal-wrapper elements that are CSS-hidden but still
        # have position:fixed in the DOM — they intercept pointer events for the
        # item-detail sidebar on subsequent items.
        await page.evaluate("""() => {
            for (const w of document.querySelectorAll('.modal-wrapper, .modal-backdrop')) {
                if (w.offsetParent === null) w.style.display = 'none';
            }
        }""")

        # Wait a moment for the new panel to fully render its option groups
        await page.wait_for_timeout(500)

        # Gather the first input id in each VISIBLE required group (offsetParent
        # !== null = in the active panel). We click it even if it already appears
        # checked: on duplicate items Paytronix reuses the same DOM panel with
        # stale selections from the previous item, and re-clicking forces a fresh
        # React onChange so the "Add to Order" button reliably enables. The
        # caller applies the user's explicit choices AFTER this, overriding these
        # defaults.
        label_ids = await page.evaluate("""() => {
            const ids = [];
            for (const g of document.querySelectorAll('.option-form')) {
                if (!g.classList.contains('required')) continue;
                if (g.offsetParent === null) continue;
                const input = g.querySelector('input[type="checkbox"], input[type="radio"]');
                if (input && input.id) ids.push(input.id);
            }
            return ids;
        }""")

        for input_id in label_ids:
            try:
                label = page.locator(f'label[for="{input_id}"]').first
                if await label.is_visible(timeout=2000):
                    await label.click()
                    await page.wait_for_timeout(400)
            except Exception:
                pass
    except Exception:
        pass


async def _ikes_apply_choices(page, tokens: list) -> None:
    """
    Apply the orderer's structured choices (bread, veggies, sauce, add-ons) saved
    by the Orders page form as comma-separated tokens. For each token, find a
    matching modifier label in the active option panel and native-click it (so
    React's onChange fires). Tokens that don't match any modifier (free-text asks)
    are ignored here — they still travel in the special-instructions textarea.
    """
    for tok in tokens:
        try:
            input_id = await page.evaluate(
                """([tok]) => {
                    function norm(s){return (s||'').toLowerCase().replace(/[^a-z0-9]/g,'');}
                    const t = norm(tok);
                    if (!t) return null;
                    for (const g of document.querySelectorAll('.option-form')) {
                        if (g.offsetParent === null) continue;
                        for (const lab of g.querySelectorAll('label.option-control, label')) {
                            const s = norm(lab.innerText || lab.textContent || '');
                            if (s && (s === t || s.includes(t) || t.includes(s))) {
                                const inp = lab.querySelector('input[type="radio"], input[type="checkbox"]');
                                if (inp && inp.id) return inp.id;
                                if (lab.getAttribute('for')) return lab.getAttribute('for');
                            }
                        }
                    }
                    return null;
                }""",
                [tok],
            )
            if input_id:
                label = page.locator(f'label[for="{input_id}"]').first
                if await label.is_visible(timeout=1500):
                    await label.click()
                    await page.wait_for_timeout(300)
        except Exception:
            continue


RESULT_PATH = os.path.join(HERE, "autoorder_result.json")


def _save_summary(added: list, skipped: list,
                  verified: list | None = None, missing: list | None = None) -> None:
    """
    Print a human summary and write autoorder_result.json so the Streamlit Order
    Station can surface what was added/skipped (and, once Phase 2 cart verification
    runs, what was verified-present vs missing) instead of failing silently.
    """
    import time
    print(f"\n{'─'*50}")
    print(f"  ✓ Added:   {len(added)} item(s): {', '.join(added) if added else '—'}")
    if skipped:
        print(f"  ✗ Skipped: {len(skipped)} item(s): {', '.join(skipped)}")
    if missing:
        print(f"  ⚠ In summary but NOT found in cart: {', '.join(missing)}")
    print(f"{'─'*50}\n")

    result = {
        "added": added,
        "skipped": skipped,
        "verified": verified if verified is not None else [],
        "missing": missing if missing is not None else [],
        "ts": time.time(),
    }
    try:
        with open(RESULT_PATH, "w") as f:
            json.dump(result, f)
    except Exception as e:
        print(f"  (could not write result file: {e})")


async def _open_cart(page, selectors: list) -> None:
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await page.wait_for_timeout(1000)
                print("  Cart opened — review your order and proceed to checkout.")
                return
        except Exception:
            continue
    print("  Could not auto-click cart — open it manually.")


async def _verify_cart(page, added: list) -> tuple:
    """
    Check each "added" item is actually present in the CART region (not just
    anywhere on the page — the menu is usually still in the DOM, which would
    falsely "verify" everything). We read text only from a cart/basket/summary
    container; if none is found we report verification as inconclusive (empty
    verified list) rather than a misleading pass.
    Returns (verified, missing) — both lists of item names.
    """
    cart_text = await page.evaluate(
        """() => {
            const sels = ['[class*="cart" i]', '[class*="basket" i]', '[class*="bag" i]',
                          '[class*="order-summary" i]', '[class*="orderSummary" i]',
                          '[class*="order-item" i]', '[class*="order-detail" i]',
                          '[class*="order-list" i]', '[class*="checkout" i]',
                          '[id*="cart" i]', '[data-testid*="cart" i]', '[aria-label*="cart" i]'];
            let best = '', bestLen = 0;
            for (const sel of sels) {
                for (const el of document.querySelectorAll(sel)) {
                    const t = (el.innerText || '');
                    // prefer a sizeable cart/order panel, but not the whole page
                    if (t.length > bestLen && t.length < 4000) { best = t; bestLen = t.length; }
                }
            }
            return best;
        }"""
    )
    norm_cart = _normalize(cart_text or "")
    # If we couldn't read a cart/order panel, verification is INCONCLUSIVE — do not
    # claim items are missing (the Add clicks already succeeded). Report honestly.
    if len(norm_cart) < 8:
        print("  ℹ Couldn't auto-read the cart panel on this site — items were added "
              "(Add clicked OK); please eyeball the cart before checkout.")
        return [], []
    verified, missing = [], []
    for name in added:
        n = _normalize(name)
        if n and n in norm_cart:
            verified.append(name)
        else:
            missing.append(name)
    if verified:
        print(f"  ✓ Verified in cart: {len(verified)}/{len(added)}")
    if missing:
        print(f"  ⚠ Added but not detected in the cart panel (double-check): {', '.join(missing)}")
    return verified, missing


async def _finalize(page, added: list, skipped: list, cart_sels: list,
                    extra_note: str = "") -> None:
    """Open the cart, verify contents, write the result summary, keep browser open."""
    await _open_cart(page, cart_sels)
    await page.wait_for_timeout(1200)
    verified, missing = await _verify_cart(page, added)
    _save_summary(added, skipped, verified=verified, missing=missing)
    if extra_note:
        print(extra_note)
    await _keep_browser_alive(page)


async def _keep_browser_alive(page) -> None:
    print("\n  Browser will stay open. Close it when you're done with checkout.\n")
    try:
        await page.wait_for_event("close", timeout=7_200_000)
    except Exception:
        pass


def _print_order_reference(items: list, restaurant_name: str) -> None:
    print(f"\n  📋 Order reference for {restaurant_name}:")
    for it in items:
        qty_str = f"{it['qty']}× " if it.get("qty", 1) > 1 else ""
        notes_str = f"  —  {it['notes']}" if it.get("notes") else ""
        print(f"    • {qty_str}{it['item']}{notes_str}")
    print()


async def _dismiss_onetrust(page) -> None:
    """
    Remove the OneTrust cookie-consent overlay (#onetrust-consent-sdk and friends).
    Its backdrop is position:fixed and intercepts pointer events, so Playwright
    clicks on buttons beneath it silently time out. The SDK re-injects on
    navigation, so this must be called again after each page change.
    """
    try:
        await page.evaluate(
            """() => {
                const sels = ['[id*="onetrust"]', '[class*="onetrust"]',
                              '[class*="ot-sdk"]', '#onetrust-consent-sdk',
                              '.onetrust-pc-dark-filter'];
                for (const sel of sels) {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                }
                document.body.style.overflow = 'auto';  // SDK locks scroll
            }"""
        )
    except Exception:
        pass


# ── Olo / Vuetify shared fill (Starbird) ───────────────────────────────────────

async def _fill_cart_olo(page, items: list, restaurant_name: str, has_notes: bool) -> None:
    # Covers the classic Olo theme and the Vuetify "menu-theme" storefront used by
    # Starbird (c-button / c-button__title product cards).
    NAME_SEL  = (
        '[data-testid="item-name"], [class*="itemName"], [class*="item-name"], '
        '.c-button__title, [class*="c-button__title"], h4, h3'
    )
    CARD_SEL  = (
        '[data-testid="menu-item-card"], [class*="MenuItem"], [class*="menuItem"], '
        '[class*="menu-item"], button.c-button.--product, button.c-button, '
        '[class*="c-button"][class*="product"]'
    )
    QTY_PLUS  = (
        '[data-testid="quantity-increment"], button[aria-label*="Increase" i], '
        'button[aria-label*="increase" i], button[class*="increment"], '
        'button[class*="plus"]'
    )
    NOTES_SEL = (
        'textarea[data-testid="special-instructions"], textarea[placeholder*="special" i], '
        'textarea[name*="instruction" i], textarea[placeholder*="instruction" i], '
        'textarea[aria-label*="instruction" i], textarea[aria-label*="special" i]'
    )
    # Starbird's add-to-cart in the item-detail modal is #btn-cart-modal-submit
    # (button.c-button.--primary, label "Add"). Classic Olo uses the testid/text forms.
    ADD_SEL   = (
        '#btn-cart-modal-submit, [data-testid="add-to-bag-button"], '
        'button.c-button.--primary:has-text("Add"), '
        'button:has-text("Add to Bag"), button:has-text("Add to Order"), '
        'button:has-text("Add to Cart"), '
        'form[data-testid="product-customization-form"] button[type="submit"]'
    )
    CART_SELS = [
        '[data-testid="cart-button"]', '[class*="cart-button"]', '[class*="cartBtn"]',
        'a[href*="cart"]', 'a[href*="basket"]', 'button[aria-label*="bag" i]',
        'button[aria-label*="cart" i]', '[class*="basket"]',
    ]

    await _scroll_to_load(page, scrolls=10)
    _print_order_reference(items, restaurant_name)
    added, skipped = [], []

    for order_item in items:
        item_name = order_item["item"]
        qty       = order_item.get("qty", 1)
        notes     = order_item.get("notes", "").strip()

        print(f"\n  Adding: {item_name} ×{qty}" + (f"  notes: {notes}" if notes else ""))

        if not await _find_scroll(page, item_name, NAME_SEL):
            print(f"    ✗ Not found in menu")
            skipped.append(item_name)
            continue

        await page.wait_for_timeout(600)

        if not await _click_card(page, item_name, NAME_SEL, CARD_SEL):
            print(f"    ✗ Could not click card")
            skipped.append(item_name)
            continue

        await page.wait_for_timeout(2000)
        await _auto_select_required_modifiers(page)

        for _ in range(qty - 1):
            try:
                await page.locator(QTY_PLUS).first.click(timeout=2000)
                await page.wait_for_timeout(300)
            except Exception:
                break

        if has_notes and notes:
            try:
                await page.locator(NOTES_SEL).first.fill(notes, timeout=3000)
            except Exception:
                pass

        try:
            await page.locator(ADD_SEL).first.click(timeout=5000)
            await page.wait_for_timeout(1500)
            print(f"    ✓ Added")
            added.append(item_name)
        except Exception as e:
            print(f"    ✗ Could not add to cart: {e}")
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(800)
            skipped.append(item_name)

    await _finalize(page, added, skipped, CART_SELS)


# ── Starbird (Olo Serve, guest checkout, has special instructions) ─────────────

async def fill_cart_starbird(page, items: list) -> None:
    print(f"\n→ Navigating to Starbird — Palo Alto (2515 El Camino Real)...")
    try:
        await page.goto(STARBIRD_URL, timeout=45000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"  Load error: {e}")
        return
    print("  Waiting for menu to render...")
    await page.wait_for_timeout(6000)

    # Dismiss the cookie consent banner — it overlays the page with
    # position:fixed and intercepts pointer events on the add-to-cart button.
    for sel in ['#btn-cookie-banner-accept-2',
                '.cookie-banner__accept-btn',
                '.cookie-banner button:has-text("Accept")',
                'button:has-text("Accept all")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2000):
                print("  Dismissing cookie banner...")
                await btn.click()
                await page.wait_for_timeout(1000)
                break
        except Exception:
            continue

    await _fill_cart_olo(page, items, "Starbird", has_notes=True)


# ── Mendocino Farms (Olo, direct Palo Alto store URL, has special instructions) ─

async def fill_cart_mendocino(page, items: list) -> None:
    print(f"\n→ Navigating to Mendocino Farms — Palo Alto (167 Hamilton Ave)...")
    try:
        await page.goto(MENDOCINO_URL, timeout=45000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"  Load error: {e}")
        return
    print("  Waiting for menu to render...")
    await page.wait_for_timeout(6000)

    # Olo storefronts commonly show a cookie-consent banner that intercepts clicks.
    for sel in ['#btn-cookie-banner-accept-2',
                '.cookie-banner__accept-btn',
                'button:has-text("Accept all")',
                'button:has-text("Accept")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2000):
                print("  Dismissing cookie banner...")
                await btn.click()
                await page.wait_for_timeout(1000)
                break
        except Exception:
            continue

    # Same Olo platform as Starbird — reuse the shared filler.
    await _fill_cart_olo(page, items, "Mendocino Farms", has_notes=True)


# ── Ike's Love & Sandwiches (Paytronix OXB, has special instructions) ──────────

async def fill_cart_ikes(page, items: list) -> None:
    print(f"\n→ Navigating to Ike's — Palo Alto (401 Lytton Ave)...")
    try:
        await page.goto(IKES_URL, timeout=45000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"  Load error: {e}")
        return

    print("  Waiting for Paytronix menu to render (may take ~7s)...")
    await page.wait_for_timeout(7000)

    # Dismiss the order-type sidebar (Takeout / ASAP is pre-selected; just click "Start your order!")
    try:
        start_btn = page.locator('button.submit-button').first
        if await start_btn.is_visible(timeout=3000):
            print("  Dismissing order-type sidebar...")
            await start_btn.click()
            await page.wait_for_timeout(1500)
    except Exception:
        pass

    # Confirmed live DOM class (Jun 2026): item names are in .item-card-name divs,
    # cards are .item-card divs (role="link").
    NAME_SEL  = '.item-card-name, [class*="item-card-name"], [class*="itemName"], [class*="item-name"], h3, h4'
    CARD_SEL  = '.item-card, [class*="item-card"], [role="link"][class*="item"], [class*="menu-item"], article'
    QTY_PLUS  = 'button[aria-label*="increase" i], button[aria-label*="Increase" i], button:has-text("+")'
    NOTES_SEL = 'textarea[aria-label*="special" i], textarea[placeholder*="special" i], textarea[placeholder*="instruction" i], label:has-text("Special") + textarea, label:has-text("Instructions") + textarea'
    ADD_SEL   = 'button:has-text("Add to Cart"), button[aria-label*="Add to Cart" i], button:has-text("Add to Order"), button[type="submit"]:has-text("Add"), button[class*="add"]'
    # Confirmed live DOM: Paytronix shows the order/cart via .order-btn ("Order")
    # and a .order-info-button.has-order indicator once items are in the order.
    CART_SELS = [
        '.order-btn', '.order-info-button.has-order', '.order-info-button',
        'button:has-text("Checkout")', 'button:has-text("Review and Checkout")',
        'a[href*="checkout" i]', 'a[href*="cart" i]', '[class*="cart-button"]',
    ]

    await _scroll_to_load(page, scrolls=8)
    _print_order_reference(items, "Ike's Love & Sandwiches")
    added, skipped = [], []

    for order_item in items:
        item_name = order_item["item"]
        qty       = order_item.get("qty", 1)
        notes     = order_item.get("notes", "").strip()

        print(f"\n  Adding: {item_name} ×{qty}" + (f"  notes: {notes}" if notes else ""))

        if not await _find_scroll(page, item_name, NAME_SEL):
            print(f"    ✗ Not found in menu")
            skipped.append(item_name)
            continue

        await page.wait_for_timeout(700)

        if not await _click_card(page, item_name, NAME_SEL, CARD_SEL):
            print(f"    ✗ Could not click card")
            skipped.append(item_name)
            continue

        # Wait for the item-detail sidebar to open and render its option groups
        try:
            await page.locator('.option-form.required').first.wait_for(
                state="visible", timeout=6000
            )
        except Exception:
            pass
        await page.wait_for_timeout(1000)
        # 1) Satisfy every required modifier group first (defaults) so the panel
        #    is in a valid, Add-enabled state — robust against duplicate items
        #    reusing a stale panel. 2) THEN apply the orderer's explicit choices
        #    (bread, veggies, sauce, add-ons), overriding those defaults.
        await _ikes_select_required_modifiers(page)
        choice_tokens = [t.strip() for t in notes.split(",") if t.strip()]
        if choice_tokens:
            await _ikes_apply_choices(page, choice_tokens)
        await page.wait_for_timeout(500)

        for _ in range(qty - 1):
            try:
                await page.locator(QTY_PLUS).first.click(timeout=2000)
                await page.wait_for_timeout(300)
            except Exception:
                break

        # Backstop: also drop the full note text into special instructions so the
        # kitchen sees the intended bread/options even if a click didn't register.
        if notes:
            try:
                await page.locator(NOTES_SEL).first.fill(notes, timeout=3000)
            except Exception:
                pass

        # Click "Add to Order" robustly. The intermittent failure mode is a stale
        # .modal-wrapper from the previous item (CSS-hidden but still position:fixed)
        # intercepting the click, or the button sitting below the fold. So: hide
        # stale overlays, scroll the button in, try a normal click then a forced
        # one, and retry twice.
        added_ok = False
        for _attempt in range(2):
            try:
                await page.evaluate("""() => {
                    for (const w of document.querySelectorAll('.modal-wrapper, .modal-backdrop')) {
                        if (w.offsetParent === null) w.style.display = 'none';
                    }
                }""")
                add_btn = page.locator(ADD_SEL).first
                await add_btn.wait_for(state="visible", timeout=5000)
                await add_btn.scroll_into_view_if_needed()
                try:
                    await add_btn.click(timeout=3500)
                except Exception:
                    await add_btn.click(force=True, timeout=2500)
                added_ok = True
                break
            except Exception:
                await page.wait_for_timeout(900)
        if added_ok:
            try:
                await page.locator('.modal-backdrop, .modal-wrapper').wait_for(
                    state="hidden", timeout=5000
                )
            except Exception:
                await page.wait_for_timeout(2000)
            print(f"    ✓ Added")
            added.append(item_name)
        else:
            print(f"    ✗ Could not add to cart (Add button never became clickable)")
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(1000)
            skipped.append(item_name)

    await _finalize(page, added, skipped, CART_SELS)


# ── Sweetgreen (no notes field, login required at checkout) ────────────────────

async def fill_cart_sweetgreen(page, items: list) -> None:
    print(f"\n→ Navigating to Sweetgreen — Palo Alto (581 Ramona St)...")
    print(f"  Note: Sweetgreen has no special-instructions field. Login required at checkout.")
    try:
        await page.goto(SWEETGREEN_URL, timeout=45000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"  Load error: {e}")
        return

    print("  Waiting for menu to render...")
    await page.wait_for_timeout(5000)
    await _dismiss_onetrust(page)  # consent overlay blocks all clicks until removed

    # Sweetgreen uses React with generated class names; cast a wide net for item titles.
    # Priority: data-testid attributes, then class patterns covering title/name/label,
    # then heading tags, then generic p/span/div as last-resort fallbacks.
    NAME_SEL  = (
        '[data-testid*="item-name"], [data-testid*="itemName"], [data-testid*="item_name"], '
        '[data-testid*="menu-item-name"], [data-testid*="product-name"], '
        '[class*="ItemTitle"], [class*="itemTitle"], [class*="item-title"], '
        '[class*="ItemName"], [class*="itemName"], [class*="item-name"], '
        '[class*="MenuItemName"], [class*="menuItemName"], [class*="menu-item-name"], '
        '[class*="ProductName"], [class*="productName"], [class*="product-name"], '
        '[class*="CardTitle"], [class*="cardTitle"], [class*="card-title"], '
        '[class*="title"], [class*="Title"], '
        '[class*="name"], [class*="Name"], '
        '[class*="label"], [class*="Label"], '
        'h1, h2, h3, h4, h5, h6, '
        '[data-testid*="item"], [data-testid*="menu"]'
    )
    CARD_SEL  = (
        '[data-testid*="menu-item-card"], [data-testid*="menuItemCard"], [data-testid*="item-card"], '
        '[class*="MenuItemCard"], [class*="menuItemCard"], [class*="menu-item-card"], '
        '[class*="MenuItem"], [class*="menuItem"], [class*="menu-item"], '
        '[class*="ItemCard"], [class*="itemCard"], [class*="item-card"], '
        '[class*="ProductCard"], [class*="productCard"], '
        '[class*="Card"], [class*="card"], '
        '[role="button"], [role="listitem"], [role="article"], '
        'article, section, li'
    )
    QTY_PLUS  = 'button[aria-label*="increase" i], button[data-testid*="quantity-increase"], button[data-testid*="increment"], button[aria-label*="add" i]'
    # Customizable bowls/salads open a full-page item builder with a TWO-STEP CTA:
    # a "Continue" button first (price-suffixed, e.g. "Continue\n$15.75"), then an
    # "Add to bag" button (also price-suffixed, e.g. "Add to bag\n$15.75"). Neither
    # is a form submit nor carries an add-to-* data-testid, so we match on visible
    # button text. CONTINUE_SEL is clicked first (if present) to reveal ADD_SEL.
    CONTINUE_SEL = (
        'button:has-text("Continue"), button:has-text("Review order"), '
        'button:has-text("Next")'
    )
    ADD_SEL   = (
        'button:has-text("Add to bag"), button:has-text("Add to Bag"), '
        'button:has-text("Add to order"), button:has-text("Add to Order"), '
        'button:has-text("Add to cart"), button:has-text("Add to Cart"), '
        'button[data-testid*="add-to-bag"], button[data-testid*="addToBag"], '
        'button[data-testid*="add-to-order"], button[data-testid*="addToOrder"], '
        'button[data-testid*="add-to-cart"], button[data-testid*="addToCart"], '
        'form button[type="submit"]'
    )
    CART_SELS = [
        'button[aria-label*="cart" i]', 'a[href*="/cart"]',
        'button[data-testid*="cart"]', 'button[aria-label*="bag" i]',
        'a[href*="bag"]', 'button[data-testid*="bag"]',
    ]

    await _scroll_to_load(page, scrolls=10)
    _print_order_reference(items, "Sweetgreen")
    added, skipped = [], []

    for order_item in items:
        item_name = order_item["item"]
        qty       = order_item.get("qty", 1)
        notes     = order_item.get("notes", "").strip()

        print(f"\n  Adding: {item_name} ×{qty}")
        if notes:
            print(f"    Note: '{notes}' must be applied manually — Sweetgreen has no notes field.")

        # Step 1: scroll item into view using the broad NAME_SEL
        if not await _find_scroll(page, item_name, NAME_SEL):
            print(f"    ✗ Not found in menu")
            skipped.append(item_name)
            continue

        await page.wait_for_timeout(700)

        # Step 2: two card types on Sweetgreen.
        #   (a) Simple items (drinks, sides, snacks) render a per-item quick-add
        #       button with aria-label "Add N <ItemName> to your bag" — clicking
        #       it adds the item directly with no builder.
        #   (b) Customizable bowls/salads render an <a href> card that NAVIGATES
        #       to a full-page item builder; there is no quick-add button and no
        #       modal. We must click that anchor (closest('a')) to navigate.
        # We try (a) first; on miss we navigate via the anchor and fall through
        # to the Continue → Add-to-bag builder flow below.
        click_result = await page.evaluate(
            """([canonical]) => {
                function norm(s) { return s.toLowerCase().replace(/[^a-z0-9]/g, ''); }
                const c = norm(canonical);
                // (a) quick-add button — only matches simple items
                for (const btn of document.querySelectorAll('button[aria-label]')) {
                    const lbl = norm(btn.getAttribute('aria-label') || '');
                    // aria-label is "add N <name> to your bag" — require it to
                    // contain "add" + the item name so we don't match nav buttons
                    if (lbl.startsWith('add') && lbl.includes(c) && lbl.includes('bag')) {
                        btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        btn.click();
                        return 'quickadd';
                    }
                }
                // (b) bowl/salad card anchor — RETURN its href so Python can
                // navigate directly. (A client-side anchor .click() lands the SPA
                // in a state where the "Continue" CTA never becomes visible; a
                // full page.goto() to the item URL renders the builder correctly.)
                for (const a of document.querySelectorAll('a[href*="/palo-alto/"]')) {
                    const t = norm(a.innerText || a.textContent || '');
                    if (t && (t === c || t.includes(c) || c.includes(t))) {
                        return a.href;  // absolute URL
                    }
                }
                return 'none';
            }""",
            [item_name],
        )

        if click_result == "quickadd":
            await page.wait_for_timeout(1500)
            print(f"    ✓ Added (verify ingredients match your order)")
            added.append(item_name)
            continue

        if click_result == "none":
            print(f"    ✗ Not found on menu (no quick-add button or item link)")
            skipped.append(item_name)
            continue

        # click_result is the item builder URL — navigate directly (matches the
        # proven probe flow). Signature bowls/salads arrive pre-configured with all
        # ingredients, so we do NOT auto-select modifiers (that would add unwanted
        # ingredients and disrupt the Continue step).
        try:
            await page.goto(click_result, timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"    ✗ Could not open item builder: {e}")
            skipped.append(item_name)
            continue
        await page.wait_for_timeout(3500)
        await _dismiss_onetrust(page)  # SDK re-injects on navigation into builder

        # Two-step flow (confirmed via live DOM): the builder page shows only a
        # "Continue $X.XX" button; clicking it reveals the final "Add to bag
        # $X.XX" button on a confirmation screen. The Continue click MUST land —
        # if it doesn't, "Add to bag" never renders and ADD_SEL times out.
        try:
            cont = page.locator(CONTINUE_SEL).first
            await cont.wait_for(state="visible", timeout=5000)
            await cont.scroll_into_view_if_needed()
            await cont.click()
            await page.wait_for_timeout(2000)
            await _dismiss_onetrust(page)  # overlay can re-appear on the confirm screen
        except Exception as e:
            print(f"    · Continue step skipped ({type(e).__name__}) — trying Add directly")

        try:
            add_btn = page.locator(ADD_SEL).first
            await add_btn.wait_for(state="visible", timeout=6000)
            await add_btn.scroll_into_view_if_needed()
            await add_btn.click()
            await page.wait_for_timeout(1800)
            print(f"    ✓ Added (verify ingredients match your order)")
            added.append(item_name)
        except Exception as e:
            print(f"    ✗ Could not add to order: {e}")
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(800)
            skipped.append(item_name)

        # Return to the menu so the next item's _find_scroll has the menu DOM.
        if not page.url.rstrip("/").endswith("/menu"):
            try:
                await page.goto(SWEETGREEN_URL, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                await _dismiss_onetrust(page)
                await _scroll_to_load(page, scrolls=10)
            except Exception:
                pass

    note = "  ⚠️  Sweetgreen requires account login to complete checkout." if added else ""
    await _finalize(page, added, skipped, CART_SELS, extra_note=note)


# ── Chipotle (wizard-per-meal-type, JS-evaluate clicks to bypass card-selection-overlay) ──

# Maps normalized item-name keywords → wizard URL
# Checked against live DOM Jun 2026: each meal type is a separate Vue SPA route.
_CHIPOTLE_MEAL_URL_MAP = [
    # order matters: more-specific patterns first
    (["burrito bowl", "bowl"],          CHIPOTLE_BOWL_URL),
    (["burrito"],                        CHIPOTLE_BURRITO_URL),
    (["taco"],                           CHIPOTLE_TACO_URL),
    (["salad", "lifestyle bowl"],        CHIPOTLE_SALAD_URL),
    (["quesadilla"],                     CHIPOTLE_QUESADILLA_URL),
    (["chips", "guac", "side", "drink"], CHIPOTLE_URL),  # chips-and-sides via main order page
]


def _chipotle_wizard_url(item_name: str) -> str:
    """Return the Chipotle wizard URL for a given item name."""
    n = item_name.lower()
    for keywords, url in _CHIPOTLE_MEAL_URL_MAP:
        if any(kw in n for kw in keywords):
            return url
    return CHIPOTLE_URL


async def _chipotle_js_click_item(page, text: str) -> bool:
    """
    Click a Chipotle wizard ingredient/option by fuzzy text match using JS evaluate.
    Native Playwright clicks are blocked by div.card-selection-overlay — JS .click()
    bypasses it.  Confirmed working selectors from live DOM inspection Jun 2026:
      - .item-name  (innerText matches protein / rice / bean / topping names)
      - [class*="item-name"]  (covers item-name-container as fallback)
      - [class*="card"]  (the whole card, useful for chips-and-sides page)
      - div[role="link"]  (top-level meal-type links on the /order landing page)
    """
    return await page.evaluate(
        """(text) => {
            function norm(s) { return s.toLowerCase().replace(/[^a-z0-9]/g,''); }
            const t = norm(text);
            if (!t) return false;
            // Try most-specific selectors first, then broader fallbacks
            const SELS = [
                '.item-name',
                '[class*="item-name"]',
                '[class*="display-name"]',
                'div[role="link"]',
                '[class*="card"]',
            ];
            for (const sel of SELS) {
                for (const el of document.querySelectorAll(sel)) {
                    const raw = el.innerText || el.textContent || '';
                    const s = norm(raw);
                    if (s && (s === t || s.includes(t) || t.includes(s))) {
                        el.click();
                        return true;
                    }
                }
            }
            return false;
        }""",
        text,
    )


async def _chipotle_dismiss_cookie_banner(page) -> None:
    """Dismiss Chipotle's privacy/cookie consent banner if it appears."""
    for sel in ['button:has-text("Accept All")', 'button:has-text("Accept")',
                '[aria-label="close banner"]']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await page.wait_for_timeout(800)
                return
        except Exception:
            pass


async def _chipotle_navigate_chips(page) -> bool:
    """
    Navigate to the Chips & Sides section.
    From the /order landing page, click the 'CHIPS & SIDES' meal-type link.
    Returns True if navigation succeeded.
    """
    try:
        await page.goto(CHIPOTLE_URL, timeout=45000, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        await _chipotle_dismiss_cookie_banner(page)
        # The meal-type options are div[role="link"] elements on this page
        found = await _chipotle_js_click_item(page, "chips & sides")
        if not found:
            found = await _chipotle_js_click_item(page, "chips")
        if found:
            await page.wait_for_timeout(3000)
            print(f"    Navigated to chips page: {page.url}")
            return True
        print(f"    Could not find CHIPS & SIDES link on {page.url}")
        return False
    except Exception as e:
        print(f"    Chips navigation error: {e}")
        return False


async def fill_cart_chipotle(page, items: list) -> None:
    """
    Chipotle order automation — Jun 2026 DOM.

    Architecture:
    - Each meal type lives at its own wizard URL (e.g. /order/build/burrito-bowl).
    - All ingredient options (protein, rice, beans, salsas, toppings, extras) are
      rendered simultaneously as .item-name elements — not gated behind Next buttons.
    - Native Playwright clicks are blocked by div.card-selection-overlay; use
      page.evaluate() with element.click() to bypass it.
    - Chips & Guacamole navigates from the /order landing page via the CHIPS & SIDES link.
    """
    print(f"\n→ Navigating to Chipotle order page...")

    # Bootstrap: hit the main order page once to warm up session + dismiss cookie banner
    try:
        await page.goto(CHIPOTLE_URL, timeout=45000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"  Load error: {e}")
        return

    print("  Waiting for page to render...")
    await page.wait_for_timeout(4000)
    await _chipotle_dismiss_cookie_banner(page)

    CART_SELS = [
        '[class*="order-bag"]', '[class*="cartBtn"]', '[class*="cart-btn"]',
        'a[href*="bag"]', 'button[aria-label*="bag" i]', 'button[aria-label*="cart" i]',
        '[class*="bag-icon"]', '[class*="bagIcon"]',
    ]

    _print_order_reference(items, "Chipotle")
    added, skipped = [], []

    for order_item in items:
        item_name   = order_item["item"]
        qty         = order_item.get("qty", 1)
        notes       = order_item.get("notes", "").strip()
        # Ingredients come in as comma-separated notes; treat each as a wizard option to click
        ingredients = [ing.strip() for ing in notes.split(",") if ing.strip()]

        print(f"\n  Adding: {item_name} ×{qty}")
        if ingredients:
            print(f"    Ingredients: {ingredients}")

        # Determine which wizard URL to use for this item
        wizard_url = _chipotle_wizard_url(item_name)
        is_chips = wizard_url == CHIPOTLE_URL  # chips takes a different navigation path

        # ── Navigate to the correct wizard page ──────────────────────────────
        if is_chips:
            ok = await _chipotle_navigate_chips(page)
            if not ok:
                print(f"    ✗ Could not navigate to chips page")
                skipped.append(item_name)
                continue
        else:
            try:
                await page.goto(wizard_url, timeout=45000, wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
                await _chipotle_dismiss_cookie_banner(page)
                print(f"    Wizard page: {page.url}")
            except Exception as e:
                print(f"    ✗ Navigation error: {e}")
                skipped.append(item_name)
                continue

        # Scroll to trigger lazy-load
        await _scroll_to_load(page, scrolls=6)

        # ── Click each ingredient using JS evaluate (bypasses overlay) ────────
        # For chips: "Chips & Guacamole" — the notes field is empty, so just find
        # the item card and click it.
        if is_chips:
            # On the chips-and-sides page the items use .item-name as well
            found = await _chipotle_js_click_item(page, "chips & guacamole")
            if not found:
                found = await _chipotle_js_click_item(page, "guacamole")
            if not found:
                found = await _chipotle_js_click_item(page, "chips")
            if not found:
                print(f"    ✗ Could not find chips item on page")
                skipped.append(item_name)
                continue
            print(f"    ✓ Chips item clicked")
            await page.wait_for_timeout(1000)
        else:
            # For burrito bowls and burritos: the notes encode the protein + toppings.
            # "Chicken Burrito Bowl" with notes "White Rice, Black Beans, ..."
            # means protein = Chicken (from item name), then notes = customizations.
            # Extract protein from the item name itself.
            item_lower = item_name.lower()
            protein = None
            if "chicken" in item_lower:
                protein = "Chicken"
            elif "steak" in item_lower:
                protein = "Steak"
            elif "barbacoa" in item_lower:
                protein = "Beef Barbacoa"
            elif "carnitas" in item_lower:
                protein = "Carnitas"
            elif "sofritas" in item_lower:
                protein = "Sofritas"
            elif "veggie" in item_lower:
                protein = "Veggie"

            # Click protein first if we identified it from item name
            if protein:
                ok = await _chipotle_js_click_item(page, protein)
                if ok:
                    print(f"    ✓ Protein: {protein}")
                    await page.wait_for_timeout(600)
                else:
                    print(f"    ? Protein not found: {protein}")

            # Then click each ingredient from notes
            for ingredient in ingredients:
                ok = await _chipotle_js_click_item(page, ingredient)
                if ok:
                    print(f"    ✓ {ingredient}")
                    await page.wait_for_timeout(400)
                else:
                    print(f"    ? Not found: {ingredient}")

        # ── Qty increment (look for +/- controls that appear after selection) ─
        for _ in range(qty - 1):
            try:
                plus = page.locator(
                    'button[aria-label*="increase" i], [class*="quantity"] button:last-child, '
                    'button[class*="increment"], button[class*="plus"]'
                ).first
                await plus.click(timeout=2000)
                await page.wait_for_timeout(300)
            except Exception:
                break

        # ── Add to Bag / Order ────────────────────────────────────────────────
        # Chipotle wizard: look for "Add to Order", "Add to Bag", or submit button.
        # Use JS evaluate so pointer-events:none overlays don't block it.
        add_result = await page.evaluate("""() => {
            function norm(s) { return s.toLowerCase().replace(/[^a-z0-9 ]/g, '').trim(); }
            // Match anything that looks like an add-to-bag/order action. Use includes()
            // (not just startsWith) so labels like "Add to Bag - $10.99" or
            // "Add to Meal" / "ADD TO BAG" inside nested spans still match.
            const targets = ['add to order', 'add to bag', 'add item', 'add to meal', 'add'];
            // Widen the candidate set: <button>, role=button, <a>, submit inputs, and
            // any element whose class/data-* attributes hint at "add".
            const CANDIDATE_SEL =
                'button, [role="button"], a, input[type="submit"], input[type="button"], ' +
                '[class*="add"], [data-qa*="add" i], [data-testid*="add" i]';
            const seen = [];
            for (const btn of document.querySelectorAll(CANDIDATE_SEL)) {
                const label = btn.innerText || btn.textContent ||
                              btn.getAttribute('aria-label') ||
                              btn.value || '';
                const t = norm(label);
                const dq = (btn.getAttribute('data-qa') || '').toLowerCase();
                const dt = (btn.getAttribute('data-testid') || '').toLowerCase();
                seen.push(t || dq || dt);
                const disabled = btn.disabled === true ||
                                 btn.getAttribute('aria-disabled') === 'true';
                if (disabled) continue;
                const textMatch = targets.some(tgt => t === tgt || t.includes(tgt));
                const attrMatch = dq.includes('add') || dt.includes('add');
                if (textMatch || attrMatch) {
                    btn.click();
                    return { clicked: true, label: t || dq || dt };
                }
            }
            return { clicked: false, candidates: seen.filter(Boolean).slice(0, 40) };
        }""")

        added_to_bag = bool(add_result.get("clicked"))
        if added_to_bag:
            print(f"    (add button matched: '{add_result.get('label', '')}')")

        if not added_to_bag:
            # Fallback: try Playwright native click on common Add button selectors.
            # Case-insensitive text match + data-qa/data-testid attribute selectors
            # (Chipotle uses data-qa hooks), plus generic add/cart class hints.
            try:
                add_btn = page.locator(
                    'button:has-text("Add to Order"), button:has-text("Add to Bag"), '
                    'button:has-text("Add Item"), button:has-text("Add to Meal"), '
                    'button:text-matches("add to (bag|order|meal)", "i"), '
                    '[data-qa*="add" i], [data-testid*="add" i], '
                    'button[class*="add" i], button[class*="cart" i], '
                    'button[type="submit"], '
                    '[class*="add-to-order"], [class*="addToOrder"], [class*="add-to-bag"], [class*="addToBag"]'
                ).first
                await add_btn.click(timeout=8000)
                added_to_bag = True
            except Exception as e:
                print(f"    ✗ Could not click Add to Bag: {e}")

        if added_to_bag:
            await page.wait_for_timeout(2000)
            print(f"    ✓ Added to bag")
            added.append(item_name)
        else:
            skipped.append(item_name)

    await _finalize(page, added, skipped, CART_SELS)



# ── Restaurant dispatch ────────────────────────────────────────────────────────

# Only restaurants whose auto-fill has been VERIFIED end-to-end (items confirmed
# added to the live cart) are registered here — so the "Auto-fill cart" button
# only appears where it actually works. Everything else falls back to manual
# ordering with no button.
SUPPORTED_RESTAURANTS: dict = {
    "seed-mj-sushi":               fill_cart_menusifu,   # MenuSifu — verified
    "seed-starbird":               fill_cart_starbird,   # Vuetify/Olo — verified
    "seed-ike-s-love-sandwiches":  fill_cart_ikes,       # Paytronix — verified
    "seed-sweetgreen":             fill_cart_sweetgreen, # verified (login req. at checkout)
    # NOT registered — button intentionally hidden until proven:
    #   seed-chipotle-mexican-grill (fill_cart_chipotle): menu is a cross-origin
    #     iframe gated behind store selection — automation can't drive it.
    #   seed-mendocino-farms (fill_cart_mendocino): Cloudflare-blocked.
    # Their fillers remain defined above for future use; re-register only after a
    # clean verified run.
}


# ── Main ───────────────────────────────────────────────────────────────────────

async def _run():
    db.init_db()

    winner_row = db.get_todays_winner()
    if not winner_row:
        print("No restaurant picked today — nothing to order.")
        return

    place_id = winner_row["winner_place_id"]
    filler = SUPPORTED_RESTAURANTS.get(place_id)
    if not filler:
        restaurant = db.get_restaurant(place_id)
        name = restaurant["name"] if restaurant else place_id
        print(f"Auto-order not supported for {name}.")
        return

    restaurant = db.get_restaurant(place_id)
    print(f"\n🍣  Auto-ordering from: {restaurant['name']}")

    # Build consolidated order
    raw_orders = db.get_todays_orders()
    orders_by_person: dict = {}
    for o in raw_orders:
        items = parse_items(o.get("order_text", ""))
        if items:
            orders_by_person[o["person"]] = items

    if not orders_by_person:
        print("No orders submitted yet.")
        return

    items = consolidate_orders(orders_by_person)
    total_qty = sum(it["qty"] for it in items)
    print(f"  {len(items)} unique item(s), {total_qty} total qty across {len(orders_by_person)} people\n")

    from playwright.async_api import async_playwright  # lazy: only needed here
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=120,
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 390, "height": 844},
        )
        page = await context.new_page()
        await filler(page, items)


if __name__ == "__main__":
    asyncio.run(_run())
