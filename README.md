# SupportFlow — Human-reviewed Email Support AI (POC)

**For the fastest Mac setup and demo script, start with [`START_HERE.md`](START_HERE.md).**

**November 13, 2026 · Synthetic proof of concept · Not a production support system**

This project demonstrates an email support workflow that **proposes P0–P3 priority and issue category, requires human classification approval, retrieves past verified resolutions, drafts a grounded reply, and requires a second human approval**. There is **no email-sending functionality**.

## 1. Quick start (macOS / Linux)

Use Python 3.11–3.13 in a virtual environment. From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.address 127.0.0.1
```

Open the localhost URL displayed in the terminal (usually `http://localhost:8501`).

**No keys needed for the default experience.** The default uses **offline illustrative Python rules** for classification and an **offline grounded template** for drafting when `GROQ_API_KEY` is absent. If `GROQ_API_KEY` is configured before launching the app, Groq becomes the default drafting choice. These modes deliberately **do not claim to execute OpenJev or an LLM**. Real integration modes can be selected in the sidebar.

Alternatively, double-click **`offline_demo.html`** for a self-contained browser-only simulation. This is NOT live OpenJev or Groq.

To verify the codebase without Streamlit:

```bash
python3 generate_mock.py
python3 -m unittest discover -s tests -v
python3 evaluation.py
python3 demo_cli.py --smoke
```

The generator uses a fixed seed; rerunning it overwrites only the synthetic CSV and manifest, not any real data. `demo_cli.py --smoke` uses simulated reviewer approvals for automated testing; real reviewers use the Streamlit UI.

## 2. What is inside?

```text
email_support_poc/
├── app.py                    # Streamlit human-review workflow
├── core.py                   # Transparent fallback classification, retrieval, SQLite state machine
├── providers.py              # Real OpenJev API adapter and local Ollama drafting adapter
├── generate_mock.py          # Reproducible October 2026 mock data generator
├── evaluation.py             # Explicit synthetic-baseline evaluation
├── demo_cli.py               # Terminal smoke demonstration
├── data/
│   ├── resolved_cases_oct_2026.csv   # 288 synthetic historical resolved cases
│   ├── incoming_examples.csv         # 12 synthetic new emails; hidden gold labels
│   └── manifest.json                 # SHA-256 hashes, generator/data version, provenance
├── tests/test_core.py       # 7 tests for retrieval / human gates / OpenJev mock
├── tests/test_groq.py       # 7 tests for Groq mock / custom demo tickets
├── START_HERE.md            # Mac commands + exact demo walkthrough
├── offline_demo.html        # Standalone browser-only rules/template simulation
├── make_offline_fallback.py # Regenerate the standalone HTML
├── SUPERVISOR_BRIEF.md        # Meeting script, demo order, limitations
├── TECHNICAL_PLAN.md         # Historical-data and production architecture plan
├── .env.example              # Example environment settings, no real key
├── requirements.txt
└── .gitignore
```

SQLite stores new synthetic custom tickets, approval and audit events under `.local/support_demo.sqlite` (excluded from git). Approving a draft means **approved but unsent**. The reviewer can edit or reject. Historical retrieval excludes unverified/obsolete resolutions and **never crosses tenant boundaries**. A separate audit event is recorded for each transition.

## 3. Demonstration sequence

Select `IN-001` (site-wide servers down). Click **Propose priority and category**, observe proposed `P0`, choose or correct the label, and **Approve classification**. Only after approval will the app show historical matches and allow reply drafting. Click **Prepare grounded email draft**, edit it, and **Approve revised draft (do NOT send)**. Open **Evaluation & audit** to show the recorded two checkpoints.

Then use `IN-002` (wrong trailer assigned, operational risk) to illustrate `P1`, `IN-003` (localized expedite error) to illustrate `P2`, and `IN-004` (account request) to illustrate `P3`. If time is limited, completing `IN-001` and showing these three additional inbox examples is sufficient.

## 4. Live OpenJev classification (optional)

A family of independent projects uses the name **OpenJev**. This demo targets the published **typed decision API**:

`POST https://api.openjev.sh/v1/systemone`

It sends `state` (the email subject and body) with `questions` of types `choice` / `noul`, requesting priority and issue category. The response should contain `answers.priority.choice` and `answers.issue_type.choice`.

