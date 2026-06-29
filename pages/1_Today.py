import math
import sys
import os
import time
import streamlit as st

OFFICE_LAT, OFFICE_LNG = 37.4076, -122.1459

def _drive_mins(lat, lng):
    if not lat or not lng:
        return None
    R = 3958.8
    p1, p2 = math.radians(OFFICE_LAT), math.radians(lat)
    dp, dl = math.radians(lat - OFFICE_LAT), math.radians(lng - OFFICE_LNG)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    miles = 2 * R * math.asin(math.sqrt(a))
    return max(1, round(miles * 2.5))

def _drive_time(lat, lng):
    mins = _drive_mins(lat, lng)
    return f"~{mins} min drive" if mins is not None else None

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
import yelp
import sidebar
import menus
import avatar

db.init_db()

from roster import TEAM
MAJORITY = math.ceil(len(TEAM) / 2)

_VEG_HINTS = (
    "salad", "mediterranean", "vegan", "vegetarian", "poke", "falafel",
    "hummus", "sweetgreen", "bowl", "healthy", "juice", "cafe", "greek",
)

def _is_veg_friendly(r: dict) -> bool:
    blob = f"{r.get('cuisine','')} {r.get('name','')}".lower()
    return any(h in blob for h in _VEG_HINTS)

def _reveal_card(name: str, final: bool = False) -> str:
    if final:
        border, bg, kicker, kicker_color = "#D97757", "#D9775718", "🏆 TODAY'S PICK", "#D97757"
    else:
        border, bg, kicker, kicker_color = "#DED9C7", "#F5F3EC", "🎲 DECIDING…", "#9C978C"
    return (
        f"<div style='border:2px solid {border};background:{bg};border-radius:16px;"
        f"padding:28px 24px;text-align:center;margin:8px 0;"
        f"box-shadow:0 4px 20px rgba(20,20,19,0.08);'>"
        f"<div style='font-family:var(--font-mono),monospace;font-size:12px;font-weight:700;"
        f"letter-spacing:2px;color:{kicker_color};margin-bottom:8px;'>{kicker}</div>"
        f"<div style='font-family:var(--font-serif),serif;font-size:34px;font-weight:700;"
        f"color:#141413;line-height:1.15;'>{name}</div>"
        f"</div>"
    )

def _run_reveal(suggestions: list, chosen_pid: str):
    """Roulette-style reveal: cycle the candidate names, ease out, land on the
    winner. Blocks ~2.5s — that's the whole point (the suspense)."""
    names = [r["name"] for r in suggestions] or ["Lunch"]
    chosen = next((r for r in suggestions if r["id"] == chosen_pid), None)
    chosen_name = chosen["name"] if chosen else "Lunch"
    placeholder = st.empty()
    spins = 22
    delay = 0.04
    for i in range(spins):
        placeholder.markdown(_reveal_card(names[i % len(names)]), unsafe_allow_html=True)
        time.sleep(delay)
        if i > spins // 2:
            delay *= 1.18  # ease out toward the end
    placeholder.markdown(_reveal_card(chosen_name, final=True), unsafe_allow_html=True)
    st.balloons()
    time.sleep(0.6)

st.set_page_config(page_title="Today's Lunch · PA", page_icon="🍜", layout="wide")

sidebar.render()

user = st.session_state.user
cuisine_alias = yelp.CUISINES.get(st.session_state.cuisine_filter)

# Celebrate a freshly-decided winner (set by the vote handler / decide button).
if st.session_state.pop("_celebrate", False):
    st.balloons()

# Confirm a reset kicked off by the organizer control in the header.
if st.session_state.pop("_reset_done", False):
    st.toast("Today's pick and votes were reset — vote away!", icon="🔄")

# --- Header ---
from datetime import date
today_label = date.today().strftime("%A, %B %-d")

col_title, col_date, col_admin = st.columns([7, 2, 1])
with col_title:
    st.markdown("## 🍽️  Where are we eating today?")
with col_date:
    st.markdown(
        f"<div style='text-align:right; padding-top:12px; color:#76726A; font-size:13px; font-weight:600;'>{today_label}</div>",
        unsafe_allow_html=True,
    )
