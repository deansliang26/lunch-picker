# status.py — shared "keep the group moving" banner: vote/order progress,
# who we're waiting on, and an order-cutoff countdown.
import streamlit as st
from datetime import datetime, date, time

import db

TEAM = ["Dean", "Evan", "Parth", "Cooper", "Aaron"]
DEFAULT_CUTOFF = time(12, 0)  # noon; the orderer can change it inline


def _ordered_set() -> set:
    """People who have a real (non-empty) order today."""
    ordered = set()
    for o in db.get_todays_orders():
        txt = (o.get("order_text") or "").strip()
        if txt and txt not in ("[]", "null"):
            ordered.add(o["person"])
    return ordered


def _bar(label: str, done_names: list, icon: str) -> str:
    done = [t for t in TEAM if t in done_names]
    waiting = [t for t in TEAM if t not in done_names]
    pct = int(len(done) / len(TEAM) * 100) if TEAM else 0
    color = "#D97757" if not waiting else ("#f59e0b" if done else "#9C978C")
    waiting_str = (
        f"<span style='color:#b45309;'>waiting on {', '.join(waiting)}</span>"
        if waiting else "<span style='color:#3F7355;'>everyone's in 🎉</span>"
    )
    return (
        f"<div style='margin-bottom:8px;'>"
        f"<div style='display:flex;justify-content:space-between;font-size:13px;font-weight:600;margin-bottom:3px;'>"
        f"<span style='color:#141413;'>{icon} {label} — {len(done)}/{len(TEAM)}</span>{waiting_str}</div>"
        f"<div style='background:#F5F3EC;border-radius:99px;height:7px;'>"
        f"<div style='background:{color};border-radius:99px;height:7px;width:{pct}%;transition:width .3s;'></div>"
        f"</div></div>"
    )


def _countdown_html() -> str:
    cutoff = st.session_state.get("order_cutoff", DEFAULT_CUTOFF)
    try:
        deadline = datetime.combine(date.today(), cutoff)
        delta = (deadline - datetime.now()).total_seconds()
    except Exception:
        return ""
    if delta > 0:
        h, m = int(delta // 3600), int((delta % 3600) // 60)
        left = f"{h}h {m}m" if h else f"{m}m"
        tone = "#A53F31" if delta < 600 else "#141413"
        return (f"<div style='font-size:13px;font-weight:700;color:{tone};margin-top:4px;'>"
                f"⏰ Orders close in {left} (by {cutoff.strftime('%-I:%M %p')})</div>")
    return ("<div style='font-size:13px;font-weight:700;color:#76726A;margin-top:4px;'>"
            f"⏰ Order window closed ({cutoff.strftime('%-I:%M %p')})</div>")


@st.fragment(run_every=15)
def render_team_status():
    """Live banner: voting + ordering progress, who we're waiting on, countdown."""
    if "order_cutoff" not in st.session_state:
        st.session_state["order_cutoff"] = DEFAULT_CUTOFF

    voted = [v["voter"] for v in db.get_todays_votes()]
    ordered = list(_ordered_set())

    with st.container(border=True):
        st.markdown(
            "<div style='font-weight:800;font-size:15px;color:#141413;margin-bottom:8px;'>"
            "👥 Team status</div>"
            + _bar("Voted", voted, "🗳️")
            + _bar("Ordered", ordered, "🧾")
            + _countdown_html(),
            unsafe_allow_html=True,
        )
        with st.popover("⏰ Set order cutoff", use_container_width=False):
            new_cut = st.time_input("Orders close at", value=st.session_state["order_cutoff"])
            if new_cut != st.session_state["order_cutoff"]:
                st.session_state["order_cutoff"] = new_cut
                st.rerun()
