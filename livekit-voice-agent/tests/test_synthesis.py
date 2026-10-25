from __future__ import annotations

import json
import unittest

from hospitality_agent.models import TranscriptTurn
from hospitality_agent.models import UrgencyClassification
from hospitality_agent.plans import PARKING_COMPLAINT
from hospitality_agent.state import InterviewState
from hospitality_agent.synthesis import (
    SynthesisGenerationError,
    SynthesisService,
    SynthesisValidationError,
)


class FakeGenerator:
    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def respondent_turn(turn_id: str, text: str, *, interrupted: bool = False) -> TranscriptTurn:
    return TranscriptTurn(
        id=turn_id,
        role="respondent",
        text=text,
        created_at=1_700_000_000.0,
        interrupted=interrupted,
    )


def sourced(value: str, *turn_ids: str) -> dict[str, object]:
    return {"value": value, "evidence_turn_ids": list(turn_ids)}


def valid_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "incident_type": "parking_complaint",
        "subcategory": "blocked_driveway",
        "classification_evidence_turn_ids": ["turn-0001"],
        "caller": {
            "name": sourced("Maya Chen", "turn-0002"),
            "contact": sourced("maya@example.com", "turn-0002"),
        },
        "location": sourced("14 Oak Street", "turn-0001"),
        "description": sourced(
            "A blue Honda sedan is blocking the caller's driveway.",
            "turn-0001",
        ),
        "occurred_at": sourced("around 8:15 this morning", "turn-0001"),
        "relevant_details": [
            sourced("The caller cannot leave the driveway.", "turn-0001")
        ],
        "urgency": {
            "classification": "priority",
            "rationale": "Access is blocked, but no immediate danger was reported.",
            "evidence_turn_ids": ["turn-0001"],
        },
        "summary": sourced(
            "Caller reports a blue Honda sedan blocking a driveway at 14 Oak Street.",
            "turn-0001",
        ),
        "confidence": "high",
        "evidence_gaps": ["License plate was not provided."],
    }


class SynthesisServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.turns = [
            respondent_turn(
                "turn-0001",
                "A blue Honda sedan has blocked my driveway at 14 Oak Street since "
                "around 8:15 this morning, and I cannot get my car out.",
            ),
            respondent_turn(
                "turn-0002",
                "My name is Maya Chen and my email is maya@example.com.",
            ),
        ]
        self.state = InterviewState(PARKING_COMPLAINT)

    async def synthesize(self, payload: dict[str, object]):
        service = SynthesisService(FakeGenerator(json.dumps(payload)))
        return await service.synthesize(turns=self.turns, state=self.state)

    async def test_valid_incident_record_is_accepted(self) -> None:
        result = await self.synthesize(valid_payload())

        self.assertEqual(result.incident_type, "parking_complaint")
        self.assertEqual(result.subcategory, "blocked_driveway")
        self.assertEqual(result.caller.name.value, "Maya Chen")
        self.assertEqual(result.urgency.classification.value, "priority")
        self.assertEqual(result.summary.evidence_turn_ids, ["turn-0001"])

    async def test_json_code_fence_is_tolerated(self) -> None:
        response = "```json\n" + json.dumps(valid_payload()) + "\n```"
        service = SynthesisService(FakeGenerator(response))

        result = await service.synthesize(turns=self.turns, state=self.state)

        self.assertEqual(result.location.value, "14 Oak Street")

    async def test_unknown_evidence_turn_is_rejected(self) -> None:
        payload = valid_payload()
        payload["description"]["evidence_turn_ids"] = ["turn-9999"]

        with self.assertRaisesRegex(SynthesisValidationError, "Unsupported evidence"):
            await self.synthesize(payload)

    async def test_interrupted_turn_cannot_support_record(self) -> None:
        self.turns[0] = respondent_turn(
            "turn-0001",
            self.turns[0].text,
            interrupted=True,
        )

        with self.assertRaisesRegex(SynthesisValidationError, "Unsupported evidence"):
            await self.synthesize(valid_payload())

    async def test_invented_contact_information_is_rejected(self) -> None:
        payload = valid_payload()
        payload["caller"]["contact"] = sourced("555-0100", "turn-0002")

        with self.assertRaisesRegex(SynthesisValidationError, "must appear verbatim"):
            await self.synthesize(payload)

    async def test_incident_type_must_match_selected_category(self) -> None:
        payload = valid_payload()
        payload["incident_type"] = "noise_complaint"

        with self.assertRaisesRegex(SynthesisValidationError, "does not match"):
            await self.synthesize(payload)

    async def test_incident_record_cannot_downgrade_active_escalation(self) -> None:
        self.state.update_urgency(
            UrgencyClassification.URGENT,
            "A potential emergency requires immediate human review.",
            source_turn_id="turn-0001",
        )
        payload = valid_payload()
        payload["urgency"] = {
            "classification": "routine",
            "rationale": "Incorrect downgrade.",
            "evidence_turn_ids": ["turn-0001"],
        }

        with self.assertRaisesRegex(SynthesisValidationError, "cannot downgrade"):
            await self.synthesize(payload)

    async def test_malformed_response_is_rejected(self) -> None:
        service = SynthesisService(FakeGenerator("not json"))

        with self.assertRaisesRegex(SynthesisValidationError, "required schema"):
            await service.synthesize(turns=self.turns, state=self.state)

    async def test_generation_failure_is_preserved(self) -> None:
        service = SynthesisService(
            FakeGenerator(error=SynthesisGenerationError("provider unavailable"))
        )

        with self.assertRaisesRegex(SynthesisGenerationError, "provider unavailable"):
            await service.synthesize(turns=self.turns, state=self.state)

    async def test_no_finalized_respondent_turns_is_rejected_before_generation(self) -> None:
        generator = FakeGenerator(json.dumps(valid_payload()))
        service = SynthesisService(generator)

        with self.assertRaisesRegex(SynthesisValidationError, "No finalized respondent"):
            await service.synthesize(turns=[], state=self.state)
        self.assertEqual(generator.prompts, [])

    def test_prompt_contains_timestamps_and_excludes_superseded_evidence(self) -> None:
        self.state.record_evidence(
            "vehicle_description",
            "The vehicle is black.",
            sufficient=True,
            source_turn_id="turn-0001",
        )
        self.state.correct_evidence(
            "vehicle_description",
            "The vehicle is blue.",
            sufficient=True,
            source_turn_id="turn-0001",
        )
        service = SynthesisService(FakeGenerator(json.dumps(valid_payload())))

        prompt = service.build_prompt(turns=self.turns, state=self.state)

        self.assertNotIn("vehicle is black", prompt)
        self.assertIn("vehicle is blue", prompt)
        self.assertIn("1700000000.000", prompt)
        self.assertIn("Do not treat a\n  transcript capture timestamp", prompt)


if __name__ == "__main__":
    unittest.main()
