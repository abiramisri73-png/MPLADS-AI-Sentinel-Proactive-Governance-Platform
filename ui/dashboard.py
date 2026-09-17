"""
ui/dashboard.py
----------------
Landing page: national/role-scoped KPI overview, risk-band distribution,
and a preview of the highest-priority alerts.
"""

import streamlit as st

from utils.data_loader import get_scoped_projects, get_scoped_alerts, load_duplicates
from utils.ui_helpers import render_kpi_row, risk_band_badge


def render_dashboard() -> None:
    df = get_scoped_projects()
    role = st.session_state.get("selected_role", "Ministry")

    st.markdown(f"## 🏠 Dashboard")
    st.caption(f"Scope: **{role}** &nbsp;•&nbsp; {len(df)} works in view")

    if df.empty:
        st.warning(
            "No scored data found for this view. Run `python3 main.py` to generate "
            "the scored dataset, or broaden the role scope."
        )
        return

    alerts = get_scoped_alerts()
    dup_df = load_duplicates()
    n_critical = int((df["risk_band"] == "Critical").sum())
    n_high = int((df["risk_band"] == "High").sum())
    total_sanctioned = df["sanctioned_amount"].sum() if "sanctioned_amount" in df.columns else 0

    n_anomalies = int(df["anomaly_flag"].sum()) if "anomaly_flag" in df.columns else 0

    render_kpi_row([
        {"label": "Total Works", "icon": "📁", "value": f"{len(df):,}", "sub": "in current scope"},
        {"label": "Critical Risk", "icon": "🔴", "value": n_critical, "sub": "immediate review", "alert": n_critical > 0},
        {"label": "High Risk", "icon": "🟠", "value": n_high, "sub": "priority review"},
        {"label": "Anomalies (ML)", "icon": "🧠", "value": n_anomalies, "sub": "Isolation Forest flags"},
        {"label": "Duplicate Pairs", "icon": "🧬", "value": len(dup_df), "sub": "possible overlap"},
    ])

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1.3])

    with left:
        st.markdown("### Risk band distribution")
        band_counts = df["risk_band"].value_counts().reindex(["Critical", "High", "Medium", "Low"]).fillna(0)
        st.bar_chart(band_counts)
        st.caption(f"Total sanctioned amount in scope: ₹{total_sanctioned/1e7:,.1f} Cr" if total_sanctioned else "")

    with right:
        st.markdown("### Highest-priority alerts")
        if alerts.empty:
            st.info("No Critical/High works in the current scope.")
        else:
            preview = alerts.head(6)
            for _, row in preview.iterrows():
                c1, c2 = st.columns([5, 1])
                with c1:
                    st.markdown(
                        f"**{row['work_id']}** — {row.get('work_name', '')}  \n"
                        f"<span style='font-size:0.8rem;color:#64748b'>{row.get('district','')}, {row.get('state','')}</span>",
                        unsafe_allow_html=True,
                    )
                with c2:
                    st.markdown(risk_band_badge(row["risk_band"]), unsafe_allow_html=True)
                    st.caption(f"{row['risk_score']:.0f}/100")
            if len(alerts) > 6:
                st.caption(f"+ {len(alerts) - 6} more in Risk Alerts tab")

    st.markdown("---")
    st.caption(
        "This overview reflects the last completed pipeline run. Re-run `python3 main.py` "
        "after new data arrives to refresh these numbers."
    )
