"""Synthetic baseline-only evaluation. Gold labels never enter classification input."""
from __future__ import annotations

import json
from pathlib import Path

from core import INCOMING_PATH, load_csv, propose_offline


def evaluate_offline(tickets: list[dict[str, str]]) -> dict:
    examples = []
    for t in tickets:
        prediction = propose_offline(t["subject"], t["body"])
        examples.append({
            "ticket_id": t["ticket_id"],
            "gold_priority": t["gold_priority"],
            "proposed_priority": prediction.priority,
            "priority_correct": prediction.priority == t["gold_priority"],
            "gold_category": t["gold_category"],
            "proposed_category": prediction.category,
            "category_correct": prediction.category == t["gold_category"],
        })
    p0 = [r for r in examples if r["gold_priority"] == "P0"]
    return {
        "method": "illustrative_rules_NOT_OpenJev",
        "dataset": "synthetic_12_emails",
        "n": len(examples),
        "priority_accuracy": sum(r["priority_correct"] for r in examples) / len(examples),
        "category_accuracy": sum(r["category_correct"] for r in examples) / len(examples),
        "p0_recall": sum(r["proposed_priority"] == "P0" for r in p0) / len(p0) if p0 else None,
        "examples": examples,
    }


if __name__ == "__main__":
    report = evaluate_offline(load_csv(INCOMING_PATH))
    print(json.dumps(report, indent=2))
    out = Path(__file__).resolve().parent / "reports" / "synthetic_eval.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print("Wrote:", out)
