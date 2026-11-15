"""Run with: streamlit run app.py --server.address 127.0.0.1"""
from __future__ import annotations

import hmac
import json
import os
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st

from core import (
    CASE_PATH, INCOMING_PATH, DB_PATH, CATEGORIES, PRIORITIES, PRIORITY_NAMES,
    SearchIndex, WorkflowStore, grounded_template, load_csv, propose_offline, priority_guardrail,
)
from providers import (
    DEFAULT_OLLAMA_BASE, DEFAULT_OLLAMA_MODEL, DEFAULT_GROQ_MODEL,
    ProviderError, classify_groq, draft_ollama, draft_groq,
)

st.set_page_config(page_title="SupportFlow | Human-reviewed Email AI", page_icon="📨", layout="wide")
st.markdown("""
<style>
.block-container { padding-top: 1.55rem; max-width: 1320px; }
h1 { letter-spacing: -0.035em; }
[data-testid="stMetric"] { border: 1px solid rgba(128,128,128,0.22); border-radius: 12px; padding: 10px 16px; }
</style>""", unsafe_allow_html=True)

# A minimal demo access gate (not corporate authentication). Configure the secret
# SUPPORTFLOW_DEMO_PASSWORD on public Streamlit Cloud deployments to avoid anonymous
# consumption of the shared Groq API quota. Never persist the provided password.
demo_password = os.getenv("SUPPORTFLOW_DEMO_PASSWORD", "")
if demo_password and not st.session_state.get("supportflow_demo_access", False):
    st.title("SupportFlow demo access")
    st.info("This is a shared demonstration environment using synthetic support emails.")
    with st.form("demo_access"):
        entered_password = st.text_input("Demo access password", type="password")
        submitted = st.form_submit_button("Enter demo", type="primary")
    if submitted:
        if hmac.compare_digest(entered_password, demo_password):
            st.session_state["supportflow_demo_access"] = True
            st.rerun()
        else:
            st.error("Incorrect demo password.")
    st.stop()


@st.cache_data(show_spinner=False)
def get_datasets():
    return load_csv(CASE_PATH), load_csv(INCOMING_PATH)


@st.cache_resource(show_spinner=False)
def get_index():
    return SearchIndex(load_csv(CASE_PATH))


cases, incoming = get_datasets()
index = get_index()
store = WorkflowStore(DB_PATH)
manifest = json.loads((CASE_PATH.parent / "manifest.json").read_text(encoding="utf-8"))
incoming_map = {t["ticket_id"]: t for t in incoming}

with st.sidebar:
    st.header("Demo settings")
    st.info("SYNTHETIC DATA ONLY. No email sending tool exists in this app.")
    reviewer = st.text_input("Human reviewer", value="Demo Reviewer")
    st.subheader("Classification engine")
    groq_key = os.getenv("GROQ_API_KEY", "")
    groq_model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    classifier = st.radio(
        "Choose classification mode",
        ["Groq API (real AI)", "Offline illustrative rules"],
        index=(0 if groq_key else 1),
        help="Groq provides a structured, human-reviewed AI proposal. Offline rules are not AI.",
    )
    st.subheader("Reply drafting engine")
    drafter = st.radio(
        "Choose drafting mode",
        ["Groq API (real)", "Grounded template (offline)", "Ollama local LLM (real)"],
        index=(0 if groq_key else 1),
        help="Groq creates a draft, not a sent email. The template is deterministic, not AI.",
    )
    if classifier.startswith("Groq") or drafter.startswith("Groq"):
        if groq_key:
            st.success("Groq API key configured server-side (not displayed in the browser).")
        else:
            st.warning("GROQ_API_KEY is missing. Add it to Streamlit Cloud Secrets or your local environment.")
        groq_model = st.text_input(
            "Groq model (both AI tasks)", value=groq_model,
            help="openai/gpt-oss-20b supports strict structured classification outputs.",
        )
        st.caption("Only synthetic data may be sent to Groq in this demo; classification and drafting are distinct API calls.")
    ollama_base = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE)
    ollama_model = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    if drafter.startswith("Ollama"):
        ollama_base = st.text_input("Ollama URL", value=ollama_base)
        ollama_model = st.text_input("Ollama model", value=ollama_model)
    st.divider()
    st.caption("Dataset: `" + manifest["dataset_id"] + "`\n\nPolicy: `support-priority-v1` · Retrieval: `tfidf-v1` · No auto-send")

