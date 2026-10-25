from __future__ import annotations

import unittest

from hospitality_agent.models import (
    CompletionReason,
    InterviewPhase,
    ObjectiveStatus,
    UrgencyClassification,
)
from hospitality_agent.plans import GENERAL_INQUIRY
from hospitality_agent.state import InterviewState


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class InterviewStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.state = InterviewState(GENERAL_INQUIRY, clock=self.clock)

    def test_state_starts_with_first_objective_and_explicit_budget(self) -> None:
        self.assertEqual(self.state.phase, InterviewPhase.OPENING)
        self.assertEqual(self.state.current_objective_id, "request_type")
        self.assertEqual(self.state.respondent_turns, 0)
        self.assertIn("respondent_turns=0/10", self.state.prompt_snapshot())

    def test_recorded_evidence_advances_to_next_uncovered_objective(self) -> None:
        self.state.record_evidence(
            "request_type",
            "The caller has a general service inquiry.",
            sufficient=True,
        )

        self.assertEqual(self.state.coverage["request_type"], ObjectiveStatus.SUFFICIENT)
        self.assertEqual(self.state.current_objective_id, "request_details")

    def test_partial_evidence_keeps_objective_current_for_one_useful_probe(self) -> None:
        self.state.record_evidence(
            "request_type",
            "The caller mentioned a routine concern but did not classify it.",
            sufficient=False,
        )

        self.assertEqual(self.state.coverage["request_type"], ObjectiveStatus.PARTIAL)
        self.assertEqual(self.state.current_objective_id, "request_type")

    def test_skip_is_honored_without_ending_the_interview(self) -> None:
        decision = self.state.observe_respondent_turn("I don't know. Can we skip that?")

        self.assertEqual(decision.kind, "skip")
        self.assertEqual(self.state.coverage["request_type"], ObjectiveStatus.SKIPPED)
        self.assertEqual(self.state.current_objective_id, "request_details")
        self.assertEqual(self.state.phase, InterviewPhase.INTERVIEWING)
        self.assertIn("without asking why", decision.instruction)

    def test_skip_applies_to_the_question_actually_asked(self) -> None:
        self.state.mark_question_asked("timing")

        self.state.observe_respondent_turn("Please skip that question.")

        self.assertEqual(self.state.coverage["timing"], ObjectiveStatus.SKIPPED)
        self.assertEqual(self.state.coverage["request_type"], ObjectiveStatus.NOT_STARTED)
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
            "request_details",
            "The caller said the request concerns curb access.",
            sufficient=True,
        )

        replacement = self.state.correct_evidence(
            "request_details",
            "The caller corrected the request to concern a street sign.",
            sufficient=True,
        )

        self.assertFalse(old_note.active)
        self.assertEqual(old_note.superseded_by, replacement.id)
        self.assertEqual(
            [note.summary for note in self.state.active_evidence("request_details")],
            ["The caller corrected the request to concern a street sign."],
        )

    def test_explicit_request_to_end_moves_directly_to_closing(self) -> None:
        decision = self.state.observe_respondent_turn("I need to stop the interview now.")

        self.assertEqual(decision.kind, "early_exit")
        self.assertEqual(self.state.phase, InterviewPhase.CLOSING)
        self.assertEqual(self.state.completion_reason, CompletionReason.RESPONDENT_ENDED)
        self.assertIn("Do not ask another question", decision.instruction)

    def test_potential_emergency_stops_intake_and_starts_simulated_escalation(self) -> None:
        decision = self.state.observe_respondent_turn(
            "Someone threatened me with a knife and I am in immediate danger.",
            source_turn_id="turn-0003",
        )

        self.assertEqual(decision.kind, "urgent_escalation")
        self.assertTrue(self.state.sensitive_disclosure)
        self.assertEqual(self.state.phase, InterviewPhase.CLOSING)
        self.assertEqual(
            self.state.completion_reason,
            CompletionReason.URGENT_ESCALATION,
        )
        self.assertEqual(self.state.urgency, UrgencyClassification.URGENT)
        self.assertTrue(self.state.human_review_required)
        self.assertEqual(self.state.escalation_status, "simulated_operator_notified")
        self.assertEqual(self.state.escalation_source_turn_id, "turn-0003")
        self.assertIn("Stop routine intake", decision.instruction)

    def test_all_required_urgent_disclosure_types_are_detected(self) -> None:
        disclosures = (
            "Someone is injured and bleeding.",
            "A person threatened us with a gun.",
            "There is violence and fighting outside.",
            "There is a fire and I can see smoke.",
            "We are in immediate danger right now.",
        )
        for disclosure in disclosures:
            with self.subTest(disclosure=disclosure):
                state = InterviewState(GENERAL_INQUIRY, clock=self.clock)
                decision = state.observe_respondent_turn(disclosure)
                self.assertEqual(decision.kind, "urgent_escalation")
                self.assertTrue(state.human_review_required)

    def test_urgency_can_increase_but_urgent_escalation_cannot_be_downgraded(self) -> None:
        self.state.update_urgency(
            UrgencyClassification.PRIORITY,
            "The access issue may need prompt review.",
        )
        changed = self.state.update_urgency(
            UrgencyClassification.URGENT,
            "The caller later reported an active threat.",
            source_turn_id="turn-0004",
        )
        downgraded = self.state.update_urgency(
            UrgencyClassification.ROUTINE,
            "Attempted automatic downgrade.",
        )

        self.assertTrue(changed)
        self.assertFalse(downgraded)
        self.assertEqual(self.state.urgency, UrgencyClassification.URGENT)
        self.assertEqual(self.state.escalation_source_turn_id, "turn-0004")

    def test_urgent_escalation_preserves_previously_collected_evidence(self) -> None:
        note = self.state.record_evidence(
            "request_type",
            "The caller initially reported a general inquiry.",
            sufficient=True,
            source_turn_id="turn-0001",
        )

        self.state.observe_respondent_turn(
            "I can see smoke and someone may be trapped.",
            source_turn_id="turn-0002",
        )

        self.assertEqual(self.state.active_evidence("request_type"), (note,))
        with self.assertRaisesRegex(ValueError, "blocked after urgent escalation"):
            self.state.mark_question_asked("request_details")

    def test_non_emergency_safety_word_does_not_trigger_escalation(self) -> None:
        decision = self.state.observe_respondent_turn(
            "The wet kitchen floor looked unsafe for the team."
        )

        self.assertEqual(decision.kind, "continue")
        self.assertEqual(self.state.phase, InterviewPhase.INTERVIEWING)

    def test_turn_budget_forces_confirmation(self) -> None:
        self.state.respondent_turns = GENERAL_INQUIRY.max_respondent_turns - 1

        decision = self.state.observe_respondent_turn("One more detail about the shift.")

        self.assertEqual(decision.kind, "turn_limit")
        self.assertEqual(self.state.phase, InterviewPhase.CONFIRMATION)
        self.assertEqual(self.state.completion_reason, CompletionReason.TURN_LIMIT)

    def test_time_budget_forces_confirmation(self) -> None:
        self.state.start_interview()
        self.clock.now = GENERAL_INQUIRY.target_duration_seconds

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
        for objective in GENERAL_INQUIRY.objectives:
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
