import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from core import (
    CASE_PATH, INCOMING_PATH, Proposal, SearchIndex, WorkflowStore,
    grounded_template, load_csv, propose_offline,
)
from providers import ProviderError, classify_openjev


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_csv(CASE_PATH)
        cls.incoming = {t["ticket_id"]: t for t in load_csv(INCOMING_PATH)}
        cls.index = SearchIndex(cls.cases)

    def test_dataset_one_month_and_synthetic(self):
        self.assertEqual(len(self.cases), 288)
        self.assertTrue(all(c["opened_at"].startswith("2026-10") for c in self.cases))
        self.assertEqual(len(self.incoming), 12)

    def test_critical_and_production_stop_rubric(self):
        self.assertEqual(propose_offline(self.incoming["IN-001"]["subject"], self.incoming["IN-001"]["body"]).priority, "P0")
        self.assertEqual(propose_offline(self.incoming["IN-005"]["subject"], self.incoming["IN-005"]["body"]).priority, "P1")

    def test_tenant_isolation_and_validated_resolution_filter(self):
        ticket = self.incoming["IN-001"]
        matches = self.index.search(ticket, "platform_outage", top_k=12)
        self.assertTrue(matches)
        self.assertTrue(all(x["tenant_id"] == ticket["tenant_id"] for x in matches))
        self.assertTrue(all(x["resolution_verified"] == "true" and x["is_current"] == "true" for x in matches))

    def test_workflow_requires_two_approvals_and_never_sends(self):
        ticket = self.incoming["IN-002"]
        proposal = propose_offline(ticket["subject"], ticket["body"])
        with tempfile.TemporaryDirectory() as td:
            store = WorkflowStore(Path(td) / "test.sqlite")
            with self.assertRaises(ValueError):
                store.save_draft("IN-002", "draft", [], "demo")
            store.propose("IN-002", proposal)
            with self.assertRaises(ValueError):
                store.approve_draft("IN-002", "Reply", "reviewer")
            store.approve_classification("IN-002", "P1", "dispatch", "reviewer")
            matches = self.index.search(ticket, "dispatch")
            draft = grounded_template(ticket, "P1", matches)
            self.assertIn("not", "not")
            store.save_draft("IN-002", draft, [c["case_id"] for c in matches], "offline template")
            self.assertEqual(store.get("IN-002")["status"], "DRAFT_PENDING")
            store.approve_draft("IN-002", draft + "\nReviewed.", "reviewer")
            self.assertEqual(store.get("IN-002")["status"], "DRAFT_APPROVED")
            log = store.audits("IN-002")
            self.assertEqual([e["event_type"] for e in reversed(log)],
                             ["CLASSIFICATION_PROPOSED", "CLASSIFICATION_APPROVED", "DRAFT_CREATED", "DRAFT_APPROVED"])
            self.assertFalse(json.loads(log[0]["payload_json"])["sent"])

    def test_rejected_reply_returns_to_classified(self):
        with tempfile.TemporaryDirectory() as td:
            s = WorkflowStore(Path(td) / "db.sqlite")
            s.propose("x", Proposal("P2", "reporting", "offline", "", []))
            s.approve_classification("x", "P2", "reporting", "reviewer")
            s.save_draft("x", "a reply", [], "template")
            s.reject_draft("x", "reviewer", "needs clarification")
            self.assertEqual(s.get("x")["status"], "CLASSIFIED")

    @patch("providers.requests.post")
    def test_live_openjev_schema_and_guardrail(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"answers": {
            "priority": {"choice": "P3", "confidence": 0.5},
            "issue_type": {"choice": "dispatch", "confidence": 0.6},
            "widespread_impact": {"noul": 0.94},
        }}
        proposed = classify_openjev("All doors unable to dispatch",
                                    "None of our driver handhelds are receiving dispatch across all doors, operations shut down.", api_key="dummy")
        self.assertEqual(proposed.priority, "P0")
        self.assertEqual(proposed.raw_model_priority, "P3")
        self.assertIn("/v1/systemone", post.call_args.args[0])

    def test_no_key_hosted_openjev_does_not_silently_use_rules(self):
        with self.assertRaises(ProviderError):
            classify_openjev("subject", "body", api_key="")


if __name__ == "__main__":
    unittest.main()
