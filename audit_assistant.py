"""
=================================================================================
AI AUDIT ASSISTANT — concise, explainable audit summaries + recommendations
=================================================================================
Turns a scored work (or a district's works) into a short, professional,
actionable audit summary -- the kind a human auditor would write after
reviewing the dashboard, but generated instantly for every flagged record.

Two modes, same output shape:

  1. TEMPLATE MODE (default, always available, zero dependencies/cost)
     Builds the summary from the actual computed risk numbers using a
     structured narrative template. Deterministic, fast, and 100% grounded
     in the data -- nothing is invented. This is what runs in the dashboard
     by default and what CI/offline batch runs use.

  2. LLM MODE (optional -- used only if ANTHROPIC_API_KEY is set)
     Sends the SAME structured facts used in template mode to Claude and
     asks it only to rewrite them into more natural prose -- not to
     add new findings. This keeps the LLM from hallucinating numbers while
     still getting more fluent, varied language. If the API key is missing,
     the network call fails, or the SDK isn't installed, this silently
     falls back to template mode -- the assistant never breaks because an
     LLM call didn't work.

Deliverables:
    - generate_work_audit_summary(row)       -> str  (6-10 lines)
    - generate_district_audit_summary(df, district) -> str (6-10 lines)
    - batch_generate_summaries(scored_df, ...) -> saves JSON + CSV of
      top-20 work summaries and top-5 district summaries

Tools: pandas, (optional) anthropic SDK
=================================================================================
"""

import os
import json
import pandas as pd

# ---- Optional LLM support -------------------------------------------------
_LLM_AVAILABLE = False
try:
    import anthropic
    _LLM_AVAILABLE = bool(os.environ.get("ANTHROPIC_API_KEY"))
except ImportError:
    _LLM_AVAILABLE = False

LLM_MODEL = "claude-sonnet-4-5"   # override if needed


# =================================================================================
# 1. FACT EXTRACTION — turns a scored row into a structured, grounded fact sheet
# =================================================================================

