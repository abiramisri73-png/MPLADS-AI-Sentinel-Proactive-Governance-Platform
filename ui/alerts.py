"""
ui/alerts.py
------------
The actionable alert feed: Critical/High works only, with rule-based reasons,
filterable and exportable.
"""

import streamlit as st

from utils.data_loader import get_scoped_alerts
from utils.ui_helpers import style_risk_band_column


def render_alerts() -> None:
    alerts = get_scoped_alerts()
    st.markdown("## 🔔 Risk Alerts")
    st.caption("Critical and High band works only — the actionable review queue.")

    if alerts.empty:
        st.success("No Critical/High risk works in the current scope. 🎉")
        return

    f1, f2 = st.columns(2)
    with f1:
        sel_band = st.multiselect("Band", ["Critical", "High"], default=["Critical", "High"])
    with f2:
        sel_state = st.multiselect("State", sorted(alerts["state"].dropna().unique().tolist()) if "state" in alerts.columns else [])

    filtered = alerts[alerts["risk_band"].isin(sel_band)] if sel_band else alerts
    if sel_state:
        filtered = filtered[filtered["state"].isin(sel_state)]

    st.caption(f"{len(filtered)} alert(s)")

    display_cols = [c for c in [
        "work_id", "work_name", "state", "district", "work_type",
        "risk_score", "risk_band", "risk_reasons",
    ] if c in filtered.columns]

    styled = (
        filtered[display_cols].sort_values("risk_score", ascending=False)
        .style.pipe(style_risk_band_column)
        .format({"risk_score": "{:.1f}"})
    )
    st.dataframe(styled, use_container_width=True, height=520)

    csv = filtered[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Download alerts as CSV", csv, "risk_alerts.csv", "text/csv")
