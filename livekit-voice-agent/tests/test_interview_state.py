from __future__ import annotations

import unittest

from hospitality_agent.models import CompletionReason, InterviewPhase, ObjectiveStatus
from hospitality_agent.plans import POST_SHIFT_GUEST_EXPERIENCE
from hospitality_agent.state import InterviewState


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class InterviewStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.state = InterviewState(POST_SHIFT_GUEST_EXPERIENCE, clock=self.clock)

    def test_state_starts_with_first_objective_and_explicit_budget(self) -> None:
        self.assertEqual(self.state.phase, InterviewPhase.OPENING)
        self.assertEqual(self.state.current_objective_id, "primary_event")
        self.assertEqual(self.state.respondent_turns, 0)
        self.assertIn("respondent_turns=0/12", self.state.prompt_snapshot())

    def test_recorded_evidence_advances_to_next_uncovered_objective(self) -> None:
        self.state.record_evidence(
            "primary_event",
            "Guests waited for rooms after the stated check-in time.",
            sufficient=True,
        )

        self.assertEqual(self.state.coverage["primary_event"], ObjectiveStatus.SUFFICIENT)
        self.assertEqual(self.state.current_objective_id, "guest_journey")

    def test_partial_evidence_keeps_objective_current_for_one_useful_probe(self) -> None:
        self.state.record_evidence(
            "primary_event",
            "The respondent mentioned a difficult check-in.",
            sufficient=False,
        )

        self.assertEqual(self.state.coverage["primary_event"], ObjectiveStatus.PARTIAL)
        self.assertEqual(self.state.current_objective_id, "primary_event")
