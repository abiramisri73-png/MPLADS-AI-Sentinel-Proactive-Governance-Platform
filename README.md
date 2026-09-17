# MPLADS SENTINEL — AI Monitoring & Risk Analytics Platform

End-to-end prototype: **Data → ML Scoring → Multi-page Dashboard → AI Audit Assistant**.

## Architecture

```
app.py                      # Entry point — page config, CSS, sidebar nav, role selector, router
main.py                     # CLI: runs the full ML pipeline, generates outputs, optionally launches app.py

risk_scoring_pipeline.py    # Unsupervised layer: features, Isolation Forest, duplicates, composite score
supervised_fraud_model.py   # Supervised layer: RF/XGBoost/LightGBM on a fraud-label column (if present)
audit_engine.py             # AI Audit Assistant backend: grounded summaries + recommendations

utils/
  config.py                 # Branding, roles, colors — single source of app-wide constants
  data_loader.py             # ALL data access + role-based scoping. UI never reads a CSV directly.
  ui_helpers.py               # Shared KPI-card / risk-band-badge rendering helpers

ui/
  dashboard.py               # KPI overview + risk distribution + alert preview
  projects.py                 # Full works table, filters, work detail drill-down
  alerts.py                    # Critical/High alert feed with reasons, exportable
  map_view.py                   # Geographic plot of works colored by risk band (pydeck)
  analytics.py                   # Risk drivers, model comparison, distributions
  audit_assistant.py              # Chat-style front end over audit_engine.py
  reports.py                       # Batch summaries + CSV/JSON exports
  users_roles.py                    # Role model explanation + live scoping demo
  settings.py                        # Data source status, cache control, LLM status
```

**Design rule this follows throughout:** UI modules never touch a CSV or compute a score —
they call `utils/data_loader.py`, which is the only file that reads `outputs/*.csv`. Swap in
a real database later and only that one file changes.

## Quick start (demo mode — no data needed)

```bash
pip install pandas numpy scikit-learn rapidfuzz xgboost lightgbm shap imbalanced-learn \
            joblib streamlit pydeck --break-system-packages

python3 main.py            # runs the full pipeline on synthetic demo data
streamlit run app.py       # opens the interactive multi-page dashboard
```

`main.py` with no arguments generates a realistic synthetic dataset (615 works across 8
states / 24 real Indian districts, injected fraud + duplicate cases, an `is_fraud_label`
column) so the whole system — including role-based scoping and the map view — works before
you touch real data.

Or do both in one step:

```bash
python3 main.py --dashboard
```

## Running on your real data

1. Put your CSV at `works_data.csv` (or pass `--input yourfile.csv`).
2. Open `risk_scoring_pipeline.py` and edit the `COLS` dictionary near the top so each key
   matches your actual column names — including `state` and `district`, which the role-based
   sidebar scoping in `utils/data_loader.py` (`scope_by_role`) filters on.
3. If you have confirmed fraud outcomes, include a column named `is_fraud_label`
   (1 = confirmed fraud/irregularity, 0 = clean). Without it the supervised layer is skipped
   automatically — nothing breaks, the app runs on the unsupervised score alone.
4. If your real state/district names differ from the demo set (`Uttar Pradesh` / `Lucknow`
   etc.), update the three scoping lists at the top of `utils/data_loader.py`
   (`_MP_DEMO_STATES`, `_DISTRICT_AUTHORITY_DEMO_DISTRICTS`, `_STATE_NODAL_DEMO_STATES`) —
   a real deployment would replace this whole function with a lookup against actual
   jurisdiction/login records.
5. Run:
   ```bash
   python3 main.py --input works_data.csv --dashboard
   ```

## Command-line options

```
python3 main.py [--input PATH] [--top-works N] [--top-districts N] [--use-llm] [--dashboard]
```

- `--top-works` / `--top-districts` — how many highest-risk works/districts get batch audit
  summaries (default 20 / 5).
- `--use-llm` — polish audit summaries with Claude. Requires `ANTHROPIC_API_KEY` in the
  environment (`pip install anthropic` first). If the key is missing or the call fails, it
  silently falls back to template mode.
- `--dashboard` — launch `streamlit run app.py` automatically once scoring finishes.

## The role selector, honestly

The sidebar's **Demo Role Selector** (Member of Parliament / District Authority / State
Nodal Authority / Ministry) is a **visual demo of what role-aware access looks like**, scoped
by hardcoded demo state/district lists in `utils/data_loader.py`. It is not real
authentication or authorization — a production system would enforce this server-side against
actual login identity and jurisdiction records, not a dropdown anyone can change. Say this
plainly if asked in review; it's a legitimate prototype simplification, not a hidden gap.

## Outputs (all in `outputs/`)

- `scored_dataset.csv` / `scored_dataset_hybrid.csv` — every work, fully scored
- `high_risk_alerts.csv` / `high_risk_alerts_hybrid.csv` — Critical/High only, with reasons
- `duplicate_pairs.csv` — flagged duplicate/overlapping work pairs
- `top_risk_drivers.csv` — system-wide ranking of what drives risk
- `model_comparison.csv`, `supervised_feature_importance.csv`, `fraud_model.joblib` —
  supervised layer artifacts (only if labels were present)
- `audit_summaries_works.json/.csv`, `audit_summaries_districts.json/.csv` — batch AI Audit
  Assistant output

## Explainability, consistently, across every layer

- Unsupervised: `risk_reasons` column (rule-based, ranked by contribution)
- Supervised: SHAP-based per-record reasons (top features actually pushing that record toward fraud)
- Audit Assistant: full narrative built from the same grounded numbers as both of the above —
  nothing is invented; LLM mode (if enabled) is only allowed to reword, never to add facts

## Known limits (worth being upfront about in review)

- Composite risk weights and Isolation Forest contamination rate are reasonable defaults, not
  calibrated against your real fraud base rate.
- With few confirmed fraud labels (common in practice), supervised metrics are noisy — watch
  `cv_pr_auc_std` in `model_comparison.csv`, not just the mean.
- The dashboard reads pre-computed CSVs; it does not re-run scoring live. Re-run `main.py`
  after new data arrives, then use Settings -> "Clear cached data" in the app.
- Role-based scoping is a UI-layer demo, not enforced access control (see above).
