import streamlit as st

LABEL_COLORS = {
    "Paper": "#4C78A8",
    "Author": "#F58518",
    "Institution": "#54A24B",
    "Country": "#B279A2",
    "VenueEdition": "#E45756",
    "Task": "#72B7B2",
    "Method": "#EECA3B",
    "Dataset": "#9D755D",
}

THEME = {
    "title": "CV Trend Radar",
    "icon": "📡",
    "primary": "#4C78A8",
    "up": "#54A24B",
    "down": "#E45756",
    "neutral": "#9AA0A6",
    "label_colors": LABEL_COLORS,
    "default_node_color": "#BAB0AC",
    "edge_color": "#8A8F98",
}


def apply_theme(title=None):
    st.set_page_config(page_title=title or THEME["title"], page_icon=THEME["icon"], layout="wide")
