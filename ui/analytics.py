"""
ui/analytics.py
----------------
System-wide analytics: what's driving risk, how the supervised model
performed (if trained), and distribution views across the portfolio.
"""

import streamlit as st

from utils.data_loader import (
    get_scoped_projects, load_risk_drivers, load_model_comparison,
    load_feature_importance, load_duplicates,
)


def render_analytics() -> None:
    df = get_scoped_projects()
    st.markdown("## 📊 Analytics")

    if df.empty:
        st.warning("No scored data found. Run `python3 main.py` first.")
        return

    tab1, tab2, tab3 = st.tabs(["Risk Drivers", "Model Performance", "Distributions"])

    with tab1:
        drivers_df = load_risk_drivers()
        if drivers_df.empty:
            st.info("No top_risk_drivers.csv found.")
        else:
            st.markdown("#### What's driving risk system-wide")
            st.bar_chart(drivers_df.set_index("risk_driver")["correlation_with_final_risk_score"])
            st.dataframe(drivers_df, use_container_width=True)

        fi_df = load_feature_importance()
        if not fi_df.empty:
            st.markdown("#### Supervised model feature importance")
            st.bar_chart(fi_df.set_index("feature")["importance_pct"])

    with tab2:
        comp_df = load_model_comparison()
        if comp_df.empty:
            st.info(
                "No supervised model was trained — this appears only when the input data "
                "includes a confirmed fraud-label column."
            )
        else:
            st.markdown("#### Random Forest vs XGBoost vs LightGBM")
            chart_df = comp_df.set_index("model")[["roc_auc", "pr_auc", "cv_pr_auc_mean"]]
            st.bar_chart(chart_df)
            st.dataframe(comp_df, use_container_width=True)
            best = comp_df.sort_values("cv_pr_auc_mean", ascending=False).iloc[0]
            st.success(
                f"**{best['model']}** selected for production — cross-validated PR-AUC "
                f"{best['cv_pr_auc_mean']:.3f} (±{best['cv_pr_auc_std']:.3f})."
            )

    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Risk score distribution")
            st.bar_chart(df["risk_score"].value_counts(bins=10).sort_index())
        with c2:
            st.markdown("#### Works by type")
            st.bar_chart(df["work_type"].value_counts())

        dup_df = load_duplicates()
        if not dup_df.empty:
            st.markdown("#### Top duplicate/overlapping work pairs")
            st.dataframe(
                dup_df.sort_values("duplicate_risk_score", ascending=False).head(20),
                use_container_width=True,
            )
