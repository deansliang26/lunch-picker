import sys
import os
import json
import streamlit as st
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
import menus
import sidebar
import status
import avatar

db.init_db()

from roster import TEAM
BUDGET = 20.00

st.set_page_config(page_title="Orders · PA Lunch", page_icon="🍜", layout="wide")
sidebar.render()

user = st.session_state.user

# --- Check for winner (preview mode if none or manually triggered) ---
winner_row = db.get_todays_winner()
if "preview_mode" not in st.session_state:
    st.session_state["preview_mode"] = False
preview_mode = False

if not winner_row or st.session_state["preview_mode"]:
    all_restaurants = db.get_cached_restaurants(max_age_days=36500)
    menu_restaurants = sorted(
        [r for r in all_restaurants if menus.get_menu(r["id"]) and menus.get_menu(r["id"]).get("categories")],
        key=lambda r: r["name"],
    )
    cols = st.columns([4, 1])
    with cols[0]:
        st.info("🔍  Preview mode — pick a restaurant to test the ordering UI.")
    with cols[1]:
        if winner_row and st.button("Exit preview", use_container_width=True):
            st.session_state["preview_mode"] = False
            st.rerun()
    names = [r["name"] for r in menu_restaurants]
    chosen = st.selectbox("Preview restaurant", names, label_visibility="collapsed")
    chosen_r = next((r for r in menu_restaurants if r["name"] == chosen), None)
    if not chosen_r:
        st.stop()
    winner_row = {"winner_place_id": chosen_r["id"]}
    preview_mode = True

winner = db.get_restaurant(winner_row["winner_place_id"])
winner_name = winner["name"] if winner else "Today's restaurant"
menu_data = menus.get_menu(winner_row["winner_place_id"])

# Derived from menu_data
menu_url = (menu_data or {}).get("menu_url", "")
# A menu is "browsable" if it has flat categories OR is a build-your-own menu.
has_items = bool(menu_data and (menu_data.get("categories") or menu_data.get("menu_type") == "build"))

# Ike's structured ordering (sandwiches need a required Bread Choice + freebies/sauce/extras)
IKES_ID            = "seed-ike-s-love-sandwiches"
IKES_SANDWICH_CATS = {"Meat Sandwiches", "Ike-conic Collabs", "Veggie Sandwiches", "Vegan Sandwiches"}
is_ikes            = winner_row["winner_place_id"] == IKES_ID
ikes_opts          = (menu_data or {}).get("ikes_options", {}) if is_ikes else {}

# --- Pre-init session state (must happen before any fragment) ---
if "open_item" not in st.session_state:
    st.session_state["open_item"] = None

# --- Header ---
meta_parts = []
if winner.get("cuisine"):
    meta_parts.append(winner["cuisine"])
if winner.get("rating"):
    meta_parts.append(f"★ {winner['rating']}")
if winner.get("price"):
    meta_parts.append(winner["price"])
if winner.get("address"):
    meta_parts.append(winner["address"])
meta_str = " · ".join(meta_parts)

