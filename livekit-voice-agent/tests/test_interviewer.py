from __future__ import annotations

import unittest
import tempfile

from livekit.agents import llm

from hospitality_agent.completion import SubmissionResult
from hospitality_agent.interviewer import NonEmergencyIntakeAgent
from hospitality_agent.models import InterviewPhase
from hospitality_agent.plans import GENERAL_INQUIRY, PARKING_COMPLAINT
from hospitality_agent.transcript import TranscriptRecorder


class NonEmergencyIntakeAgentTests(unittest.IsolatedAsyncioTestCase):
    def test_prompt_encodes_intake_and_safety_guardrails(self) -> None:
        agent = NonEmergencyIntakeAgent()
        instructions = str(agent.instructions)

        self.assertIn("General non-emergency inquiry or request", instructions)
        self.assertIn("Ask exactly one clear question at a time", instructions)
        self.assertIn("Do not use sarcasm", instructions)
        self.assertIn("Do not ask the respondent to repeat it", instructions)
        self.assertIn("Do not claim to be a dispatcher", instructions)
        self.assertIn("contact 911 or their local emergency number", instructions)
        self.assertIn("Parking: distinguish illegal parking", instructions)
        self.assertIn("Lost pets: distinguish a missing pet", instructions)
        self.assertIn("Noise: distinguish a party", instructions)
        self.assertIn("Do not force it into one of the three primary categories", instructions)
        self.assertIn("silently call set_call_category", instructions)
        self.assertIn("whose objective is already sufficient", instructions)
        self.assertIn("record_turn_evidence", instructions)
        self.assertIn("correct_objective_evidence", instructions)
        self.assertIn("select_next_objective", instructions)
        self.assertIn("than 28 spoken words", instructions)

    def test_agent_exposes_only_internal_research_control_tools(self) -> None:
        agent = NonEmergencyIntakeAgent()
        names = {tool.info.name for tool in agent.tools}

        self.assertEqual(
            names,
            {
                "update_call_urgency",
                "set_call_category",
                "record_turn_evidence",
                "correct_objective_evidence",
                "select_next_objective",
                "prepare_interview_close",
                "finish_interview",
            },
        )

    async def test_contextual_urgent_disclosure_blocks_routine_tools(self) -> None:
        agent = NonEmergencyIntakeAgent()
        result = await agent.update_call_urgency(
            "urgent",
            "The caller described circumstances that may involve immediate danger.",
        )

        evidence_result = await agent.record_turn_evidence(
            ["request_type"],
            ["The caller initially described a general request."],
            [True],
        )
        question_result = await agent.select_next_objective("request_type")

        self.assertIn("Urgent — Human Review Required", result)
        self.assertTrue(agent.interview_state.human_review_required)
        self.assertIn("Do not record routine evidence", evidence_result)
        self.assertIn("Do not ask another question", question_result)

    async def test_urgent_finish_message_does_not_claim_dispatch(self) -> None:
        agent = NonEmergencyIntakeAgent()
        await agent.update_call_urgency("urgent", "A potential emergency was disclosed.")

        result = await agent.finish_interview()

        self.assertIn("simulated operator escalation", result)
        self.assertIn("has not dispatched emergency help", result)

    async def test_intent_classification_switches_plan_without_resetting_call_budget(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            recorder = TranscriptRecorder(plan=GENERAL_INQUIRY, output_dir=output_dir)
            agent = NonEmergencyIntakeAgent(recorder=recorder)
            await agent.on_user_turn_completed(
                llm.ChatContext.empty(),
                llm.ChatMessage(
                    role="user",
                    content=["A blue Honda is blocking my driveway at 14 Oak Street."],
                ),
            )

            result = await agent.set_call_category("parking_complaint")

            self.assertIs(agent.plan, PARKING_COMPLAINT)
            self.assertIs(agent.interview_state.plan, PARKING_COMPLAINT)
            self.assertIs(recorder.plan, PARKING_COMPLAINT)
            self.assertEqual(agent.interview_state.respondent_turns, 1)
            self.assertEqual(agent.interview_state.current_objective_id, "parking_issue")
            self.assertIn("changed from general_inquiry to parking_complaint", result)
            self.assertIn("category=parking_complaint", str(agent.instructions))

    async def test_first_answer_fills_multiple_fields_before_next_question(self) -> None:
        agent = NonEmergencyIntakeAgent()
        await agent.set_call_category("parking_complaint")

        result = await agent.record_turn_evidence(
            ["parking_issue", "location", "vehicle_description", "observed_impact"],
            [
                "The caller reported a blocked driveway.",
                "The vehicle is at 14 Oak Street.",
                "The vehicle is a blue Honda sedan.",
                "The vehicle prevents the caller from leaving the driveway.",
            ],
            [True, True, True, True],
        )

        self.assertIn("next uncovered objective is timing_and_duration", result)
        for objective_id in (
            "parking_issue",
            "location",
            "vehicle_description",
            "observed_impact",
        ):
            self.assertEqual(
                agent.interview_state.coverage[objective_id].value,
                "sufficient",
            )

        repeat = await agent.select_next_objective("location")
        self.assertIn("Objective is already resolved", repeat)

    async def test_user_turn_hook_updates_state_before_next_reply(self) -> None:
        agent = NonEmergencyIntakeAgent()
        message = llm.ChatMessage(role="user", content=["Please skip this question."])

        await agent.on_user_turn_completed(llm.ChatContext.empty(), message)

        self.assertEqual(agent.interview_state.respondent_turns, 1)
        self.assertEqual(agent.interview_state.current_objective_id, "request_details")
        self.assertIn("Honor the skip", str(agent.instructions))

    async def test_prepare_close_records_the_finding_and_confirmation_phase(self) -> None:
        agent = NonEmergencyIntakeAgent()
        for objective in agent.plan.objectives:
            agent.interview_state.record_evidence(
                objective.id,
                f"Supported evidence for {objective.id}.",
                sufficient=True,
            )

        result = await agent.prepare_interview_close(
            "The caller needs guidance about a routine service request."
        )

        self.assertEqual(agent.interview_state.phase, InterviewPhase.CONFIRMATION)
        self.assertIn("28 spoken words", result)
        self.assertIn("Did I get that right?", result)
        self.assertIn("routine service request", agent.interview_state.main_finding or "")

    async def test_routine_finish_returns_confirmation_only_after_submission_handler(self) -> None:
        calls: list[InterviewPhase] = []

        async def submit(state):
            calls.append(state.phase)
            return SubmissionResult(
                success=True,
                incident_id="INC-test",
                submission_status="Submitted for Review",
                notification_status="queued",
                confirmation=(
                    "Your report INC-test has been recorded and submitted for human review. "
                    "The simulated reviewer notification is queued. No dispatcher, police "
                    "department, or emergency service was contacted."
                ),
            )

        agent = NonEmergencyIntakeAgent(completion_handler=submit)
        for objective in agent.plan.objectives:
            agent.interview_state.record_evidence(
                objective.id,
                f"Supported evidence for {objective.id}.",
                sufficient=True,
            )
        await agent.prepare_interview_close("A routine report is ready for review.")

        result = await agent.finish_interview()

        self.assertEqual(calls, [InterviewPhase.COMPLETED])
        self.assertIn("report INC-test", result)
        self.assertIn("notification is queued", result)
        self.assertIn("No dispatcher, police department", result)

    async def test_batch_capture_records_every_objective_in_the_first_answer(self) -> None:
        agent = NonEmergencyIntakeAgent()
        await agent.set_call_category("general_inquiry")

        result = await agent.record_turn_evidence(
            ["request_type", "request_details"],
            [
                "The caller has a routine public-safety request.",
                "The caller needs information about a local service.",
            ],
            [True, True],
        )

        self.assertIn("next uncovered objective is location", result)
        self.assertEqual(agent.interview_state.current_objective_id, "location")

    async def test_screenshot_conversation_retains_only_corrected_cause(self) -> None:
        agent = NonEmergencyIntakeAgent()
        await agent.set_call_category("general_inquiry")
        await agent.record_turn_evidence(
            ["request_type", "request_details"],
            ["The caller reported a routine request.", "The request concerns a local service."],
            [True, True],
        )
        await agent.record_turn_evidence(
            ["location", "timing", "requested_outcome"],
            [
                "The issue was reported near the library.",
                "The caller first noticed it this morning.",
                "The caller wants the reviewing team to provide guidance.",
            ],
            [True, True, True],
        )

        await agent.correct_objective_evidence(
            "location",
            "The caller corrected the location to the community center.",
            True,
        )

        active = agent.interview_state.active_evidence("location")
        self.assertEqual(len(active), 1)
        self.assertIn("community center", active[0].summary)
        self.assertNotIn("library", active[0].summary)

    async def test_next_question_binding_makes_skip_target_explicit(self) -> None:
        agent = NonEmergencyIntakeAgent()
        await agent.set_call_category("general_inquiry")
        result = await agent.select_next_objective("timing")

        await agent.on_user_turn_completed(
            llm.ChatContext.empty(),
            llm.ChatMessage(role="user", content=["I don't know. Please skip that."]),
        )

        self.assertIn("Ask one concise question", result)
        self.assertEqual(agent.interview_state.coverage["timing"].value, "skipped")

    async def test_evidence_links_to_latest_finalized_respondent_turn(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            recorder = TranscriptRecorder(
                plan=GENERAL_INQUIRY,
                output_dir=output_dir,
            )
            agent = NonEmergencyIntakeAgent(recorder=recorder)
            await agent.set_call_category("general_inquiry")
            message = llm.ChatMessage(
                id="provider-user-1",
                role="user",
                content=["I need help with a routine city service."],
            )

            await agent.on_user_turn_completed(llm.ChatContext.empty(), message)
            await agent.record_turn_evidence(
                ["request_type", "request_details"],
                ["The caller has a general inquiry.", "The inquiry concerns a city service."],
                [True, True],
            )

            evidence = agent.interview_state.active_evidence("request_type")[0]
            self.assertEqual(evidence.source_turn_id, "turn-0001")

    async def test_agent_cannot_close_before_objectives_or_budget_are_resolved(self) -> None:
        agent = NonEmergencyIntakeAgent()

        prepare_result = await agent.prepare_interview_close("A premature conclusion.")
        finish_result = await agent.finish_interview()

        self.assertIn("Do not close yet", prepare_result)
        self.assertIn("Do not finish yet", finish_result)
        self.assertEqual(agent.interview_state.phase, InterviewPhase.OPENING)


if __name__ == "__main__":
    unittest.main()
