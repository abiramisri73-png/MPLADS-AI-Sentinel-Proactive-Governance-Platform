"""
=================================================================================
PUBLIC WORKS / SCHEME EXPENDITURE — FRAUD & RISK DETECTION PIPELINE
=================================================================================
Detects:
    1. Anomalies in expenditure / utilisation / cost / progress (Isolation Forest)
    2. Duplicate / overlapping works (name similarity + geo + cost + time window)
    3. Composite explainable Risk Score (0-100) with Critical/High/Medium/Low bands
    4. Early-warning signals for delay + potential fund diversion
    5. Human-readable alert reasons ("why is this flagged")

Deliverables produced (in OUTPUT_DIR):
    - scored_dataset.csv        : every work with all sub-scores + final risk score
    - high_risk_alerts.csv      : Critical/High records only, with reasons
    - duplicate_pairs.csv       : pairs of works flagged as possible duplicates
    - top_risk_drivers.csv      : which features drive risk most, system-wide

Libraries: pandas, numpy, scikit-learn, rapidfuzz
Author note: This script is written to be dropped onto a REAL dataset. Point
INPUT_CSV to your file and map your column names in the CONFIG section below.
If no input file is found, it auto-generates a realistic synthetic dataset so
the pipeline can be demoed end-to-end.
=================================================================================
"""

import os
import math
import itertools
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from rapidfuzz import fuzz

# =================================================================================
# CONFIG — EDIT THESE FOR YOUR REAL DATASET
# =================================================================================

INPUT_CSV  = "works_data.csv"          # path to your real dataset (if it exists)
OUTPUT_DIR = "outputs"

# Map your actual column names here if they differ from the defaults used below.
COLS = {
    "id":            "work_id",
    "name":          "work_name",
    "work_type":     "work_type",
    "district":      "district",
    "lat":           "lat",
    "lon":           "lon",
    "sanctioned":    "sanctioned_amount",
    "expenditure":   "expenditure",
    "phys_progress":  "physical_progress_pct",
    "fin_progress":   "financial_progress_pct",
    "start_date":    "start_date",
    "end_date":      "end_date",           # planned end date
    "actual_end":    "actual_end_date",    # actual/expected completion (NaT if ongoing)
    "n_payments":    "num_payment_txns",
    "max_txn_pct":   "max_single_txn_pct_of_sanctioned",
    "vendor":        "vendor_id",
}

RANDOM_STATE = 42

# Composite risk score weights (must sum to 1.0)
RISK_WEIGHTS = {
    "anomaly":            0.25,   # Isolation Forest output
    "cost_overrun":       0.18,
    "delay":              0.15,
    "utilisation_irreg":  0.15,
    "duplicate":          0.12,
    "fund_diversion":     0.15,
}

RISK_BANDS = [
    (80, 100, "Critical"),
    (60, 80,  "High"),
    (40, 60,  "Medium"),
    (0,  40,  "Low"),
]

# Duplicate detection blocking / thresholds
DUPLICATE_NAME_SIM_MIN   = 55     # below this, don't even consider as duplicate
DUPLICATE_DIST_KM_CLOSE  = 1.0    # within this -> strong geo signal
DUPLICATE_DIST_KM_MEDIUM = 5.0
DUPLICATE_COST_TOL       = 0.25   # cost within +/-25% counts as "similar cost"
DUPLICATE_RISK_ALERT_MIN = 60     # duplicate_risk_score >= this => report pair


# =================================================================================
# 0. SYNTHETIC DATA GENERATOR (used only if INPUT_CSV is not found — for demo/testing)
# =================================================================================

