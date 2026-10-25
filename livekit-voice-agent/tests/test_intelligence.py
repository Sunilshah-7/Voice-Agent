from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from hospitality_agent.intelligence import (
    MIN_AGGREGATE_SAMPLE_SIZE,
    IntelligenceStore,
)


DAY = 86400


def artifact(
    session_id: str,
    *,
    created_at: float,
    issue: str = "Delayed room-status updates",
    practice: str | None = "The team kept guests updated",
    property_id: str = "property-a",
    department: str = "front_desk",
    synthesis_status: str = "completed",
    session_status: str = "completed",
    evidence_turn_id: str = "turn-0001",
    human_review_required: bool = False,
) -> dict[str, object]:
    incident_record: dict[str, object] = {
        "schema_version": "1.0",
        "incident_type": "parking_complaint",
        "subcategory": "blocked_driveway",
        "classification_evidence_turn_ids": [evidence_turn_id],
        "caller": {
            "name": {
                "value": "Maya Chen",
                "evidence_turn_ids": [evidence_turn_id],
            },
            "contact": None,
        },
        "location": {
            "value": "14 Oak Street",
            "evidence_turn_ids": [evidence_turn_id],
        },
        "description": {
            "value": issue,
            "evidence_turn_ids": [evidence_turn_id],
        },
        "occurred_at": {
            "value": "this morning",
            "evidence_turn_ids": [evidence_turn_id],
        },
        "relevant_details": [],
        "urgency": {
            "classification": "urgent" if human_review_required else "routine",
            "rationale": (
                "Immediate human review is required."
                if human_review_required
                else "No immediate danger was reported."
            ),
            "evidence_turn_ids": [evidence_turn_id],
        },
        "summary": {
            "value": issue,
            "evidence_turn_ids": [evidence_turn_id],
        },
        "confidence": "medium",
        "evidence_gaps": [],
    }
    result: dict[str, object] = {
        "operational_issue": {
            "text": issue,
            "evidence_turn_ids": [evidence_turn_id],
        },
        "positive_practice": (
            {
                "text": practice,
                "evidence_turn_ids": [evidence_turn_id],
            }
            if practice
            else None
        ),
        "confidence": "medium",
    }
    synthesis: dict[str, object] = {"status": synthesis_status}
    if synthesis_status == "completed":
        synthesis["result"] = result
    return {
        "schema_version": "2.0",
        "session": {
            "id": session_id,
            "status": session_status,
            "started_at": created_at - 60,
            "artifact_created_at": created_at,
        },
        "interview_plan": {
            "id": "post_shift_guest_experience",
            "version": "1.0",
        },
        "respondent_context": {
            "property_id": property_id,
            "department": department,
        },
        "transcript": [
            {
                "id": "turn-0001",
                "role": "respondent",
                "text": issue,
                "created_at": created_at,
                "interrupted": False,
            }
        ],
        "objective_coverage": [],
        "safety": {
            "urgency": "urgent" if human_review_required else "routine",
            "human_review_required": human_review_required,
            "review_flag": (
                "Urgent — Human Review Required" if human_review_required else None
            ),
            "escalation": (
                {
                    "status": "simulated_operator_notified",
                    "source_turn_id": evidence_turn_id,
                    "elapsed_seconds": 4.0,
                    "simulated": True,
                }
                if human_review_required
                else None
            ),
        },
        "incident_record": incident_record,
        "synthesis": synthesis,
        "usage": {},
    }


class IntelligenceStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "signals.db"
        self.store = IntelligenceStore(self.database_path)
        self.addCleanup(self.store.close)

    def index(self, session_id: str, **kwargs: object) -> None:
        self.store.index_artifact(
            f"session-{session_id}.json",
            artifact(session_id, **kwargs),
        )

    def test_recurring_issue_is_withheld_until_threshold_and_keeps_sources(self) -> None:
        self.index("one", created_at=1)
        self.index("two", created_at=2)

        below = self.store.intelligence_snapshot(as_of=10)

        self.assertEqual(below["recurring_issues"], [])
        self.index("three", created_at=3)
        qualified = self.store.intelligence_snapshot(as_of=10)
        issue = qualified["recurring_issues"][0]
        self.assertEqual(issue["sample_size"], MIN_AGGREGATE_SAMPLE_SIZE)
        self.assertEqual(issue["supporting_session_ids"], ["one", "three", "two"])
        self.assertEqual(
            issue["supporting_artifact_ids"],
            ["session-one.json", "session-three.json", "session-two.json"],
        )

    def test_property_groups_qualify_independently(self) -> None:
        for index in range(3):
            self.index(
                f"a-{index}",
                created_at=index + 1,
                property_id="property-a",
            )
        for index in range(2):
            self.index(
                f"b-{index}",
                created_at=index + 1,
                property_id="property-b",
            )

        snapshot = self.store.intelligence_snapshot(
            group_by="property_id",
            as_of=10,
        )

        self.assertEqual(
            [item["dimension_value"] for item in snapshot["recurring_issues"]],
            ["property-a"],
        )

    def test_positive_practices_use_the_same_threshold_and_traceability(self) -> None:
        for index in range(3):
            self.index(f"session-{index}", created_at=index + 1)

        practices = self.store.intelligence_snapshot(as_of=10)["positive_practices"]

        self.assertEqual(len(practices), 1)
        self.assertEqual(practices[0]["sample_size"], 3)
        self.assertEqual(len(practices[0]["supporting_session_ids"]), 3)

    def test_incomplete_synthesis_is_durable_but_not_a_signal(self) -> None:
        self.index("failed", created_at=1, synthesis_status="failed")

        snapshot = self.store.intelligence_snapshot(as_of=10)

        self.assertEqual(snapshot["indexed_sessions"], 1)
        self.assertEqual(snapshot["recurring_issues"], [])

    def test_incomplete_session_and_invalid_evidence_cannot_create_signals(self) -> None:
        for index in range(3):
            self.index(
                f"incomplete-{index}",
                created_at=index + 1,
                session_status="incomplete",
            )
            self.index(
                f"invalid-evidence-{index}",
                created_at=index + 10,
                evidence_turn_id="turn-9999",
            )

        snapshot = self.store.intelligence_snapshot(as_of=100)

        self.assertEqual(snapshot["indexed_sessions"], 6)
        self.assertEqual(snapshot["recurring_issues"], [])
        self.assertEqual(snapshot["positive_practices"], [])

    def test_reindex_is_idempotent_and_replaces_stale_signals(self) -> None:
        for index in range(3):
            self.index(f"session-{index}", created_at=index + 1)
        self.index(
            "session-0",
            created_at=4,
            issue="A corrected operational issue",
            practice=None,
        )

        snapshot = self.store.intelligence_snapshot(as_of=10)

        self.assertEqual(snapshot["indexed_sessions"], 3)
        self.assertEqual(snapshot["recurring_issues"], [])
        self.assertEqual(snapshot["positive_practices"], [])

    def test_emerging_and_increasing_signals_require_recent_threshold(self) -> None:
        as_of = 100 * DAY
        for index in range(2):
            self.index(
                f"baseline-{index}",
                created_at=(50 + index) * DAY,
            )
        for index in range(3):
            self.index(
                f"recent-{index}",
                created_at=(80 + index) * DAY,
            )
        for index in range(3):
            self.index(
                f"emerging-{index}",
                created_at=(85 + index) * DAY,
                issue="A newly reported service delay",
            )

        trends = self.store.intelligence_snapshot(as_of=as_of)["trends"]

        self.assertEqual(
            {trend["classification"] for trend in trends},
            {"increasing", "emerging"},
        )
        self.assertTrue(all(len(trend["supporting_session_ids"]) >= 3 for trend in trends))

    def test_invalid_grouping_and_low_threshold_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported grouping"):
            self.store.intelligence_snapshot(group_by="employee_name")
        with self.assertRaisesRegex(ValueError, "cannot be below"):
            self.store.intelligence_snapshot(minimum_sample_size=1)

    def test_database_survives_reopen(self) -> None:
        for index in range(3):
            self.index(f"session-{index}", created_at=index + 1)
        self.store.close()
        self.store = IntelligenceStore(self.database_path)

        snapshot = self.store.intelligence_snapshot(as_of=10)

        self.assertEqual(snapshot["indexed_sessions"], 3)
        self.assertEqual(len(snapshot["recurring_issues"]), 1)
        recovered = self.store.load_artifact("session-0")
        self.assertEqual(recovered["session"]["id"], "session-0")

    def test_structured_incident_record_is_persisted_in_existing_database(self) -> None:
        self.index("incident", created_at=1, human_review_required=True)

        record = self.store.load_incident_record("incident")
        row = self.store.connection.execute(
            """
            SELECT incident_type, subcategory, caller_name, incident_location,
                   incident_description, occurred_at, urgency, summary,
                   human_review_required, escalation_status
            FROM incident_records
            WHERE session_id = ?
            """,
            ("incident",),
        ).fetchone()

        self.assertEqual(record["incident_type"], "parking_complaint")
        self.assertEqual(record["caller"]["name"]["value"], "Maya Chen")
        self.assertEqual(row["subcategory"], "blocked_driveway")
        self.assertEqual(row["incident_location"], "14 Oak Street")
        self.assertEqual(row["occurred_at"], "this morning")
        self.assertEqual(row["urgency"], "urgent")
        self.assertEqual(row["human_review_required"], 1)
        self.assertEqual(row["escalation_status"], "simulated_operator_notified")

    def test_existing_incident_table_is_migrated_with_escalation_columns(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        connection.execute(
            """
            CREATE TABLE incident_records (
                session_id TEXT PRIMARY KEY,
                incident_schema_version TEXT NOT NULL,
                incident_type TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                caller_name TEXT,
                caller_contact TEXT,
                incident_location TEXT,
                incident_description TEXT NOT NULL,
                occurred_at TEXT,
                urgency TEXT NOT NULL,
                summary TEXT NOT NULL,
                incident_json TEXT NOT NULL
            )
            """
        )
        connection.commit()
        connection.close()

        migrated = IntelligenceStore(legacy_path)
        self.addCleanup(migrated.close)
        columns = {
            row["name"]
            for row in migrated.connection.execute("PRAGMA table_info(incident_records)")
        }

        self.assertIn("human_review_required", columns)
        self.assertIn("escalation_status", columns)
        self.assertIn("incident_id", columns)
        self.assertIn("submission_status", columns)
        notification_table = migrated.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("operator_notifications",),
        ).fetchone()
        self.assertIsNotNone(notification_table)
