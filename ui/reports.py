"""
ui/reports.py
--------------
Pre-generated batch reports: the top-N highest-risk works and top-N
riskiest districts, as produced by `audit_engine.batch_generate_summaries`
during the main.py run — plus raw data exports.
"""

import json

import streamlit as st

from utils.data_loader import get_scoped_projects, get_scoped_alerts, load_audit_summaries


def render_reports() -> None:
    st.markdown("## 📄 Reports")

    tab1, tab2, tab3 = st.tabs(["Batch Audit Summaries", "Alert Export", "Full Dataset Export"])

    with tab1:
        work_summaries = load_audit_summaries("works")
        district_summaries = load_audit_summaries("districts")

        if not work_summaries and not district_summaries:
            st.info(
                "No batch summaries found. These are generated automatically by "
                "`python3 main.py` for the top 20 highest-risk works and top 5 riskiest districts."
            )
        else:
            st.markdown(f"#### Top {len(work_summaries)} highest-risk works")
            for item in work_summaries:
                with st.expander(f"{item['work_id']} — {item.get('work_name','')} ({item.get('risk_band','')}, {item.get('risk_score',0):.0f}/100)"):
                    st.markdown(item["summary"])

            st.markdown(f"#### Top {len(district_summaries)} riskiest districts")
            for item in district_summaries:
                with st.expander(f"{item['district']} — avg risk {item.get('avg_risk_score',0):.0f}/100 ({item.get('n_works',0)} works)"):
                    st.markdown(item["summary"])

            st.download_button(
                "⬇ Download work summaries (JSON)",
                json.dumps(work_summaries, indent=2, default=str),
                "audit_summaries_works.json", "application/json",
            )
            st.download_button(
                "⬇ Download district summaries (JSON)",
                json.dumps(district_summaries, indent=2, default=str),
                "audit_summaries_districts.json", "application/json",
            )

    with tab2:
        alerts = get_scoped_alerts()
        if alerts.empty:
            st.success("No Critical/High alerts in the current scope.")
        else:
            st.dataframe(alerts, use_container_width=True, height=420)
            st.download_button(
                "⬇ Download alerts (CSV)",
                alerts.to_csv(index=False).encode("utf-8"),
                "alerts_export.csv", "text/csv",
            )

    with tab3:
        df = get_scoped_projects()
        if df.empty:
            st.warning("No scored data found.")
        else:
            st.caption(f"{len(df)} works in current scope")
            st.dataframe(df, use_container_width=True, height=420)
            st.download_button(
                "⬇ Download full scored dataset (CSV)",
                df.to_csv(index=False).encode("utf-8"),
                "scored_dataset_export.csv", "text/csv",
            )