def generate_synthetic_data(n=600, seed=RANDOM_STATE):
    rng = np.random.default_rng(seed)
    districts = [f"District_{i}" for i in range(1, 13)]
    work_types = ["Road Construction", "Bridge", "School Building", "Water Supply",
                  "Irrigation Canal", "Community Hall", "Drainage", "Anganwadi Center"]
    vendors = [f"VEND_{i:03d}" for i in range(1, 60)]

    rows = []
    for i in range(n):
        district = rng.choice(districts)
        wtype = rng.choice(work_types)
        base_lat = 20 + hash(district) % 10 * 0.3
        base_lon = 78 + hash(district) % 10 * 0.3
        lat = base_lat + rng.normal(0, 0.05)
        lon = base_lon + rng.normal(0, 0.05)

        sanctioned = rng.choice([500000, 1000000, 2500000, 5000000, 10000000]) * rng.uniform(0.8, 1.3)
        start = datetime(2023, 1, 1) + timedelta(days=int(rng.integers(0, 500)))
        planned_duration = int(rng.integers(90, 400))
        planned_end = start + timedelta(days=planned_duration)

        # normal behaviour baseline
        phys_progress = float(np.clip(rng.normal(65, 20), 0, 100))
        fin_progress  = float(np.clip(phys_progress + rng.normal(0, 8), 0, 100))
        expenditure   = sanctioned * (fin_progress / 100) * rng.uniform(0.95, 1.05)
        actual_end = None
        if phys_progress >= 98:
            actual_end = planned_end + timedelta(days=int(rng.integers(-20, 60)))

        n_payments = int(rng.integers(2, 15))
        max_txn_pct = float(np.clip(rng.normal(20, 10), 5, 60))

        rows.append(dict(
            work_id=f"WRK{i:05d}",
            work_name=f"{wtype} at {district} Sector {rng.integers(1,40)}",
            work_type=wtype,
            district=district,
            lat=lat, lon=lon,
            sanctioned_amount=round(sanctioned, 2),
            expenditure=round(expenditure, 2),
            physical_progress_pct=round(phys_progress, 1),
            financial_progress_pct=round(fin_progress, 1),
            start_date=start.date().isoformat(),
            end_date=planned_end.date().isoformat(),
            actual_end_date=actual_end.date().isoformat() if actual_end else "",
            num_payment_txns=n_payments,
            max_single_txn_pct_of_sanctioned=round(max_txn_pct, 1),
            vendor_id=rng.choice(vendors),
            is_fraud_label=0,   # overwritten below for injected anomaly rows
        ))

    df = pd.DataFrame(rows)

    # ---- Inject deliberate ANOMALIES (fund diversion / cost overrun / ghost progress) ----
    anomaly_idx = rng.choice(df.index, size=int(n * 0.06), replace=False)
    for idx in anomaly_idx:
        kind = rng.integers(0, 4)
        if kind == 0:  # money spent, no physical work (classic diversion pattern)
            df.loc[idx, "financial_progress_pct"] = float(rng.uniform(70, 100))
            df.loc[idx, "physical_progress_pct"] = float(rng.uniform(5, 25))
            df.loc[idx, "expenditure"] = df.loc[idx, "sanctioned_amount"] * (df.loc[idx, "financial_progress_pct"] / 100)
        elif kind == 1:  # cost overrun / over-billing
            df.loc[idx, "expenditure"] = df.loc[idx, "sanctioned_amount"] * rng.uniform(1.3, 1.8)
            df.loc[idx, "financial_progress_pct"] = 100.0
        elif kind == 2:  # extreme delay
            df.loc[idx, "actual_end_date"] = ""
            df.loc[idx, "end_date"] = (datetime.strptime(df.loc[idx, "start_date"], "%Y-%m-%d") + timedelta(days=60)).date().isoformat()
        else:  # payment structuring: many small suspicious transactions just under limits
            df.loc[idx, "num_payment_txns"] = int(rng.integers(20, 40))
            df.loc[idx, "max_single_txn_pct_of_sanctioned"] = float(rng.uniform(45, 60))
        # In real life not every anomaly gets confirmed/labeled as fraud (investigations
        # are imperfect) -- simulate ~80% of injected anomalies actually being confirmed/labeled.
        if rng.random() < 0.80:
            df.loc[idx, "is_fraud_label"] = 1

    # A small number of *unlabeled-anomaly* works are ALSO confirmed fraud via other means
    # (e.g. whistleblower, physical audit) even though nothing looks statistically unusual --
    # this keeps the supervised task realistically non-trivial (label isn't 100% derivable
    # from the anomaly features alone).
    extra_fraud_idx = rng.choice(df.index, size=max(1, int(n * 0.01)), replace=False)
    df.loc[extra_fraud_idx, "is_fraud_label"] = 1

    # ---- Inject deliberate DUPLICATE / overlapping works ----
    dup_source_idx = rng.choice(df.index, size=15, replace=False)
    dup_rows = []
    for idx in dup_source_idx:
        src = df.loc[idx].copy()
        src["work_id"] = src["work_id"] + "_DUP"
        src["work_name"] = src["work_name"] + " Phase" if rng.random() < 0.5 else src["work_name"].replace("Sector", "Sec")
        src["lat"] = src["lat"] + rng.normal(0, 0.003)
        src["lon"] = src["lon"] + rng.normal(0, 0.003)
        src["sanctioned_amount"] = src["sanctioned_amount"] * rng.uniform(0.9, 1.1)
        dup_rows.append(src)
    df = pd.concat([df, pd.DataFrame(dup_rows)], ignore_index=True)

    return df


