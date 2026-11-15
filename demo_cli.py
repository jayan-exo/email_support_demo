"""Credential-free terminal demonstration of the two mandatory approval gates.

--smoke uses SIMULATED reviewer decisions in a temporary database for tests.
Without --smoke a real terminal user must explicitly approve both gates.
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from core import (
    CASE_PATH, INCOMING_PATH, SearchIndex, WorkflowStore,
    grounded_template, load_csv, propose_offline,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Terminal fallback for SupportFlow Streamlit demo")
    ap.add_argument("--ticket", default="IN-001", help="Incoming synthetic ticket ID")
    ap.add_argument("--smoke", action="store_true", help="TEST ONLY: use simulated human approvals")
    opts = ap.parse_args()
    all_tickets = {x["ticket_id"]: x for x in load_csv(INCOMING_PATH)}
    if opts.ticket not in all_tickets:
        ap.error("Unknown synthetic ticket. Available: " + ", ".join(all_tickets))
    ticket = all_tickets[opts.ticket]
    idx = SearchIndex(load_csv(CASE_PATH))
    proposal = propose_offline(ticket["subject"], ticket["body"])
    print("\nSUPPORTFLOW DEMO — STRICTLY SYNTHETIC\n" + "=" * 50)
    print("Mode:", "SIMULATED HUMAN TEST (NOT A LIVE APPROVAL)" if opts.smoke else "HUMAN REVIEW IN THE TERMINAL")
    print("Ticket:", ticket["ticket_id"], "|", ticket["customer"])
    print("Subject:", ticket["subject"])
    print("Customer email:", ticket["body"])
    print("\nGate 1: Classification proposal (offline rules, NOT OpenJev)")
    print("Proposed priority/category:", proposal.priority, "/", proposal.category)
    print("Evidence:", "; ".join(proposal.signals))
    if opts.smoke:
        reviewer = "SIMULATED-SMOKE-REVIEWER"
        choice = "y"
    else:
        reviewer = input("Your reviewer name: ").strip()
        choice = input("Approve this priority and category? [y/N]: ").strip().lower()
    if choice != "y" or not reviewer:
        print("STOP: human classification was not approved; no reply draft generated.")
        return
    # Smoke tests use a disposable database. Interactive CLI also uses its own
    # DB to avoid disturbing approval sessions managed by Streamlit.
    if opts.smoke:
        temp = tempfile.TemporaryDirectory()
        db_path = Path(temp.name) / "smoke.sqlite"
    else:
        temp = None
        db_path = Path(__file__).resolve().parent / ".local" / "terminal_review.sqlite"
    try:
        store = WorkflowStore(db_path)
        if store.get(ticket["ticket_id"])["status"] != "NEW":
            print("This terminal ticket is already started; resetting demo state (audit retained).")
            store.reset_demo(ticket["ticket_id"], reviewer)
        store.propose(ticket["ticket_id"], proposal)
        store.approve_classification(ticket["ticket_id"], proposal.priority, proposal.category, reviewer)
        print("\nClassification was", "TEST-SIMULATED" if opts.smoke else "HUMAN-APPROVED")
        matches = idx.search(ticket, proposal.category)
        print("Top historical evidence (same customer/tenant and verified):")
        for c in matches[:3]:
            print(f"  - {c['case_id']} | {c['subject']} | score {c['similarity_score']:.3f}")
        draft = grounded_template(ticket, proposal.priority, matches)
        store.save_draft(ticket["ticket_id"], draft, [x["case_id"] for x in matches],
                         "OFFLINE TEMPLATE (not AI text)")
        print("\nGate 2: Reply draft awaiting human review:\n")
        print(draft)
        if opts.smoke:
            approved = "y"
        else:
            approved = input("\nApprove the reply as written (UNSENT)? [y/N]: ").strip().lower()
        if approved != "y":
            store.reject_draft(ticket["ticket_id"], reviewer, "Not approved in CLI")
            print("STOP: reply rejected. No email sent.")
            return
        store.approve_draft(ticket["ticket_id"], draft, reviewer)
        print("\nFinal state:", store.get(ticket["ticket_id"])["status"], "— UNSENT")
        print("Audit events:", [x["event_type"] for x in reversed(store.audits(ticket["ticket_id"]))])
        print("Note: no OpenJev, LLM, or email sending was invoked in this credential-free smoke demo.")
    finally:
        if temp:
            temp.cleanup()


if __name__ == "__main__":
    main()
