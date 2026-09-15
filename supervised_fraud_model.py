"""
=================================================================================
SUPERVISED FRAUD MODEL LAYER — trains on your labeled ground truth
=================================================================================
Use this when your dataset has a confirmed fraud/no-fraud label column
(e.g. from past audits/investigations), typically called `is_fraud_label`
(1 = confirmed fraud/irregularity, 0 = clean).

The unsupervised Isolation Forest (risk_scoring_pipeline.py) answers:
    "Which works look statistically unusual?"

This module answers a DIFFERENT, more valuable question:
    "Based on what confirmed fraud has actually looked like before,
     how likely is THIS work to be fraudulent?"

It trains and compares three supervised classifiers:
    - Random Forest
    - XGBoost
    - LightGBM
...on the SAME engineered features as the unsupervised model, PLUS the
unsupervised outputs themselves (anomaly_score, duplicate_risk_score, etc.)
as additional input features. This is a common and effective pattern called
"stacking" — the supervised model gets to learn things like "an anomaly score
above 70 combined with a duplicate flag is almost always fraud" directly from
your labeled history, rather than that relationship being hand-coded into
fixed weights.

Deliverables produced (in OUTPUT_DIR):
    - model_comparison.csv          : RF vs XGBoost vs LightGBM performance
    - supervised_feature_importance.csv : which features the winning model relies on
    - scored_dataset_hybrid.csv      : every work with unsupervised score,
                                        supervised fraud probability, and a
                                        blended hybrid_risk_score + band
    - high_risk_alerts_hybrid.csv    : Critical/High only, with combined reasons
    - fraud_model.joblib             : the trained winning model (for reuse/deployment)

Libraries: scikit-learn, xgboost, lightgbm, shap, imbalanced-learn, joblib
=================================================================================
"""

import os
import numpy as np
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    roc_auc_score, average_precision_score, precision_score,
    recall_score, f1_score, precision_recall_curve, confusion_matrix
)

from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
import shap

import risk_scoring_pipeline as rsp   # reuse feature engineering + unsupervised pipeline

# =================================================================================
# CONFIG
# =================================================================================

LABEL_COL   = "is_fraud_label"      # 1 = confirmed fraud, 0 = clean. Change if yours differs.
OUTPUT_DIR  = "outputs"
RANDOM_STATE = 42
TEST_SIZE   = 0.25

# Features fed to the supervised models: the raw engineered risk features
# PLUS the unsupervised pipeline's own outputs (stacking).
SUPERVISED_FEATURES = rsp.ANOMALY_FEATURES + [
    "anomaly_score", "duplicate_risk_score",
    "delay_risk", "utilisation_irregularity", "fund_diversion_score",
]

# How much to trust the learned (supervised) model vs. the rule-based
# composite (unsupervised) score in the final hybrid number.
# Supervised gets more weight because it is validated against real outcomes.
HYBRID_WEIGHTS = {"supervised": 0.65, "unsupervised": 0.35}

RISK_BANDS = rsp.RISK_BANDS  # reuse same Critical/High/Medium/Low cut points


# =================================================================================
# 1. TRAIN + COMPARE MODELS
# =================================================================================

def build_models(scale_pos_weight, random_state=RANDOM_STATE):
    """
    Each model is configured to handle class imbalance, since confirmed
    fraud cases are almost always a small minority of all records.
    """
    return {
        "RandomForest": RandomForestClassifier(
            n_estimators=400, max_depth=8, min_samples_leaf=3,
            class_weight="balanced", random_state=random_state, n_jobs=-1,
        ),
        "XGBoost": XGBClassifier(
            n_estimators=400, max_depth=4, learning_rate=0.05,
            subsample=0.85, colsample_bytree=0.85,
            scale_pos_weight=scale_pos_weight,
            eval_metric="aucpr", random_state=random_state, n_jobs=-1,
        ),
        "LightGBM": LGBMClassifier(
            n_estimators=400, max_depth=-1, num_leaves=24, learning_rate=0.05,
            subsample=0.85, colsample_bytree=0.85,
            is_unbalance=True, random_state=random_state, n_jobs=-1, verbosity=-1,
        ),
    }


