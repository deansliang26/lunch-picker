import streamlit as st
import db
import yelp
import avatar

from roster import TEAM

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:wght@400;500;600;700&family=Hanken+Grotesk:wght@400;500;600;700;800&family=Spline+Sans+Mono:wght@400;500;600;700&display=swap');

/* ── Proposal-agent design tokens ── */
:root {
    --font-serif: 'Newsreader', Georgia, serif;
    --font-sans:  'Hanken Grotesk', system-ui, sans-serif;
    --font-mono:  'Spline Sans Mono', 'SF Mono', monospace;
    --clay-500: #D97757;
    --clay-600: #BD5D3A;
    --text-strong: #141413;
    --text-body: #34322E;
    --text-muted: #76726A;
    --border-default: #DED9C7;
    --surface-sunken: #F5F3EC;
}

/* ── Hide Streamlit chrome ── */
#MainMenu { display: none !important; }
header[data-testid="stHeader"] { display: none !important; }
footer { display: none !important; }
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stSidebarNavItems"] { display: none !important; }
[data-testid="stSidebarNavLink"] { display: none !important; }
[data-testid="stSidebarNavSeparator"] { display: none !important; }
[data-testid="stSidebarHeader"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }

/* ── Custom fixed top bar ── */
.pa-topbar {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 56px;
    background: #ffffff;
    border-bottom: 1px solid #DED9C7;
    display: flex;
    align-items: center;
    padding: 0 24px;
    gap: 14px;
    z-index: 999999;
    box-shadow: 0 1px 6px rgba(20,20,19,0.06);
}
.pa-topbar-icon {
    background: linear-gradient(135deg, #D97757, #BD5D3A);
    border-radius: 9px;
    width: 34px; height: 34px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; flex-shrink: 0;
    box-shadow: 0 2px 6px rgba(217,119,87,0.3);
}
.pa-topbar-text-main {
    font-weight: 800; font-size: 15px; color: #141413; line-height: 1.2;
}
.pa-topbar-text-sub {
    font-size: 11px; color: #D97757; font-weight: 700;
    letter-spacing: 1px; line-height: 1.3;
}

/* ── Push page content below fixed bar ── */
.main .block-container {
    padding-top: 72px !important;
}
section[data-testid="stSidebar"] > div:first-child {
    padding-top: 68px !important;
}

/* ── Global typography ── */
html, body, [class*="css"], .stApp, .main, input, textarea, select, button {
    font-family: var(--font-sans) !important;
}
.pa-topbar-text-main { font-family: var(--font-serif) !important; }
h1, h2, h3, h4 {
    font-family: var(--font-serif) !important;
    color: var(--text-strong);
}
h1 { font-weight: 700 !important; letter-spacing: -0.5px; }
h2 { font-weight: 600 !important; }
h3 { font-weight: 600 !important; }
/* Mono for labels, prices, data, code */
.stCodeBlock, code, pre, [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
    font-family: var(--font-mono) !important;
}

/* ── Restaurant cards ── */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px !important;
    box-shadow: 0 2px 12px rgba(20,20,19,0.07) !important;
    border: 1px solid #DED9C7 !important;
    overflow: hidden;
    transition: box-shadow 0.15s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 4px 20px rgba(20,20,19,0.12) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    background-color: #F5F3EC;
    border-radius: 10px;
    padding: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 6px 14px;
    font-weight: 500;
}
.stTabs [aria-selected="true"] {
    background-color: #ffffff !important;
    box-shadow: 0 1px 4px rgba(20,20,19,0.1) !important;
}

/* ── Buttons ── */
button[kind="primary"] {
    border-radius: 8px !important;
    font-weight: 600 !important;
}
button[kind="secondary"] {
    border-radius: 8px !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background-color: #ffffff;
    border-right: 1px solid #DED9C7;
}

