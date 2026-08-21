import streamlit as st

from components import render_hero
from data_loader import load_css, load_opportunity_spaces
from views.opportunity import render_opportunity_detail
from views.radar import render_radar

import front_config as config

st.set_page_config(
    page_title="Orange Business Innovation Radar",
    page_icon="",
    layout="wide",
)

load_css(config.CSS_PATH)
render_hero()

opportunity_spaces = load_opportunity_spaces(config.DB_PATH)

if not opportunity_spaces:
    st.error("No opportunity spaces found.")
    st.stop()

pending_view = st.session_state.pop("pending_view", None)
if pending_view in ["Radar", "Opportunity detail"]:
    st.session_state["selected_view"] = pending_view

selected_view = st.sidebar.selectbox(
    "View",
    ["Radar", "Opportunity detail"],
    key="selected_view",
)

if selected_view == "Radar":
    render_radar(opportunity_spaces)
else:
    render_opportunity_detail(
        opportunity_spaces,
        selected_opportunity_id=st.session_state.get("selected_opportunity_id"),
    )
