"""Generate one reproducible month of strictly synthetic support cases.

No real customer mail, account numbers, or identifying information is used.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "data"
SEED = 20261113
TENANTS = [
    ("tenant_north", "Northline Logistics"),
    ("tenant_summit", "Summit Manufacturing"),
    ("tenant_river", "Riverbend Freight"),
]

# ID, priority, category, subject template, symptom template, historical root cause,
# verified resolution, safe next-step suggestion for a *new* occurrence.
SCENARIOS = [
    ("platform_outage", "P0", "platform_outage", "All portal users cannot connect at {facility}",
     "Every team at {facility} receives a server unavailable message when opening the operations portal. Dock activity has stopped for the whole shift.",
     "Expired gateway certificate interrupted access across the facility.",
     "The infrastructure team renewed the certificate and confirmed successful logins with the site administrator.",
     "have the on-call infrastructure team check the gateway health and the active certificate, and confirm the scope of the outage"),
    ("service_down", "P0", "platform_outage", "Service unavailable for entire {facility} location",
     "The entire site is seeing service unavailable in Exotrac. All warehouse operators are affected and dock processing is unavailable.",
     "The application service pool stopped after a failed deployment.",
     "The deployment was rolled back and the service health checks returned to normal; operations confirmed recovery.",
     "escalate to the incident on-call team to inspect service health and the most recent deployment"),
    ("authentication_wide", "P0", "authentication", "Company-wide login failure at {facility}",
     "No one in the facility can sign in. Every user is receiving a server error and all shifts are blocked.",
     "An identity-provider signing key rotation was incomplete.",
     "The identity configuration was corrected and site leads verified sign-in restoration.",
     "ask the identity and on-call teams to validate provider status and the affected user scope"),
    ("dispatch_down", "P0", "dispatch", "Dispatch unavailable across all doors at {facility}",
     "None of our drivers receive movement assignments at any dock. Every shift is unable to dispatch trailers, resulting in a facility-wide shutdown.",
     "Message-broker subscription for site dispatch events was inactive.",
     "Dispatch subscriptions were restored and test assignments reached driver handhelds.",
     "escalate the site-wide dispatch event pipeline to the on-call team and verify delivery of test assignments"),
    ("wrong_trailer", "P1", "dispatch", "Incorrect trailer selected at dock {dock}",
     "At dock {dock}, a handheld request is assigning the wrong trailer to an operator. We have paused the affected dock to prevent an incorrect move.",
     "A stale dock-to-trailer mapping remained in the dispatch cache.",
     "Support refreshed the mapping after verification, and the dock lead validated the correct assignment.",
     "verify the requested trailer, the affected dock mapping, and the current dispatch event before allowing a move"),
    ("production_stop", "P1", "handheld_sync", "Line halted because drivers lack dispatches at {facility}",
     "The production line is shut down because our driver handhelds are not receiving assigned dispatches. We need urgent assistance.",
     "The handheld sync queue was stalled for the affected facility.",
     "The queue backlog was cleared, then drivers confirmed new assignments arrived.",
     "check the handheld synchronization queue and the last successful dispatch event with the operations lead"),
    ("offsite_locked", "P1", "trailer_inventory", "Offsite trailers cannot be returned to pool at {facility}",
     "Several trailers scanned to offsite parking still show as offsite when brought back. The system says already in and blocks inbound handling for today's production.",
     "Two inventory states diverged after delayed scan processing.",
     "The support team reconciled the scan event log and the yard lead verified inbound processing.",
     "compare the latest yard-scan events with the current inventory state before modifying any trailer records"),
    ("inbound_missing", "P1", "trailer_inventory", "Active trailers missing from pool report at {facility}",
     "Trailers needed for the production shift can be searched but do not appear in the pool report. Inbound route data is missing and dispatch is blocked.",
     "A delayed import omitted required inbound-route records.",
     "The import was replayed by support after validation, and the trailers appeared in the pool report.",
     "verify inbound-route records, scan history, and report filters for the affected trailers"),
    ("pending_upload", "P2", "handheld_sync", "Device {device} has pending uploads",
     "Handheld device {device} is showing eight pending uploads. Please assist with syncing the records; other devices remain operational.",
     "The device had lost connectivity while awaiting upload confirmation.",
     "The operations team reconnected the device and confirmed all uploads were processed.",
     "verify network connectivity, the upload queue, and the last successful sync timestamp"),
    ("duplicated_report", "P2", "reporting", "Duplicate entries in departure report for {facility}",
     "Departure reporting lists some trailers twice for yesterday's activity. The original movement events look correct; we need the report checked.",
     "A report join duplicated entries when a departure was reprocessed.",
     "The reporting query was corrected and the customer validated totals against source movements.",
     "compare report filters and distinct departure event IDs before changing source data"),
    ("expedite_error", "P2", "expedite", "Expedite Request-In error at door {dock}",
     "We receive an error on the Request-In step for expediting at door {dock}. Other docks work normally; a unit number field might be involved.",
     "A missing unit-number validation rule affected one dock workflow.",
     "The input validation was corrected and the request was completed in a controlled test.",
     "capture the exact error, requested unit number, and affected door before reproducing the Request-In step"),
    ("specific_dock_moves", "P2", "dispatch", "Dock move to {dock} missing on handheld",
     "When trailers are called to door {dock}, assignments do not appear on driver handhelds, while other doors dispatch correctly. Yard staff are moving them manually.",
     "The door-specific dispatch routing rule had an outdated destination.",
     "The route rule was updated and drivers confirmed receipt of a test movement.",
     "review the door-specific routing rule and compare a working door's dispatch event trace"),
    ("single_trailer_error", "P2", "trailer_inventory", "Server error opening one trailer record",
     "A server error occurs only when opening details for one trailer. Other trailer details are opening normally and operations continue.",
     "The affected trailer record contained inconsistent metadata.",
     "The support team corrected the data after checking the audit log, and the trailer record opened successfully.",
     "capture the affected record identifier securely and check the relevant server error logs and record integrity"),
    ("single_user_auth", "P2", "authentication", "Portal signs one operator out repeatedly at {facility}",
     "One operator is kicked out of the portal and gets a server error on re-login. Other operators are unaffected.",
     "The user's session token had an invalid cached claim.",
     "The stale session was revoked and the operator successfully signed in again.",
     "check the user's session records and authentication error code without requesting a password"),
    ("add_user", "P3", "user_access", "New user onboarding request for {facility}",
     "Please set up a new operator account for our team at {facility}. This is a routine request with no production impact.",
     "New access required administrator authorization.",
     "The authorized site administrator approved the role and support provisioned the account.",
     "request the authorized manager's approval, business role, and permitted site scope"),
    ("add_door", "P3", "dock_config", "Add door {dock} at {facility}",
     "Please add dock door {dock} to the facility configuration for a future schedule and make it available to the permitted dispatch group.",
     "The dock and dispatch-group mapping had not been configured.",
     "Support added the approved door configuration and an administrator validated its visibility.",
     "confirm the facility, proposed door, dispatch group, and authorized approver before changing configuration"),
    ("exotrac_user", "P3", "user_access", "Create Exotrac account for new dock coordinator",
     "We have a new dock coordinator joining {facility} next week. Please arrange account access with the appropriate permissions.",
     "The coordinator was not in the approved role mapping.",
     "The manager authorized permissions and support created the account with the correct role.",
     "ask for an approved access request including the user's role and site before provisioning"),
    ("routine_report", "P3", "reporting", "How can I export last month's trailer report?",
     "Could you explain the normal steps to export last month's completed trailer report? There is no system error.",
     "The user needed guidance on the reporting export filters.",
     "Support provided the export workflow and the customer confirmed they could generate the report.",
     "confirm the requested report, date range, and available export permission before sharing current instructions"),
]

INCOMING = [
    ("IN-001", "tenant_north", "Northline Logistics", "P0", "platform_outage", "All users report servers down", "Every team at Facility N2 receives a servers down message in the portal. Nobody can log in and all dock operations have stopped."),
    ("IN-002", "tenant_north", "Northline Logistics", "P1", "dispatch", "Wrong trailer sent at dock 11G", "At dock 11G the handheld sends the wrong trailer when an operator requests a container. We stopped this dock because the move could be incorrect."),
    ("IN-003", "tenant_north", "Northline Logistics", "P2", "expedite", "Request-In error at AS04", "The Request-In action at door AS04 throws an error on two unit numbers. Other doors are working; can you investigate?"),
    ("IN-004", "tenant_north", "Northline Logistics", "P3", "user_access", "New coordinator account", "Please create a new user with dock coordinator access at Facility N2 next week. Manager approval can be provided."),
    ("IN-005", "tenant_summit", "Summit Manufacturing", "P1", "handheld_sync", "Production line stopped—no handheld dispatch", "Our production line is stopped. Drivers do not receive any dispatches on their handheld devices. Need immediate help."),
    ("IN-006", "tenant_summit", "Summit Manufacturing", "P2", "reporting", "Repeated trailers in departure report", "Our departure report lists the same trailers twice but we can still dispatch them. Please check report filtering."),
    ("IN-007", "tenant_river", "Riverbend Freight", "P2", "handheld_sync", "Pending uploads on one device", "Device H-13 shows eight pending uploads. Only this handheld is affected; please help sync safely."),
    ("IN-008", "tenant_river", "Riverbend Freight", "P3", "dock_config", "Add a dock door to configuration", "Can we add dock door 53 to the system for next month? Please assign it to our approved dispatch group."),
    ("IN-009", "tenant_summit", "Summit Manufacturing", "P1", "trailer_inventory", "Offsite trailer status prevents return", "Offsite trailers appear already inbound and cannot be brought into the pool. Today's production shift is blocked from using them."),
    ("IN-010", "tenant_river", "Riverbend Freight", "P2", "trailer_inventory", "One trailer detail fails to open", "A server error occurs on just one trailer record, but other records open and there is no general outage."),
    ("IN-011", "tenant_north", "Northline Logistics", "P0", "dispatch", "All doors unable to dispatch", "None of our driver handhelds receive dispatch moves anywhere at Facility N2. Every dock is affected and operations are completely shut down."),
    ("IN-012", "tenant_river", "Riverbend Freight", "P3", "reporting", "Report export instructions", "Could someone show our supervisor how to export the monthly trailer inventory report? There is no technical problem."),
]


def build() -> tuple[Path, Path, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    resolved = []
    # 1 month, 18 archetypes x 16 occurrences, 288 distinct synthetic cases.
    day0 = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
    for i in range(288):
        scenario = SCENARIOS[i % len(SCENARIOS)]
        sid, priority, category, subject_t, body_t, cause, resolution, safe = scenario
        tenant_id, tenant_name = TENANTS[i % len(TENANTS)]
        # Reassign some tenants for a balanced searchable collection.
        if i >= 18:
            tenant_id, tenant_name = TENANTS[rng.randrange(len(TENANTS))]
        facility = rng.choice(["Facility N2", "Plant S1", "Distribution R4", "Yard L3"])
        dock = rng.choice(["AS04", "AW58", "11G", "53", "C12"])
        device = rng.choice(["H-13", "H-17", "H-22"])
        vals = {"facility": facility, "dock": dock, "device": device}
        opened = day0 + timedelta(days=i % 31, hours=rng.randrange(0, 13), minutes=rng.randrange(0, 59))
        resolved_at = opened + timedelta(hours=rng.randrange(1, 25))
        # Some examples represent obsolete or unverified resolutions and must not be retrieved.
        verified = i % 19 != 0
        current = i % 23 != 0
        resolved.append({
            "case_id": f"CASE-{i+1:04d}", "thread_id": f"THREAD-{i+1:04d}",
            "tenant_id": tenant_id, "customer": tenant_name,
            "opened_at": opened.isoformat(), "resolved_at": resolved_at.isoformat(),
            "subject": subject_t.format(**vals), "body": body_t.format(**vals),
            "priority": priority, "category": category, "scenario_id": sid,
            "root_cause": cause, "verified_resolution": resolution,
            "safe_next_step": safe, "resolution_verified": str(verified).lower(),
            "is_current": str(current).lower(), "status": "resolved",
            "runbook_version": "runbook-2026-10-v1", "data_version": "mock-oct-2026-v1"
        })
    rng.shuffle(resolved)
    incoming = [{
        "ticket_id": ticket_id, "thread_id": f"CURRENT-{ticket_id}",
        "tenant_id": tenant, "customer": customer,
        "received_at": f"2026-11-{1+j:02d}T09:00:00+00:00",
        "subject": subject, "body": body,
        "gold_priority": priority, "gold_category": category,
    } for j, (ticket_id, tenant, customer, priority, category, subject, body) in enumerate(INCOMING)]

    resolved_path = OUT / "resolved_cases_oct_2026.csv"
    incoming_path = OUT / "incoming_examples.csv"
    for path, rows in [(resolved_path, resolved), (incoming_path, incoming)]:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    manifest = {
        "dataset_id": "synthetic-email-support-2026-10-v1",
        "synthetic": True,
        "month": "2026-10",
        "seed": SEED,
        "generator_version": "1.0.0",
        "resolved_case_count": len(resolved),
        "incoming_example_count": len(incoming),
        "artifacts": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (resolved_path, incoming_path)
        },
        "caution": "Not actual customer data. Synthetic priority labels and resolutions are illustrative; not an accuracy benchmark."
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return resolved_path, incoming_path, manifest_path


if __name__ == "__main__":
    files = build()
    print("Generated synthetic demo data:", *files, sep="\n - ")
