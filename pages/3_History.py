import sys
import os
import streamlit as st
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
import yelp
import sidebar

db.init_db()

from roster import TEAM

st.set_page_config(page_title="History · PA Lunch", page_icon="🍜", layout="wide")

sidebar.render()

st.markdown("## 📅  Past Lunches")

history = db.get_history(limit=60)

if not history:
    st.info("No lunch history yet — come back after the first vote!")
    st.stop()

for entry in history:
    # Format date nicely
    try:
        d = datetime.strptime(entry["date"], "%Y-%m-%d")
        date_label = d.strftime("%A, %B %-d, %Y")
    except Exception:
        date_label = entry["date"]

    orders_count = db.orders_count_for_date(entry["date"])
    votes_label = f"{entry['vote_count']}/{entry['total_voters']} votes"
    orders_label = f"{orders_count}/{len(TEAM)} orders"

    meta_parts = []
    if entry.get("cuisine"):
        meta_parts.append(entry["cuisine"])
    if entry.get("rating"):
        meta_parts.append(f"★ {entry['rating']}")
    if entry.get("price"):
        meta_parts.append(entry["price"])

    with st.expander(f"**{date_label}** — {entry['name']}  ·  {votes_label}  ·  {orders_label}"):
        cols = st.columns([3, 1])
        with cols[0]:
            st.markdown(f"### {entry['name']}")
            if meta_parts:
                st.caption(" · ".join(meta_parts))
            if entry.get("yelp_url"):
                st.markdown(f"[View on Yelp ↗]({entry['yelp_url']})")

        with cols[1]:
            st.metric("Votes", votes_label)
            st.metric("Orders", orders_label)

        # Order list for that day
        day_orders = db.get_history_orders(entry["date"])
        if day_orders:
            st.divider()
            st.subheader("What everyone got")
            for o in day_orders:
                try:
                    t = datetime.fromisoformat(o["updated_at"]).strftime("%-I:%M %p")
                except Exception:
                    t = ""
                st.markdown(f"**{o['person']}** — {o['order_text']} <span style='color:gray;font-size:0.8em'>{t}</span>", unsafe_allow_html=True)
        else:
            st.caption("No orders recorded for this day.")
