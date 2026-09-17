"""
utils/config.py
----------------
App-wide constants: branding, roles, and shared config. Change values here,
not in the UI modules, to keep branding/config in one place.
"""

APP_NAME = "MPLADS SENTINEL"
APP_SUBTITLE = "AI Monitoring & Risk Analytics Platform"
APP_VERSION = "1.0.0"

PRIMARY_COLOR = "#1e3a5f"
ACCENT_COLOR = "#a1721a"

USER_ROLES = [
    "Member of Parliament",
    "District Authority",
    "State Nodal Authority",
    "Ministry",
]

DEMO_BANNER_TEXT = (
    "Demo build \u2014 scored on synthetic data. Point the pipeline at real "
    "MPLADS data to replace these numbers."
)

# Where the ML pipeline (risk_scoring_pipeline.py / supervised_fraud_model.py /
# audit_engine.py) writes its outputs. Every loader in utils/data_loader.py
# reads from here.
OUTPUT_DIR = "outputs"

RISK_BAND_COLORS = {
    "Critical": "#b42318",
    "High": "#b54708",
    "Medium": "#8a6d1a",
    "Low": "#1a7f4e",
}

RISK_BAND_BG = {
    "Critical": "#fbeae8",
    "High": "#fdf1e6",
    "Medium": "#f8f3df",
    "Low": "#e6f3ec",
}