Reference: [OpenJev API documentation](https://openjev.sh/docs) and the [open-weights OpenJev model card](https://huggingface.co/openjev/openjev).

To try a hosted endpoint, obtain an account key from the provider and select **OpenJev API (real)** in the sidebar; enter the key and verify the chosen base URL and model. The defaults are `https://api.openjev.sh` and `openjev`, which follow one published provider. Because similarly named implementations have differing models/URLs, confirm them for your chosen service. A local OpenJev server may be used by overriding the base URL and model. **No key or provider server is included**, and we have not claimed a successful remote inference.

For real customer emails, **do not use a third-party endpoint unless your company approves the deployment, data processing, retention terms and access controls**.

OpenJev produces structured decisions; it **does not write free-form customer emails**. Even when it returns a confidence-like scalar, that value is an output-distribution concentration and is **not** an externally measured probability of correct priority.

## 5. Groq API reply drafting (recommended for the live synthetic demo)

[Groq API docs](https://console.groq.com/docs/api-reference) specify `POST https://api.groq.com/openai/v1/chat/completions`. This demo uses the existing `requests` dependency to call that endpoint; no additional Groq SDK is required.

```bash
export GROQ_API_KEY='your-secret-key'
streamlit run app.py --server.address 127.0.0.1
```

Choose **Groq API (real)** in the sidebar. Model default: `openai/gpt-oss-20b`; current availability and free-tier limits should be verified in your Groq dashboard. Your API key can alternatively be entered in the sidebar password field. The app sends the current **synthetic** issue, **human-approved priority and category**, and up to 3 **same-tenant, current, verified** historic summaries. The LLM draft can **only** be saved as `DRAFT_PENDING`; a human must explicitly approve the text. No auto-sending function exists.

If Groq returns an authentication error, rate limit, or invalid output, an error is displayed, and no template fallback is passed off as Groq output. Groq calls were **mock-tested**, not live-tested in the packaging environment. Never use this public API with confidential emails without the organization's explicit data-processing approval.

## 6. Local LLM reply drafting (alternative)


[Ollama](https://docs.ollama.com/api) allows a small language model to run on a local laptop:

```bash
# Install Ollama for your system first, then:
ollama pull qwen3:4b-instruct
ollama list
```

Keep Ollama running, then select **Ollama local LLM (real)** in the sidebar. By default, the adapter uses `http://127.0.0.1:11434/api/chat` with `model=qwen3:4b-instruct` and `stream=false`. You may change the model name in the sidebar if you have another local model installed. A minimum amount of free RAM/disk is necessary; check Ollama's current model details.

Ollama receives the current selected **synthetic** email, **human-approved classification**, and **selected verified historical evidence**. It is instructed not to invent a diagnosis or claim past fixes were performed on the new ticket. Its draft still needs review. Prompting is not a complete defense against unsafe generation or malicious email content.

A private enterprise LLM service can replace this adapter later, after security and governance approval.

## 7. Human gates and explicitly excluded actions

### Gate #1: classification

`NEW → CLASSIFICATION_PENDING → CLASSIFIED`

There is no path from a new email directly into reply drafting. Classification may be **changed by the reviewer** before approval. The system applies a basic floor for explicit widespread outages or incorrect/blocked dispatches, but this is only a proposed priority and not a substitute for support policy.

### Gate #2: reply

`CLASSIFIED → DRAFT_PENDING → DRAFT_APPROVED (UNSENT)`

Rejection returns the workflow to `CLASSIFIED` for redrafting and preserves the audit event. The demo lacks SMTP, Gmail, Outlook and arbitrary agent tools, so there is no way for the AI to send a message or modify customer systems. Export of a human-approved `.txt` file is manual.

## 8. Evaluation notes

```bash
python3 evaluation.py
```

The evaluation uses twelve **curated synthetic tickets** and a handwritten rules baseline only. It is an executable sanity check, **not a measure of OpenJev performance, real-world quality, or calibration**. The small, deliberately straightforward sample can produce an unrealistically high percentage. A real evaluation must use a de-identified, temporally separated, expert-annotated dataset and report per-priority recall (especially P0/P1), false escalation rates, cost of errors, abstention rates, search Recall@k, grounding quality, and percentage of replies requiring human edits.

`python3 -m unittest discover -s tests -v` checks workflow gates, tenant isolation, stale/unverified evidence filters, high-impact guardrails, mocked OpenJev and Groq API response schemas/error handling, and custom synthetic ticket persistence.

## 9. Security and production warning

This is a **local prototype**, with no authentication, reviewer roles, virus scanning, enterprise key management, retention policy enforcement, or privacy redaction pipeline. SQLite writes plaintext synthetic drafts and audit records. Do not load real confidential email archives before hardening those components. The provider keys are not logged in code, and `.env` / DB files are excluded from git, but a production deployment needs secret management, encryption, RBAC, proper audit retention, tenant access controls and incident escalation integration.

See `TECHNICAL_PLAN.md` for the proposed ingestion, versioning, retrieval, privacy, evaluation and rollout architecture.

### Sources

- [Groq REST API reference](https://console.groq.com/docs/api-reference)
- [Groq current rate limits](https://console.groq.com/docs/rate-limits)

- [OpenJev open-weights model card](https://huggingface.co/openjev/openjev)
- [OpenJev HTTP API docs](https://openjev.sh/docs)
- [LangGraph durable human-interrupt workflow](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Microsoft hybrid retrieval overview](https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview)
- [DVC data versioning](https://doc.dvc.org/user-guide)
- [NIST AI 600-1 Generative AI Risk Management Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence)
- [OWASP LLM Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
