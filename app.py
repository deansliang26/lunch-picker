import streamlit as st
import db
import sidebar

db.init_db()

st.set_page_config(
    page_title="PA Lunch Picker",
    page_icon="🍜",
    layout="wide",
    initial_sidebar_state="expanded",
)

sidebar.render()

st.switch_page("pages/1_Today.py")