st.title("📨 SupportFlow — Human-reviewed email automation")
st.caption("Working proof of concept · synthetic October 2026 cases · both decisions require human approval · no automatic sending")

custom_incoming = store.custom_tickets()
incoming_map.update({t["ticket_id"]: t for t in custom_incoming})
statuses = store.all_statuses()
counts = Counter(statuses.values())
summary = st.columns(4)
summary[0].metric("Historical resolved cases", f"{len(cases):,}")
summary[1].metric("Incoming demo tickets", len(incoming_map))
summary[2].metric("Classification awaiting review", counts.get("CLASSIFICATION_PENDING", 0))
summary[3].metric("Drafts approved, not sent", counts.get("DRAFT_APPROVED", 0))

process_tab, kb_tab, eval_tab, design_tab = st.tabs([
    "01 · Process an email", "02 · Historical knowledge", "03 · Evaluation & audit", "04 · Architecture"
])

with process_tab:
    st.subheader("Incoming ticket")
    with st.expander("+ Create a synthetic ticket to test your own example", expanded=False):
        st.caption("Use fictional or sanitized text only. Custom demo tickets are stored in local SQLite.")
        customers = sorted({(c["tenant_id"], c["customer"]) for c in cases})
        with st.form("custom_synthetic_ticket"):
            selected_customer = st.selectbox("Synthetic company", customers, format_func=lambda x: x[1])
            new_subject = st.text_input("Email subject", placeholder="Dispatch requests failing at dock 7")
            new_body = st.text_area("Email message", placeholder="Drivers report that ...", height=110)
            add_custom = st.form_submit_button("Add new demo ticket")
        if add_custom:
            try:
                created = store.add_demo_ticket(tenant_id=selected_customer[0], customer=selected_customer[1],
                                                subject=new_subject, body=new_body)
                st.session_state["demo_ticket_selected"] = created["ticket_id"]
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    choice = st.selectbox("Select a synthetic customer email", list(incoming_map), key="demo_ticket_selected",
                          format_func=lambda key: f"{key}  ·  {incoming_map[key]['subject']}  ·  {incoming_map[key]['customer']}")
    ticket = incoming_map[choice]
    state = store.get(choice)
    status = state["status"]
    left, right = st.columns([2.3, 1], gap="large")
    with left:
        st.markdown(f"**Subject:** {ticket['subject']}")
        st.markdown(f"**From company:** {ticket['customer']}  ·  **Received:** {ticket['received_at'][:10]}")
        st.markdown("**Customer message:**")
        st.info(ticket["body"])
    with right:
        st.markdown("**Current workflow state**")
        st.code(status, language=None)
        st.caption("All changes are audited in local SQLite.")
        if st.button("Reset this demo ticket", use_container_width=True, help="For demonstration replay; audit history is retained"):
            store.reset_demo(choice, reviewer or "Demo Reviewer")
            st.session_state.pop(f"edit_{choice}", None)
            st.rerun()
    st.divider()
    st.markdown("#### Gate 1 — Human verification of classification")
    if status == "NEW":
        st.write("The system first proposes a priority and issue category. It **cannot continue** until a reviewer confirms them.")
        if st.button("1. Propose priority and category", type="primary"):
            try:
                with st.spinner("Analyzing the email..."):
                    if classifier.startswith("Groq"):
                        proposal = classify_groq(
                            ticket["subject"], ticket["body"],
                            api_key=groq_key, model=groq_model,
                        )
                    else:
                        proposal = propose_offline(ticket["subject"], ticket["body"])
                    store.propose(choice, proposal)
                st.rerun()
            except (ProviderError, ValueError) as exc:
                st.error(str(exc) + " · No automatic substitution was made.")
    elif status == "CLASSIFICATION_PENDING":
        proposal = json.loads(state["proposal_json"])
        st.info(f"**Proposed priority: {proposal['priority']}** — {PRIORITY_NAMES[proposal['priority']]}\n\n"
                f"**Proposed category:** {CATEGORIES.get(proposal['category'], proposal['category'])}\n\n"
                f"**Source:** {proposal['source']}")
        if proposal.get("raw_model_priority"):
            st.warning(f"Business rule escalated model proposal from {proposal['raw_model_priority']} to {proposal['priority']} for human review.")
        if proposal.get("model_confidence") is not None:
            st.caption(f"Provider confidence indicator: {proposal['model_confidence']:.3f} (NOT calibrated accuracy)")
        st.write("**Why this classification was proposed:** " + proposal.get("explanation", "No rationale available."))
        st.caption("Reported impact signals: " + (" · ".join(proposal["signals"]) if proposal["signals"] else "None identified"))
        if proposal["source"].startswith("Groq"):
            st.caption("Structured-output format was validated. Priority correctness still requires human review.")
        with st.form(key=f"priority_review_{choice}"):
            selected_priority = st.selectbox("Human-approved priority", PRIORITIES,
                                             index=PRIORITIES.index(proposal["priority"]),
                                             format_func=lambda p: f"{p} — {PRIORITY_NAMES[p]}")
            cats = list(CATEGORIES)
            selected_category = st.selectbox("Human-approved issue category", cats,
                                             index=cats.index(proposal["category"]), format_func=lambda c: CATEGORIES[c])
            floor, _ = priority_guardrail(ticket["subject"] + "\n" + ticket["body"])
            override_ack = st.checkbox("I verified the impact and explicitly authorize any downgrade of a high-impact case.", value=False) if floor else False
            confirmed = st.form_submit_button("Approve classification", type="primary")
        if confirmed:
            if floor and PRIORITIES.index(selected_priority) > PRIORITIES.index(floor) and not override_ack:
                st.error(f"A {floor} impact signal is present. Confirm the high-impact downgrade before saving a lower priority.")
            else:
                try:
                    store.approve_classification(choice, selected_priority, selected_category, reviewer)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    else:
        st.success(f"Classification approved by {state['review_by']} — {state['approved_priority']} · {CATEGORIES[state['approved_category']]}")

    if status in {"CLASSIFIED", "DRAFT_PENDING", "DRAFT_APPROVED"}:
        st.divider()
        st.markdown("#### Retrieve historical resolved cases")
        matches = index.search(ticket, state["approved_category"], top_k=4)
        st.caption("TF-IDF pilot retrieval · same tenant only · approved/current/resolved cases only · not yet production hybrid vector search")
        if not matches:
            st.warning("No verified matching resolutions found. A draft must not guess the fix.")
        else:
            for match in matches:
                with st.expander(f"{match['case_id']} · {match['subject']} · relevance {match['similarity_score']:.3f}"):
                    st.write(f"**Category:** {CATEGORIES.get(match['category'], match['category'])} · **Historical priority:** {match['priority']}")
                    st.write(f"**Past verified resolution:** {match['verified_resolution']}")
                    st.write(f"**Safe diagnostic step for a new case:** {match['safe_next_step']}")
                    st.caption(f"Tenant-isolated · {match['resolved_at'][:10]} · runbook {match['runbook_version']}")
        st.divider()
        st.markdown("#### Gate 2 — Human verification of the reply draft")
        if status == "CLASSIFIED":
            st.write("Generate a draft using only the approved classification and tenant-authorized historical evidence. External providers receive synthetic data only.")
            if st.button("2. Prepare grounded email draft", type="primary"):
                try:
                    with st.spinner("Preparing the draft..."):
                        if drafter.startswith("Groq"):
                            draft = draft_groq(ticket, state["approved_priority"], state["approved_category"],
                                               matches, api_key=groq_key, model=groq_model)
                            provider = f"Groq LIVE LLM ({groq_model})"
                        elif drafter.startswith("Ollama"):
                            draft = draft_ollama(ticket, state["approved_priority"], state["approved_category"],
                                                 matches, base_url=ollama_base, model=ollama_model)
                            provider = f"Ollama local LLM ({ollama_model})"
                        else:
                            draft = grounded_template(ticket, state["approved_priority"], matches)
                            provider = "Offline deterministic template (NOT AI-generated)"
                        store.save_draft(choice, draft, [m["case_id"] for m in matches], provider)
                    st.rerun()
                except (ProviderError, ValueError) as exc:
                    st.error(str(exc) + " · Draft was not saved or sent.")
        elif status == "DRAFT_PENDING":
            st.warning("Reply awaiting explicit human approval. No email has been sent.")
            st.caption(f"Drafting method: {state['model_name']}")
            revised_text = st.text_area("Edit proposed reply before approving", value=state["draft_text"],
                                        height=320, key=f"edit_{choice}")
            col_a, col_b = st.columns(2)
            if col_a.button("3. Approve revised draft (do NOT send)", type="primary", use_container_width=True):
                try:
                    store.approve_draft(choice, revised_text, reviewer)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            reject_note = st.text_input("Reason for rejection (optional)", key=f"reason_{choice}")
            if col_b.button("Reject & redraft", use_container_width=True):
                try:
                    store.reject_draft(choice, reviewer, reject_note)
                    st.session_state.pop(f"edit_{choice}", None)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        elif status == "DRAFT_APPROVED":
            st.success("Human-approved email draft · safe to export to a supervised sending system · NOT SENT")
            st.code(state["draft_text"], language=None)
            st.download_button("Download approved email draft (.txt)", data=state["draft_text"],
                               file_name=f"{choice}_approved_draft.txt", mime="text/plain")

