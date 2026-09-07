from __future__ import annotations

import json
import unittest

from hospitality_agent.models import TranscriptTurn
from hospitality_agent.plans import POST_SHIFT_GUEST_EXPERIENCE
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


def valid_payload() -> dict[str, object]:
    return {
        "operational_issue": {
            "text": "Guests waited at check-in for room status updates.",
            "evidence_turn_ids": ["turn-0001"],
        },
        "guest_impact": {
            "text": "Guests were frustrated and asked for a manager.",
            "evidence_turn_ids": ["turn-0002"],
        },
        "root_cause_hypotheses": [
            {
                "text": "A delayed front-desk system may have contributed to stale room status.",
                "evidence_turn_ids": ["turn-0002"],
            }
        ],
        "reported_frequency": {
            "text": "The respondent reported that it happened three times this week.",
            "evidence_turn_ids": ["turn-0002"],
        },
        "reported_severity": None,
        "workaround": {
            "text": "The team called the housekeeping supervisor manually.",
            "evidence_turn_ids": ["turn-0002"],
        },
        "positive_practice": {
            "text": "The front-desk team kept guests updated.",
            "evidence_turn_ids": ["turn-0002"],
        },
        "recommended_action": {
            "text": "Pilot a room-status confirmation during shift handoff.",
            "evidence_turn_ids": ["turn-0002"],
            "scope": "pilot",
        },
        "representative_quotes": [
            {
                "text": "Guests were frustrated and two asked for a manager.",
                "turn_id": "turn-0002",
            }
        ],
        "confidence": "medium",
        "evidence_gaps": ["No housekeeping perspective was collected."],
    }


class SynthesisServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.turns = [
            respondent_turn(
                "turn-0001",
                "Several guests waited at check-in because rooms were still marked dirty.",
            ),
            respondent_turn(
                "turn-0002",
                "The front-desk system was delayed. It happened three times this week. "
                "Guests were frustrated and two asked for a manager. We called the "
                "housekeeping supervisor manually and kept guests updated. A room-status "
                "confirmation during shift handoff could help.",
            ),
        ]
        self.state = InterviewState(POST_SHIFT_GUEST_EXPERIENCE)

    async def synthesize(self, payload: dict[str, object]):
        generator = FakeGenerator(json.dumps(payload))
        service = SynthesisService(generator)
        return await service.synthesize(turns=self.turns, state=self.state)

    async def test_valid_evidence_grounded_result_is_accepted(self) -> None:
        result = await self.synthesize(valid_payload())

        self.assertEqual(result.confidence.value, "medium")
        self.assertEqual(result.recommended_action.scope, "pilot")
        self.assertEqual(result.representative_quotes[0].turn_id, "turn-0002")

    async def test_json_code_fence_is_tolerated(self) -> None:
        response = "```json\n" + json.dumps(valid_payload()) + "\n```"
        service = SynthesisService(FakeGenerator(response))

        result = await service.synthesize(turns=self.turns, state=self.state)

        self.assertEqual(result.operational_issue.evidence_turn_ids, ["turn-0001"])

    async def test_unknown_evidence_turn_is_rejected(self) -> None:
        payload = valid_payload()
        payload["operational_issue"]["evidence_turn_ids"] = ["turn-9999"]

        with self.assertRaisesRegex(SynthesisValidationError, "Unsupported evidence"):
            await self.synthesize(payload)

    async def test_interrupted_respondent_turn_cannot_support_a_finding(self) -> None:
        self.turns[0] = respondent_turn(
            "turn-0001",
            self.turns[0].text,
            interrupted=True,
        )

        with self.assertRaisesRegex(SynthesisValidationError, "Unsupported evidence"):
            await self.synthesize(valid_payload())

    async def test_invented_quote_is_rejected(self) -> None:
        payload = valid_payload()
        payload["representative_quotes"][0]["text"] = "A quote nobody said."

        with self.assertRaisesRegex(SynthesisValidationError, "not verbatim"):
            await self.synthesize(payload)

    async def test_invented_frequency_number_is_rejected(self) -> None:
        payload = valid_payload()
        payload["reported_frequency"]["text"] = "It happened twelve times this week."

        with self.assertRaisesRegex(SynthesisValidationError, "unsupported number"):
            await self.synthesize(payload)

    async def test_organization_wide_overclaim_is_rejected(self) -> None:
        payload = valid_payload()
        payload["operational_issue"]["text"] = (
            "This proves the issue happens across the company."
        )

        with self.assertRaisesRegex(SynthesisValidationError, "organization-wide claim"):
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

    def test_prompt_excludes_superseded_evidence(self) -> None:
        self.state.record_evidence(
            "operational_context",
            "Housekeeping failed to update the room.",
            sufficient=True,
            source_turn_id="turn-0002",
        )
        self.state.correct_evidence(
            "operational_context",
            "The front-desk system was delayed.",
            sufficient=True,
            source_turn_id="turn-0002",
        )
        service = SynthesisService(FakeGenerator(json.dumps(valid_payload())))

        prompt = service.build_prompt(turns=self.turns, state=self.state)

        self.assertNotIn("Housekeeping failed", prompt)
        self.assertIn("front-desk system was delayed", prompt)


if __name__ == "__main__":
    unittest.main()