with col_admin:
    # Organizer escape hatch. A locked-in winner — whether voted in or rolled by
    # "Decide for us now" — otherwise can't be undone in the app. Tucked behind a
    # popover so it's a deliberate, two-step action rather than a stray tap.
    with st.popover("⚙️", use_container_width=True, help="Organizer tools"):
        st.markdown("**Reset today's pick**")
        st.caption(
            "Clears today's locked-in winner **and** everyone's votes so the team "
            "can start over. Orders and past days are left untouched."
        )
        if st.button("↺  Reset today", type="primary", use_container_width=True, key="reset_today"):
            db.clear_todays_pick()
            st.session_state["_reset_done"] = True
            st.rerun()

# --- Check if winner already decided ---
winner_row = db.get_todays_winner()
winner = db.get_restaurant(winner_row["winner_place_id"]) if winner_row else None
if winner:
    meta = " · ".join(filter(None, [winner.get('cuisine'), winner.get('price'), f"★ {winner.get('rating')}" if winner.get('rating') else None]))
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #D9775715, #D9775708);
            border: 1.5px solid #D9775755;
            border-radius: 14px;
            padding: 16px 20px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 14px;
        ">
          <div style="font-size:28px;">🏆</div>
          <div style="flex:1;">
            <div style="font-weight:800; font-size:18px; color:#141413;">Today's pick: {winner['name']}</div>
            <div style="font-size:13px; color:#76726A; margin-top:2px;">{meta}</div>
          </div>
          <div style="display:flex; gap:8px;">
            <a href="{winner.get('yelp_url','#')}" target="_blank"
               style="background:#D97757; color:white; padding:8px 14px; border-radius:8px;
                      text-decoration:none; font-weight:600; font-size:13px;">Yelp ↗</a>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # Order CTA: use Streamlit's native page nav (a raw <a href="2_Orders"> hit the
    # wrong page slug and silently did nothing, esp. under a hosted base path).
    _, cta_col, _ = st.columns([1, 2, 1])
    with cta_col:
        st.page_link("pages/2_Orders.py", label="🧾  Place your order →", use_container_width=True)

# --- Load today's suggestions ---
with st.spinner("Loading restaurants..."):
    suggestions = yelp.get_suggestions(cuisine_filter=cuisine_alias)

if not suggestions:
    st.warning(
        "No restaurants loaded. Make sure your **YELP_API_KEY** is set in `.env` (locally) "
        "or as a Replit Secret."
    )
    st.stop()

# --- Vote tally fragment (auto-refreshes every 3s) ---
@st.fragment(run_every=3)
def vote_tally():
    votes = db.get_todays_votes()
    tally = {}
    for v in votes:
        tally[v["place_id"]] = tally.get(v["place_id"], 0) + 1

    voted_names = {v["voter"] for v in votes}
    voted_count = len(voted_names)
    not_voted = [t for t in TEAM if t not in voted_names]

    def _avatar_row(names: list[str], opacity: float = 1.0) -> str:
        chips = "".join(
            f'<div style="display:flex;align-items:center;gap:6px;opacity:{opacity};">'
            f'{avatar.html(n, size=26)}'
            f'<span style="font-size:12px;color:#34322E;font-weight:500;">{n}</span>'
            f'</div>'
            for n in names
        )
        return f'<div style="display:flex;flex-wrap:wrap;gap:10px;">{chips}</div>'

    st.markdown(
        f"<div style='font-size:13px; color:#76726A; margin-bottom:8px;'>"
        f"<span style='font-weight:700; color:#141413;'>{voted_count}/{len(TEAM)}</span> voted &nbsp;·&nbsp; "
        f"Need <span style='font-weight:700; color:#D97757;'>{MAJORITY}</span> for majority"
        f"</div>",
        unsafe_allow_html=True,
    )
    voted_list   = [t for t in TEAM if t in voted_names]
    col_v, col_w = st.columns(2)
    with col_v:
        if voted_list:
            st.markdown(_avatar_row(voted_list), unsafe_allow_html=True)
    with col_w:
        if not_voted:
            st.markdown(
                f'<div style="font-size:11px;color:#9C978C;margin-bottom:4px;">Waiting on</div>'
                f'{_avatar_row(not_voted, opacity=0.4)}',
                unsafe_allow_html=True,
            )

    if tally:
        for pid, count in sorted(tally.items(), key=lambda x: -x[1]):
            r = db.get_restaurant(pid)
            name = r["name"] if r else pid
            pct = int(count / len(TEAM) * 100)
            is_leader = count == max(tally.values())
            bar_color = "#D97757" if is_leader else "#9C978C"
            st.markdown(
                f"""<div style="margin-bottom:6px;">
                  <div style="display:flex; align-items:center; gap:10px; margin-bottom:3px;">
                    <span style="font-weight:{'700' if is_leader else '400'}; font-size:14px; color:#141413;">{name}</span>
                    <span style="font-size:13px; color:{bar_color}; font-weight:600;">{count} vote{'s' if count!=1 else ''}</span>
                  </div>
                  <div style="background:#F5F3EC; border-radius:99px; height:6px; width:100%;">
                    <div style="background:{bar_color}; border-radius:99px; height:6px; width:{pct}%;
                                transition:width 0.3s ease;"></div>
                  </div>
                </div>""",
                unsafe_allow_html=True,
            )

