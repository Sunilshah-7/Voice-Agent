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

    def test_skip_is_honored_without_ending_the_interview(self) -> None:
        decision = self.state.observe_respondent_turn("I don't know. Can we skip that?")

        self.assertEqual(decision.kind, "skip")
        self.assertEqual(self.state.coverage["primary_event"], ObjectiveStatus.SKIPPED)
        self.assertEqual(self.state.current_objective_id, "guest_journey")
        self.assertEqual(self.state.phase, InterviewPhase.INTERVIEWING)
        self.assertIn("without asking why", decision.instruction)

    def test_skip_applies_to_the_question_actually_asked(self) -> None:
        self.state.mark_question_asked("workaround")

        self.state.observe_respondent_turn("Please skip that question.")

        self.assertEqual(self.state.coverage["workaround"], ObjectiveStatus.SKIPPED)
        self.assertEqual(self.state.coverage["primary_event"], ObjectiveStatus.NOT_STARTED)
        self.assertIsNone(self.state.asked_objective_id)

    def test_correction_is_accepted_and_counted(self) -> None:
        decision = self.state.observe_respondent_turn(
            "Actually, that's not right. The delay happened before check-in."
        )

        self.assertEqual(decision.kind, "correction")
        self.assertEqual(self.state.corrections, 1)
        self.assertIn("without defensiveness", decision.instruction)
        self.assertIn("correct_objective_evidence", decision.instruction)

    def test_corrected_evidence_supersedes_the_old_explanation(self) -> None:
        old_note = self.state.record_evidence(
            "operational_context",
            "Housekeeping did not update the room status.",
            sufficient=True,
        )

        replacement = self.state.correct_evidence(
            "operational_context",
            "Housekeeping updated it, but the front-desk system was delayed.",
            sufficient=True,
        )

        self.assertFalse(old_note.active)
        self.assertEqual(old_note.superseded_by, replacement.id)
        self.assertEqual(
            [note.summary for note in self.state.active_evidence("operational_context")],
            ["Housekeeping updated it, but the front-desk system was delayed."],
        )

    def test_explicit_request_to_end_moves_directly_to_closing(self) -> None:
        decision = self.state.observe_respondent_turn("I need to stop the interview now.")

        self.assertEqual(decision.kind, "early_exit")
        self.assertEqual(self.state.phase, InterviewPhase.CLOSING)
        self.assertEqual(self.state.completion_reason, CompletionReason.RESPONDENT_ENDED)
        self.assertIn("Do not ask another question", decision.instruction)

    def test_sensitive_disclosure_closes_without_investigative_probe(self) -> None:
        decision = self.state.observe_respondent_turn(
            "A supervisor threatened me and I feel unsafe."
        )

        self.assertEqual(decision.kind, "sensitive_disclosure")
        self.assertTrue(self.state.sensitive_disclosure)
        self.assertEqual(self.state.phase, InterviewPhase.CLOSING)
        self.assertEqual(
            self.state.completion_reason,
            CompletionReason.SENSITIVE_DISCLOSURE,
        )
        self.assertIn("Do not investigate", decision.instruction)

    def test_operational_safety_word_does_not_trigger_personal_disclosure_flow(self) -> None:
        decision = self.state.observe_respondent_turn(
            "The wet kitchen floor looked unsafe for the team."
        )

        self.assertEqual(decision.kind, "continue")
        self.assertEqual(self.state.phase, InterviewPhase.INTERVIEWING)

    def test_turn_budget_forces_confirmation(self) -> None:
        self.state.respondent_turns = POST_SHIFT_GUEST_EXPERIENCE.max_respondent_turns - 1

        decision = self.state.observe_respondent_turn("One more detail about the shift.")

        self.assertEqual(decision.kind, "turn_limit")
        self.assertEqual(self.state.phase, InterviewPhase.CONFIRMATION)
        self.assertEqual(self.state.completion_reason, CompletionReason.TURN_LIMIT)

    def test_time_budget_forces_confirmation(self) -> None:
        self.state.start_interview()
        self.clock.now = POST_SHIFT_GUEST_EXPERIENCE.target_duration_seconds

        decision = self.state.observe_respondent_turn("The team offered luggage storage.")

        self.assertEqual(decision.kind, "time_limit")
        self.assertEqual(self.state.phase, InterviewPhase.CONFIRMATION)
        self.assertEqual(self.state.completion_reason, CompletionReason.TIME_LIMIT)

    def test_clock_starts_when_interview_starts(self) -> None:
        self.clock.now = 200.0
        self.state.start_interview()
        self.clock.now = 205.0

        self.assertEqual(self.state.elapsed_seconds, 5.0)

    def test_all_resolved_objectives_move_to_confirmation(self) -> None:
        for objective in POST_SHIFT_GUEST_EXPERIENCE.objectives:
            self.state.record_evidence(
                objective.id,
                f"Supported evidence for {objective.id}.",
                sufficient=True,
            )

        self.assertEqual(self.state.phase, InterviewPhase.CONFIRMATION)
        self.assertIsNone(self.state.current_objective_id)

    def test_unknown_objective_cannot_be_recorded(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown research objective"):
            self.state.record_evidence("invented_objective", "Made up", sufficient=True)


if __name__ == "__main__":
    unittest.main()
