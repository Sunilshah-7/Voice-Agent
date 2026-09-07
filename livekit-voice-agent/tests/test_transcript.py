from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from livekit.agents import llm

from hospitality_agent.models import CompletionReason, InterviewPhase, RespondentContext
from hospitality_agent.plans import POST_SHIFT_GUEST_EXPERIENCE
from hospitality_agent.state import InterviewState
from hospitality_agent.transcript import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactWriteError,
    TranscriptRecorder,
    respondent_context_from_job_metadata,
)


class FixedClock:
    def __init__(self, value: float = 1_700_000_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class TranscriptRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FixedClock()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.recorder = TranscriptRecorder(
            plan=POST_SHIFT_GUEST_EXPERIENCE,
            session_id="hotel-room/session 42",
            output_dir=self.temp_dir.name,
            respondent_context=RespondentContext(
                property_id="property-12",
                department="front_desk",
                anonymous_participation=True,
            ),
            clock=self.clock,
        )

    def message(
        self,
        *,
        message_id: str,
        role: str,
        text: str,
        interrupted: bool = False,
    ) -> llm.ChatMessage:
        return llm.ChatMessage(
            id=message_id,
            role=role,
            content=[text],
            interrupted=interrupted,
            created_at=self.clock(),
        )

    def test_records_stable_normalized_turns_and_deduplicates_provider_events(self) -> None:
        message = self.message(
            message_id="provider-user-1",
            role="user",
            text="Guests   waited\n at check-in.",
        )

        first = self.recorder.record_chat_message(message)
        duplicate = self.recorder.record_chat_message(message)

        self.assertIsNotNone(first)
        self.assertEqual(first, duplicate)
        self.assertEqual(len(self.recorder.turns), 1)
        self.assertEqual(first.id, "turn-0001")
        self.assertEqual(first.role, "respondent")
        self.assertEqual(first.text, "Guests waited at check-in.")

    def test_ignores_non_conversation_roles_and_empty_messages(self) -> None:
        system_message = self.message(
            message_id="system-1",
            role="system",
            text="Internal instruction",
        )
        empty_message = self.message(
            message_id="assistant-empty",
            role="assistant",
            text="   ",
        )

        self.assertIsNone(self.recorder.record_chat_message(system_message))
        self.assertIsNone(self.recorder.record_chat_message(empty_message))
        self.assertEqual(self.recorder.turns, [])

    def test_completed_artifact_contains_plan_transcript_coverage_and_allowed_metadata(self) -> None:
        state = InterviewState(POST_SHIFT_GUEST_EXPERIENCE, clock=self.clock)
        self.recorder.record_chat_message(
            self.message(message_id="assistant-1", role="assistant", text="What happened?")
        )
        respondent_turn = self.recorder.record_chat_message(
            self.message(
                message_id="provider-user-1",
                role="user",
                text="Guests waited at check-in.",
            )
        )
        assert respondent_turn is not None
        state.record_evidence(
            "primary_event",
            "Guests waited for rooms.",
            sufficient=True,
            source_turn_id=respondent_turn.id,
        )
        state.phase = InterviewPhase.CONFIRMATION
        state.completion_reason = CompletionReason.OBJECTIVES_COVERED
        state.complete()
        self.clock.value += 60
        self.recorder.set_close("task_completed", created_at=self.clock())

        path = self.recorder.finalize(
            state,
            usage={"llm_prompt_tokens": 42},
            synthesis={
                "status": "completed",
                "result": {"confidence": "medium"},
            },
        )
        artifact = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(artifact["schema_version"], ARTIFACT_SCHEMA_VERSION)
        self.assertEqual(artifact["session"]["status"], "completed")
        self.assertEqual(artifact["session"]["interview_phase"], "completed")
        self.assertEqual(artifact["session"]["close_reason"], "task_completed")
        self.assertEqual(artifact["session"]["ended_at"], 1_700_000_060.0)
        self.assertEqual(artifact["interview_plan"]["version"], "1.0")
        self.assertEqual(artifact["respondent_context"]["department"], "front_desk")
        self.assertEqual(len(artifact["transcript"]), 2)
        self.assertEqual(artifact["session"]["transcript_turns"], 2)
        evidence = artifact["objective_coverage"][0]["evidence"][0]
        self.assertEqual(evidence["source_turn_id"], respondent_turn.id)
        self.assertEqual(artifact["usage"]["llm_prompt_tokens"], 42)
        self.assertEqual(artifact["synthesis"]["status"], "completed")
        self.assertEqual(artifact["synthesis"]["result"]["confidence"], "medium")
        serialized = path.read_text(encoding="utf-8")
        self.assertNotIn("provider-user-1", serialized)

    def test_disconnect_before_completion_is_saved_as_incomplete(self) -> None:
        state = InterviewState(POST_SHIFT_GUEST_EXPERIENCE, clock=self.clock)
        state.start_interview()
        self.recorder.set_close("participant_disconnected")

        artifact = self.recorder.build_artifact(state)

        self.assertEqual(artifact["session"]["status"], "incomplete")
        self.assertEqual(
            artifact["session"]["close_reason"],
            "participant_disconnected",
        )
        self.assertIsNone(artifact["session"]["completion_reason"])

    def test_interrupted_agent_turn_is_preserved_and_marked(self) -> None:
        turn = self.recorder.record_chat_message(
            self.message(
                message_id="assistant-1",
                role="assistant",
                text="A response that was interrupted",
                interrupted=True,
            )
        )

        self.assertIsNotNone(turn)
        self.assertTrue(turn.interrupted)

    def test_finalize_is_idempotent(self) -> None:
        state = InterviewState(POST_SHIFT_GUEST_EXPERIENCE, clock=self.clock)

        first_path = self.recorder.finalize(state)
        original = first_path.read_text(encoding="utf-8")
        self.clock.value += 30
        second_path = self.recorder.finalize(state, usage={"changed": 1})

        self.assertEqual(first_path, second_path)
        self.assertEqual(first_path.read_text(encoding="utf-8"), original)

    def test_filename_cannot_escape_output_directory(self) -> None:
        path = self.recorder.finalize(InterviewState(POST_SHIFT_GUEST_EXPERIENCE))

        self.assertEqual(path.parent, Path(self.temp_dir.name))
        self.assertNotIn("/", path.name)

    def test_write_failure_is_explicit(self) -> None:
        blocking_file = Path(self.temp_dir.name) / "not-a-directory"
        blocking_file.write_text("occupied", encoding="utf-8")
        recorder = TranscriptRecorder(
            plan=POST_SHIFT_GUEST_EXPERIENCE,
            output_dir=blocking_file,
        )

        with self.assertRaisesRegex(ArtifactWriteError, "Could not write session artifact"):
            recorder.finalize(InterviewState(POST_SHIFT_GUEST_EXPERIENCE))

    def test_respondent_context_rejects_unapproved_identifiers(self) -> None:
        with self.assertRaisesRegex(ValueError, "guest_name, room_number"):
            RespondentContext.from_mapping(
                {"guest_name": "Example Guest", "room_number": "404"}
            )

    def test_job_metadata_loads_only_nested_allowed_respondent_context(self) -> None:
        context = respondent_context_from_job_metadata(
            json.dumps(
                {
                    "unrelated_dispatch_value": "not persisted",
                    "respondent_context": {
                        "department": "housekeeping",
                        "shift_type": "evening",
                    },
                }
            )
        )

        self.assertEqual(context.department, "housekeeping")
        self.assertEqual(context.shift_type, "evening")

    def test_invalid_job_metadata_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            respondent_context_from_job_metadata("not-json")

        with self.assertRaisesRegex(ValueError, "Unsupported respondent metadata"):
            respondent_context_from_job_metadata(
                json.dumps({"respondent_context": {"employee_name": "Do not store"}})
            )


if __name__ == "__main__":
    unittest.main()
