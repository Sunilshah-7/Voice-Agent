from __future__ import annotations

import unittest
import tempfile

from livekit.agents import llm

from hospitality_agent.interviewer import HospitalityInterviewer
from hospitality_agent.models import InterviewPhase
from hospitality_agent.plans import POST_SHIFT_GUEST_EXPERIENCE
from hospitality_agent.transcript import TranscriptRecorder


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
        self.assertIn("record_turn_evidence", instructions)
        self.assertIn("correct_objective_evidence", instructions)
        self.assertIn("select_next_objective", instructions)
        self.assertIn("than 28 spoken words", instructions)

    def test_agent_exposes_only_internal_research_control_tools(self) -> None:
        agent = HospitalityInterviewer()
        names = {tool.info.name for tool in agent.tools}

        self.assertEqual(
            names,
            {
                "record_turn_evidence",
                "correct_objective_evidence",
                "select_next_objective",
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