st.markdown(
    f"""
    <div style="margin-bottom: 12px;">
      <div style="font-size:26px; font-weight:800; color:#141413; line-height:1.2;">
        🧾  Orders — {winner_name}
      </div>
      <div style="font-size:13px; color:#76726A; margin-top:4px;">{meta_str}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

btn_cols = st.columns(4)
with btn_cols[0]:
    if winner.get("yelp_url"):
        st.link_button("View on Yelp ↗", winner["yelp_url"])
with btn_cols[1]:
    if menu_url:
        st.link_button("📋 View actual menu ↗", menu_url)
with btn_cols[2]:
    google_url = f"https://www.google.com/search?q={winner_name.replace(' ', '+')}+menu+order+online"
    st.link_button("Order Online ↗", google_url)
with btn_cols[3]:
    if not preview_mode and st.button("🔍 Preview another restaurant"):
        st.session_state["preview_mode"] = True
        st.rerun()

if menu_data and not has_items:
    st.warning(
        f"⚠️ Menu couldn't be scraped automatically. "
        + (f"[View the real menu here ↗]({menu_url})" if menu_url else "Search for the menu online.")
        + "  Enter your order in the text box below."
    )

status.render_team_status()

st.divider()


# --- Helpers ---

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


def save_items(person: str, items: list[dict]):
    if not preview_mode:
        db.upsert_order(person, json.dumps(items))


def subtotal(items: list[dict]) -> float:
    return sum((it.get("price") or 0.0) * (it.get("qty") or 1) for it in items)


def format_order_doc(orders_by_person: dict) -> str:
    today_label = date.today().strftime("%A, %B %-d, %Y")
    lines = [f"ORDER — {winner_name}", today_label, ""]
    grand_total = 0.0
    for person in TEAM:
        items = orders_by_person.get(person, [])
        if not items:
            continue
        lines.append(person.upper())
        person_total = 0.0
        for it in items:
            qty = it.get("qty") or 1
            name = it.get("item", "")
            price = it.get("price") or 0.0   # may be stored None; coerce for arithmetic
            notes = it.get("notes", "").strip()
            qty_str = f"{qty}x " if qty > 1 else "   "
            price_str = f"${price * qty:.2f}" if price else ""
            line = f"  {qty_str}{name}"
            if price_str:
                line = f"{line:<38}{price_str}"
            lines.append(line)
            if notes:
                lines.append(f"       → {notes}")
            person_total += price * qty
        if person_total:
            lines.append(f"  {'Subtotal':<36}${person_total:.2f}")
            if person_total > BUDGET:
                overage = person_total - BUDGET
                lines.append(f"  {'  Company covers':<36}${BUDGET:.2f}")
                lines.append(f"  {'  You pay':<36}${overage:.2f}")
        grand_total += person_total
        lines.append("")
    if grand_total:
        lines.append(f"{'TOTAL':<38}${grand_total:.2f}")
    else:
        lines.append(f"Total items: {sum(len(v) for v in orders_by_person.values())}")
    return "\n".join(lines)


# --- Load today's orders (module-level snapshot for the menu browser's add-form) ---
existing_orders = {o["person"]: o for o in db.get_todays_orders()}


# =====================================================================
# MAIN LAYOUT: left = menu browser, right = your order panel
# =====================================================================
if has_items:
    menu_col, order_col = st.columns([3, 2], gap="large")
else:
    menu_col = st.container()
    order_col = None

# ---- LEFT: Menu browser ----
with menu_col:
    if has_items:
        st.subheader("Menu")
        if menu_data.get("prices_verified"):
            st.caption("_✓ Prices verified against the restaurant's live ordering site_")
        else:
            st.warning(
                "⚠️ **Prices not verified** — these came from the original seed data and "
                "may be inaccurate (every restaurant we *could* check had wrong prices). "
                "Confirm on the restaurant's site before relying on them."
            )

        # ── Build-your-own restaurants (Chipotle, Panda): a builder with a
        #    computed price, instead of flat named items. ──
        is_build = menu_data.get("menu_type") == "build"
        if is_build:
            b = menu_data["builder"]
            st.markdown("#### 🧑‍🍳 Build your meal")
            if b.get("instructions"):
                st.caption(b["instructions"])
            if not user:
                st.info("Pick your name in the sidebar to build an order.")
            else:
                # No st.form here: the builder is fully reactive so changing the
                # format updates the entrée count + base price immediately, and the
                # live price reflects entrée upcharges as you check them. (Form
                # widgets don't apply until submit — that breaks the format ↔ count
                # link, so this must stay form-free.)
                rid = winner_row["winner_place_id"]
                fmt = st.selectbox(
                    "Format", [f["name"] for f in b["formats"]],
                    key=f"build_fmt_{rid}",
                )
                selected_fmt_obj = next((f for f in b["formats"] if f["name"] == fmt), {})
                n = selected_fmt_obj.get("num_entrees", b.get("num_proteins", 1))
                prot_names = [p["name"] for p in b["proteins"]]
                entree_label = b.get("entree_label", "Protein")
                has_protein_images = any(p.get("image_url") for p in b["proteins"])

                if has_protein_images:
                    st.markdown(
                        f"<div style='font-size:14px;font-weight:600;margin-bottom:8px;'>"
                        f"{entree_label} — pick {'1' if n == 1 else f'up to {n}'}</div>",
                        unsafe_allow_html=True,
                    )
                    chosen = []
                    COLS = 4
                    for row_start in range(0, len(b["proteins"]), COLS):
                        row_prots = b["proteins"][row_start : row_start + COLS]
                        img_cols = st.columns(COLS)
                        for ci, prot in enumerate(row_prots):
                            with img_cols[ci]:
                                if prot.get("image_url"):
                                    st.markdown(
                                        f'<img src="{prot["image_url"]}" onerror="this.style.display=\'none\'" '
                                        f'style="width:100%;'
                                        f'border-radius:8px;aspect-ratio:1/1;object-fit:cover;'
                                        f'margin-bottom:4px;">',
                                        unsafe_allow_html=True,
                                    )
                                upcharge = f" +${prot['upcharge']:.2f}" if prot.get("upcharge") else ""
                                if st.checkbox(
                                    f"{prot['name']}{upcharge}",
                                    key=f"build_prot_{rid}_{row_start + ci}",
                                ):
                                    chosen.append(prot["name"])
                    if len(chosen) > n:
                        st.warning(
                            f"⚠️ {fmt} comes with {n} entrée{'s' if n > 1 else ''} — "
                            f"please uncheck {len(chosen) - n}."
                        )
                else:
                    if n == 1:
                        chosen = [st.selectbox(entree_label, prot_names, key=f"build_ent_{rid}")]
                    else:
                        chosen = st.multiselect(
                            f"{entree_label} (pick up to {n})", prot_names,
                            max_selections=n, key=f"build_ent_{rid}",
                        )

                opt_pick = {}
                for label, choices in (b.get("options") or {}).items():
                    if not choices:
                        continue
                    okey = f"build_opt_{rid}_{label}"
                    if any(k in label.lower() for k in ("toppings", "add-ons", "extras", "mix-ins")):
                        opt_pick[label] = st.multiselect(label, choices, placeholder="Optional…", key=okey)
                    else:
                        opt_pick[label] = [st.selectbox(label, choices, key=okey)]
                bq1, bq2 = st.columns([1, 3])
                with bq1:
                    bqty = st.number_input("Qty", min_value=1, max_value=10, value=1, key=f"build_qty_{rid}")
                fmt_base = next((f["base"] for f in b["formats"] if f["name"] == fmt), 0.0)
                up = sum(
                    next((p.get("upcharge", 0.0) for p in b["proteins"] if p["name"] == pn), 0.0)
                    for pn in chosen
                )
                bprice = round(fmt_base + up, 2)
                with bq2:
                    st.markdown(
                        f"<div style='padding-top:26px;font-weight:800;color:#141413;font-size:18px;'>"
                        f"Price: ${bprice:.2f}</div>",
                        unsafe_allow_html=True,
                    )
                valid_build = bool(chosen) and len(chosen) <= n
                if st.button("Add to my order", use_container_width=True, type="primary",
                             key=f"build_add_{rid}", disabled=not valid_build):
                    item_name = f"{fmt} — {', '.join(chosen)}"
                    note_parts = []
                    for _label, vals in opt_pick.items():
                        note_parts += [v for v in vals if v]
                    notes = ", ".join(note_parts)
                    current = {o["person"]: o for o in db.get_todays_orders()}
                    cur_items = parse_items(current.get(user, {}).get("order_text", ""))
                    save_items(user, cur_items + [{
                        "item": item_name, "qty": int(bqty),
                        "notes": notes, "price": bprice,
                    }])
                    for k in list(st.session_state.keys()):
                        if (k.startswith(f"build_prot_{rid}_")
                                or k == f"build_ent_{rid}"
                                or k.startswith(f"build_opt_{rid}_")
                                or k == f"build_qty_{rid}"):
                            del st.session_state[k]
                    st.rerun()
            if menu_data.get("categories"):
                st.markdown("##### Sides, drinks & extras")

        def render_item(cat, item, item_idx, cat_idx):
            # Key by category INDEX (not display name) so duplicate category names
            # can't collide into the same widget key / open-item state.
            item_key = f"{cat_idx}|{item_idx}"
            is_open = st.session_state["open_item"] == item_key

            with st.container(border=True):
                img_col, name_col, price_col, btn_col = st.columns([1, 4, 1, 1])

                with img_col:
                    if item.get("image_url"):
                        st.markdown(
                            f'<img src="{item["image_url"]}" onerror="this.style.display=\'none\'" '
                            'style="width:100%;aspect-ratio:1/1;'
                            'object-fit:cover;border-radius:6px;display:block;">',
                            unsafe_allow_html=True,
                        )

                with name_col:
                    badge = "🔥 " if item.get("popular") else ""
                    st.markdown(f"**{badge}{item['name']}**")
                    if item.get("description"):
                        st.caption(item["description"])

                with price_col:
                    if item.get("price"):
                        st.markdown(f"**${item['price']:.2f}**")

                with btn_col:
                    if not is_open:
                        if st.button(
                            "+ Add",
                            key=f"open_{cat_idx}_{item_idx}",
                            use_container_width=True,
                        ):
                            st.session_state["open_item"] = item_key
                            st.rerun()
                    else:
                        if st.button(
                            "✕",
                            key=f"cancel_{cat_idx}_{item_idx}",
                            use_container_width=True,
                        ):
                            st.session_state["open_item"] = None
                            st.rerun()

                # Inline add form — appears below the item row
                if is_open:
                    if not user:
                        st.warning("Pick your name in the sidebar first.")
                    else:
                        use_ikes_form = (
                            is_ikes
                            and bool(ikes_opts)
                            and cat["name"] in IKES_SANDWICH_CATS
                        )
                        with st.form(key=f"form_{cat_idx}_{item_idx}", clear_on_submit=True):
                            fc1, fc2 = st.columns([1, 3])
                            with fc1:
                                qty = st.number_input(
                                    "Qty",
                                    min_value=1,
                                    max_value=10,
                                    value=1,
                                )
                            with fc2:
                                if use_ikes_form:
                                    # Bread is a REQUIRED choice on every Ike's sandwich.
                                    bread = st.selectbox("Bread *", ikes_opts.get("bread", []))
                                    veggies = st.multiselect(
                                        "Veggies (free)",
                                        ikes_opts.get("veggies", []),
                                        placeholder="Pick your veggies…",
                                    )
                                    sauce = st.selectbox("Dirty Sauce", ikes_opts.get("dirty_sauce", []))
                                    extras = st.multiselect(
                                        "Add-ons",
                                        ikes_opts.get("extras", []),
                                        placeholder="Optional paid extras…",
                                    )
                                    extra_notes = st.text_input(
                                        "Anything else", placeholder="optional"
                                    )
                                    # Bread first so the filler can apply it; skip the
                                    # default "Regular" sauce (it's already on the sandwich).
                                    parts = [bread] + veggies
                                    if sauce and not sauce.lower().startswith("regular"):
                                        parts.append(sauce)
                                    parts += extras
                                    if extra_notes.strip():
                                        parts.append(extra_notes.strip())
                                    notes = ", ".join(p for p in parts if p)
                                else:
                                    notes = st.text_input(
                                        "Customizations",
                                        placeholder="e.g. no sour cream, add guac, extra spicy",
                                    )
                            if st.form_submit_button(
                                f"Add {item['name']} to my order",
                                use_container_width=True,
                            ):
                                if user:
                                    # Re-read from DB at submit time (not stale module-level snapshot)
                                    current_orders = {o["person"]: o for o in db.get_todays_orders()}
                                    current_items = parse_items(current_orders.get(user, {}).get("order_text", ""))
                                    new_items = current_items + [{
                                        "item": item["name"],
                                        "qty": int(qty),
                                        "notes": notes.strip(),
                                        "price": item.get("price") or 0.0,
                                    }]
                                    save_items(user, new_items)
                                    st.session_state["open_item"] = None
                                    st.rerun()

        # ── Search across the whole menu, else browse by category tabs ──
        # (Only if there are flat categories — a build menu may have none.)
        search_q = ""
        if menu_data.get("categories"):
          search_q = st.text_input(
            "🔍 Search the menu",
            placeholder="e.g. salmon, vegan, spicy, avocado",
            key="menu_search",
          ).strip().lower()

        if not menu_data.get("categories"):
            pass  # build-only menu with no flat extras — builder above is the whole menu
        elif search_q:
            matches = [
                (ci, cat, item, i)
                for ci, cat in enumerate(menu_data["categories"])
                for i, item in enumerate(cat["items"])
                if search_q in item["name"].lower()
                or search_q in (item.get("description") or "").lower()
            ]
            st.caption(f"{len(matches)} result(s) for “{search_q}”")
            if not matches:
                st.info("No items match — try a different word.")
            for ci, cat, item, i in matches:
                render_item(cat, item, i, ci)
        else:
            cat_names = [c["name"] for c in menu_data["categories"]]
            tabs = st.tabs(cat_names)
            for ci, (tab, cat) in enumerate(zip(tabs, menu_data["categories"])):
                with tab:
                    for item_idx, item in enumerate(cat["items"]):
                        render_item(cat, item, item_idx, ci)

        # ── Custom item ──
        st.markdown("---")
        st.markdown("**➕ Add a custom item**")
        with st.form("custom_item_form", clear_on_submit=True):
            ci1, ci2, ci3 = st.columns([3, 1, 2])
            with ci1:
                custom_name = st.text_input("Item name", placeholder="e.g. Large Drink, Extra Sauce")
            with ci2:
                custom_price = st.number_input("Price ($)", min_value=0.0, step=0.25, value=0.0)
            with ci3:
                custom_notes = st.text_input("Notes", placeholder="optional")
            if st.form_submit_button("Add to my order", use_container_width=True):
                if user and custom_name.strip():
                    current_orders = {o["person"]: o for o in db.get_todays_orders()}
                    current_items = parse_items(current_orders.get(user, {}).get("order_text", ""))
                    new_items = current_items + [{
                        "item": custom_name.strip(),
                        "qty": 1,
                        "notes": custom_notes.strip(),
                        "price": custom_price,
                    }]
                    save_items(user, new_items)
                    st.rerun()
                elif not user:
                    st.warning("Pick your name in the sidebar first.")

    else:
        # Fallback for custom restaurants with no menu data
        st.subheader("Your order")
        st.info("No menu on file for this restaurant. Enter your order below.")
        if not user:
            st.warning("Pick your name in the sidebar to save your order.")
        else:
            existing_text = existing_orders.get(user, {}).get("order_text", "")
            # Show existing structured items read-only (don't pre-fill free text with JSON)
            existing_items = parse_items(existing_text)
            if existing_items and existing_text.startswith("["):
                st.markdown("**Your current order:**")
                for it in existing_items:
                    qty_str = f"{it['qty']}× " if it.get("qty", 1) > 1 else ""
                    st.markdown(f"• {qty_str}{it['item']}")
                if st.button("Clear order", key="fallback_clear"):
                    if not preview_mode:
                        db.clear_order(user)
                    st.rerun()
            with st.form("fallback_order_form"):
                order_input = st.text_area(
                    "Add / replace order text",
                    value="",
                    placeholder="e.g. Chicken sandwich, no pickles + side salad",
                    height=100,
                )
                if st.form_submit_button("Save order"):
                    if order_input.strip():
                        if not preview_mode:
                            db.upsert_order(user, order_input.strip())
                        st.toast("Saved!" if not preview_mode else "Preview mode — not saved.")
                        st.rerun()


# ---- RIGHT: Your order panel ----
def _render_order_panel():
    if not user:
        st.info("Pick your name in the sidebar to start ordering.")
        return

    # Always re-read from DB so removes/adds in the left panel are immediately reflected
    fresh_orders = {o["person"]: o for o in db.get_todays_orders()}
    panel_items = parse_items(fresh_orders.get(user, {}).get("order_text", ""))

    person_total = subtotal(panel_items)
    count = len(panel_items)
    header = f"Your order ({count} item{'s' if count != 1 else ''})"
    if person_total:
        header += f" — ${person_total:.2f}"
    st.subheader(header)

    if not panel_items:
        st.caption("Nothing added yet — browse the menu on the left.")
    else:
        for i, it in enumerate(panel_items):
            qty = it.get("qty", 1)
            price = it.get("price") or 0.0   # assigned before column split (bug fix)
            ic1, ic2, ic3 = st.columns([4, 1, 1])
            with ic1:
                qty_str = f"**{qty}×** " if qty > 1 else ""
                st.markdown(f"{qty_str}**{it['item']}**")
                if it.get("notes"):
                    st.caption(f"→ {it['notes']}")
            with ic2:
                if price:
                    st.markdown(f"${price * qty:.2f}")
            with ic3:
                if st.button("✕", key=f"rm_{i}", help="Remove"):
                    new_items = [x for j, x in enumerate(panel_items) if j != i]
                    save_items(user, new_items)
                    st.rerun()

        if person_total:
            st.markdown("---")
            overage = max(0.0, person_total - BUDGET)
            pct = min(100, int(person_total / BUDGET * 100))
            bar_color = "#A53F31" if overage else ("#f59e0b" if pct >= 80 else "#D97757")
            bar_pct = 100 if overage else pct
            st.markdown(
                f"""<div style="margin-bottom:10px;">
                  <div style="display:flex;justify-content:space-between;font-size:12px;color:#76726A;margin-bottom:4px;">
                    <span>Team budget</span><span>${person_total:.2f} / $20.00</span>
                  </div>
                  <div style="background:#F5F3EC;border-radius:99px;height:8px;">
                    <div style="background:{bar_color};border-radius:99px;height:8px;width:{bar_pct}%;transition:width 0.3s;"></div>
                  </div>
                </div>""",
                unsafe_allow_html=True,
            )
            if overage:
                st.markdown(
                    f"""<div style="background:#F4DED9;border:1px solid #A53F31;border-radius:10px;padding:10px 14px;margin-bottom:10px;">
                      <div style="font-weight:700;color:#A53F31;font-size:14px;">⚠️ ${overage:.2f} over budget</div>
                      <div style="font-size:12px;color:#76726A;margin-top:2px;">Company covers ${BUDGET:.2f} · You pay <strong>${overage:.2f}</strong></div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"**Subtotal: ${person_total:.2f}**")

        if st.button("Clear my order", key="clear_order"):
            if not preview_mode:
                db.clear_order(user)
            st.rerun()