# =================================================================================
# 1. FEATURE ENGINEERING
# =================================================================================

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def engineer_features(df, cols=COLS):
    df = df.copy()

    df[cols["start_date"]] = pd.to_datetime(df[cols["start_date"]], errors="coerce")
    df[cols["end_date"]]   = pd.to_datetime(df[cols["end_date"]], errors="coerce")
    df["_actual_end_dt"]   = pd.to_datetime(df[cols["actual_end"]], errors="coerce")
    today = pd.Timestamp(datetime.now().date())

    # --- Utilisation (%) : how much of sanctioned amount has been spent ---
    df["utilisation_pct"] = (df[cols["expenditure"]] / df[cols["sanctioned"]].replace(0, np.nan)) * 100

    # --- Cost overrun (%) : expenditure vs sanctioned amount, only meaningful positive overrun ---
    df["cost_overrun_pct"] = ((df[cols["expenditure"]] - df[cols["sanctioned"]]) /
                               df[cols["sanctioned"]].replace(0, np.nan)) * 100
    df["cost_overrun_pct"] = df["cost_overrun_pct"].clip(lower=-100)

    # --- Progress gap : financial progress vs physical progress ---
    # Large positive gap = money shown as spent but work not actually done -> diversion signal
    df["progress_gap"] = df[cols["fin_progress"]] - df[cols["phys_progress"]]

    # --- Delay (days) : actual/ongoing completion vs planned end date ---
    reference_completion = df["_actual_end_dt"].fillna(today)
    df["delay_days"] = (reference_completion - df[cols["end_date"]]).dt.days
    # If work is fully finished with actual_end before planned end, delay is 0 (not negative credit)
    df.loc[(df[cols["phys_progress"]] >= 98) & (df["delay_days"] < 0), "delay_days"] = 0
    # If ongoing and already past deadline, delay = days overdue
    df["delay_days"] = df["delay_days"].fillna(0)

    # --- Cost per unit progress : efficiency of spend. Higher = money burned without output ---
    df["cost_per_progress"] = df[cols["expenditure"]] / df[cols["phys_progress"]].replace(0, np.nan)
    df["cost_per_progress"] = df["cost_per_progress"].fillna(df[cols["expenditure"]])  # 0 progress -> full exp as penalty basis

    # --- Payment irregularity : proxy composite of txn patterning ---
    # High txn count + very large single-transaction share => red flag (splitting / lump-sum siphoning)
    n_pay = df[cols["n_payments"]].fillna(0)
    max_txn = df[cols["max_txn_pct"]].fillna(0)
    df["payment_irregularity"] = (
        (max_txn > 40).astype(int) * 40 +          # one payment >40% of sanctioned amount = red flag
        (n_pay > 15).astype(int) * 30 +            # unusually high number of transactions
        np.clip((max_txn - 20), 0, None) * 0.8     # continuous penalty scaling with txn concentration
    )
    df["payment_irregularity"] = df["payment_irregularity"].clip(0, 100)

    return df


# =================================================================================
# 2. ANOMALY DETECTION — ISOLATION FOREST
# =================================================================================

ANOMALY_FEATURES = [
    "cost_overrun_pct", "utilisation_pct", "progress_gap",
    "delay_days", "payment_irregularity", "cost_per_progress",
]


