"""Test Groq API adapter with mocked HTTP; never make remote calls in tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import CASE_PATH, INCOMING_PATH, SearchIndex, WorkflowStore, load_csv, propose_offline, grounded_template
from providers import (DEFAULT_GROQ_MODEL, GROQ_COMPLETION_URL,
                       ProviderError, build_groq_messages, draft_groq)


class GroqIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_csv(CASE_PATH)
        cls.incoming = {x["ticket_id"]: x for x in load_csv(INCOMING_PATH)}
        cls.index = SearchIndex(cls.cases)
        cls.ticket = cls.incoming["IN-001"]
        cls.matches = cls.index.search(cls.ticket, "platform_outage", top_k=4)

    def test_groq_prompt_has_approved_context_and_limits_evidence(self):
        messages = build_groq_messages(self.ticket, "P0", "platform_outage", self.matches)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("Past resolutions are examples", messages[0]["content"])
        data = json.loads(messages[1]["content"].split("\n", 1)[1])
        self.assertEqual(data["human_approved_priority"], "P0")
        self.assertEqual(data["email_subject_untrusted"], self.ticket["subject"])
        self.assertTrue(all("case_id" in c for c in data["retrieved_prior_cases_untrusted"]))
        self.assertLessEqual(len(data["retrieved_prior_cases_untrusted"]), 3)
        self.assertFalse(any("tenant_river" in json.dumps(c) for c in data["retrieved_prior_cases_untrusted"]))

    def test_missing_groq_key_rejects_before_http_call(self):
        with patch("providers.requests.post") as post:
            with self.assertRaisesRegex(ProviderError, "API key required"):
                draft_groq(self.ticket, "P0", "platform_outage", self.matches, api_key="")
            post.assert_not_called()

    @patch("providers.requests.post")
    def test_live_groq_response_contract_mock(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"choices": [{"message": {
            "content": "Hello,\n\nWe understand the outage. Please share the affected facility and timestamp.\n\nKind regards,\nSupport Team"
        }}]}
        draft = draft_groq(self.ticket, "P0", "platform_outage", self.matches, api_key="fake-key")
        self.assertTrue(draft.startswith("Hello,"))
        self.assertEqual(post.call_args.args[0], GROQ_COMPLETION_URL)
        self.assertEqual(post.call_args.kwargs["json"]["model"], DEFAULT_GROQ_MODEL)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer fake-key")

    @patch("providers.requests.post")
    def test_groq_429_returns_clear_error_without_fallback(self, post):
        post.return_value = Mock(status_code=429)
        with self.assertRaisesRegex(ProviderError, "rate limit"):
            draft_groq(self.ticket, "P0", "platform_outage", self.matches, api_key="fake-key")

    @patch("providers.requests.post")
    def test_groq_malformed_response_fails_closed(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"choices": []}
        with self.assertRaises(ProviderError):
            draft_groq(self.ticket, "P0", "platform_outage", self.matches, api_key="fake-key")

    def test_custom_tickets_persist_and_complete_two_gate_flow(self):
        with tempfile.TemporaryDirectory() as td:
            dbpath = Path(td) / "demo.sqlite"
            store = WorkflowStore(dbpath)
            ticket = store.add_demo_ticket(
                tenant_id=self.ticket["tenant_id"], customer=self.ticket["customer"],
                subject="Production shift stopped at dock 11G",
                body="The production line is stopped because the trailer is not receiving dispatch assignments."
            )
            self.assertIn(ticket["ticket_id"], [x["ticket_id"] for x in WorkflowStore(dbpath).custom_tickets()])
            proposal = propose_offline(ticket["subject"], ticket["body"])
            self.assertEqual(proposal.priority, "P1")
            store.propose(ticket["ticket_id"], proposal)
            self.assertEqual(store.get(ticket["ticket_id"])["status"], "CLASSIFICATION_PENDING")
            store.approve_classification(ticket["ticket_id"], proposal.priority, proposal.category, "Human Reviewer")
            matches = self.index.search(ticket, proposal.category)
            draft = grounded_template(ticket, proposal.priority, matches)
            store.save_draft(ticket["ticket_id"], draft, [x["case_id"] for x in matches], "offline template")
            store.approve_draft(ticket["ticket_id"], draft, "Human Reviewer")
            self.assertEqual(store.get(ticket["ticket_id"])["status"], "DRAFT_APPROVED")
            self.assertEqual(store.audits(ticket["ticket_id"])[-1]["event_type"], "SYNTHETIC_TICKET_CREATED")

    def test_custom_ticket_rejects_blank_input(self):
        with tempfile.TemporaryDirectory() as td:
            store = WorkflowStore(Path(td) / "demo.sqlite")
            with self.assertRaises(ValueError):
                store.add_demo_ticket(tenant_id="tenant_north", customer="Northline", subject="bad", body="too short")


if __name__ == "__main__":
    unittest.main()
