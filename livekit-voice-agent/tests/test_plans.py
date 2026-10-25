from __future__ import annotations

import json
import unittest

from hospitality_agent.models import InterviewPlan, ResearchObjective
from hospitality_agent.plans import (
    DEFAULT_INTERVIEW_PLAN,
    GENERAL_INQUIRY,
    INTERVIEW_PLANS,
    LOST_PET,
    NOISE_COMPLAINT,
    PARKING_COMPLAINT,
    get_interview_plan,
    interview_plan_from_job_metadata,
)
from hospitality_agent.state import InterviewState


class InterviewPlanTests(unittest.TestCase):
    def test_registry_contains_primary_categories_and_general_inquiry(self) -> None:
        self.assertEqual(
            set(INTERVIEW_PLANS),
            {
                "general_inquiry",
                "parking_complaint",
                "lost_pet",
                "noise_complaint",
            },
        )
        self.assertIs(
            INTERVIEW_PLANS[GENERAL_INQUIRY.id],
            GENERAL_INQUIRY,
        )
        self.assertIs(INTERVIEW_PLANS[PARKING_COMPLAINT.id], PARKING_COMPLAINT)
        self.assertIs(INTERVIEW_PLANS[LOST_PET.id], LOST_PET)
        self.assertIs(
            INTERVIEW_PLANS[NOISE_COMPLAINT.id],
            NOISE_COMPLAINT,
        )
        self.assertEqual({plan.version for plan in INTERVIEW_PLANS.values()}, {"1.0"})

    def test_each_template_has_safe_opening_and_valid_completion_contract(self) -> None:
        for plan in INTERVIEW_PLANS.values():
            with self.subTest(plan=plan.id):
                self.assertIn("AI non-emergency call intake agent", plan.opening_message)
                self.assertIn("not a dispatcher", plan.opening_message)
                self.assertIn("skip a question", plan.opening_message)
                self.assertIn("call 911 or your local emergency number", plan.opening_message)
                self.assertTrue(set(plan.core_objective_ids).issubset(plan.objective_ids))
                self.assertEqual(plan.initial_objective_id, plan.objectives[0].id)

    def test_each_template_can_reach_confirmation_using_its_own_objectives(self) -> None:
        for plan in INTERVIEW_PLANS.values():
            with self.subTest(plan=plan.id):
                state = InterviewState(plan)
                for objective in plan.objectives:
                    state.record_evidence(
                        objective.id,
                        f"Evidence for {objective.id}",
                        sufficient=True,
                    )
                self.assertTrue(state.should_confirm)
                self.assertEqual(state.phase.value, "confirmation")

    def test_default_and_explicit_plan_selection(self) -> None:
        self.assertIs(get_interview_plan(None), DEFAULT_INTERVIEW_PLAN)
        self.assertIs(get_interview_plan(""), DEFAULT_INTERVIEW_PLAN)
        self.assertIs(get_interview_plan("parking_complaint"), PARKING_COMPLAINT)
        selected = interview_plan_from_job_metadata(
            json.dumps({"call_category": "noise_complaint"})
        )
        self.assertIs(selected, NOISE_COMPLAINT)

    def test_legacy_metadata_key_remains_compatible(self) -> None:
        selected = interview_plan_from_job_metadata(
            json.dumps({"interview_plan_id": "lost_pet"})
        )
        self.assertIs(selected, LOST_PET)

    def test_unknown_or_invalid_plan_metadata_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown interview plan"):
            get_interview_plan("unknown")
        with self.assertRaisesRegex(ValueError, "must be a string"):
            interview_plan_from_job_metadata(json.dumps({"call_category": 7}))

    def test_plan_model_rejects_invalid_completion_contract(self) -> None:
        objective = ResearchObjective(
            id="known",
            goal="Known goal",
            evidence_needed="Known evidence",
        )
        with self.assertRaisesRegex(ValueError, "Unknown core objective"):
            InterviewPlan(
                id="invalid",
                version="1.0",
                title="Invalid",
                business_goal="Test validation",
                respondent_type="Tester",
                target_duration_seconds=60,
                max_respondent_turns=2,
                opening_message="Opening",
                closing_message="Closing",
                objectives=(objective,),
                core_objective_ids=("missing",),
            )


if __name__ == "__main__":
    unittest.main()
