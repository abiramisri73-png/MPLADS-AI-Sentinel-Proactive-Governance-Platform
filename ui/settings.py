"""
ui/settings.py
---------------
Housekeeping: shows where data is coming from, whether the LLM-polish path
is active, and lets the demo operator clear the Streamlit data cache after
re-running the pipeline (main.py) on new data.
"""

import os

import streamlit as st

import audit_engine as engine
from utils.config import APP_NAME, APP_VERSION, OUTPUT_DIR
from utils.data_loader import pipeline_has_run, load_projects


def render_settings() -> None:
    st.markdown("## ⚙️ Settings")

    st.markdown("#### Data source")
    if pipeline_has_run():
        df = load_projects()
        mode = df["scoring_mode"].iloc[0] if "scoring_mode" in df.columns and not df.empty else "unknown"
        st.success(f"Pipeline output found in `{os.path.abspath(OUTPUT_DIR)}/` — scoring mode: **{mode}**.")
    else:
        st.error(
            f"No pipeline output found in `{OUTPUT_DIR}/`. Run `python3 main.py` from the "
            f"project root first."
        )

    if st.button("🔄 Clear cached data (reload from outputs/)"):
        st.cache_data.clear()
        st.success("Cache cleared. Data will be reloaded from disk on next page view.")
        st.rerun()

    st.markdown("---")
    st.markdown("#### AI Audit Assistant — LLM polishing")
    if engine._LLM_AVAILABLE:
        st.success("`ANTHROPIC_API_KEY` detected — LLM-polished summaries are available (toggle per-page).")
    else:
        st.info(
            "`ANTHROPIC_API_KEY` not set — the Audit Assistant runs in **template mode**: "
            "fast, deterministic, grounded summaries with zero external dependency. "
            "Set the environment variable and restart to enable LLM polishing."
        )

    st.markdown("---")
    st.markdown("#### About")
    st.write(f"**{APP_NAME}** v{APP_VERSION}")
    st.caption(
        "Data → ML scoring (Isolation Forest + Random Forest/XGBoost/LightGBM) → "
        "explainable risk bands → AI Audit Assistant, wired into one Streamlit app."
    )