def run_isolation_forest(df, feature_cols=ANOMALY_FEATURES, contamination=0.08, random_state=RANDOM_STATE):
    """
    Fits an Isolation Forest on the engineered risk features.
    Outputs:
        anomaly_score  (0-100, higher = more anomalous)
        anomaly_flag   (1 = flagged anomaly, 0 = normal)
    """
    df = df.copy()
    X = df[feature_cols].copy()

    # Robust to outliers/NaNs: median-impute, then scale (RobustScaler is less
    # distorted by extreme values than StandardScaler — appropriate for fraud data)
    X = X.fillna(X.median())
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X)

    iso = IsolationForest(
        n_estimators=300,
        contamination=contamination,
        max_samples="auto",
        random_state=random_state,
        n_jobs=-1,
    )
    iso.fit(X_scaled)

    # decision_function: higher = more normal, lower/negative = more anomalous
    raw_scores = iso.decision_function(X_scaled)
    predictions = iso.predict(X_scaled)  # -1 = anomaly, 1 = normal

    # Convert to intuitive 0-100 anomaly score (higher = worse) via min-max inversion
    inverted = -raw_scores
    min_s, max_s = inverted.min(), inverted.max()
    anomaly_score = (inverted - min_s) / (max_s - min_s + 1e-9) * 100

    df["anomaly_score"] = anomaly_score.round(1)
    df["anomaly_flag"] = (predictions == -1).astype(int)

    return df, iso, scaler, X


def anomaly_feature_contributions(df, X_raw, feature_cols=ANOMALY_FEATURES):
    """
    Explainability for Isolation Forest (which has no native feature_importances_).
    Approach: for each flagged anomaly, compute the per-feature robust z-score
    (deviation from the population median in MAD units). Features with the
    largest |z| are the ones "driving" that record's anomaly — this is the
    standard practical approach for explaining IF outputs without SHAP.
    """
    med = X_raw.median()
    mad = (X_raw - med).abs().median().replace(0, 1e-6)
    z = (X_raw - med) / (1.4826 * mad)   # robust z-score (MAD-scaled)
    z.columns = [f"z_{c}" for c in feature_cols]
    return pd.concat([df.reset_index(drop=True), z.reset_index(drop=True)], axis=1)


# =================================================================================
# 3. DUPLICATE / OVERLAPPING WORKS DETECTION
# =================================================================================

def _cost_similarity(c1, c2, tol=DUPLICATE_COST_TOL):
    if c1 <= 0 or c2 <= 0:
        return 0
    ratio = min(c1, c2) / max(c1, c2)
    # ratio=1 -> identical cost -> 100 ; ratio <= (1-tol) -> 0, scaled linearly
    return float(np.clip((ratio - (1 - tol * 2)) / (tol * 2) * 100, 0, 100))


def _time_overlap_score(s1, e1, s2, e2):
    if pd.isna(s1) or pd.isna(e1) or pd.isna(s2) or pd.isna(e2):
        return 0
    latest_start = max(s1, s2)
    earliest_end = min(e1, e2)
    overlap_days = (earliest_end - latest_start).days
    if overlap_days <= 0:
        return 0
    total_span = (max(e1, e2) - min(s1, s2)).days
    return float(np.clip(overlap_days / max(total_span, 1) * 100, 0, 100))


def _geo_score(lat1, lon1, lat2, lon2):
    if any(pd.isna(v) for v in [lat1, lon1, lat2, lon2]):
        return 0
    d = haversine_km(lat1, lon1, lat2, lon2)
    if d <= DUPLICATE_DIST_KM_CLOSE:
        return 100
    if d <= DUPLICATE_DIST_KM_MEDIUM:
        return float(np.interp(d, [DUPLICATE_DIST_KM_CLOSE, DUPLICATE_DIST_KM_MEDIUM], [100, 40]))
    if d <= 15:
        return float(np.interp(d, [DUPLICATE_DIST_KM_MEDIUM, 15], [40, 5]))
    return 0