if order_col is not None:
    with order_col:
        _render_order_panel()

st.divider()


# =====================================================================
# BOTTOM: Live team summary + order document (auto-refreshes every 3s)
# =====================================================================
@st.fragment(run_every=10)
def team_summary():
    orders = db.get_todays_orders()
    orders_by_person: dict = {}
    for o in orders:
        items = parse_items(o.get("order_text", ""))
        if items:
            orders_by_person[o["person"]] = items

    submitted = sum(1 for p in TEAM if orders_by_person.get(p))
    st.subheader(f"All orders  ({submitted}/{len(TEAM)} submitted)")

    # Per-person expandable rows
    for person in TEAM:
        items = orders_by_person.get(person, [])
        you = " ← you" if person == user else ""
        person_total = subtotal(items)
        overage = max(0.0, person_total - BUDGET)
        check = "✓ " if items else ""
        label = f"{check}{person}{you}"
        if items and person_total:
            label += f"  —  ${person_total:.2f}"
        if overage:
            label += f"  ⚠️ +${overage:.2f} personal"
        with st.expander(label, expanded=bool(items)):
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
                f'{avatar.html(person, size=30)}'
                f'<span style="font-weight:700;font-size:15px;color:#141413;">{person}</span>'
                f'{"<span style=\'font-size:12px;color:#9C978C;\'>← you</span>" if person == user else ""}'
                f'</div>',
                unsafe_allow_html=True,
            )
            if items:
                for it in items:
                    qty = it.get("qty", 1)
                    qty_str = f"{qty}× " if qty > 1 else ""
                    price_str = f"  ${it['price'] * qty:.2f}" if it.get("price") else ""
                    notes_str = f"  —  {it['notes']}" if it.get("notes") else ""
                    st.markdown(f"• {qty_str}**{it['item']}**{price_str}{notes_str}")
            else:
                st.caption("No order yet")

    # Group total
    if orders_by_person:
        grand = sum(subtotal(v) for v in orders_by_person.values())
        total_items = sum(len(v) for v in orders_by_person.values())
        if grand:
            st.markdown(f"### Group total: ${grand:.2f}")
            st.caption(f"{total_items} items across {submitted} people")

    # Kitchen ticket — identical items combined across everyone, so the orderer
    # can read off totals ("3× Chicken Burrito") instead of name-by-name.
    if orders_by_person:
        agg: dict = {}
        for items in orders_by_person.values():
            for it in items:
                key = (it.get("item", ""), (it.get("notes") or "").strip())
                agg[key] = agg.get(key, 0) + (it.get("qty") or 1)
        st.divider()
        st.subheader("🧑‍🍳 Kitchen ticket")
        st.caption("Identical items combined — read this off when you call it in")
        ticket_lines = []
        for (name, notes), qty in sorted(agg.items(), key=lambda x: (-x[1], x[0][0].lower())):
            note_str = f"  ({notes})" if notes else ""
            ticket_lines.append(f"{qty:>2}×  {name}{note_str}")
        st.code("\n".join(ticket_lines), language=None)

    # Order document (per-person breakdown with prices + budget)
    if orders_by_person:
        st.divider()
        st.subheader("Order document")
        st.caption("Per-person breakdown — for splitting cost or the receipt")
        doc = format_order_doc(orders_by_person)
        st.code(doc, language=None)


team_summary()
