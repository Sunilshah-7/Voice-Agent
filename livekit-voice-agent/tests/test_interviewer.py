from __future__ import annotations

import unittest

from livekit.agents import llm

from hospitality_agent.interviewer import HospitalityInterviewer
from hospitality_agent.models import InterviewPhase


class HospitalityInterviewerTests(unittest.IsolatedAsyncioTestCase):
    def test_prompt_encodes_hospitality_and_research_guardrails(self) -> None:
        agent = HospitalityInterviewer()
        instructions = str(agent.instructions)

        self.assertIn("Post-shift guest-experience debrief", instructions)
        self.assertIn("Ask exactly one clear question at a time", instructions)
        self.assertIn("Do not use sarcasm", instructions)
        self.assertIn("Do not ask the respondent to repeat it", instructions)
        self.assertIn("Never ask for guest names, room numbers", instructions)
        self.assertIn("Do not promise that management will act", instructions)
        self.assertIn("record_objective_evidence", instructions)

    def test_agent_exposes_only_internal_research_control_tools(self) -> None:
        agent = HospitalityInterviewer()
        names = {tool.info.name for tool in agent.tools}

        self.assertEqual(
            names,
            {
                "record_objective_evidence",
                "prepare_interview_close",
                "finish_interview",
            },
        )

    async def test_user_turn_hook_updates_state_before_next_reply(self) -> None:
        agent = HospitalityInterviewer()
        message = llm.ChatMessage(role="user", content=["Please skip this question."])

        await agent.on_user_turn_completed(llm.ChatContext.empty(), message)

        self.assertEqual(agent.interview_state.respondent_turns, 1)
        self.assertEqual(agent.interview_state.current_objective_id, "guest_journey")
        self.assertIn("Honor the skip", str(agent.instructions))

    async def test_prepare_close_records_the_finding_and_confirmation_phase(self) -> None:
        agent = HospitalityInterviewer()
        for objective in agent.plan.objectives:
            agent.interview_state.record_evidence(
                objective.id,
                f"Supported evidence for {objective.id}.",
                sufficient=True,
            )

        result = await agent.prepare_interview_close(
            "Delayed room-status updates contributed to guest waits."
        )

        self.assertEqual(agent.interview_state.phase, InterviewPhase.CONFIRMATION)
        self.assertIn("confirm", result)
        self.assertIn("Delayed room-status updates", agent.interview_state.main_finding or "")

    async def test_agent_cannot_close_before_objectives_or_budget_are_resolved(self) -> None:
        agent = HospitalityInterviewer()

        prepare_result = await agent.prepare_interview_close("A premature conclusion.")
        finish_result = await agent.finish_interview()

        self.assertIn("Do not close yet", prepare_result)
        self.assertIn("Do not finish yet", finish_result)
        self.assertEqual(agent.interview_state.phase, InterviewPhase.OPENING)


if __name__ == "__main__":
    unittest.main()