def detect_duplicates(df, cols=COLS):
    """
    Blocking strategy: only compare works within the SAME district + work_type
    (keeps comparisons tractable: O(n^2) within small blocks instead of full dataset).

    For each candidate pair computes:
        - name_sim        : rapidfuzz token_sort_ratio on work_name (0-100)
        - geo_score        : proximity score based on haversine distance (0-100)
        - cost_sim         : how close the sanctioned amounts are (0-100)
        - time_overlap     : how much their execution windows overlap (0-100)

    duplicate_risk_score (pair) = weighted average of the above.
    Each work's duplicate_risk_score (in main table) = MAX over all pairs it appears in.
    """
    pairs = []
    df = df.reset_index(drop=True)
    blocks = df.groupby([cols["district"], cols["work_type"]]).indices

    for _, idxs in blocks.items():
        if len(idxs) < 2:
            continue
        for i, j in itertools.combinations(idxs, 2):
            r1, r2 = df.loc[i], df.loc[j]
            name_sim = fuzz.token_sort_ratio(str(r1[cols["name"]]), str(r2[cols["name"]]))
            if name_sim < DUPLICATE_NAME_SIM_MIN:
                continue  # cheap early exit — names too different to plausibly be duplicates

            geo = _geo_score(r1[cols["lat"]], r1[cols["lon"]], r2[cols["lat"]], r2[cols["lon"]])
            cost_sim = _cost_similarity(r1[cols["sanctioned"]], r2[cols["sanctioned"]])
            time_ov = _time_overlap_score(r1[cols["start_date"]], r1[cols["end_date"]],
                                           r2[cols["start_date"]], r2[cols["end_date"]])

            dup_score = (0.35 * name_sim + 0.30 * geo + 0.15 * cost_sim + 0.20 * time_ov)

            if dup_score >= DUPLICATE_RISK_ALERT_MIN:
                pairs.append({
                    "work_id_1": r1[cols["id"]], "work_id_2": r2[cols["id"]],
                    "work_name_1": r1[cols["name"]], "work_name_2": r2[cols["name"]],
                    "district": r1[cols["district"]], "work_type": r1[cols["work_type"]],
                    "name_similarity": round(name_sim, 1),
                    "geo_proximity_score": round(geo, 1),
                    "cost_similarity": round(cost_sim, 1),
                    "time_overlap_score": round(time_ov, 1),
                    "duplicate_risk_score": round(dup_score, 1),
                })

    dup_df = pd.DataFrame(pairs).sort_values("duplicate_risk_score", ascending=False) if pairs else \
        pd.DataFrame(columns=["work_id_1", "work_id_2", "work_name_1", "work_name_2", "district",
                               "work_type", "name_similarity", "geo_proximity_score",
                               "cost_similarity", "time_overlap_score", "duplicate_risk_score"])

    # Roll up: max duplicate_risk_score per individual work_id
    per_work_max = {}
    for _, row in dup_df.iterrows():
        for wid in [row["work_id_1"], row["work_id_2"]]:
            per_work_max[wid] = max(per_work_max.get(wid, 0), row["duplicate_risk_score"])

    df["duplicate_risk_score"] = df[cols["id"]].map(per_work_max).fillna(0)

    return df, dup_df


# =================================================================================
# 4. EARLY-WARNING SIGNALS: DELAY + FUND DIVERSION
# =================================================================================

def compute_early_warning_signals(df, cols=COLS):
    df = df.copy()

    # --- Delay risk (0-100): scales with how many days overdue, saturates at 365 days ---
    df["delay_risk"] = np.clip(df["delay_days"] / 365 * 100, 0, 100)

    # --- Utilisation irregularity (0-100) ---
    # Two failure modes are both risky:
    #   (a) over-utilisation (>100%) -> spent more than sanctioned
    #   (b) high utilisation with low physical progress -> money out, no output
    over_util = np.clip(df["utilisation_pct"] - 100, 0, None) * 2         # penalize spend beyond sanction
    ghost_progress = np.clip(df["progress_gap"], 0, None) * 1.2            # fin% way ahead of phys% = ghost billing
    df["utilisation_irregularity"] = np.clip(over_util + ghost_progress, 0, 100)

    # --- Fund diversion score (0-100): composite early-warning for possible siphoning ---
    # Combines: ghost progress (paid without work), payment structuring/irregularity,
    # and cost-per-progress blowing up (spend per % of work done far above normal)
    cpp = df["cost_per_progress"]
    cpp_z = (cpp - cpp.median()) / (cpp.std(ddof=0) + 1e-9)
    cpp_risk = np.clip(cpp_z * 15, 0, 100)

    df["fund_diversion_score"] = np.clip(
        0.45 * np.clip(df["progress_gap"], 0, None) * 1.5 +
        0.35 * df["payment_irregularity"] +
        0.20 * cpp_risk,
        0, 100
    )

    return df


# =================================================================================
# 5. COMPOSITE RISK SCORE + BANDS
# =================================================================================

def minmax_0_100(s):
    s = s.astype(float)
    lo, hi = s.min(), s.max()
    if hi - lo < 1e-9:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo) * 100


