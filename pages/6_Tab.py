import sys
import os
import json
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
import sidebar
import avatar

db.init_db()

from roster import TEAM
BUDGET = 20.00   # company covers this much per person per day; the rest is "the tab"

# Manual baseline adjustments: positive for orders that never got logged in the
# app, negative for one-time payments/credits made outside the app. Added on
# top of each person's computed over-budget total. Edit as needed.
MANUAL_ADJUSTMENTS = {
    "Parth": 1.75 - 17.59,  # +1.75 unlogged order, then a $17.59 one-time payment received
    "Cooper": 3.50,
}

st.set_page_config(page_title="The Tab · PA Lunch", page_icon="💸", layout="wide")
sidebar.render()


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


# ── Header ──
st.markdown("## 💸  The Tab")
st.caption(
    f"How much each person has gone over the **${BUDGET:.0f}/day** company budget, "
    "added up over time. The company covers the first "
    f"${BUDGET:.0f} of each order — anything above that lands on your tab."
)

# ── Crunch every order into per-day overage, then accumulate ──
# per_date_person[date][person] = that day's over-budget amount (>= 0)
per_date_person: dict[str, dict[str, float]] = {}
for o in db.get_all_orders():
    items = parse_items(o.get("order_text", ""))
    over = max(0.0, subtotal(items) - BUDGET)
    per_date_person.setdefault(o["date"], {})[o["person"]] = over

dates_sorted = sorted(per_date_person.keys())

if not dates_sorted and not any(MANUAL_ADJUSTMENTS.values()):
    st.info("No orders on record yet — once people start ordering, their tabs show up here.")
    st.stop()

# Seed each running tab with its manual adjustment (unlogged orders), then add
# each day's over-budget amount on top.
running = {p: float(MANUAL_ADJUSTMENTS.get(p, 0.0)) for p in TEAM}
timeline_rows = []
for d in dates_sorted:
    for p in TEAM:
        running[p] += per_date_person[d].get(p, 0.0)
    timeline_rows.append({p: round(running[p], 2) for p in TEAM})

totals = dict(running)  # final cumulative over-budget per person
days_over = {p: sum(1 for d in dates_sorted if per_date_person[d].get(p, 0.0) > 0) for p in TEAM}
grand_total = sum(totals.values())

# ── Leaderboard (who owes the most, top of the list) ──
ranked = sorted(TEAM, key=lambda p: totals[p], reverse=True)

_adj_note = " &nbsp;·&nbsp; incl. manual adjustments" if any(MANUAL_ADJUSTMENTS.values()) else ""
st.markdown(
    f"<div style='font-size:13px;color:#76726A;margin:8px 0 4px;'>"
    f"Across <strong>{len(dates_sorted)}</strong> lunch day{'s' if len(dates_sorted) != 1 else ''} "
    f"&nbsp;·&nbsp; total over budget: <strong style='color:#A53F31;'>${grand_total:.2f}</strong>{_adj_note}</div>",
    unsafe_allow_html=True,
)

for rank, person in enumerate(ranked, start=1):
    owed = totals[person]
    if owed > 0:
        over_color = "#A53F31"
        amount_txt = f"${owed:.2f}"
    elif owed < 0:
        over_color = "#3F7355"
        amount_txt = f"-${abs(owed):.2f}"
    else:
        over_color = "#3F7355"
        amount_txt = "$0.00 ✓"
    if days_over[person]:
        days_txt = f"over budget {days_over[person]} day{'s' if days_over[person] != 1 else ''}"
    elif MANUAL_ADJUSTMENTS.get(person, 0) > 0:
        days_txt = "unlogged orders"
    elif MANUAL_ADJUSTMENTS.get(person, 0) < 0:
        days_txt = "credit on file"
    else:
        days_txt = "always under budget"
    with st.container(border=True):
        c_av, c_name, c_amt = st.columns([1, 5, 3])
        with c_av:
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:8px;'>"
                f"<span style='font-family:var(--font-mono),monospace;color:#9C978C;"
                f"font-weight:700;font-size:14px;'>{rank}</span>"
                f"{avatar.html(person, size=36)}</div>",
                unsafe_allow_html=True,
            )
        with c_name:
            st.markdown(
                f"<div style='padding-top:6px;'>"
                f"<span style='font-weight:800;font-size:17px;color:#141413;'>{person}</span><br>"
                f"<span style='font-size:12px;color:#76726A;'>{days_txt}</span></div>",
                unsafe_allow_html=True,
            )
        with c_amt:
            st.markdown(
                f"<div style='text-align:right;padding-top:10px;font-family:var(--font-mono),monospace;"
                f"font-weight:700;font-size:20px;color:{over_color};'>{amount_txt}</div>",
                unsafe_allow_html=True,
            )

# ── Cumulative-over-time chart ──
st.divider()
st.markdown("##### 📈  Running tab over time")
if dates_sorted and grand_total > 0:
    df = pd.DataFrame(timeline_rows, index=pd.to_datetime(dates_sorted))
    df.index.name = "Date"
    st.line_chart(df, y_label="Cumulative over budget ($)")
    st.caption("Each line is one person's tab adding up across lunch days.")
elif grand_total > 0:
    st.caption("Tabs above are from manually-recorded unlogged orders — no per-day order history yet to chart.")
else:
    st.success("🎉  Nobody's gone over budget yet — the company's covered every order in full.")