with kb_tab:
    st.subheader("One month of synthetic historical resolutions")
    st.write("Every row represents a **resolved ticket with a verified root cause and response**, rather than an isolated email message. This is the unit we should index in a real historical archive.")
    cs = pd.DataFrame(cases)
    c1, c2 = st.columns(2)
    selected_p = c1.multiselect("Priority", PRIORITIES, default=PRIORITIES)
    selected_c = c2.multiselect("Issue category", list(CATEGORIES), default=list(CATEGORIES), format_func=lambda x: CATEGORIES[x])
    view = cs[cs["priority"].isin(selected_p) & cs["category"].isin(selected_c)].copy()
    st.dataframe(view[["case_id", "customer", "opened_at", "priority", "category", "subject", "resolution_verified", "is_current"]],
                 use_container_width=True, hide_index=True, height=420)
    st.caption(f"{len(view)} of {len(cases)} historical cases shown. Deliberately some cases are unverified or obsolete; these are excluded from retrieval.")
    st.download_button("Download mock historical CSV", data=CASE_PATH.read_bytes(),
                       file_name=CASE_PATH.name, mime="text/csv")
    st.download_button("Download mock incoming email CSV", data=INCOMING_PATH.read_bytes(),
                       file_name=INCOMING_PATH.name, mime="text/csv")
    with st.expander("Dataset integrity metadata (SHA-256)"):
        st.json(manifest)

