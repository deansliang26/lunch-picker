import sys
import os
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
import menus
import sidebar

db.init_db()

st.set_page_config(page_title="Menus · PA Lunch", page_icon="📋", layout="wide")
sidebar.render()

st.markdown("## 📋  Menus")


def _render_category(cat):
    items = cat.get("items", [])
    if not items:
        st.caption("No items listed.")
        return
    for it in items:
        badge = "🔥 " if it.get("popular") else ""
        price_str = f"  ·  **${it['price']:.2f}**" if it.get("price") else ""
        desc_str = (
            f"<span style='font-size:12px;color:#76726A;display:block;margin-top:2px;'>"
            f"{it['description']}</span>"
            if it.get("description") else ""
        )
        st.markdown(
            f"<div style='padding:6px 0;border-bottom:1px solid #F5F3EC;'>"
            f"<span style='font-weight:600;color:#141413;'>{badge}{it['name']}</span>"
            f"<span style='color:#D97757;'>{price_str}</span>"
            f"{desc_str}</div>",
            unsafe_allow_html=True,
        )


# Build list of restaurants that have scraped menu data
all_restaurants = db.get_cached_restaurants(max_age_days=36500)
menu_restaurants = []
for r in sorted(all_restaurants, key=lambda x: x["name"]):
    m = menus.get_menu(r["id"])
    if m and m.get("categories"):
        menu_restaurants.append(r)

if not menu_restaurants:
    st.info("No menu data loaded yet.")
    st.stop()

names = [r["name"] for r in menu_restaurants]
selected_name = st.selectbox("Pick a restaurant", names, label_visibility="collapsed",
                              placeholder="Choose a restaurant…")

restaurant = next((r for r in menu_restaurants if r["name"] == selected_name), None)
if not restaurant:
    st.stop()

menu_data = menus.get_menu(restaurant["id"])

# ── Header ──────────────────────────────────────────────────────────────────
col_info, col_link = st.columns([3, 1])
with col_info:
    meta_parts = []
    if restaurant.get("cuisine"):
        meta_parts.append(restaurant["cuisine"])
    if restaurant.get("rating"):
        meta_parts.append(f"★ {restaurant['rating']}")
    if restaurant.get("price"):
        meta_parts.append(restaurant["price"])
    if restaurant.get("address"):
        meta_parts.append(restaurant["address"])
    st.markdown(f"### {restaurant['name']}")
    if meta_parts:
        st.caption(" · ".join(meta_parts))

with col_link:
    menu_url = menu_data.get("menu_url", "") if menu_data else ""
    yelp_url = restaurant.get("yelp_url", "")
    if menu_url:
        st.markdown(
            f'<a href="{menu_url}" target="_blank" style="'
            f'display:inline-block;margin-top:18px;padding:8px 16px;'
            f'background:#D97757;color:#fff;border-radius:8px;'
            f'text-decoration:none;font-weight:600;font-size:13px;">'
            f'Order Online ↗</a>',
            unsafe_allow_html=True,
        )
    elif yelp_url:
        st.markdown(
            f'<a href="{yelp_url}" target="_blank" style="'
            f'display:inline-block;margin-top:18px;padding:8px 16px;'
            f'background:#D97757;color:#fff;border-radius:8px;'
            f'text-decoration:none;font-weight:600;font-size:13px;">'
            f'View on Yelp ↗</a>',
            unsafe_allow_html=True,
        )

st.divider()

# ── Menu categories ──────────────────────────────────────────────────────────
if not menu_data or not menu_data.get("categories"):
    st.info("No menu data available for this restaurant.")
    st.stop()

if not menu_data.get("prices_verified", False):
    st.warning("⚠️  Prices for this restaurant haven't been verified — they may be outdated.")

categories = menus.display_categories(menu_data)

if len(categories) <= 8:
    tabs = st.tabs([c["name"] for c in categories])
    for tab, cat in zip(tabs, categories):
        with tab:
            _render_category(cat)
else:
    for cat in categories:
        with st.expander(cat["name"], expanded=False):
            _render_category(cat)
