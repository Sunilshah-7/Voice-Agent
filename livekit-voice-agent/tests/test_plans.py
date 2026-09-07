from __future__ import annotations

import json
import unittest

from hospitality_agent.models import InterviewPlan, ResearchObjective
from hospitality_agent.plans import (
    DEFAULT_INTERVIEW_PLAN,
    INTERVIEW_PLANS,
    NEW_PROCESS_ROLLOUT,
    POST_SHIFT_GUEST_EXPERIENCE,
    RECURRING_SERVICE_BREAKDOWN,
    get_interview_plan,
    interview_plan_from_job_metadata,
)
from hospitality_agent.state import InterviewState


class InterviewPlanTests(unittest.TestCase):
    def test_registry_contains_three_distinct_versioned_templates(self) -> None:
        self.assertEqual(
            set(INTERVIEW_PLANS),
            {
                "post_shift_guest_experience",
                "new_process_rollout",
                "recurring_service_breakdown",
            },
        )
        self.assertIs(
            INTERVIEW_PLANS[POST_SHIFT_GUEST_EXPERIENCE.id],
            POST_SHIFT_GUEST_EXPERIENCE,
        )
        self.assertIs(INTERVIEW_PLANS[NEW_PROCESS_ROLLOUT.id], NEW_PROCESS_ROLLOUT)
        self.assertIs(
            INTERVIEW_PLANS[RECURRING_SERVICE_BREAKDOWN.id],
            RECURRING_SERVICE_BREAKDOWN,
        )
        self.assertEqual({plan.version for plan in INTERVIEW_PLANS.values()}, {"1.0"})

    def test_each_template_has_safe_opening_and_valid_completion_contract(self) -> None:
        for plan in INTERVIEW_PLANS.values():
            with self.subTest(plan=plan.id):
                self.assertIn("AI interviewer", plan.opening_message)
                self.assertIn("not a performance evaluation", plan.opening_message)
                self.assertIn("skip any question", plan.opening_message)
                self.assertIn("guest names", plan.opening_message)
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
        self.assertIs(get_interview_plan("new_process_rollout"), NEW_PROCESS_ROLLOUT)
        selected = interview_plan_from_job_metadata(
            json.dumps({"interview_plan_id": "recurring_service_breakdown"})
        )
        self.assertIs(selected, RECURRING_SERVICE_BREAKDOWN)

    def test_unknown_or_invalid_plan_metadata_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown interview plan"):
            get_interview_plan("unknown")
        with self.assertRaisesRegex(ValueError, "must be a string"):
            interview_plan_from_job_metadata(json.dumps({"interview_plan_id": 7}))

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