with eval_tab:
    st.subheader("Synthetic evaluation — offline baseline")
    st.caption("This evaluates hand-written offline rules against synthetic examples; it is NOT a Groq accuracy evaluation or a company benchmark.")
    from evaluation import evaluate_offline
    report = evaluate_offline(incoming)
    m = st.columns(3)
    m[0].metric("Offline priority accuracy", f"{report['priority_accuracy']:.1%}")
    m[1].metric("Offline P0 recall", f"{report['p0_recall']:.1%}" if report['p0_recall'] is not None else "n/a")
    m[2].metric("Offline category accuracy", f"{report['category_accuracy']:.1%}")
    st.dataframe(pd.DataFrame(report["examples"]), use_container_width=True, hide_index=True)
    st.info("Before production, build a human-labeled time-separated evaluation set with P0 recall, P1 recall, confusion matrix, retrieval Recall@k, grounded reply quality, escalation failures, and reviewer edit rates.")
    st.subheader("Audit events")
    audits = store.audits()
    if audits:
        st.dataframe(pd.DataFrame(audits)[["event_time", "ticket_id", "event_type", "reviewer", "payload_json"]],
                     use_container_width=True, hide_index=True)
    else:
        st.caption("Audit log is empty. Process an email to create immutable review events.")
    st.caption("There is no SMTP/Gmail/Outlook send implementation. Approved drafts cannot be sent by this demo.")

with design_tab:
    st.subheader("Architecture and explanation for the supervisor")
    st.code("""
INCOMING EMAIL (synthetic)
        |
        v
[Groq: structured P0-P3 + category AI proposal]  <--- offline rule fallback
        |
        v
[HUMAN GATE #1: change / approve priority and category]
        |
        v
[Retrieve relevant, verified historical resolutions]
    | Tenant access filters | Valid runbook only |
        |
        v
[Groq hosted LLM: evidence-grounded reply]  <--- local Ollama or template alternative
        |
        v
[HUMAN GATE #2: edit / approve or reject draft]
        |
        v
[AUDIT + APPROVED UNSENT DRAFT]

PRODUCTION ONLY: approved sending integration with separate authorization
""", language="text")
    st.markdown("**The colleague's 'tree structure':** `priority → issue category → facility/product → historical solved cases → approved diagnostic steps` is a hierarchical index/taxonomy. The old fixes live in the searchable knowledge base, not hard-coded in tree branches.")
    st.markdown("**This demo deliberately does not:** ingest PST/EML archives, use production hybrid search, authenticate corporate reviewers, send customer emails, or use a Groq API key unless configured server-side. The OpenJev adapter is inactive while its hosted service is unavailable.")