def best_f1_threshold(y_true, y_proba):
    """Fraud detection should not default to a 0.5 cutoff -- with imbalanced
    classes the F1-optimal threshold is usually much lower. Search the
    precision-recall curve for the threshold that maximizes F1."""
    prec, rec, thr = precision_recall_curve(y_true, y_proba)
    f1 = 2 * prec * rec / (prec + rec + 1e-12)
    best_idx = np.nanargmax(f1[:-1]) if len(thr) > 0 else 0
    return float(thr[best_idx]) if len(thr) > 0 else 0.5, float(f1[best_idx])


def train_and_compare_models(df, feature_cols=SUPERVISED_FEATURES, label_col=LABEL_COL,
                              test_size=TEST_SIZE, random_state=RANDOM_STATE):
    df = df.copy()
    if label_col not in df.columns:
        raise ValueError(
            f"Column '{label_col}' not found. Set LABEL_COL to your actual fraud-label "
            f"column name at the top of this script."
        )

    X = df[feature_cols].fillna(df[feature_cols].median())
    y = df[label_col].astype(int)

    n_pos, n_neg = y.sum(), len(y) - y.sum()
    if n_pos < 5:
        raise ValueError(
            f"Only {n_pos} positive (fraud) labels found -- too few to train a reliable "
            f"supervised model. Isolation Forest (unsupervised) is the right tool until "
            f"you have more confirmed cases (aim for 30+)."
        )
    print(f"[INFO] Label distribution: {n_pos} fraud / {n_neg} clean "
          f"({n_pos / len(y) * 100:.1f}% positive rate)")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=random_state
    )
    scale_pos_weight = n_neg / max(n_pos, 1)
    models = build_models(scale_pos_weight, random_state)

    results = []
    fitted_models = {}
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state)

    for name, model in models.items():
        model.fit(X_train, y_train)
        proba_test = model.predict_proba(X_test)[:, 1]

        # Cross-validated PR-AUC on the TRAIN split only -- more reliable estimate
        # of generalization than a single train/test split when fraud cases are rare.
        cv_scores = cross_val_score(model, X_train, y_train, cv=cv, scoring="average_precision")

        thr, best_f1 = best_f1_threshold(y_test, proba_test)
        y_pred = (proba_test >= thr).astype(int)

        tn, fp, fn, tp = confusion_matrix(y_test, y_pred, labels=[0, 1]).ravel()

        results.append({
            "model": name,
            "roc_auc": round(roc_auc_score(y_test, proba_test), 3),
            "pr_auc": round(average_precision_score(y_test, proba_test), 3),
            "cv_pr_auc_mean": round(cv_scores.mean(), 3),
            "cv_pr_auc_std": round(cv_scores.std(), 3),
            "best_threshold": round(thr, 3),
            "precision_at_best_thr": round(precision_score(y_test, y_pred, zero_division=0), 3),
            "recall_at_best_thr": round(recall_score(y_test, y_pred, zero_division=0), 3),
            "f1_at_best_thr": round(best_f1, 3),
            "true_positives": int(tp), "false_positives": int(fp),
            "false_negatives": int(fn), "true_negatives": int(tn),
        })
        fitted_models[name] = model

    comparison_df = pd.DataFrame(results).sort_values("cv_pr_auc_mean", ascending=False)
    best_model_name = comparison_df.iloc[0]["model"]
    print(f"\n[INFO] Best model by cross-validated PR-AUC: {best_model_name}")
    print(comparison_df.to_string(index=False))

    # Refit the winning model type on ALL labeled data before deployment/scoring
    # (standard practice once model selection is done on the held-out split above).
    final_model = build_models(scale_pos_weight, random_state)[best_model_name]
    final_model.fit(X, y)

    return {
        "comparison": comparison_df,
        "best_model_name": best_model_name,
        "final_model": final_model,
        "feature_cols": feature_cols,
        "X_full": X,
    }


# =================================================================================
# 2. FEATURE IMPORTANCE + PER-RECORD EXPLAINABILITY (SHAP)
# =================================================================================

def get_feature_importance(final_model, feature_cols):
    if hasattr(final_model, "feature_importances_"):
        imp = final_model.feature_importances_
    else:
        raise ValueError("Model has no feature_importances_ attribute.")
    imp_pct = imp / imp.sum() * 100
    fi = pd.DataFrame({"feature": feature_cols, "importance_pct": imp_pct.round(2)})
    return fi.sort_values("importance_pct", ascending=False).reset_index(drop=True)


