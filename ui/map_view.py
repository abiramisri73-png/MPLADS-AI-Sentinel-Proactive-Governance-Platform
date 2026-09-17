"""
ui/map_view.py
---------------
Geographic view of works, colored by risk band, using pydeck (no external
tile API key required — pydeck's default basemap works out of the box).
"""

import pandas as pd
import pydeck as pdk
import streamlit as st

from utils.config import RISK_BAND_COLORS
from utils.data_loader import get_scoped_projects


def _hex_to_rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    return [int(hex_color[i:i + 2], 16) for i in (0, 2, 4)]


def render_map_view() -> None:
    df = get_scoped_projects()
    st.markdown("## 🗺️ Map View")

    if df.empty or "lat" not in df.columns or "lon" not in df.columns:
        st.warning("No geolocated works found in the current scope.")
        return

    sel_bands = st.multiselect("Show risk bands", ["Critical", "High", "Medium", "Low"],
                                default=["Critical", "High", "Medium", "Low"])
    plot_df = df[df["risk_band"].isin(sel_bands)].dropna(subset=["lat", "lon"]).copy()

    if plot_df.empty:
        st.info("No works match the selected bands.")
        return

    plot_df["color"] = plot_df["risk_band"].map(lambda b: _hex_to_rgb(RISK_BAND_COLORS.get(b, "#64748b")))
    plot_df["radius"] = plot_df["risk_score"].clip(lower=10) * 300

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=plot_df,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.65,
        stroked=True,
        get_line_color=[255, 255, 255],
        line_width_min_pixels=1,
    )

    view_state = pdk.ViewState(
        latitude=float(plot_df["lat"].mean()),
        longitude=float(plot_df["lon"].mean()),
        zoom=4.2,
        pitch=0,
    )

    tooltip = {
        "html": "<b>{work_id}</b><br/>{work_name}<br/>{district}, {state}<br/>"
                "Risk: {risk_score} ({risk_band})",
        "style": {"backgroundColor": "#1e1b4b", "color": "white"},
    }

    st.pydeck_chart(pdk.Deck(
        layers=[layer], initial_view_state=view_state, tooltip=tooltip,
        map_style="road",
    ))

    legend_html = " &nbsp; ".join(
        f'<span style="color:{color}">●</span> {band}'
        for band, color in RISK_BAND_COLORS.items()
    )
    st.markdown(legend_html, unsafe_allow_html=True)
    st.caption(f"{len(plot_df)} works plotted. Marker size scales with risk score.")