def _fmt_money(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "N/A"
    if v >= 1e7:
        return f"₹{v/1e7:.2f} Cr"
    if v >= 1e5:
        return f"₹{v/1e5:.2f} L"
    return f"₹{v:,.0f}"


def extract_work_facts(row):
    """Pulls every number the summary is allowed to talk about, in one place,
    so template mode and LLM mode both work from identical grounded facts."""
    g = lambda k, default=None: row[k] if k in row and pd.notna(row[k]) else default

    risk_score = g("hybrid_risk_score", g("risk_score", 0))
    risk_band = g("hybrid_risk_band", g("risk_band", "Low"))

    facts = {
        "work_id": g("work_id", "UNKNOWN"),
        "work_name": g("work_name", "Unnamed work"),
        "district": g("district", "Unknown district"),
        "work_type": g("work_type", "Unspecified"),
        "risk_score": round(float(risk_score), 1),
        "risk_band": risk_band,
        "anomaly_score": round(float(g("anomaly_score", 0)), 1),
        "anomaly_flag": bool(g("anomaly_flag", 0)),
        "cost_overrun_pct": round(float(g("cost_overrun_pct", 0)), 1),
        "utilisation_pct": round(float(g("utilisation_pct", 0)), 1),
        "physical_progress_pct": round(float(g("physical_progress_pct", 0)), 1) if g("physical_progress_pct") is not None else None,
        "financial_progress_pct": round(float(g("financial_progress_pct", 0)), 1) if g("financial_progress_pct") is not None else None,
        "progress_gap": round(float(g("progress_gap", 0)), 1),
        "delay_days": round(float(g("delay_days", 0)), 0),
        "payment_irregularity": round(float(g("payment_irregularity", 0)), 1),
        "duplicate_risk_score": round(float(g("duplicate_risk_score", 0)), 1),
        "fund_diversion_score": round(float(g("fund_diversion_score", 0)), 1),
        "supervised_fraud_probability": g("supervised_fraud_probability"),
        "sanctioned_amount": g("sanctioned_amount"),
        "expenditure": g("expenditure"),
    }
    return facts


def extract_district_facts(district_df, district_name):
    n_works = len(district_df)
    risk_col = "hybrid_risk_score" if "hybrid_risk_score" in district_df.columns else "risk_score"
    band_col = "hybrid_risk_band" if "hybrid_risk_band" in district_df.columns else "risk_band"

    facts = {
        "district": district_name,
        "n_works": n_works,
        "avg_risk_score": round(district_df[risk_col].mean(), 1),
        "n_critical": int((district_df[band_col] == "Critical").sum()),
        "n_high": int((district_df[band_col] == "High").sum()),
        "n_anomalies": int(district_df.get("anomaly_flag", pd.Series(dtype=int)).sum()),
        "n_duplicates_flagged": int((district_df.get("duplicate_risk_score", pd.Series(dtype=float)) > 0).sum()),
        "avg_cost_overrun_pct": round(district_df.get("cost_overrun_pct", pd.Series(dtype=float)).mean(), 1),
        "avg_delay_days": round(district_df.get("delay_days", pd.Series(dtype=float)).mean(), 0),
        "avg_fund_diversion_score": round(district_df.get("fund_diversion_score", pd.Series(dtype=float)).mean(), 1),
        "top_risk_work_ids": district_df.sort_values(risk_col, ascending=False)["work_id"].head(3).tolist()
            if "work_id" in district_df.columns else [],
        "dominant_work_type": district_df["work_type"].mode().iloc[0] if "work_type" in district_df.columns and not district_df["work_type"].mode().empty else "N/A",
    }
    return facts


# =================================================================================
# 2. TEMPLATE-MODE NARRATIVE GENERATION (grounded, deterministic, always works)
# =================================================================================

def _work_findings_lines(f):
    lines = []

    lines.append(
        f"**{f['work_id']} — {f['work_name']}** ({f['work_type']}, {f['district']}) "
        f"carries a risk score of **{f['risk_score']}/100 ({f['risk_band']})**."
    )

    if f["anomaly_flag"] or f["anomaly_score"] >= 50:
        lines.append(
            f"The ML anomaly model flagged this work (anomaly score {f['anomaly_score']}/100), "
            f"indicating its cost, progress, and payment pattern deviate materially from comparable works."
        )

    if f["cost_overrun_pct"] > 10:
        lines.append(f"Expenditure exceeds the sanctioned amount by {f['cost_overrun_pct']}%, well above normal variance.")
    elif f["cost_overrun_pct"] < -20:
        lines.append(f"Recorded expenditure is {abs(f['cost_overrun_pct']):.0f}% below sanction, worth confirming against physical progress.")

    if f["progress_gap"] > 15:
        lines.append(
            f"Financial progress ({f['financial_progress_pct']}%) is running {f['progress_gap']:.0f} points ahead of "
            f"physical progress ({f['physical_progress_pct']}%) — funds appear to have been drawn faster than work was executed."
        )

    if f["delay_days"] > 30:
        lines.append(f"The work is running {int(f['delay_days'])} days behind its planned completion date.")

    if f["payment_irregularity"] > 30:
        lines.append(f"Payment pattern shows irregularity (score {f['payment_irregularity']}/100) — e.g. unusually large or frequent transactions.")

    if f["duplicate_risk_score"] > 0:
        lines.append(f"Flagged as a possible duplicate/overlapping work (duplicate risk {f['duplicate_risk_score']}/100) — verify against nearby sanctioned works.")

    if f["fund_diversion_score"] > 40:
        lines.append(f"Fund diversion signal is elevated ({f['fund_diversion_score']}/100), combining payment and progress-mismatch indicators.")

    if f["supervised_fraud_probability"] is not None:
        lines.append(f"The trained fraud-classification model independently estimates a {f['supervised_fraud_probability']:.0f}% probability of fraud based on confirmed historical cases.")

    return lines


def _recommend_actions(f):
    actions = []
    if f["risk_band"] in ("Critical", "High"):
        actions.append("prioritize for physical site verification")
    if f["progress_gap"] > 15 or f["fund_diversion_score"] > 40:
        actions.append("cross-check utilisation certificates against measured physical progress before releasing further payments")
    if f["cost_overrun_pct"] > 10:
        actions.append("obtain justification for cost escalation and compare against approved revised estimates")
    if f["duplicate_risk_score"] > 0:
        actions.append("reconcile against nearby/similar sanctioned works to rule out duplicate funding")
    if f["delay_days"] > 30:
        actions.append("request an updated completion timeline and reasons for delay from the implementing agency")
    if f["payment_irregularity"] > 30:
        actions.append("review the transaction ledger for split-payment or structuring patterns")
    if not actions:
        actions.append("continue routine monitoring; no urgent action required at this time")
    return actions


def generate_work_audit_summary_template(row):
    f = extract_work_facts(row)
    lines = _work_findings_lines(f)
    actions = _recommend_actions(f)

    summary_lines = lines[:6]  # keep findings concise
    action_text = "**Recommended actions:** " + "; ".join(actions[:4]) + "."
    summary_lines.append(action_text)
    return "\n".join(summary_lines)


def _district_findings_lines(f):
    lines = []
    lines.append(
        f"**{f['district']}** has {f['n_works']} tracked works with an average risk score of "
        f"**{f['avg_risk_score']}/100**, dominated by {f['dominant_work_type']} projects."
    )
    lines.append(f"{f['n_critical']} work(s) fall in the Critical band and {f['n_high']} in High — together requiring priority review.")
    if f["n_anomalies"] > 0:
        lines.append(f"{f['n_anomalies']} work(s) were flagged as statistical anomalies by the ML detection model.")
    if f["n_duplicates_flagged"] > 0:
        lines.append(f"{f['n_duplicates_flagged']} work(s) show possible duplicate/overlapping funding within the district.")
    if f["avg_cost_overrun_pct"] > 5:
        lines.append(f"Average cost overrun across the district's works is {f['avg_cost_overrun_pct']}%, above the expected range.")
    if f["avg_delay_days"] > 20:
        lines.append(f"Works are delayed by an average of {int(f['avg_delay_days'])} days versus planned schedules.")
    if f["avg_fund_diversion_score"] > 30:
        lines.append(f"District-wide fund diversion signal averages {f['avg_fund_diversion_score']}/100, indicating a pattern rather than isolated cases.")
    if f["top_risk_work_ids"]:
        lines.append(f"Highest-priority works for review: {', '.join(f['top_risk_work_ids'])}.")
    return lines


def _district_recommend_actions(f):
    actions = []
    if f["n_critical"] + f["n_high"] > 0:
        actions.append(f"schedule field audits for the {f['n_critical'] + f['n_high']} Critical/High works identified")
    if f["n_duplicates_flagged"] > 0:
        actions.append("conduct a district-level reconciliation of works to eliminate duplicate/overlapping sanctions")
    if f["avg_cost_overrun_pct"] > 5:
        actions.append("review the district engineer's cost-estimation and approval process")
    if f["avg_delay_days"] > 20:
        actions.append("assess implementing agency capacity and contractor performance across ongoing works")
    if not actions:
        actions.append("maintain standard quarterly review cadence; district shows no systemic red flags")
    return actions


def generate_district_audit_summary_template(district_df, district_name):
    f = extract_district_facts(district_df, district_name)
    lines = _district_findings_lines(f)
    actions = _district_recommend_actions(f)
    summary_lines = lines[:6]
    summary_lines.append("**Recommended actions:** " + "; ".join(actions[:4]) + ".")
    return "\n".join(summary_lines)


# =================================================================================
# 3. OPTIONAL LLM-POLISHED MODE (facts are fixed; LLM only rewords/tightens)
# =================================================================================

def _llm_rewrite(facts, template_summary, subject_label):
    """
    Sends the SAME grounded facts (not raw data, not free rein) to Claude and asks
    for a tighter, more natural rewrite. If anything goes wrong -- no key, no
    network, SDK error -- returns None so the caller falls back to template mode.
    """
    if not _LLM_AVAILABLE:
        return None
    try:
        client = anthropic.Anthropic()
        prompt = f"""You are an audit assistant for a government public-works monitoring system.
Below are STRUCTURED, VERIFIED facts about {subject_label}, followed by a template-generated
draft summary built directly from those facts.

Rewrite the draft into a polished 6-10 line professional audit summary. Rules:
- Do NOT invent, add, or infer any fact, number, or finding not present below.
- Keep every number exactly as given.
- Professional, neutral, actionable tone -- suitable for a government auditor.
- End with a clear "Recommended actions:" line.

FACTS (JSON):
{json.dumps(facts, indent=2, default=str)}

DRAFT SUMMARY:
{template_summary}

Rewritten summary:"""
        resp = client.messages.create(
            model=LLM_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        return text.strip() if text.strip() else None
    except Exception as e:
        print(f"[WARN] LLM rewrite failed ({e}); falling back to template summary.")
        return None


def generate_work_audit_summary(row, use_llm=True):
    facts = extract_work_facts(row)
    template = generate_work_audit_summary_template(row)
    if use_llm and _LLM_AVAILABLE:
        polished = _llm_rewrite(facts, template, f"work {facts['work_id']} ({facts['work_name']})")
        if polished:
            return polished
    return template


def generate_district_audit_summary(district_df, district_name, use_llm=True):
    facts = extract_district_facts(district_df, district_name)
    template = generate_district_audit_summary_template(district_df, district_name)
    if use_llm and _LLM_AVAILABLE:
        polished = _llm_rewrite(facts, template, f"{district_name} district")
        if polished:
            return polished
    return template


# =================================================================================
# 4. BATCH GENERATION — top-20 works, top-5 districts
# =================================================================================

def batch_generate_summaries(scored_df, output_dir="outputs", top_n_works=20, top_n_districts=5, use_llm=False):
    os.makedirs(output_dir, exist_ok=True)
    risk_col = "hybrid_risk_score" if "hybrid_risk_score" in scored_df.columns else "risk_score"

    # ---- Top-N work summaries ----
    top_works = scored_df.sort_values(risk_col, ascending=False).head(top_n_works)
    work_summaries = []
    for _, row in top_works.iterrows():
        summary = generate_work_audit_summary(row, use_llm=use_llm)
        work_summaries.append({
            "work_id": row.get("work_id"),
            "work_name": row.get("work_name"),
            "district": row.get("district"),
            "risk_score": float(row.get(risk_col, 0)),
            "risk_band": row.get("hybrid_risk_band", row.get("risk_band")),
            "summary": summary,
        })

    # ---- Top-N district summaries ----
    district_risk = scored_df.groupby("district")[risk_col].mean().sort_values(ascending=False)
    top_districts = district_risk.head(top_n_districts).index.tolist()
    district_summaries = []
    for d in top_districts:
        d_df = scored_df[scored_df["district"] == d]
        summary = generate_district_audit_summary(d_df, d, use_llm=use_llm)
        district_summaries.append({
            "district": d,
            "n_works": len(d_df),
            "avg_risk_score": float(d_df[risk_col].mean()),
            "summary": summary,
        })

    # ---- Save ----
    works_json_path = os.path.join(output_dir, "audit_summaries_works.json")
    districts_json_path = os.path.join(output_dir, "audit_summaries_districts.json")
    with open(works_json_path, "w") as f:
        json.dump(work_summaries, f, indent=2, default=str)
    with open(districts_json_path, "w") as f:
        json.dump(district_summaries, f, indent=2, default=str)

    pd.DataFrame(work_summaries).to_csv(os.path.join(output_dir, "audit_summaries_works.csv"), index=False)
    pd.DataFrame(district_summaries).to_csv(os.path.join(output_dir, "audit_summaries_districts.csv"), index=False)

    print(f"[INFO] Generated {len(work_summaries)} work summaries and {len(district_summaries)} district summaries "
          f"({'LLM-polished' if use_llm and _LLM_AVAILABLE else 'template mode'}).")
    print(f"[OUTPUT FILES]\n  {works_json_path}\n  {districts_json_path}")

    return work_summaries, district_summaries


if __name__ == "__main__":
    # Standalone smoke test using whatever scored dataset is available
    for candidate in ["outputs/scored_dataset_hybrid.csv", "outputs/scored_dataset.csv"]:
        if os.path.exists(candidate):
            df = pd.read_csv(candidate)
            print(f"[INFO] Loaded {candidate} ({len(df)} rows)")
            batch_generate_summaries(df, use_llm=False)
            break
    else:
        print("[ERROR] No scored dataset found. Run risk_scoring_pipeline.py first.")