vote_tally()

# --- Decide-now CTA (resolves any state with ≥1 vote, incl. a full tie) ---
_decide_votes = db.get_todays_votes()
if not winner_row and _decide_votes:
    _n_voted = len({v["voter"] for v in _decide_votes})
    _, dc, _ = st.columns([1, 2, 1])
    with dc:
        if st.button("🎲  Decide for us now", use_container_width=True, type="primary", key="decide_now"):
            chosen_pid = db.pick_weighted_winner()
            if chosen_pid:
                _run_reveal(suggestions, chosen_pid)
                _final_tally = db.tally_votes()
                db.record_winner(chosen_pid, _final_tally.get(chosen_pid, 0), len(TEAM))
                st.session_state["_celebrate"] = True
                st.rerun()
        st.caption(
            f"Picks from the {_n_voted} vote{'s' if _n_voted != 1 else ''} so far — "
            "weighted by votes, but an underdog can still win 🍀"
        )

st.divider()

# --- Restaurant cards ---
cols = st.columns(2)
votes = db.get_todays_votes()
tally = {}
for v in votes:
    tally[v["place_id"]] = tally.get(v["place_id"], 0) + 1
user_vote = next((v["place_id"] for v in votes if v.get("voter") == user), None)
leader = max(tally, key=tally.get) if tally else None

# Detect 5-way tie: everyone voted but all for different spots
is_full_tie = (
    bool(tally)
    and sum(tally.values()) >= len(TEAM)
    and len(tally) >= len(TEAM)
    and max(tally.values()) == 1
)
if is_full_tie and not winner_row:
    st.warning("🤷 Dead heat — everyone picked a different spot. Hit **🎲 Decide for us now** above to settle it.")

# --- Quick filter chips (client-side; narrows the cards below) ---
# NB: a bare "$"/"$$" label renders as a LaTeX math block in Streamlit markdown
# (and shows blank), so the price chips use escaped labels mapped to a tag.
_PRICE_LABELS = {r"\$": "$", r"\$\$": "$$"}
_RATING_LABEL = "Top rated"
_FILTERS = list(_PRICE_LABELS) + ["Nearby", _RATING_LABEL, "Veg-friendly", "Has menu"]
_active = st.pills("Filter", _FILTERS, selection_mode="multi", key="today_filters", label_visibility="collapsed") or []
_price_sel = {_PRICE_LABELS[f] for f in _active if f in _PRICE_LABELS}

def _passes(r: dict) -> bool:
    if _price_sel:
        tag = {1: "$", 2: "$$"}.get(len((r.get("price") or "").strip()))
        if tag not in _price_sel:
            return False
    if "Nearby" in _active:
        m = _drive_mins(r.get("lat"), r.get("lng"))
        if m is None or m > 10:
            return False
    if _RATING_LABEL in _active and (r.get("rating") or 0) < 4.2:
        return False
    if "Veg-friendly" in _active and not _is_veg_friendly(r):
        return False
    if "Has menu" in _active:
        md = menus.get_menu(r["id"])
        if not (md and (md.get("categories") or md.get("menu_type") == "build")):
            return False
    return True

shown = [r for r in suggestions if _passes(r)] if _active else suggestions
if _active:
    st.caption(f"Showing {len(shown)} of {len(suggestions)} spots")
if not shown:
    st.info("No spots match these filters — clear a chip to see more.")