/* ── Sidebar nav links ── */
.pa-nav a {
    display: block;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    color: #141413;
    text-decoration: none;
    margin-bottom: 2px;
    transition: background 0.1s;
}
.pa-nav a:hover { background: #F5F3EC; }
.pa-nav a.active {
    background: #D9775718;
    color: #D97757;
    font-weight: 700;
}

/* ── Expanders ── */
div[data-testid="stExpander"] {
    border-radius: 10px !important;
    border: 1px solid #DED9C7 !important;
}

/* ── Divider ── */
hr { border-color: #F5F3EC !important; }

/* ── Code block (order doc) ── */
.stCodeBlock { border-radius: 10px !important; }

/* ── Metric cards ── */
div[data-testid="stMetric"] {
    background: #F5F3EC;
    border-radius: 10px;
    padding: 12px 16px;
    border: 1px solid #DED9C7;
}
</style>
"""

_TOPBAR = """
<div class="pa-topbar">
  <div class="pa-topbar-icon">🍜</div>
  <div>
    <div class="pa-topbar-text-main">Pareto Agent</div>
    <div class="pa-topbar-text-sub">LUNCHES</div>
  </div>
</div>
"""


def _render_user_gate():
    """Full-screen 'who are you?' picker shown before any page content when no
    user is selected. Renders in the main area (the sidebar is already drawn)."""
    st.markdown(
        "<div style='text-align:center;max-width:560px;margin:7vh auto 0;'>"
        "<div style='font-size:46px;'>🍜</div>"
        "<div style='font-family:var(--font-serif),serif;font-size:30px;font-weight:700;"
        "color:#141413;margin-top:6px;'>Welcome to PA Lunch</div>"
        "<div style='color:#76726A;font-size:15px;margin-top:6px;'>"
        "Pick your name to start voting on today's lunch.</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 3, 1])
    with mid:
        cols = st.columns(len(TEAM))
        for i, name in enumerate(TEAM):
            with cols[i]:
                st.markdown(
                    "<div style='display:flex;justify-content:center;margin-bottom:8px;'>"
                    f"{avatar.html(name, size=54)}</div>",
                    unsafe_allow_html=True,
                )
                if st.button(name, key=f"gate_pick_{name}", use_container_width=True):
                    st.session_state.user = name
                    st.query_params["user"] = name
                    st.rerun()


def render():
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(_TOPBAR, unsafe_allow_html=True)

    with st.sidebar:
        # ── Navigation ──
        st.page_link("pages/1_Today.py",        label="🗳️  Vote",           use_container_width=True)
        st.page_link("pages/2_Orders.py",       label="🧾  Orders",         use_container_width=True)
        st.page_link("pages/4_Order_Station.py",label="📋  Order Station",  use_container_width=True)
        st.page_link("pages/5_Menus.py",        label="🍽️  Menus",          use_container_width=True)
        st.page_link("pages/3_History.py",      label="📅  History",        use_container_width=True)

        st.divider()

        if "user" not in st.session_state:
            param = st.query_params.get("user")
            st.session_state.user = param if param in TEAM else None

        options = ["— pick your name —"] + TEAM
        current_idx = options.index(st.session_state.user) if st.session_state.user in options else 0
        selected = st.selectbox("Who are you?", options, index=current_idx)
        st.session_state.user = selected if selected != "— pick your name —" else None

        if st.session_state.user:
            st.query_params["user"] = st.session_state.user
        elif "user" in st.query_params:
            del st.query_params["user"]

        if st.session_state.user:
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;margin-top:4px;">'
                f'{avatar.html(st.session_state.user, size=32)}'
                f'<span style="font-weight:600;font-size:14px;color:#141413;">{st.session_state.user}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        if "cuisine_filter" not in st.session_state:
            st.session_state.cuisine_filter = "All"
        st.session_state.cuisine_filter = st.selectbox(
            "Cuisine", list(yelp.CUISINES.keys()),
            index=list(yelp.CUISINES.keys()).index(st.session_state.cuisine_filter),
        )

        st.divider()

        with st.expander("➕ Add a restaurant"):
            with st.form("add_restaurant_form", clear_on_submit=True):
                name = st.text_input("Name *", placeholder="e.g. Evvia Estiatorio")
                cuisine = st.text_input("Cuisine *", placeholder="e.g. Greek")
                address = st.text_input("Address", placeholder="e.g. 420 Emerson St, Palo Alto")
                price = st.selectbox("Price", ["", "$", "$$", "$$$", "$$$$"])
                yelp_url = st.text_input("Yelp / website URL", placeholder="https://...")
                submitted = st.form_submit_button("Add")
                if submitted:
                    if name.strip() and cuisine.strip():
                        db.add_custom_restaurant(
                            name=name.strip(),
                            cuisine=cuisine.strip(),
                            address=address.strip(),
                            price=price,
                            yelp_url=yelp_url.strip(),
                        )
                        st.success(f"Added {name}!")
                    else:
                        st.warning("Name and Cuisine are required.")

        st.caption("Pareto Agent · Palo Alto")

    # Gate: nobody gets past this until they've picked who they are.
    if not st.session_state.user:
        _render_user_gate()
        st.stop()
