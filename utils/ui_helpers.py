"""
utils/ui_helpers.py
--------------------
Small rendering helpers shared by more than one ui/ page, so the KPI card
markup and risk-band styling stay identical everywhere they appear instead
of drifting between pages.
"""

import streamlit as st
from utils.config import RISK_BAND_COLORS, RISK_BAND_BG


def kpi_card(label: str, value, sub: str = "", icon: str = "", alert: bool = False) -> str:
    css_class = "kpi-card kpi-card--alert" if alert else "kpi-card"
    return f"""
<div class="{css_class}">
  <div class="kpi-icon">{icon}</div>
  <div class="kpi-label">{label}</div>
  <div class="kpi-value">{value}</div>
  <div class="kpi-sub">{sub}</div>
</div>
"""


def render_kpi_row(cards: list) -> None:
    """cards: list of dicts with keys label, value, sub, icon, alert (all but label/value optional)."""
    cols = st.columns(len(cards))
    for col, card in zip(cols, cards):
        with col:
            st.markdown(
                kpi_card(
                    card["label"], card["value"],
                    card.get("sub", ""), card.get("icon", ""), card.get("alert", False),
                ),
                unsafe_allow_html=True,
            )


def risk_band_badge(band: str) -> str:
    color = RISK_BAND_COLORS.get(band, "#64748b")
    bg = RISK_BAND_BG.get(band, "#f1f5f9")
    return (
        f'<span style="background:{bg};color:{color};padding:2px 10px;'
        f'border-radius:999px;font-size:0.78rem;font-weight:700">{band}</span>'
    )


def style_risk_band_column(styler, band_col: str = "risk_band"):
    """Apply background colors to a risk_band column in a pandas Styler."""
    def _color(val):
        return f"background-color:{RISK_BAND_BG.get(val, '')}"
    # pandas >=2.1 renamed Styler.applymap -> Styler.map; support both.
    map_fn = getattr(styler, "map", None) or styler.applymap
    return map_fn(_color, subset=[band_col])
