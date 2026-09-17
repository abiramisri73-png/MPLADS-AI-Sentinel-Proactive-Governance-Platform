"""
ui/projects.py
---------------
Full works ("projects") table with filters, plus a detail panel for a
selected work -- its full sub-score breakdown and rule-based risk reasons.
Deep-links into the AI Audit Assistant for a generated narrative summary.
"""

import streamlit as st

from utils.data_loader import get_scoped_projects
from utils.ui_helpers import risk_band_badge, style_risk_band_column


def render_projects() -> None:
    df = get_scoped_projects()
    st.markdown("## 📁 Projects")

    if df.empty:
        st.warning("No scored data found. Run `python3 main.py` first.")
        return

    # ---- Filters ----
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        sel_states = st.multiselect("State", sorted(df["state"].dropna().unique().tolist()) if "state" in df.columns else [])
    with f2:
        sel_types = st.multiselect("Work type", sorted(df["work_type"].dropna().unique().tolist()))
    with f3:
        sel_bands = st.multiselect("Risk band", ["Critical", "High", "Medium", "Low"])
    with f4:
        search = st.text_input("Search work ID / name")

    filtered = df.copy()
    if sel_states:
        filtered = filtered[filtered["state"].isin(sel_states)]
    if sel_types:
        filtered = filtered[filtered["work_type"].isin(sel_types)]
    if sel_bands:
        filtered = filtered[filtered["risk_band"].isin(sel_bands)]
    if search:
        s = search.lower()
        filtered = filtered[
            filtered["work_id"].astype(str).str.lower().str.contains(s) |
            filtered["work_name"].astype(str).str.lower().str.contains(s)
        ]

    st.caption(f"{len(filtered)} of {len(df)} works in scope match the current filters")

    display_cols = [c for c in [
        "work_id", "work_name", "state", "district", "work_type",
        "risk_score", "risk_band", "anomaly_score", "duplicate_risk_score",
    ] if c in filtered.columns]

    styled = (
        filtered[display_cols].sort_values("risk_score", ascending=False)
        .style.pipe(style_risk_band_column)
        .format({"risk_score": "{:.1f}"})
    )
    st.dataframe(styled, use_container_width=True, height=360)

    st.markdown("---")
    st.markdown("### Work detail")

    options = filtered.sort_values("risk_score", ascending=False)["work_id"].tolist()
    if not options:
        st.info("No works match the current filters.")
        return

    default_idx = 0
    if st.session_state.get("selected_project") in options:
        default_idx = options.index(st.session_state["selected_project"])

    chosen = st.selectbox("Select a work", options, index=default_idx)
    st.session_state["selected_project"] = chosen
    row = df[df["work_id"] == chosen].iloc[0]

    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.markdown(f"#### {row['work_id']} — {row.get('work_name','')}")
        st.markdown(risk_band_badge(row["risk_band"]), unsafe_allow_html=True)
        st.write("")
        st.write(f"**State / District:** {row.get('state','N/A')} / {row.get('district','N/A')}")
        st.write(f"**Work type:** {row.get('work_type','N/A')}")
        if "sanctioned_amount" in row and "expenditure" in row:
            st.write(f"**Sanctioned:** ₹{row['sanctioned_amount']:,.0f}  |  **Spent:** ₹{row['expenditure']:,.0f}")
        if "risk_reasons" in row and str(row["risk_reasons"]) not in ("nan", ""):
            st.markdown("**Rule-based risk reasons:**")
            st.info(str(row["risk_reasons"]))

    with c2:
        m1, m2 = st.columns(2)
        m1.metric("Risk score", f"{row['risk_score']:.1f}")
        m2.metric("Anomaly score", f"{row.get('anomaly_score', 0):.0f}")
        m3, m4 = st.columns(2)
        m3.metric("Duplicate risk", f"{row.get('duplicate_risk_score', 0):.0f}")
        m4.metric("Cost overrun", f"{row.get('cost_overrun_pct', 0):.0f}%" if "cost_overrun_pct" in row else "N/A")

        if st.button("🤖 Open in AI Audit Assistant", use_container_width=True):
            st.session_state["page"] = "AI Audit Assistant"
            st.session_state["assistant_prefill_work"] = chosen
            st.rerun()
