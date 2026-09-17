"""
app.py
------
MPLADS SENTINEL — Application entry point.

Configures Streamlit, builds the sidebar navigation and role selector,
and routes to the appropriate UI module based on session state.

All page content lives in ui/ modules.
All data access goes through utils/data_loader.py.
"""

import streamlit as st

# ─── Page configuration — must be first Streamlit call ───────────────────────
st.set_page_config(
    page_title="MPLADS SENTINEL — AI Monitoring Platform",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.config import (
    APP_NAME, APP_SUBTITLE, APP_VERSION,
    USER_ROLES, DEMO_BANNER_TEXT, PRIMARY_COLOR,
)
from utils.data_loader import load_projects, load_alerts


# ─── CSS Injection ────────────────────────────────────────────────────────────

def _inject_css() -> None:
    """Inject global CSS for the MPLADS SENTINEL design system."""
    st.markdown(
        """
<style>
/* ── Google Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@500;600;700&family=Public+Sans:wght@300;400;500;600;700&display=swap');

/* ── Root tokens ── */
:root {
  --primary:      #1e3a5f;
  --primary-dark: #14283f;
  --accent:       #a1721a;
  --sidebar-bg:   #14213d;
  --card-bg:      #ffffff;
  --page-bg:      #f4f5f7;
  --text:         #1a1f2b;
  --text-body:    #2d3142;
  --text-muted:   #667085;
  --border:       #d7dbe2;
  --radius:       6px;
  --shadow:       0 1px 3px rgba(16,24,40,0.06);
}

/* ── Base & Global Text Readability ── */
html, body, [class*="css"], [data-testid="stAppViewContainer"] {
  font-family: 'Public Sans', sans-serif;
  color: var(--text-body);
}

p, span, li, td, th {
  color: var(--text-body);
}

/* ── App background ── */
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stHeader"],
[data-testid="stBottom"],
[data-testid="stBottom"] > div {
  background-color: var(--page-bg) !important;
}

/* ── Sidebar (Solid Institutional Navy) ── */
[data-testid="stSidebar"] {
  background: var(--sidebar-bg) !important;
  border-right: 1px solid rgba(255,255,255,0.06);
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] div:not([data-baseweb="popover"] *):not([data-baseweb="menu"] *) {
  color: #dce3f0;
}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] span {
  color: #a9b6cc !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] {
  background: rgba(255,255,255,0.06) !important;
  border: 1px solid rgba(255,255,255,0.16) !important;
  border-radius: 4px !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] div {
  color: #ffffff !important;
}

/* ── Form Controls, Inputs & Dropdowns (High Contrast) ── */
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] span,
[data-testid="stWidgetLabel"] label {
  color: #0f172a !important;
  font-weight: 600 !important;
  font-size: 0.84rem !important;
}

[data-baseweb="select"] {
  background-color: #ffffff !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 8px !important;
}
[data-baseweb="select"] span,
[data-baseweb="select"] div {
  color: #0f172a !important;
}

[data-baseweb="popover"],
[data-baseweb="menu"],
ul[role="listbox"] {
  background-color: #ffffff !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 8px !important;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12) !important;
}
[data-baseweb="menu"] li,
li[role="option"] {
  background-color: #ffffff !important;
  color: #0f172a !important;
}
[data-baseweb="menu"] li *,
li[role="option"] * {
  color: #0f172a !important;
}
[data-baseweb="menu"] li:hover,
li[role="option"]:hover,
li[aria-selected="true"] {
  background-color: #eef1f6 !important;
}
li[aria-selected="true"] * {
  color: #1e3a5f !important;
  font-weight: 600 !important;
}

/* Multiselect chips */
[data-baseweb="tag"] {
  background-color: #e4e9f1 !important;
  border: 1px solid #c3cddc !important;
  border-radius: 4px !important;
}
[data-baseweb="tag"] span {
  color: #1e3a5f !important;
  font-weight: 600 !important;
}

/* Text inputs */
[data-baseweb="input"] {
  background-color: #ffffff !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 8px !important;
}
[data-baseweb="input"] input {
  color: #0f172a !important;
}
[data-baseweb="input"] input::placeholder {
  color: #64748b !important;
}

/* ── Subtitles, Captions & Secondary Text ── */
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p,
.stCaption,
small {
  color: #475569 !important;
  font-size: 0.8rem !important;
  font-weight: 500 !important;
}
p[style*="color:#64748b"],
span[style*="color:#64748b"] {
  color: #475569 !important;
  font-weight: 500 !important;
}

/* ── Headings ── */
h1, h2, h3, h4, h5, h6 {
  font-family: 'Source Serif 4', serif !important;
  color: #1a1f2b !important;
  font-weight: 600 !important;
}
h2 {
  font-size: 1.6rem !important;
  margin-bottom: 4px !important;
}
h3 {
  font-size: 1.2rem !important;
  color: #2d3142 !important;
}

/* ── KPI Cards ── */
.kpi-card {
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  padding: 18px 16px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
  min-height: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
}
.kpi-card:hover {
  box-shadow: 0 4px 14px rgba(16,24,40,0.10);
  transform: translateY(-1px);
}
.kpi-card--alert {
  border-color: #e8d9b0;
  background: #fdf9ef;
}
.kpi-icon {
  font-size: 1.5rem;
}
.kpi-label {
  font-size: 0.78rem;
  font-weight: 700;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.kpi-value {
  font-size: 1.65rem;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.1;
}
.kpi-sub {
  font-size: 0.74rem;
  color: #64748b;
  font-weight: 500;
}

/* ── Main content cards & Containers ── */
.stContainer,
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--card-bg) !important;
  border-radius: 12px;
  border: 1px solid #cbd5e1 !important;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}

/* ── Metric ── */
[data-testid="stMetricValue"] {
  font-size: 1.45rem !important;
  font-weight: 800 !important;
  color: #0f172a !important;
}
[data-testid="stMetricLabel"] {
  font-size: 0.78rem !important;
  color: #475569 !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.04em !important;
}

/* ── Dataframes ── */
[data-testid="stDataFrame"] {
  background: var(--card-bg);
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
[data-testid="stDataFrame"] * {
  color: #0f172a !important;
}

/* ── Buttons ── */
.stButton button {
  background-color: #ffffff !important;
  color: #1e293b !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
  transition: all 0.15s ease !important;
}
.stButton button:hover {
  border-color: #1e3a5f !important;
  color: #1e3a5f !important;
  background-color: #f2f4f7 !important;
  transform: translateY(-1px);
  box-shadow: 0 3px 10px rgba(16,24,40,0.10) !important;
}
[data-testid="stDownloadButton"] button {
  background-color: #1e3a5f !important;
  color: #ffffff !important;
  border: none !important;
  font-weight: 600 !important;
  border-radius: 6px !important;
}
[data-testid="stDownloadButton"] button:hover {
  background-color: #14283f !important;
  color: #ffffff !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] [data-baseweb="tab"] {
  font-weight: 600 !important;
  padding: 8px 16px !important;
  color: #475569 !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
  border-bottom: 2px solid var(--accent) !important;
  color: var(--primary) !important;
}

/* ── Info/Warning boxes ── */
[data-testid="stInfo"] {
  background-color: #eef1f6 !important;
  border-radius: 6px !important;
  border-left: 4px solid #1e3a5f !important;
}
[data-testid="stInfo"] * {
  color: #14283f !important;
}
[data-testid="stWarning"] {
  background-color: #fffbeb !important;
  border-left: 4px solid #f59e0b !important;
}
[data-testid="stWarning"] * {
  color: #78350f !important;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
  background: var(--card-bg) !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 12px !important;
  margin-bottom: 8px !important;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
[data-testid="stChatMessage"] * {
  color: #0f172a !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
  background: var(--card-bg) !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 10px !important;
  margin-bottom: 8px !important;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
[data-testid="stExpander"] summary {
  color: #0f172a !important;
  font-weight: 700 !important;
}
[data-testid="stExpander"] summary * {
  color: #0f172a !important;
  font-weight: 700 !important;
}
[data-testid="stExpander"] details {
  background: var(--card-bg) !important;
  border-radius: 10px;
}

/* ── Radio & Checkboxes ── */
[data-testid="stRadio"] label,
[data-testid="stRadio"] span,
[data-testid="stCheckbox"] label,
[data-testid="stCheckbox"] span {
  color: #1e293b !important;
  font-weight: 500 !important;
}

/* ── Divider ── */
hr {
  border-color: #cbd5e1 !important;
}

/* ── Progress bar ── */
.stProgress > div > div > div {
  background: linear-gradient(90deg, #1e3a5f, #a1721a) !important;
  border-radius: 999px !important;
}

/* ── Demo banner ── */
.demo-banner {
  background: rgba(180,35,24,0.10);
  border: 1px solid rgba(180,35,24,0.30);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 0.72rem;
  color: #e29a92;
  margin-top: 8px;
  text-align: center;
  line-height: 1.4;
}

/* ── Sidebar nav button ── */
.nav-btn {
  width: 100%;
  text-align: left;
  padding: 10px 14px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
  color: #a9b6cc;
  font-size: 0.92rem;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
  border: none;
  background: transparent;
}
.nav-btn:hover, .nav-btn--active {
  background: rgba(255,255,255,0.08);
  color: #fff;
}

/* ── Sidebar nav button (Streamlit-rendered) ── */
[data-testid="stSidebar"] .stButton button {
  background-color: transparent !important;
  border: none !important;
  border-left: 2px solid transparent !important;
  border-radius: 4px !important;
  color: #a9b6cc !important;
  text-align: left !important;
  box-shadow: none !important;
}
[data-testid="stSidebar"] .stButton button:hover {
  border-left: 2px solid var(--accent) !important;
  background-color: rgba(255,255,255,0.06) !important;
  color: #fff !important;
  transform: none !important;
}
[data-testid="stSidebar"] [data-testid="stDownloadButton"] button {
  background-color: rgba(255,255,255,0.08) !important;
  color: #fff !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


# ─── Session state initialisation ────────────────────────────────────────────

def _init_session() -> None:
    defaults = {
        "page":             "Dashboard",
        "selected_project": None,
        "selected_alert":   None,
        "selected_role":    USER_ROLES[0],
        "show_demo_banner": True,
        "chat_history":     [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ─── Sidebar ─────────────────────────────────────────────────────────────────

NAV_ITEMS = [
    ("Dashboard",       "🏠"),
    ("Projects",        "📁"),
    ("Risk Alerts",     "🔔"),
    ("Map View",        "🗺️"),
    ("Analytics",       "📊"),
    ("AI Audit Assistant", "🤖"),
    ("Reports",         "📄"),
    ("Users & Roles",   "👥"),
    ("Settings",        "⚙️"),
]


def _render_sidebar() -> None:
    """Render the full sidebar including branding, nav, role selector, and demo banner."""
    with st.sidebar:
        # ── Branding ──
        st.markdown(
            f"""
<div style="text-align:center;padding:8px 0 16px 0">
  <div style="font-size:1.8rem;font-weight:800;color:#dce3f0;letter-spacing:-0.5px">
    🏛️ MPLADS
  </div>
  <div style="font-size:0.75rem;color:#a9b6cc;font-weight:500;margin-top:2px">
    SENTINEL
  </div>
  <div style="font-size:0.65rem;color:#7e8caa;margin-top:4px;font-style:italic">
    {APP_SUBTITLE}
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()

        # ── Navigation ──
        st.markdown(
            "<div style='font-size:0.65rem;color:#7e8caa;font-weight:600;"
            "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px'>"
            "Navigation</div>",
            unsafe_allow_html=True,
        )

        for label, icon in NAV_ITEMS:
            is_active = st.session_state["page"] == label
            btn_style = (
                "background:rgba(255,255,255,0.14);color:#fff;" if is_active
                else "background:transparent;color:#a9b6cc;"
            )
            if st.button(
                f"{icon}  {label}",
                key=f"nav_{label}",
                use_container_width=True,
                type="secondary",
            ):
                st.session_state["page"] = label
                # Clear drill-down state when navigating away
                st.session_state["selected_project"] = None
                st.session_state["selected_alert"] = None
                st.rerun()

        st.divider()

        # ── Role Selector ──
        st.markdown(
            "<div style='font-size:0.65rem;color:#7e8caa;font-weight:600;"
            "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px'>"
            "Demo Role Selector</div>",
            unsafe_allow_html=True,
        )
        selected_role = st.selectbox(
            "Logged in as",
            USER_ROLES,
            index=USER_ROLES.index(st.session_state["selected_role"]),
            key="role_selector",
            label_visibility="collapsed",
        )
        st.session_state["selected_role"] = selected_role

        role_icons = {
            "Member of Parliament":  "🏛️",
            "District Authority":    "🏢",
            "State Nodal Authority": "🏗️",
            "Ministry":              "🏛️",
        }
        st.markdown(
            f"<div style='font-size:0.75rem;color:#a9b6cc;padding:4px 0'>"
            f"{role_icons.get(selected_role, '👤')} {selected_role}"
            f"</div>",
            unsafe_allow_html=True,
        )
        _render_role_hint(selected_role)

        st.divider()

        # ── AI Assistant Callout ──
        st.markdown(
            """
<div style="background:rgba(255,255,255,0.05);
  border:1px solid rgba(161,114,26,0.35);border-left:3px solid #a1721a;
  border-radius:6px;padding:12px;margin-bottom:8px">
  <div style="font-size:0.85rem;font-weight:600;color:#dce3f0">🤖 AI Audit Assistant</div>
  <div style="font-size:0.72rem;color:#a9b6cc;margin-top:4px">
    Ask questions about MPLADS monitoring data
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Open Assistant →", key="sidebar_assistant", use_container_width=True):
            st.session_state["page"] = "AI Audit Assistant"
            st.rerun()

        # ── Demo Banner ──
        if st.session_state.get("show_demo_banner", True):
            st.markdown(
                f"<div class='demo-banner'>{DEMO_BANNER_TEXT}</div>",
                unsafe_allow_html=True,
            )

        # ── Version ──
        st.markdown(
            f"<div style='text-align:center;font-size:0.62rem;color:#5b6a8a;"
            f"margin-top:12px'>v{APP_VERSION} · Member 4 Frontend Module</div>",
            unsafe_allow_html=True,
        )


def _render_role_hint(role: str) -> None:
    """Show a brief role-awareness hint in the sidebar."""
    hints = {
        "Member of Parliament":
            "Showing: constituency view, own projects",
        "District Authority":
            "Showing: district projects, payments, compliance",
        "State Nodal Authority":
            "Showing: state-level fund utilisation & risk",
        "Ministry":
            "Showing: national overview, all states",
    }
    hint = hints.get(role, "")
    if hint:
        st.markdown(
            f"<div style='font-size:0.68rem;color:#7e8caa;font-style:italic;padding:2px 0'>"
            f"{hint}</div>",
            unsafe_allow_html=True,
        )


# ─── Role-aware data scoping ──────────────────────────────────────────────────

def _apply_role_scope(projects):
    """
    Simulate role-based data scoping for demo purposes.
    A production system would enforce this at the backend/API layer.
    """
    role = st.session_state.get("selected_role", "Ministry")
    if projects.empty:
        return projects

    if role == "Member of Parliament":
        # Show only a fixed set of demo states for MP view
        sample_states = ["Uttar Pradesh", "Rajasthan"]
        return projects[projects["state"].isin(sample_states)]
    elif role == "District Authority":
        sample_districts = ["Lucknow", "Nagpur", "Patna", "Jaipur", "Gaya"]
        return projects[projects["district"].isin(sample_districts)]
    elif role == "State Nodal Authority":
        sample_states = ["Uttar Pradesh", "Maharashtra", "Bihar", "Rajasthan", "Tamil Nadu"]
        return projects[projects["state"].isin(sample_states)]
    else:
        # Ministry — full view
        return projects


# ─── Router ──────────────────────────────────────────────────────────────────

def _route() -> None:
    """Route to the correct UI module based on session state."""
    page = st.session_state.get("page", "Dashboard")

    if page == "Dashboard":
        from ui.dashboard import render_dashboard
        render_dashboard()

    elif page == "Projects":
        from ui.projects import render_projects
        render_projects()

    elif page == "Risk Alerts":
        from ui.alerts import render_alerts
        render_alerts()

    elif page == "Map View":
        from ui.map_view import render_map_view
        render_map_view()

    elif page == "Analytics":
        from ui.analytics import render_analytics
        render_analytics()

    elif page == "AI Audit Assistant":
        from ui.audit_assistant import render_audit_assistant
        render_audit_assistant()

    elif page == "Reports":
        from ui.reports import render_reports
        render_reports()

    elif page == "Users & Roles":
        from ui.users_roles import render_users_roles
        render_users_roles()

    elif page == "Settings":
        from ui.settings import render_settings
        render_settings()

    else:
        st.error(f"Unknown page: `{page}`")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    _inject_css()
    _init_session()
    _render_sidebar()
    _route()


if __name__ == "__main__":
    main()

