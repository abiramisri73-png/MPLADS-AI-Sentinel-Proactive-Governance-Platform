"""
utils/data_loader.py
---------------------
All data access for the UI goes through this module. UI code never reads a
CSV directly -- that keeps a single, cache-aware seam between the ML
pipeline's output files and everything the dashboard displays.

If you swap in a real database or API later, this is the only file that
needs to change.
"""

import os
import json

import pandas as pd
import streamlit as st

from utils.config import OUTPUT_DIR


def _path(filename: str) -> str:
    return os.path.join(OUTPUT_DIR, filename)


def pipeline_has_run() -> bool:
    """True once main.py / risk_scoring_pipeline.py has produced at least the base dataset."""
    return os.path.exists(_path("scored_dataset.csv"))


# =================================================================================
# Core datasets
# =================================================================================

@st.cache_data
def load_projects() -> pd.DataFrame:
    """
    The full scored works ("projects") table -- one row per work, every
    sub-score, and a single unified `risk_score` / `risk_band` (hybrid if the
    supervised layer ran, unsupervised-only otherwise).
    """
    hybrid_path = _path("scored_dataset_hybrid.csv")
    base_path = _path("scored_dataset.csv")

    if os.path.exists(hybrid_path):
        df = pd.read_csv(hybrid_path)
        df["risk_score"] = df["hybrid_risk_score"]
        df["risk_band"] = df["hybrid_risk_band"]
        df["risk_reasons"] = df.get("combined_reasons", "")
        df["scoring_mode"] = "hybrid (supervised + unsupervised)"
    elif os.path.exists(base_path):
        df = pd.read_csv(base_path)
        df["scoring_mode"] = "unsupervised only"
    else:
        return pd.DataFrame()

    return df


@st.cache_data
def load_alerts() -> pd.DataFrame:
    """Critical/High works only -- the actionable alert feed."""
    df = load_projects()
    if df.empty:
        return df
    return df[df["risk_band"].isin(["Critical", "High"])].sort_values("risk_score", ascending=False)


@st.cache_data
def load_duplicates() -> pd.DataFrame:
    path = _path("duplicate_pairs.csv")
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


@st.cache_data
def load_risk_drivers() -> pd.DataFrame:
    path = _path("top_risk_drivers.csv")
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


@st.cache_data
def load_model_comparison() -> pd.DataFrame:
    path = _path("model_comparison.csv")
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


@st.cache_data
def load_feature_importance() -> pd.DataFrame:
    path = _path("supervised_feature_importance.csv")
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


@st.cache_data
def load_audit_summaries(level: str = "works") -> list:
    """level: 'works' or 'districts' -- pre-generated batch summaries from audit_engine.py."""
    fname = f"audit_summaries_{level}.json"
    path = _path(fname)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


# =================================================================================
# Role-based scoping
# =================================================================================
# Mirrors the demo scoping in app.py's _apply_role_scope, exposed here so every
# UI page (not just the sidebar) can apply the same rule consistently. A real
# deployment would enforce this server-side, keyed off the logged-in user's
# actual mandate -- this is a visual demo of what role-aware access looks like.

_MP_DEMO_STATES = ["Uttar Pradesh", "Rajasthan"]
_DISTRICT_AUTHORITY_DEMO_DISTRICTS = ["Lucknow", "Nagpur", "Patna", "Jaipur", "Gaya"]
_STATE_NODAL_DEMO_STATES = ["Uttar Pradesh", "Maharashtra", "Bihar", "Rajasthan", "Tamil Nadu"]


def scope_by_role(df: pd.DataFrame, role: str) -> pd.DataFrame:
    if df.empty or "state" not in df.columns:
        return df
    if role == "Member of Parliament":
        return df[df["state"].isin(_MP_DEMO_STATES)]
    if role == "District Authority":
        return df[df["district"].isin(_DISTRICT_AUTHORITY_DEMO_DISTRICTS)]
    if role == "State Nodal Authority":
        return df[df["state"].isin(_STATE_NODAL_DEMO_STATES)]
    return df  # Ministry — full national view


def get_scoped_projects() -> pd.DataFrame:
    """Convenience: load_projects() + scope_by_role() using the current session's role."""
    role = st.session_state.get("selected_role", "Ministry")
    return scope_by_role(load_projects(), role)


def get_scoped_alerts() -> pd.DataFrame:
    role = st.session_state.get("selected_role", "Ministry")
    return scope_by_role(load_alerts(), role)
