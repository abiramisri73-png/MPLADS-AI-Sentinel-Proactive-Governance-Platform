"""
=================================================================================
MAIN — end-to-end runnable flow: Data -> ML -> Dashboard -> AI Audit Assistant
=================================================================================
Run with:
    python3 main.py

What it does, in order:
    1. Loads your data (or generates synthetic demo data if none is found)
    2. Runs the unsupervised risk-scoring pipeline (anomaly, duplicates,
       early-warning signals, composite risk score)
    3. If a fraud-label column is present, also trains and applies the
       supervised fraud model, producing a hybrid risk score
    4. Generates AI Audit Assistant summaries for the top 20 highest-risk
       works and the top 5 riskiest districts
    5. Prints a summary + tells you how to launch the interactive dashboard

The dashboard itself (Streamlit) is a separate long-running process by
design -- `main.py` prepares everything it needs and exits; you then run
`streamlit run dashboard_app.py` to open the interactive UI, or this
script can launch it for you with --dashboard.
=================================================================================
"""

import argparse
import os
import subprocess
import sys

import risk_scoring_pipeline as rsp
import supervised_fraud_model as sfm
import audit_assistant as aa

OUTPUT_DIR = "outputs"


def run_full_flow(input_csv=None, top_n_works=20, top_n_districts=5, use_llm=False, launch_dashboard=False):
    input_csv = input_csv or rsp.INPUT_CSV

    print("=" * 80)
    print("STEP 1-2/4 — Unsupervised risk scoring (anomaly + duplicates + composite score)")
    print("=" * 80)
    rsp.run_pipeline(input_csv=input_csv, output_dir=OUTPUT_DIR)

    print("\n" + "=" * 80)
    print("STEP 3/4 — Supervised fraud model (only runs if a fraud-label column exists)")
    print("=" * 80)
    try:
        supervised_result = sfm.run_supervised_pipeline(input_csv=input_csv, output_dir=OUTPUT_DIR)
    except Exception as e:
        print(f"[WARN] Supervised layer skipped: {e}")
        supervised_result = None

    final_dataset_path = (
        os.path.join(OUTPUT_DIR, "scored_dataset_hybrid.csv") if supervised_result is not None
        else os.path.join(OUTPUT_DIR, "scored_dataset.csv")
    )

    print("\n" + "=" * 80)
    print("STEP 4/4 — AI Audit Assistant: batch summaries")
    print("=" * 80)
    import pandas as pd
    final_df = pd.read_csv(final_dataset_path)
    aa.batch_generate_summaries(
        final_df, output_dir=OUTPUT_DIR,
        top_n_works=top_n_works, top_n_districts=top_n_districts,
        use_llm=use_llm,
    )

    print("\n" + "=" * 80)
    print("PIPELINE COMPLETE")
    print("=" * 80)
    print(f"Final scored dataset : {final_dataset_path}")
    print(f"All outputs in       : {os.path.abspath(OUTPUT_DIR)}/")
    print("\nTo explore results interactively, run:")
    print("    streamlit run dashboard_app.py")

    if launch_dashboard:
        print("\n[INFO] Launching dashboard (Ctrl+C to stop)...")
        subprocess.run([sys.executable, "-m", "streamlit", "run", "dashboard_app.py"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full works-risk detection + audit assistant pipeline.")
    parser.add_argument("--input", type=str, default=None, help="Path to your works CSV (default: works_data.csv, or synthetic demo data if missing).")
    parser.add_argument("--top-works", type=int, default=20, help="Number of highest-risk works to generate audit summaries for.")
    parser.add_argument("--top-districts", type=int, default=5, help="Number of riskiest districts to generate audit summaries for.")
    parser.add_argument("--use-llm", action="store_true", help="Polish audit summaries with Claude (requires ANTHROPIC_API_KEY).")
    parser.add_argument("--dashboard", action="store_true", help="Launch the Streamlit dashboard after the pipeline finishes.")
    args = parser.parse_args()

    run_full_flow(
        input_csv=args.input,
        top_n_works=args.top_works,
        top_n_districts=args.top_districts,
        use_llm=args.use_llm,
        launch_dashboard=args.dashboard,
    )
