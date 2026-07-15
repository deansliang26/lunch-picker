import subprocess
import sys
import os
import json
import time
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
import menus
import sidebar
import status
from autoorder import SUPPORTED_RESTAURANTS, _fuzzy_match, RESULT_PATH

db.init_db()

HERE = os.path.dirname(os.path.abspath(__file__))   # pages/
PROJECT_ROOT = os.path.dirname(HERE)                 # lunch-picker/

from roster import TEAM
BUDGET = 20.00

# On a hosted (headless) deploy there is no browser/display, so the auto-fill
# subprocess can't run — hide the button and show a manual-order note instead.
def _is_cloud() -> bool:
    if os.getenv("LUNCH_PICKER_CLOUD"):
        return True
    try:
        return bool(st.secrets.get("CLOUD", ""))
    except Exception:
        return False

IS_CLOUD = _is_cloud()

st.set_page_config(page_title="Order Station · PA Lunch", page_icon="🧾", layout="wide")
sidebar.render()

user = st.session_state.user


# ── Helpers ──

def parse_items(order_text: str) -> list[dict]:
    if not order_text:
        return []
    try:
        parsed = json.loads(order_text)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return [{"item": order_text, "qty": 1, "notes": "", "price": 0.0}]


def subtotal(items: list[dict]) -> float:
    return sum((it.get("price") or 0.0) * (it.get("qty") or 1) for it in items)


def menu_item_names(place_id: str) -> list[str]:
    """All item names across every category of a restaurant's menu."""
    data = menus.get_menu(place_id)
    if not data:
        return []
    names = []
    for cat in data.get("categories", []):
        for it in cat.get("items", []):
            if it.get("name"):
                names.append(it["name"])
    return names


def unmatchable_items(orders_by_person: dict, place_id: str) -> list[str]:
    """
    Item names in the order that won't fuzzy-match anything on the menu — these
    are what the auto-fill browser will skip (custom items, typos, off-menu asks).
    Returns a de-duplicated, order-preserving list.
    """
    names = menu_item_names(place_id)
    if not names:
        return []
    seen, unmatched = set(), []
    for items in orders_by_person.values():
        for it in items:
            item = it.get("item", "").strip()
            if not item or item.lower() in seen:
                continue
            seen.add(item.lower())
            if not any(_fuzzy_match(item, m) for m in names):
                unmatched.append(item)
    return unmatched


# ── Guard: need a winner ──

winner_row = db.get_todays_winner()
if not winner_row:
    st.markdown("## 🧾 Order Station")
    st.info("No restaurant picked yet — head to Today to vote first.")
    st.page_link("pages/1_Today.py", label="← Back to voting", icon="🗳️")
    st.stop()

winner = db.get_restaurant(winner_row["winner_place_id"])
winner_name = winner["name"] if winner else "Today's restaurant"
menu_data = menus.get_menu(winner_row["winner_place_id"])
menu_url = (menu_data or {}).get("menu_url", "")

# ── Load orders ──

orders = db.get_todays_orders()
orders_by_person: dict = {}
for o in orders:
    items = parse_items(o.get("order_text", ""))
    if items:
        orders_by_person[o["person"]] = items

submitted = [p for p in TEAM if orders_by_person.get(p)]

if not submitted:
    st.markdown("## 🧾 Order Station")
    st.info("Nobody has submitted an order yet. Head to Orders to add items.")
    st.page_link("pages/2_Orders.py", label="← Go to Orders", icon="🧾")
    st.stop()

# ── Session state: placed checkboxes ──

for p in TEAM:
    if f"placed_{p}" not in st.session_state:
        st.session_state[f"placed_{p}"] = False

placed_count = sum(1 for p in submitted if st.session_state.get(f"placed_{p}"))
all_done = placed_count == len(submitted)

# ── Header ──

st.markdown(f"## 🧾 Order Station — {winner_name}")

meta_parts = []
if winner.get("cuisine"):
    meta_parts.append(winner["cuisine"])
if winner.get("rating"):
    meta_parts.append(f"★ {winner['rating']}")
if winner.get("address"):
    meta_parts.append(winner["address"])
if meta_parts:
    st.caption(" · ".join(meta_parts))

_vstatus = menus.verification_status(menu_data) if menu_data else {"state": "unverified"}
if _vstatus["state"] == "unverified":
    st.warning(
        "⚠️ **Prices for this spot aren't verified** against the live site — the group "
        "total below may be inaccurate. Verify them on the **Menus** page."
    )