def compute_shap_explanations(final_model, X_full, feature_cols, max_rows=2000):
    """
    Returns a DataFrame of per-record SHAP values (impact of each feature on
    THAT record's fraud probability). Used to generate individualized reasons
    like "flagged mainly due to progress_gap and payment_irregularity".
    Capped at max_rows for speed on very large datasets (sampled, not truncated,
    to keep representative coverage) -- for datasets under the cap, all rows get
    real per-record SHAP explanations.
    """
    if len(X_full) > max_rows:
        sample_idx = X_full.sample(max_rows, random_state=RANDOM_STATE).index
        X_sample = X_full.loc[sample_idx]
    else:
        X_sample = X_full

    explainer = shap.TreeExplainer(final_model)
    shap_values = explainer.shap_values(X_sample)
    # Binary classifiers: different libraries/versions return this differently --
    # a list [class0_values, class1_values], a 3-D array (n, n_features, n_classes),
    # or already a plain 2-D array of "push toward positive class" values.
    if isinstance(shap_values, list):
        shap_values = shap_values[1]
    elif isinstance(shap_values, np.ndarray) and shap_values.ndim == 3:
        shap_values = shap_values[:, :, 1]
    shap_df = pd.DataFrame(shap_values, columns=[f"shap_{c}" for c in feature_cols], index=X_sample.index)
    return shap_df