def compute_composite_risk(df, weights=RISK_WEIGHTS):
    df = df.copy()

    # Normalize each sub-signal to a comparable 0-100 scale before weighting
    df["_n_anomaly"]     = df["anomaly_score"]                                  # already 0-100
    df["_n_cost"]        = minmax_0_100(np.clip(df["cost_overrun_pct"], 0, None))
    df["_n_delay"]       = df["delay_risk"]                                     # already 0-100
    df["_n_util_irreg"]  = df["utilisation_irregularity"]                       # already 0-100
    df["_n_duplicate"]   = df["duplicate_risk_score"]                           # already 0-100
    df["_n_diversion"]   = df["fund_diversion_score"]                           # already 0-100

    df["risk_score"] = (
        weights["anomaly"]           * df["_n_anomaly"] +
        weights["cost_overrun"]      * df["_n_cost"] +
        weights["delay"]             * df["_n_delay"] +
        weights["utilisation_irreg"] * df["_n_util_irreg"] +
        weights["duplicate"]         * df["_n_duplicate"] +
        weights["fund_diversion"]    * df["_n_diversion"]
    ).round(1)

    df["risk_score"] = df["risk_score"].clip(0, 100)

    def band(score):
        for lo, hi, label in RISK_BANDS:
            if lo <= score < hi or (label == "Critical" and score == 100):
                return label
        return "Low"

    df["risk_band"] = df["risk_score"].apply(band)

    return df


# =================================================================================
# 6. EXPLAINABLE REASONS
# =================================================================================

def generate_reasons(row, cols=COLS, top_n=4):
    """
    Builds a human-readable explanation string listing the top contributing
    factors behind a work's risk score, ranked by their (weight x normalized value)
    contribution to the final composite score.
    """
    contributions = {
        f"Anomaly pattern detected by ML model (score {row['anomaly_score']:.0f}/100 on cost/progress/payment behaviour)":
            RISK_WEIGHTS["anomaly"] * row["_n_anomaly"],
        f"Cost overrun of {row['cost_overrun_pct']:.0f}% vs sanctioned amount":
            RISK_WEIGHTS["cost_overrun"] * row["_n_cost"] if row["cost_overrun_pct"] > 5 else 0,
        f"Delayed by {row['delay_days']:.0f} days beyond planned completion":
            RISK_WEIGHTS["delay"] * row["_n_delay"] if row["delay_days"] > 15 else 0,
        f"Utilisation irregularity: {row['utilisation_pct']:.0f}% of funds used vs {row[cols['phys_progress']]:.0f}% physical work done":
            RISK_WEIGHTS["utilisation_irreg"] * row["_n_util_irreg"] if row["_n_util_irreg"] > 10 else 0,
        f"Possible duplicate/overlapping work found (duplicate risk {row['duplicate_risk_score']:.0f}/100)":
            RISK_WEIGHTS["duplicate"] * row["_n_duplicate"] if row["duplicate_risk_score"] > 0 else 0,
        f"Fund diversion signal: financial progress ({row[cols['fin_progress']]:.0f}%) far ahead of physical progress ({row[cols['phys_progress']]:.0f}%), payment irregularity {row['payment_irregularity']:.0f}/100":
            RISK_WEIGHTS["fund_diversion"] * row["_n_diversion"] if row["_n_diversion"] > 10 else 0,
    }

    ranked = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)
    reasons = [k for k, v in ranked if v > 1][:top_n]
    if not reasons:
        reasons = ["No single dominant risk driver; low overall risk profile"]
    return " | ".join(reasons)


# =================================================================================
# 7. TOP RISK DRIVERS (system-wide, for reporting)
# =================================================================================

def top_risk_drivers_report(df):
    """
    System-wide ranking of which underlying signals correlate most with high risk,
    to tell auditors/program managers WHERE to focus review effort.
    """
    driver_cols = {
        "Anomaly (Isolation Forest)": "_n_anomaly",
        "Cost overrun": "_n_cost",
        "Delay": "_n_delay",
        "Utilisation irregularity": "_n_util_irreg",
        "Duplicate/overlapping works": "_n_duplicate",
        "Fund diversion signal": "_n_diversion",
    }
    rows = []
    for label, col in driver_cols.items():
        if df[col].nunique() <= 1:
            corr = 0
        else:
            corr = df[col].corr(df["risk_score"])
        pct_flagged_high = (df.loc[df["risk_band"].isin(["Critical", "High"]), col] > 50).mean() * 100
        avg_value_high_risk = df.loc[df["risk_band"].isin(["Critical", "High"]), col].mean()
        rows.append({
            "risk_driver": label,
            "weight_in_composite": RISK_WEIGHTS[[k for k in RISK_WEIGHTS if k in col.replace("_n_", "") or True][0]] if False else None,
            "correlation_with_final_risk_score": round(corr, 3),
            "avg_score_among_high_risk_works": round(avg_value_high_risk, 1),
            "pct_of_high_risk_works_driven_by_this (score>50)": round(pct_flagged_high, 1),
        })
    report = pd.DataFrame(rows).sort_values("correlation_with_final_risk_score", ascending=False)
    report = report.drop(columns=["weight_in_composite"])
    return report


