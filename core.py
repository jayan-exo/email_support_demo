"""Policy, retrieval, and an auditable two-gate workflow for the synthetic demo.

This module has no email send capability. An LLM never controls workflow state.
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parent
CASE_PATH = ROOT / "data" / "resolved_cases_oct_2026.csv"
INCOMING_PATH = ROOT / "data" / "incoming_examples.csv"
DB_PATH = ROOT / ".local" / "support_demo.sqlite"

PRIORITIES = ["P0", "P1", "P2", "P3"]
PRIORITY_NAMES = {
    "P0": "Critical — site-wide outage / widespread unavailable operations",
    "P1": "Urgent — production blocked, unsafe or incorrect dispatch",
    "P2": "Important — localized functional problem / workaround",
    "P3": "Routine — access/configuration/help request",
}
CATEGORIES = {
    "platform_outage": "Platform / service outage",
    "authentication": "Authentication / portal access",
    "dispatch": "Dispatch / dock moves",
    "handheld_sync": "Handheld / sync",
    "trailer_inventory": "Trailer inventory / status",
    "reporting": "Reporting / analytics",
    "expedite": "Expedite / request-in",
    "user_access": "User access / setup",
    "dock_config": "Dock configuration",
    "other": "Other / uncertain",
}


def load_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def infer_category(text: str) -> tuple[str, list[str]]:
    """Transparent non-AI fallback rules; not trained nor benchmark-calibrated."""
    t = text.lower()
    # Widespread explicit server failures are outages, even if login also fails.
    if any(x in t for x in ["servers down", "server unavailable", "service unavailable"]) and any(
        x in t for x in ["all users", "every team", "entire site", "whole shift", "everyone", "entire facility"]
    ):
        return "platform_outage", ["widespread server failure"]
    choices = [
        ("user_access", ["new user", "new operator", "create an account", "create a new user", "coordinator account", "account access", "set up a new", "provision", "user onboarding"]),
        ("dock_config", ["add a dock", "add dock", "add door", "door added", "add a door", "dock configuration", "door to configuration"]),
        ("expedite", ["expedite", "request-in", "request in"]),
        ("reporting", ["departure report", "pool report", "export", "monthly", "report filters", "duplicate entries", "duplicated in"]),
        ("authentication", ["log in", "login", "sign in", "sign-in", "sign out", "re-login", "kicked out", "session", "authentication"]),
        ("handheld_sync", ["pending upload", "sync", "synchronization", "handheld device"]),
        ("dispatch", ["wrong trailer", "incorrect trailer", "dispatch", "dock move", "assignments", "driver handheld"]),
        ("trailer_inventory", ["trailer", "offsite", "inbound", "inventory", "yard pool"]),
        ("platform_outage", ["server down", "servers down", "service unavailable", "service down", "portal", "site down"]),
    ]
    for category, keywords in choices:
        hits = [kw for kw in keywords if kw in t]
        if hits:
            # 'every user can't log in' is authentication; this is intentional.
            return category, hits[:3]
    return "other", []


def priority_guardrail(text: str) -> tuple[str | None, list[str]]:
    """Business-impact floors; only proposes values, never bypasses a reviewer.

    A site-wide outage is P0. A halted line / unsafe or wrong dispatch is at
    least P1. Not all 'urgent' subjects are operational emergencies.
    """
    t = text.lower()
    evidence: list[str] = []
    sitewide = any(p in t for p in [
        "all portal users", "every team", "entire site", "company-wide", "all users",
        "every user", "whole shift", "every dock", "all doors", "entire facility",
        "nobody can log in", "none of our driver handhelds", "every shift", "all dock operations",
        "facility-wide", "across all doors", "operations are completely shut down",
    ])
    outage = any(p in t for p in [
        "server unavailable", "servers down", "service unavailable", "can't log in", "cannot connect",
        "all doors unable", "none of our driver", "cannot sign in", "service down", "portal",
        "not receiving", "unable to dispatch", "cannot dispatch", "shut down", "stopped",
    ])
    if sitewide and outage:
        evidence.append("High-impact guardrail: widespread service failure / site-wide shutdown")
        return "P0", evidence
    p1_patterns = [
        "wrong trailer", "incorrect trailer", "production line is stopped", "production line is shut down",
        "line halted", "production shift is blocked", "production shift", "production line",
        "dispatch is blocked", "blocked from using", "cannot be brought into the pool",
        "shut down the production", "paused the affected dock", "could be incorrect",
    ]
    matched = [p for p in p1_patterns if p in t]
    if matched:
        evidence.append("P1 floor: production impact or incorrect/unsafe operational move")
        return "P1", evidence
    return None, evidence


@dataclass
class Proposal:
    priority: str
    category: str
    source: str
    explanation: str
    signals: list[str]
    model_confidence: float | None = None
    raw_model_priority: str | None = None


def propose_offline(subject: str, body: str) -> Proposal:
    """Deterministic illustration only. Must NOT be labeled OpenJev or AI."""
    text = subject + "\n" + body
    category, matches = infer_category(text)
    floor, flags = priority_guardrail(text)
    lower = text.lower()
    if floor:
        priority = floor
    elif category in {"user_access", "dock_config"}:
        priority = "P3"
    elif category == "reporting" and any(x in lower for x in ["how can i", "could someone show", "instructions", "no technical problem"]):
        priority = "P3"
    elif any(x in lower for x in ["other records", "one trailer", "only one", "some trailers", "other devices", "other doors", "eight pending", "error", "server error", "does not appear", "missing", "duplicate"]):
        priority = "P2"
    elif category == "platform_outage":
        priority = "P2"  # single-user failures remain localized unless impact is clear
    elif category == "other":
        priority = "P2"  # uncertain issues get mandatory human review
    else:
        priority = "P2"
    if category == "other":
        flags.append("Unrecognized issue category; request manual triage")
    return Proposal(priority, category, "Offline illustrative rules (NOT OpenJev)",
                    "Impact-based demonstration heuristic; human verification is required.",
                    flags + [f"Topic match: {x}" for x in matches], None)


def apply_guardrail(proposal: Proposal, text: str) -> Proposal:
    floor, flags = priority_guardrail(text)
    if floor and PRIORITIES.index(floor) < PRIORITIES.index(proposal.priority):
        proposal.raw_model_priority = proposal.priority
        proposal.priority = floor
        proposal.explanation += f" Policy guardrail raised priority to {floor}; human must confirm."
    for f in flags:
        if f not in proposal.signals:
            proposal.signals.append(f)
    return proposal


class SearchIndex:
    """Toy tenant-filtered TF-IDF retrieval, NOT production hybrid semantic RAG."""
    def __init__(self, cases: list[dict[str, str]]):
        self.cases = list(cases)
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        texts = [f"{c['subject']} {c['body']} {c['category'].replace('_',' ')}" for c in self.cases]
        self.matrix = self.vectorizer.fit_transform(texts)

    def search(self, ticket: dict[str, str], approved_category: str, top_k: int = 4) -> list[dict[str, Any]]:
        query = f"{ticket['subject']} {ticket['body']} {approved_category.replace('_',' ')}"
        q = self.vectorizer.transform([query])
        scores = cosine_similarity(q, self.matrix).ravel()
        eligible = []
        for i, c in enumerate(self.cases):
            # Enforce tenant isolation outside the LLM. No cross-tenant leakage.
            if c["tenant_id"] != ticket["tenant_id"]:
                continue
            if c.get("status") != "resolved":
                continue
            if c.get("resolution_verified") != "true" or c.get("is_current") != "true":
                continue
            if not c.get("verified_resolution", "").strip():
                continue
            score = float(scores[i])
            if c["category"] == approved_category:
                score += 0.10
            if score > 0.04:
                eligible.append((score, c))
        eligible.sort(key=lambda pair: pair[0], reverse=True)
        return [{**c, "similarity_score": round(score, 3)} for score, c in eligible[:top_k]]


def grounded_template(ticket: dict[str, str], approved_priority: str, matches: list[dict[str, Any]]) -> str:
    """Explicitly non-LLM draft for credential-free product walkthrough."""
    salutation = "Hello,"
    a = [salutation, "", "Thank you for contacting the support team.", "",
         f"We understand that you are reporting: {ticket['subject'].rstrip('.')}.", ""]
    if approved_priority == "P0":
        a.append("We understand this may affect site-wide operations. We are treating the report as critical and will confirm the impact and escalation path with the on-call team.")
    elif approved_priority == "P1":
        a.append("We understand the operational impact and will prioritize review with the support team. Please keep unsafe or incorrect trailer moves paused until your operations lead confirms it is safe to proceed.")
    elif approved_priority == "P2":
        a.append("We will investigate the affected workflow and compare the symptoms with the available operational records.")
    else:
        a.append("We can review this routine request after the relevant permissions and configuration details are confirmed.")
    if matches:
        a.extend(["", "For an initial diagnostic check, our support team can "+matches[0]["safe_next_step"].rstrip(".")+"."])
    else:
        a.extend(["", "We have not found a verified prior resolution for these symptoms, so we will investigate rather than assume a particular fix."])
    a.extend(["", "Could you confirm the affected facility, approximate time of the issue, and any relevant error message (without sending passwords or secrets)?", "", "Kind regards,", "Support Team"])
    return "\n".join(a)


class WorkflowStore:
    """SQLite demonstration state machine with immutable audit events."""
    def __init__(self, path: Path | str = DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS workflow (
                ticket_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                proposal_json TEXT,
                approved_priority TEXT,
                approved_category TEXT,
                draft_text TEXT,
                retrieved_ids TEXT,
                review_by TEXT,
                model_name TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS demo_ticket (
                ticket_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                customer TEXT NOT NULL,
                received_at TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_event (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                event_time TEXT NOT NULL
            );
            """)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def add_demo_ticket(self, *, tenant_id: str, customer: str, subject: str, body: str) -> dict[str, str]:
        """Store a new synthetic message for an interactive, repeatable demo.

        The UI must not expose this feature to real confidential emails.
        This method writes only to local SQLite and never sends mail.
        """
        if not tenant_id.strip() or not customer.strip():
            raise ValueError("Choose an existing synthetic demo customer")
        subject, body = subject.strip(), body.strip()
        if not 5 <= len(subject) <= 200 or not 15 <= len(body) <= 5000:
            raise ValueError("Use a 5-200 character subject and 15-5000 character message")
        ticket_id = "CUSTOM-" + uuid4().hex[:10].upper()
        ticket = {"ticket_id": ticket_id, "thread_id": "DEMO-" + ticket_id,
                  "tenant_id": tenant_id, "customer": customer,
                  "received_at": now_iso(), "subject": subject, "body": body}
        with self.connect() as db:
            db.execute("""INSERT INTO demo_ticket
                (ticket_id, thread_id, tenant_id, customer, received_at, subject, body)
                VALUES (:ticket_id,:thread_id,:tenant_id,:customer,:received_at,:subject,:body)""", ticket)
            self._event(db, ticket_id, "SYNTHETIC_TICKET_CREATED", "demo-user",
                        {"tenant_id":tenant_id,"subject_length":len(subject),"body_length":len(body)})
        return ticket

    def custom_tickets(self) -> list[dict[str, str]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM demo_ticket ORDER BY received_at DESC, ticket_id DESC").fetchall()
        return [dict(r) for r in rows]

    def get(self, ticket_id: str) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute("SELECT * FROM workflow WHERE ticket_id = ?", (ticket_id,)).fetchone()
        return dict(row) if row else {"ticket_id": ticket_id, "status": "NEW"}

    def _event(self, db: sqlite3.Connection, ticket_id: str, event: str, reviewer: str, payload: dict[str, Any]) -> None:
        db.execute("INSERT INTO audit_event (ticket_id,event_type,reviewer,payload_json,event_time) VALUES (?,?,?,?,?)",
                   (ticket_id, event, reviewer, json.dumps(payload, ensure_ascii=False), now_iso()))

    def propose(self, ticket_id: str, proposal: Proposal) -> None:
        if self.get(ticket_id)["status"] not in ("NEW", "CLASSIFICATION_PENDING"):
            raise ValueError("Classification proposal is locked after approval. Reset only in demo mode.")
        with self.connect() as db:
            db.execute("""INSERT INTO workflow (ticket_id,status,proposal_json,updated_at) VALUES (?,?,?,?)
               ON CONFLICT(ticket_id) DO UPDATE SET status=excluded.status,proposal_json=excluded.proposal_json,updated_at=excluded.updated_at""",
               (ticket_id, "CLASSIFICATION_PENDING", json.dumps(asdict(proposal)), now_iso()))
            self._event(db, ticket_id, "CLASSIFICATION_PROPOSED", "system", asdict(proposal))

    def approve_classification(self, ticket_id: str, priority: str, category: str, reviewer: str) -> None:
        if self.get(ticket_id)["status"] != "CLASSIFICATION_PENDING":
            raise ValueError("Classification proposal must be reviewed before continuing")
        if priority not in PRIORITIES or category not in CATEGORIES or not reviewer.strip():
            raise ValueError("Valid priority, category and reviewer are required")
        with self.connect() as db:
            db.execute("UPDATE workflow SET status=?,approved_priority=?,approved_category=?,review_by=?,updated_at=? WHERE ticket_id=?",
                       ("CLASSIFIED", priority, category, reviewer, now_iso(), ticket_id))
            self._event(db, ticket_id, "CLASSIFICATION_APPROVED", reviewer, {"priority": priority, "category": category})

    def save_draft(self, ticket_id: str, draft: str, sources: list[str], provider: str) -> None:
        if self.get(ticket_id)["status"] != "CLASSIFIED":
            raise ValueError("A human must approve classification before draft generation")
        if not draft.strip():
            raise ValueError("Cannot save an empty draft")
        with self.connect() as db:
            db.execute("UPDATE workflow SET status=?,draft_text=?,retrieved_ids=?,model_name=?,updated_at=? WHERE ticket_id=?",
                       ("DRAFT_PENDING", draft, json.dumps(sources), provider, now_iso(), ticket_id))
            self._event(db, ticket_id, "DRAFT_CREATED", "system", {"provider": provider, "source_case_ids": sources, "draft_length": len(draft)})

    def approve_draft(self, ticket_id: str, edited_draft: str, reviewer: str) -> None:
        if self.get(ticket_id)["status"] != "DRAFT_PENDING":
            raise ValueError("A generated draft must be reviewed before approval")
        if not reviewer.strip() or not edited_draft.strip():
            raise ValueError("Reviewer and non-empty text required")
        with self.connect() as db:
            db.execute("UPDATE workflow SET status=?,draft_text=?,review_by=?,updated_at=? WHERE ticket_id=?",
                       ("DRAFT_APPROVED", edited_draft, reviewer, now_iso(), ticket_id))
            self._event(db, ticket_id, "DRAFT_APPROVED", reviewer, {"edited": True, "draft_length": len(edited_draft), "sent": False})

    def reject_draft(self, ticket_id: str, reviewer: str, note: str) -> None:
        if self.get(ticket_id)["status"] != "DRAFT_PENDING":
            raise ValueError("No draft awaiting review")
        if not reviewer.strip():
            raise ValueError("Reviewer required")
        with self.connect() as db:
            db.execute("UPDATE workflow SET status=?,draft_text=NULL,retrieved_ids=NULL,updated_at=? WHERE ticket_id=?",
                       ("CLASSIFIED", now_iso(), ticket_id))
            self._event(db, ticket_id, "DRAFT_REJECTED", reviewer, {"reason": note, "sent": False})

    def reset_demo(self, ticket_id: str, reviewer: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM workflow WHERE ticket_id=?", (ticket_id,))
            self._event(db, ticket_id, "DEMO_WORKFLOW_RESET", reviewer, {"purpose": "replay"})

    def audits(self, ticket_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as db:
            if ticket_id:
                rows = db.execute("SELECT * FROM audit_event WHERE ticket_id=? ORDER BY event_id DESC", (ticket_id,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM audit_event ORDER BY event_id DESC LIMIT 200").fetchall()
        return [dict(r) for r in rows]

    def all_statuses(self) -> dict[str, str]:
        with self.connect() as db:
            rows = db.execute("SELECT ticket_id,status FROM workflow").fetchall()
        return {r["ticket_id"]: r["status"] for r in rows}