for i, r in enumerate(shown):
    col = cols[i % 2]
    with col:
        is_leader = r["id"] == leader
        is_my_vote = r["id"] == user_vote

        # Card styling via container
        container = st.container(border=True)
        with container:
            img_col, info_col = st.columns([1, 3])

            with img_col:
                if r.get("image_url"):
                    st.markdown(
                        f'<img src="{r["image_url"]}" onerror="this.style.display=\'none\'" '
                        'style="width:100%;aspect-ratio:1/1;'
                        'object-fit:cover;border-radius:8px;display:block;">',
                        unsafe_allow_html=True,
                    )

            with info_col:
                name_line = f"### {r['name']}"
                if is_leader:
                    name_line += " 🏆"
                st.markdown(name_line)

                meta_parts = []
                if r.get("cuisine"):
                    meta_parts.append(r["cuisine"])
                if r.get("rating"):
                    meta_parts.append(f"★ {r['rating']}")
                if r.get("price"):
                    meta_parts.append(r["price"])
                drive = _drive_time(r.get("lat"), r.get("lng"))
                if drive:
                    meta_parts.append(drive)
                st.caption(" · ".join(meta_parts))

                if r.get("address"):
                    st.caption(r["address"])

                # Vote / Withdraw are mutually exclusive, so they share one wide
                # action column — narrow columns made the labels wrap vertically.
                link_col, vote_count_col, action_col = st.columns([3, 2, 3])
                with link_col:
                    if r.get("yelp_url"):
                        st.markdown(f"[View on Yelp ↗]({r['yelp_url']})")
                with vote_count_col:
                    vote_count = tally.get(r["id"], 0)
                    if is_my_vote:
                        st.markdown("**✓ Your pick**")
                    elif vote_count:
                        st.caption(f"{vote_count} vote{'s' if vote_count > 1 else ''}")
                with action_col:
                    if not winner_row and user and not user_vote:
                        if st.button("Vote", key=f"vote_{r['id']}", use_container_width=True):
                            db.cast_vote(user, r["id"])
                            new_tally = db.tally_votes()
                            total_votes = sum(new_tally.values())

                            # Majority → instant win
                            winner_found = False
                            for pid, cnt in new_tally.items():
                                if cnt >= MAJORITY:
                                    db.record_winner(pid, cnt, len(TEAM))
                                    winner_found = True
                                    break

                            # All voted, no majority yet
                            if not winner_found and total_votes >= len(TEAM):
                                max_cnt = max(new_tally.values())
                                is_all_tied = (len(new_tally) >= len(TEAM) and max_cnt == 1)
                                if not is_all_tied:
                                    leaders = [pid for pid, cnt in new_tally.items() if cnt == max_cnt]
                                    winner_pid = max(
                                        leaders,
                                        key=lambda pid: (db.get_restaurant(pid) or {}).get("rating") or 0
                                    )
                                    db.record_winner(winner_pid, max_cnt, len(TEAM))
                                    winner_found = True

                            if winner_found:
                                st.session_state["_celebrate"] = True
                            st.rerun()
                    elif not winner_row and user and is_my_vote:
                        if st.button("Withdraw", key=f"withdraw_{r['id']}", use_container_width=True):
                            db.withdraw_vote(user)
                            st.rerun()

            # ── Inline menu preview (full-width below the image+info row) ──
            card_menu = menus.get_menu(r["id"])
            if card_menu and card_menu.get("categories"):
                with st.expander("📋 See menu"):
                    for cat in menus.display_categories(card_menu):
                        items_in_cat = cat.get("items", [])
                        if not items_in_cat:
                            continue
                        st.markdown(f"**{cat['name']}**")
                        for it in items_in_cat:
                            badge = "🔥 " if it.get("popular") else ""
                            price_str = f"  ·  ${it['price']:.2f}" if it.get("price") else ""
                            desc_str = f"<span style='font-size:12px;color:#76726A;display:block;'>{it['description']}</span>" if it.get("description") else ""
                            st.markdown(
                                f"<div style='padding:4px 0;border-bottom:1px solid #F5F3EC;'>"
                                f"<span style='font-weight:600;'>{badge}{it['name']}</span>"
                                f"<span style='color:#D97757;font-weight:600;'>{price_str}</span>"
                                f"{desc_str}</div>",
                                unsafe_allow_html=True,
                            )
                        st.markdown("<div style='margin:6px 0'></div>", unsafe_allow_html=True)
