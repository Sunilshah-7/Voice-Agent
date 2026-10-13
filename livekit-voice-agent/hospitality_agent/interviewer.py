"""LiveKit Agent specialization for the hospitality research interview."""

from __future__ import annotations

from livekit.agents import Agent, llm

from .models import InterviewPhase, InterviewPlan
from .plans import POST_SHIFT_GUEST_EXPERIENCE
from .state import InterviewState
from .transcript import TranscriptRecorder


class HospitalityInterviewer(Agent):
    """A concise interviewer whose research progress is explicit and inspectable."""

    def __init__(
        self,
        plan: InterviewPlan = POST_SHIFT_GUEST_EXPERIENCE,
        recorder: TranscriptRecorder | None = None,
    ) -> None:
        self.plan = plan
        self.interview_state = InterviewState(plan)
        self.recorder = recorder
        self._turn_instruction = "Begin with the configured opening message."
        super().__init__(instructions=self._build_instructions())

    async def on_enter(self) -> None:
        self.interview_state.start_interview()
        self.interview_state.mark_question_asked(self.plan.initial_objective_id)
        await self.update_instructions(self._build_instructions())
        await self.session.say(
            self.plan.opening_message,
            allow_interruptions=True,
            add_to_chat_ctx=True,
        )

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        del turn_ctx
        if self.recorder is not None:
            self.recorder.record_chat_message(new_message)
        decision = self.interview_state.observe_respondent_turn(new_message.text_content or "")
        self._turn_instruction = decision.instruction
        await self.update_instructions(self._build_instructions())