elif _vstatus["state"] == "stale":
    st.warning(
        f"🟡 **Prices last verified {_vstatus['date']}** ({_vstatus['age_days']} days ago) — "
        "the group total may be off. Re-verify on the **Menus** page."
    )

status.render_team_status()

# ── Action bar ──

autofill_supported = winner_row["winner_place_id"] in SUPPORTED_RESTAURANTS
can_autofill = autofill_supported and bool(submitted)
unmatched = unmatchable_items(orders_by_person, winner_row["winner_place_id"]) if can_autofill else []

ac1, ac2, ac3, ac4, ac5 = st.columns([2, 2, 2, 1, 1])
with ac1:
    if menu_url:
        st.link_button("🌐 Open Online Ordering ↗", menu_url, use_container_width=True)
    elif winner.get("yelp_url"):
        st.link_button("View on Yelp ↗", winner["yelp_url"], use_container_width=True)
with ac2:
    if winner.get("yelp_url") and menu_url:
        st.link_button("View on Yelp ↗", winner["yelp_url"], use_container_width=True)
with ac3:
    if not autofill_supported:
        st.markdown(
            "<div style='padding-top:6px;font-size:13px;color:#76726A;'>"
            "✋ <strong>Manual order only</strong><br><span style='font-size:12px;'>"
            "no auto-fill for this spot</span></div>",
            unsafe_allow_html=True,
        )
    elif not submitted:
        st.markdown(
            "<div style='padding-top:6px;font-size:13px;color:#141413;'>"
            "🛒 <strong>Auto-fill available</strong><br><span style='font-size:12px;color:#76726A;'>"
            "enables once orders are in</span></div>",
            unsafe_allow_html=True,
        )
    if can_autofill and IS_CLOUD:
        st.markdown(
            "<div style='padding-top:6px;font-size:13px;color:#76726A;'>"
            "🌐 <strong>Auto-fill not available on the hosted version</strong><br>"
            "<span style='font-size:12px;'>order manually via the link above</span></div>",
            unsafe_allow_html=True,
        )
    elif can_autofill:
        if st.button("🛒 Auto-fill cart", use_container_width=True, type="primary",
                     help="Opens a browser and automatically adds all orders to the cart"):
            try:
                # Clear any stale result so the panel below reflects THIS run.
                try:
                    os.remove(RESULT_PATH)
                except FileNotFoundError:
                    pass
                venv_python = os.path.join(PROJECT_ROOT, ".venv", "bin", "python")
                py = venv_python if os.path.exists(venv_python) else sys.executable
                subprocess.Popen(
                    [py, os.path.join(PROJECT_ROOT, "autoorder.py")],
                    cwd=PROJECT_ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                st.session_state["autofill_launched_at"] = time.time()
                st.toast("Browser opened — finish checkout in that window", icon="✅")
            except Exception as e:
                st.error(f"Failed to launch: {e}")
with ac4:
    grand = sum(subtotal(v) for v in orders_by_person.values())
    st.metric("Group total", f"${grand:.2f}")
with ac5:
    if st.button("Reset", use_container_width=True, help="Uncheck all placed items"):
        for p in TEAM:
            st.session_state[f"placed_{p}"] = False
        st.rerun()

# ── Pre-flight: items the auto-fill browser can't match on the menu ──
if can_autofill and unmatched:
    items_md = " · ".join(f"**{name}**" for name in unmatched)
    st.markdown(
        f"""<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;
            padding:10px 14px;margin-top:8px;font-size:13px;">
          ⚠️ Auto-fill can't add these (not on the online menu) — add them manually in the browser:
          &nbsp;{items_md}
        </div>""",
        unsafe_allow_html=True,
    )


# ── Post-run report: what the auto-fill browser actually added/skipped ──
def read_autofill_result() -> dict | None:
    try:
        with open(RESULT_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


launched_at = st.session_state.get("autofill_launched_at")
if can_autofill and launched_at:
    result = read_autofill_result()
    rc1, rc2 = st.columns([5, 1])
    with rc2:
        if st.button("🔄 Refresh", use_container_width=True, help="Check auto-fill progress"):
            st.rerun()
    with rc1:
        if not result or result.get("ts", 0) < launched_at:
            st.info("🛒 Browser is open and filling the cart — click **Refresh** when it finishes.")
        else:
            added = result.get("added", [])
            skipped = result.get("skipped", [])
            missing = result.get("missing", [])
            parts = [f"✅ **{len(added)}** added"]
            if skipped:
                parts.append(f"⚠️ **{len(skipped)}** skipped")
            if missing:
                parts.append(f"❌ **{len(missing)}** missing from cart")
            st.success("Auto-fill done — " + " · ".join(parts))
            if skipped:
                st.caption("Skipped (add manually): " + ", ".join(skipped))
            if missing:
                st.caption("In summary but not found in cart — verify these: " + ", ".join(missing))

# ── Progress bar ──

pct = int(placed_count / len(submitted) * 100) if submitted else 0
bar_color = "#D97757" if all_done else ("#f59e0b" if placed_count > 0 else "#9C978C")

st.markdown(
    f"""<div style="margin:12px 0 4px 0;">
      <div style="display:flex;justify-content:space-between;font-size:13px;font-weight:600;margin-bottom:6px;">
        <span style="color:#141413;">Placing order</span>
        <span style="color:{bar_color};">{placed_count} of {len(submitted)} done</span>
      </div>
      <div style="background:#F5F3EC;border-radius:99px;height:10px;">
        <div style="background:{bar_color};border-radius:99px;height:10px;width:{pct}%;transition:width 0.3s;"></div>
      </div>
    </div>""",
    unsafe_allow_html=True,
)

if all_done:
    st.success("✅  All orders placed — go pick up the food!")

st.divider()

# ── Per-person order cards ──

for person in TEAM:
    items = orders_by_person.get(person, [])
    if not items:
        continue

    placed_key = f"placed_{person}"
    is_placed = st.session_state.get(placed_key, False)
    person_total = subtotal(items)
    overage = max(0.0, person_total - BUDGET)

    with st.container(border=True):
        h1, h2, h3 = st.columns([3, 1, 1])

        with h1:
            icon = "✅" if is_placed else "⬜"
            you_tag = "  *(you)*" if person == user else ""
            name_color = "#76726A" if is_placed else "#141413"
            st.markdown(
                f"<div style='font-size:20px;font-weight:800;color:{name_color};padding-top:4px;'>"
                f"{icon} {person}{you_tag}</div>",
                unsafe_allow_html=True,
            )

        with h2:
            color = "#A53F31" if overage else "#141413"
            st.markdown(
                f"<div style='font-size:20px;font-weight:700;color:{color};padding-top:6px;text-align:right;'>"
                f"${person_total:.2f}</div>",
                unsafe_allow_html=True,
            )

        with h3:
            if is_placed:
                if st.button("↩ Undo", key=f"place_btn_{person}", use_container_width=True):
                    st.session_state[placed_key] = False
                    st.rerun()
            else:
                if st.button("✓ Mark placed", key=f"place_btn_{person}",
                             use_container_width=True, type="primary"):
                    st.session_state[placed_key] = True
                    st.rerun()

        # Item rows
        for it in items:
            qty = it.get("qty") or 1
            price = it.get("price") or 0.0
            notes = it.get("notes", "").strip()
            ic1, ic2 = st.columns([5, 1])
            with ic1:
                qty_str = f"**{qty}×** " if qty > 1 else ""
                notes_md = f"  ·  *{notes}*" if notes else ""
                opacity = "0.45" if is_placed else "1"
                st.markdown(
                    f"<div style='padding-left:20px;opacity:{opacity};'>"
                    f"{qty_str}**{it['item']}**{notes_md}</div>",
                    unsafe_allow_html=True,
                )
            with ic2:
                if price:
                    st.markdown(
                        f"<div style='text-align:right;opacity:{'0.45' if is_placed else '1'};'>"
                        f"${price * qty:.2f}</div>",
                        unsafe_allow_html=True,
                    )

        # Budget overage callout
        if overage:
            st.markdown(
                f"""<div style="background:#F4DED9;border:1px solid #A53F31;border-radius:8px;
                    padding:8px 14px;margin-top:8px;font-size:13px;">
                  ⚠️ Company covers ${BUDGET:.2f} &nbsp;·&nbsp; <strong>{person} pays ${overage:.2f}</strong>
                </div>""",
                unsafe_allow_html=True,
            )

# ── People with no orders yet ──

no_order = [p for p in TEAM if p not in orders_by_person]
if no_order:
    st.caption(f"No order submitted: {', '.join(no_order)}")
