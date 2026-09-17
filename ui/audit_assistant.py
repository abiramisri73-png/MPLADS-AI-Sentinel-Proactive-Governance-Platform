"""
ui/audit_assistant.py
----------------------
The AI Audit Assistant page. A chat-style front end over audit_engine.py:
pick a work or district (or arrive here already deep-linked from the
Projects page) and get a grounded, explainable summary + recommended
actions. Every summary is built from the same computed risk numbers shown
elsewhere in the dashboard -- this page doesn't compute anything new, it
just narrates what's already been scored.
"""

import streamlit as st

import audit_engine as engine
from utils.data_loader import get_scoped_projects


def _add_message(role: str, content: str) -> None:
    st.session_state["chat_history"].append({"role": role, "content": content})


def render_audit_assistant() -> None:
    st.markdown("## 🤖 AI Audit Assistant")
    st.caption(
        "Ask for a summary of any work or district. Every summary is generated "
        "from the same risk numbers used across this dashboard — nothing is invented."
    )

    df = get_scoped_projects()
    if df.empty:
        st.warning("No scored data found. Run `python3 main.py` first.")
        return

    llm_available = engine._LLM_AVAILABLE
    use_llm = st.toggle(
        "Polish summaries with Claude",
        value=False,
        disabled=not llm_available,
        help="Requires ANTHROPIC_API_KEY in the environment. The model only rewords "
             "the grounded facts below — it can't add or change a number."
             if llm_available else
             "Set ANTHROPIC_API_KEY to enable this. Currently running in template mode.",
    )

    st.markdown("---")

    # ---- Quick-pick controls (also used by deep links from Projects/Reports) ----
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        work_options = df.sort_values("risk_score", ascending=False)["work_id"].tolist()
        default_work = st.session_state.pop("assistant_prefill_work", None)
        default_idx = work_options.index(default_work) if default_work in work_options else 0
        pick_work = st.selectbox("Summarize a work", work_options, index=default_idx if work_options else 0)
    with c2:
        district_options = sorted(df["district"].dropna().unique().tolist())
        pick_district = st.selectbox("...or a district", district_options)
    with c3:
        st.write("")
        st.write("")
        work_btn = st.button("Summarize work", use_container_width=True)
        district_btn = st.button("Summarize district", use_container_width=True)

    if work_btn and pick_work:
        row = df[df["work_id"] == pick_work].iloc[0]
        _add_message("user", f"Summarize work **{pick_work}**")
        with st.spinner("Generating audit summary..."):
            summary = engine.generate_work_audit_summary(row, use_llm=use_llm)
        _add_message("assistant", summary)

    if district_btn and pick_district:
        d_df = df[df["district"] == pick_district]
        _add_message("user", f"Summarize district **{pick_district}**")
        with st.spinner("Generating district summary..."):
            summary = engine.generate_district_audit_summary(d_df, pick_district, use_llm=use_llm)
        _add_message("assistant", summary)

    # ---- Free-text box: matched against work IDs / district names ----
    prompt = st.chat_input("Or type a work ID, work name, or district name...")
    if prompt:
        _add_message("user", prompt)
        match_work = df[
            df["work_id"].astype(str).str.lower().str.contains(prompt.lower()) |
            df["work_name"].astype(str).str.lower().str.contains(prompt.lower())
        ]
        match_district = [d for d in district_options if d.lower() in prompt.lower()]

        if not match_work.empty:
            row = match_work.sort_values("risk_score", ascending=False).iloc[0]
            with st.spinner("Generating audit summary..."):
                summary = engine.generate_work_audit_summary(row, use_llm=use_llm)
            _add_message("assistant", summary)
        elif match_district:
            d_df = df[df["district"] == match_district[0]]
            with st.spinner("Generating district summary..."):
                summary = engine.generate_district_audit_summary(d_df, match_district[0], use_llm=use_llm)
            _add_message("assistant", summary)
        else:
            _add_message(
                "assistant",
                f"I couldn't match \"{prompt}\" to a work ID, work name, or district in the "
                f"current scope. Try the dropdowns above, or check the spelling.",
            )

    st.markdown("---")

    # ---- Chat history ----
    if not st.session_state["chat_history"]:
        st.info("No summaries generated yet this session. Pick a work or district above to get started.")
    else:
        for msg in st.session_state["chat_history"]:
            with st.chat_message("user" if msg["role"] == "user" else "assistant"):
                st.markdown(msg["content"])

        if st.button("Clear conversation"):
            st.session_state["chat_history"] = []
            st.rerun()