def top_shap_reasons(row, shap_cols, feature_display_names, top_n=3):
    vals = {c: row[c] for c in shap_cols if row[c] > 0}  # only factors PUSHING toward fraud
    ranked = sorted(vals.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    if not ranked:
        return "No strong individual factor -- flagged on combined weak signals"
    names = [feature_display_names.get(c.replace("shap_", ""), c.replace("shap_", "")) for c, _ in ranked]
    return "Model flagged mainly due to: " + ", ".join(names)


FEATURE_DISPLAY_NAMES = {
    "cost_overrun_pct": "cost overrun",
    "utilisation_pct": "fund utilisation level",
    "progress_gap": "financial-vs-physical progress mismatch",
    "delay_days": "schedule delay",
    "payment_irregularity": "payment/transaction irregularity",
    "cost_per_progress": "cost inefficiency per unit progress",
    "anomaly_score": "overall statistical anomaly",
    "duplicate_risk_score": "duplicate/overlapping work signal",
    "delay_risk": "delay risk",
    "utilisation_irregularity": "utilisation irregularity",
    "fund_diversion_score": "fund diversion signal",
}


# =================================================================================
# 3. HYBRID RISK SCORE (unsupervised composite + supervised probability)
# =================================================================================

def compute_hybrid_score(df, weights=HYBRID_WEIGHTS):
    df = df.copy()
    df["hybrid_risk_score"] = (
        weights["supervised"] * df["supervised_fraud_probability"] +
        weights["unsupervised"] * df["risk_score"]
    ).round(1).clip(0, 100)

    def band(score):
        for lo, hi, label in RISK_BANDS:
            if lo <= score < hi or (label == "Critical" and score == 100):
                return label
        return "Low"

    df["hybrid_risk_band"] = df["hybrid_risk_score"].apply(band)
    return df


# =================================================================================
# 4. MAIN PIPELINE
# =================================================================================

def run_supervised_pipeline(input_csv=rsp.INPUT_CSV, output_dir=OUTPUT_DIR, cols=rsp.COLS):
    os.makedirs(output_dir, exist_ok=True)

    # ---- Step 1: run the unsupervised pipeline first (features + anomaly + duplicates) ----
    if os.path.exists(input_csv):
        raw_df = pd.read_csv(input_csv)
    else:
        print(f"[INFO] '{input_csv}' not found -- using synthetic demo data (includes is_fraud_label).")
        raw_df = rsp.generate_synthetic_data()

    df = rsp.engineer_features(raw_df, cols)
    df, iso_model, scaler, X_raw = rsp.run_isolation_forest(df)
    df, dup_pairs_df = rsp.detect_duplicates(df, cols)
    df = rsp.compute_early_warning_signals(df, cols)
    df = rsp.compute_composite_risk(df)

    if LABEL_COL not in raw_df.columns:
        print(f"[WARN] No '{LABEL_COL}' column found in the input data -- "
              f"cannot train supervised models. Falling back to unsupervised-only scoring.")
        return None
    df[LABEL_COL] = raw_df[LABEL_COL].values

    # ---- Step 2: train + compare supervised models ----
    train_result = train_and_compare_models(df)
    final_model = train_result["final_model"]
    feature_cols = train_result["feature_cols"]

    df["supervised_fraud_probability"] = (final_model.predict_proba(df[feature_cols].fillna(
        df[feature_cols].median()))[:, 1] * 100).round(1)

    # ---- Step 3: explainability ----
    fi_df = get_feature_importance(final_model, feature_cols)
    shap_df = compute_shap_explanations(final_model, train_result["X_full"], feature_cols)
    shap_cols = [f"shap_{c}" for c in feature_cols]
    df = df.join(shap_df, how="left")
    df["supervised_reason"] = df.apply(
        lambda r: top_shap_reasons(r, shap_cols, FEATURE_DISPLAY_NAMES) if not pd.isna(r.get(shap_cols[0], np.nan))
        else "Not scored for individual factors (large dataset sample)", axis=1
    )

    # ---- Step 4: hybrid risk score combining both approaches ----
    df = compute_hybrid_score(df)
    df["combined_reasons"] = df.apply(
        lambda r: f"{r['supervised_reason']} | Rule-based signals: {r['risk_reasons']}"
        if pd.notna(r.get("risk_reasons")) else r["supervised_reason"], axis=1
    ) if "risk_reasons" in df.columns else df["supervised_reason"]

    # Need risk_reasons for combined explanation
    df["risk_reasons"] = df.apply(rsp.generate_reasons, axis=1, cols=cols)
    df["combined_reasons"] = (
        "[Learned from history] " + df["supervised_reason"] +
        "  ||  [Rule-based] " + df["risk_reasons"]
    )

    # ---- Assemble outputs ----
    output_cols = [
        cols["id"], cols["name"], cols["work_type"], cols["district"],
        "anomaly_score", "duplicate_risk_score", "risk_score", "risk_band",
        "supervised_fraud_probability", "hybrid_risk_score", "hybrid_risk_band",
        LABEL_COL, "combined_reasons",
    ]
    scored_hybrid = df[output_cols].sort_values("hybrid_risk_score", ascending=False)
    alerts_hybrid = scored_hybrid[scored_hybrid["hybrid_risk_band"].isin(["Critical", "High"])]

    scored_path = os.path.join(output_dir, "scored_dataset_hybrid.csv")
    alerts_path = os.path.join(output_dir, "high_risk_alerts_hybrid.csv")
    comp_path = os.path.join(output_dir, "model_comparison.csv")
    fi_path = os.path.join(output_dir, "supervised_feature_importance.csv")
    model_path = os.path.join(output_dir, "fraud_model.joblib")

    scored_hybrid.to_csv(scored_path, index=False)
    alerts_hybrid.to_csv(alerts_path, index=False)
    train_result["comparison"].to_csv(comp_path, index=False)
    fi_df.to_csv(fi_path, index=False)
    joblib.dump({"model": final_model, "feature_cols": feature_cols,
                 "model_name": train_result["best_model_name"]}, model_path)

    print(f"\n[SUMMARY]")
    print(f"  Best model                 : {train_result['best_model_name']}")
    print(f"  Hybrid Critical            : {(scored_hybrid['hybrid_risk_band']=='Critical').sum()}")
    print(f"  Hybrid High                : {(scored_hybrid['hybrid_risk_band']=='High').sum()}")
    print(f"\n[OUTPUT FILES]\n  {scored_path}\n  {alerts_path}\n  {comp_path}\n  {fi_path}\n  {model_path}")

    return {
        "scored_dataset_hybrid": scored_hybrid,
        "high_risk_alerts_hybrid": alerts_hybrid,
        "model_comparison": train_result["comparison"],
        "feature_importance": fi_df,
        "final_model": final_model,
    }


if __name__ == "__main__":
    run_supervised_pipeline()
