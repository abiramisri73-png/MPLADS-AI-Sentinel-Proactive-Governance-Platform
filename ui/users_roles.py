"""
ui/users_roles.py
-------------------
Describes the demo role model used by the sidebar's role selector, and
shows what each role currently sees. This is a demo/explanatory page, not
a real user-management screen — a production system would enforce this
scoping server-side against actual login identity, not a dropdown.
"""

import streamlit as st

from utils.config import USER_ROLES
from utils.data_loader import load_projects, scope_by_role

ROLE_DESCRIPTIONS = {
    "Member of Parliament": (
        "Sees works funded under their own constituency's MPLADS allocation. "
        "In this demo, scoped to a fixed pair of states (Uttar Pradesh, Rajasthan) "
        "to illustrate constituency-level visibility."
    ),
    "District Authority": (
        "Sees works being implemented within their district — responsible for "
        "on-the-ground execution, payments, and compliance verification."
    ),
    "State Nodal Authority": (
        "Sees fund utilisation and risk across all districts in their state — "
        "the level at which cross-district patterns (e.g. a vendor operating in "
        "multiple districts) become visible."
    ),
    "Ministry": (
        "Full national view across all states and districts — the level at which "
        "systemic patterns and state-to-state comparisons are made."
    ),
}


def render_users_roles() -> None:
    st.markdown("## 👥 Users & Roles")
    st.caption(
        "This demo shows role-based data scoping using the sidebar's role selector. "
        "A production deployment would enforce this against real login identity and "
        "actual jurisdiction records, not a dropdown."
    )

    df = load_projects()
    current_role = st.session_state.get("selected_role", "Ministry")

    for role in USER_ROLES:
        scoped = scope_by_role(df, role)
        is_current = role == current_role
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"#### {role}" + (" — *currently active*" if is_current else ""))
                st.write(ROLE_DESCRIPTIONS.get(role, ""))
            with c2:
                st.metric("Works visible", len(scoped))

    st.markdown("---")
    st.caption(
        "Switch roles from the sidebar's **Demo Role Selector** to see the Dashboard, "
        "Projects, Risk Alerts, and Map View scope to that role's data."
    )