# =================================================================================
# 8. MAIN PIPELINE
# =================================================================================

def run_pipeline(input_csv=INPUT_CSV, output_dir=OUTPUT_DIR, cols=COLS):
    os.makedirs(output_dir, exist_ok=True)

    if os.path.exists(input_csv):
        print(f"[INFO] Loading real dataset from {input_csv}")
        df = pd.read_csv(input_csv)
    else:
        print(f"[INFO] '{input_csv}' not found — generating synthetic demo dataset instead.")
        df = generate_synthetic_data()
        df.to_csv(os.path.join(output_dir, "synthetic_input_used.csv"), index=False)

    print(f"[INFO] Loaded {len(df)} work records.")

    # 1. Feature engineering
    df = engineer_features(df, cols)

    # 2. Anomaly detection
    df, iso_model, scaler, X_raw = run_isolation_forest(df)
    df = anomaly_feature_contributions(df, X_raw)

    # 3. Duplicate detection
    df, dup_pairs_df = detect_duplicates(df, cols)

    # 4. Early warning signals (delay + fund diversion)
    df = compute_early_warning_signals(df, cols)

    # 5. Composite risk score + bands
    df = compute_composite_risk(df)

    # 6. Explainable reasons
    df["risk_reasons"] = df.apply(generate_reasons, axis=1, cols=cols)

    # 7. Top risk drivers report
    drivers_report = top_risk_drivers_report(df)

    # ----- Assemble final scored dataset (clean column selection) -----
    output_cols = [
        cols["id"], cols["name"], cols["work_type"], cols["district"],
        cols["sanctioned"], cols["expenditure"],
        cols["phys_progress"], cols["fin_progress"],
        "utilisation_pct", "cost_overrun_pct", "progress_gap", "delay_days",
        "payment_irregularity", "cost_per_progress",
        "anomaly_score", "anomaly_flag",
        "duplicate_risk_score",
        "delay_risk", "utilisation_irregularity", "fund_diversion_score",
        "risk_score", "risk_band", "risk_reasons",
    ]
    scored_df = df[output_cols].sort_values("risk_score", ascending=False)

    high_risk_alerts = scored_df[scored_df["risk_band"].isin(["Critical", "High"])].copy()

    # ----- Save deliverables -----
    scored_path   = os.path.join(output_dir, "scored_dataset.csv")
    alerts_path   = os.path.join(output_dir, "high_risk_alerts.csv")
    dup_path      = os.path.join(output_dir, "duplicate_pairs.csv")
    drivers_path  = os.path.join(output_dir, "top_risk_drivers.csv")

    scored_df.to_csv(scored_path, index=False)
    high_risk_alerts.to_csv(alerts_path, index=False)
    dup_pairs_df.to_csv(dup_path, index=False)
    drivers_report.to_csv(drivers_path, index=False)

    print("\n[SUMMARY]")
    print(f"  Total works scored           : {len(scored_df)}")
    print(f"  Critical risk                : {(scored_df['risk_band']=='Critical').sum()}")
    print(f"  High risk                    : {(scored_df['risk_band']=='High').sum()}")
    print(f"  Medium risk                  : {(scored_df['risk_band']=='Medium').sum()}")
    print(f"  Low risk                     : {(scored_df['risk_band']=='Low').sum()}")
    print(f"  Anomalies flagged (IF)       : {(scored_df['anomaly_flag']==1).sum()}")
    print(f"  Duplicate pairs found        : {len(dup_pairs_df)}")
    print(f"\n[OUTPUT FILES]\n  {scored_path}\n  {alerts_path}\n  {dup_path}\n  {drivers_path}")

    return {
        "scored_dataset": scored_df,
        "high_risk_alerts": high_risk_alerts,
        "duplicate_pairs": dup_pairs_df,
        "top_risk_drivers": drivers_report,
        "isolation_forest_model": iso_model,
    }


if __name__ == "__main__":
    results = run_pipeline()
