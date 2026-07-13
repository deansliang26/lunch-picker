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

# ── Running tab: over-budget amounts that accumulate per person ───────────────
ledger = db.get_ledger()
owed = {p: d for p, d in ledger.items() if d["owed"] > 0}
if owed:
    total_owed = sum(d["owed"] for d in owed.values())
    st.markdown("### 💸  Running tab")
    st.caption(
        f"The company covers ${db.DAILY_BUDGET:.0f}/person each day. Anything over that "
        "accumulates here and stays on the tab until it's settled — under-budget "
        "days never reduce a balance."
    )
    chips = "".join(
        '<div style="background:#FFFFFF;border:1px solid #DED9C7;border-radius:12px;'
        'padding:10px 16px;min-width:104px;">'
        f'<div style="font-size:12px;color:#76726A;">{person}</div>'
        '<div style="font-size:20px;font-weight:800;color:#A8492A;'
        f'font-family:monospace;">${d["owed"]:.2f}</div></div>'
        for person, d in sorted(owed.items(), key=lambda x: -x[1]["owed"])
    )
    chips += (
        '<div style="background:#F8EBE4;border:1px solid #F2D8CD;border-radius:12px;'
        'padding:10px 16px;min-width:104px;">'
        '<div style="font-size:12px;color:#76726A;">Total owed</div>'
        '<div style="font-size:20px;font-weight:800;color:#141413;'
        f'font-family:monospace;">${total_owed:.2f}</div></div>'
    )
    st.markdown(
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px;">{chips}</div>',
        unsafe_allow_html=True,
    )
    with st.expander("Breakdown by day"):
        for person, d in sorted(owed.items(), key=lambda x: -x[1]["owed"]):
            st.markdown(f"**{person}** — owes ${d['owed']:.2f}")
            for day in d["days"]:
                st.caption(
                    f"• {day['date']}:  ${day['total']:.2f} order  →  "
                    f"${day['overage']:.2f} over budget"
                )
    st.divider()

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
