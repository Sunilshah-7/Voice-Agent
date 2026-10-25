from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hospitality_agent.completion import (
    CompletionCoordinator,
    SimulatedOperatorNotifier,
)
from hospitality_agent.intelligence import IntelligenceStore
from hospitality_agent.models import InterviewPhase, TranscriptTurn
from hospitality_agent.plans import PARKING_COMPLAINT
from hospitality_agent.state import InterviewState
from hospitality_agent.synthesis import IncidentRecord, SynthesisValidationError
from hospitality_agent.transcript import TranscriptRecorder


def incident_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "incident_type": "parking_complaint",
        "subcategory": "blocked_driveway",
        "classification_evidence_turn_ids": ["turn-0001"],
        "caller": {"name": None, "contact": None},
        "location": {
            "value": "14 Oak Street",
            "evidence_turn_ids": ["turn-0001"],
        },
        "description": {
            "value": "A blue sedan is blocking a driveway.",
            "evidence_turn_ids": ["turn-0001"],
        },
        "occurred_at": {
            "value": "this morning",
            "evidence_turn_ids": ["turn-0001"],
        },
        "relevant_details": [],
        "urgency": {
            "classification": "routine",
            "rationale": "No immediate danger was reported.",
            "evidence_turn_ids": ["turn-0001"],
        },
        "summary": {
            "value": "A caller reports a blue sedan blocking a driveway at 14 Oak Street.",
            "evidence_turn_ids": ["turn-0001"],
        },
        "confidence": "high",
        "evidence_gaps": ["License plate was not provided."],
    }


class FakeSynthesisService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def synthesize(self, **_: object) -> IncidentRecord:
        self.calls += 1
        if self.fail:
            raise SynthesisValidationError("invalid extraction")
        return IncidentRecord.model_validate(incident_payload())


class CompletionCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def make_context(self, root: str) -> tuple[TranscriptRecorder, InterviewState]:
        recorder = TranscriptRecorder(
            plan=PARKING_COMPLAINT,
            session_id="session-completion",
            output_dir=Path(root) / "outputs",
        )
        recorder.turns.append(
            TranscriptTurn(
                id="turn-0001",
                role="respondent",
                text="A blue sedan is blocking my driveway at 14 Oak Street this morning.",
                created_at=1_700_000_000.0,
            )
        )
        state = InterviewState(PARKING_COMPLAINT)
        state.phase = InterviewPhase.CONFIRMATION
        state.complete()
        return recorder, state

    async def test_delivered_notification_submits_report_and_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            recorder, state = self.make_context(root)
            database_path = Path(root) / "incidents.db"
            coordinator = CompletionCoordinator(
                recorder=recorder,
                synthesis_service=FakeSynthesisService(),
                database_path=database_path,
                notifier=SimulatedOperatorNotifier("delivered", clock=lambda: 123.0),
                usage_provider=lambda: {"llm_prompt_tokens": 7},
            )

            result = await coordinator.submit(state)

            self.assertTrue(result.success)
            self.assertRegex(result.incident_id, r"^INC-[0-9a-f-]{36}$")
            self.assertEqual(result.submission_status, "Submitted for Review")
            self.assertEqual(result.notification_status, "delivered")
            self.assertIn("simulated reviewer notification was delivered", result.confirmation)
            self.assertIn("No dispatcher, police department", result.confirmation)
            self.assertIsNotNone(result.artifact_path)

            artifact = json.loads(result.artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["incident"]["id"], result.incident_id)
            self.assertEqual(artifact["incident"]["status"], "Submitted for Review")
            self.assertEqual(artifact["transcript"][0]["id"], "turn-0001")
            self.assertEqual(artifact["operator_notification"]["status"], "delivered")

            store = IntelligenceStore(database_path)
            self.addCleanup(store.close)
            record = store.load_incident_record("session-completion")
            notification = store.connection.execute(
                "SELECT * FROM operator_notifications WHERE incident_id = ?",
                (result.incident_id,),
            ).fetchone()
            self.assertEqual(record["summary"]["value"], incident_payload()["summary"]["value"])
            self.assertEqual(notification["category"], "parking_complaint")
            self.assertEqual(notification["location"], "14 Oak Street")
            self.assertEqual(notification["urgency"], "routine")
            self.assertEqual(notification["status"], "delivered")
            self.assertEqual(notification["simulated"], 1)

    async def test_notification_states_are_distinct_and_idempotent(self) -> None:
        for mode in ("queued", "failed"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                recorder, state = self.make_context(root)
                synthesis = FakeSynthesisService()
                coordinator = CompletionCoordinator(
                    recorder=recorder,
                    synthesis_service=synthesis,
                    database_path=Path(root) / "incidents.db",
                    notifier=SimulatedOperatorNotifier(mode),
                )

                first = await coordinator.submit(state)
                second = await coordinator.submit(state)

                self.assertIs(first, second)
                self.assertEqual(first.notification_status, mode)
                self.assertIn(f"notification {'is queued' if mode == 'queued' else 'failed'}", first.confirmation)
                self.assertEqual(synthesis.calls, 1)

                store = IntelligenceStore(Path(root) / "incidents.db")
                rows = store.connection.execute(
                    "SELECT status, delivered_at, failure_reason FROM operator_notifications"
                ).fetchall()
                store.close()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["status"], mode)
                self.assertIsNone(rows[0]["delivered_at"])
                self.assertEqual(
                    rows[0]["failure_reason"],
                    "simulated_notification_failure" if mode == "failed" else None,
                )

    async def test_failed_extraction_never_claims_submission_or_notification(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            recorder, state = self.make_context(root)
            coordinator = CompletionCoordinator(
                recorder=recorder,
                synthesis_service=FakeSynthesisService(fail=True),
                database_path=Path(root) / "incidents.db",
            )

            result = await coordinator.submit(state)

            self.assertFalse(result.success)
            self.assertEqual(result.submission_status, "Not Submitted")
            self.assertIsNone(result.notification_status)
            self.assertIn("couldn't submit", result.confirmation)
            self.assertIn("No dispatcher, police department", result.confirmation)

    async def test_database_failure_never_claims_successful_submission(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            recorder, state = self.make_context(root)
            blocking_file = Path(root) / "not-a-directory"
            blocking_file.write_text("occupied", encoding="utf-8")
            coordinator = CompletionCoordinator(
                recorder=recorder,
                synthesis_service=FakeSynthesisService(),
                database_path=blocking_file / "incidents.db",
            )

            result = await coordinator.submit(state)

            self.assertFalse(result.success)
            self.assertEqual(result.error_code, "database_persistence_failed")
            self.assertEqual(result.submission_status, "Not Submitted")
            self.assertIn("couldn't submit", result.confirmation)

    def test_incident_ids_are_unique_per_session_recorder(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            first, _ = self.make_context(root)
            second = TranscriptRecorder(
                plan=PARKING_COMPLAINT,
                session_id="another-session",
                output_dir=root,
            )

            self.assertNotEqual(first.incident_id, second.incident_id)


if __name__ == "__main__":
    unittest.main()
