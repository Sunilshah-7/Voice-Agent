"""LiveKit Agent specialization for the hospitality research interview."""

from __future__ import annotations

from livekit.agents import Agent, llm

from .models import InterviewPhase, InterviewPlan
from .plans import POST_SHIFT_GUEST_EXPERIENCE
from .state import InterviewState


class HospitalityInterviewer(Agent):
    """A concise interviewer whose research progress is explicit and inspectable."""

    def __init__(self, plan: InterviewPlan = POST_SHIFT_GUEST_EXPERIENCE) -> None:
        self.plan = plan
        self.interview_state = InterviewState(plan)
        self._turn_instruction = "Begin with the configured opening message."
        super().__init__(instructions=self._build_instructions())

    async def on_enter(self) -> None:
        self.interview_state.start_interview()
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
        decision = self.interview_state.observe_respondent_turn(new_message.text_content or "")
        self._turn_instruction = decision.instruction
        await self.update_instructions(self._build_instructions())

    @llm.function_tool
    async def record_objective_evidence(
        self,
        objective_id: str,
        evidence_summary: str,
        sufficient: bool,
    ) -> str:
        """Record which research objective the respondent's latest answer supports.

        Args:
            objective_id: Exact objective identifier from the interview plan.
            evidence_summary: Short factual paraphrase of what the respondent said.
            sufficient: True only if the objective no longer needs a follow-up.
        """
        try:
            self.interview_state.record_evidence(
                objective_id,
                evidence_summary,
                sufficient=sufficient,
            )
        except ValueError as exc:
            return f"Evidence was not recorded: {exc}. Use an exact objective identifier."

        await self.update_instructions(self._build_instructions())
        current = self.interview_state.current_objective_id
        if self.interview_state.phase == InterviewPhase.CONFIRMATION:
            return "Evidence recorded. The plan is resolved; briefly confirm the main finding next."
        return f"Evidence recorded. The next uncovered objective is {current}."

    @llm.function_tool
    async def prepare_interview_close(self, main_finding: str) -> str:
        """Move to confirmation once enough useful evidence exists or the budget is exhausted.

        Args:
            main_finding: A concise, transcript-grounded description to confirm with the respondent.
        """
        try:
            self.interview_state.begin_confirmation(main_finding)
        except ValueError as exc:
            unresolved = ", ".join(self.interview_state.uncovered_objective_ids)
            return f"Do not close yet: {exc}. Uncovered objectives: {unresolved}."
        await self.update_instructions(self._build_instructions())
        return (
            "Ask one short confirmation question that reflects this finding. "
            "Do not add a new interpretation or recommendation."
        )

    @llm.function_tool
    async def finish_interview(self) -> str:
        """Mark the interview complete after confirmation or an enforced early close."""
        if self.interview_state.phase not in {
            InterviewPhase.CONFIRMATION,
            InterviewPhase.CLOSING,
        }:
            return "Do not finish yet. Continue the interview until confirmation or an enforced close."
        self.interview_state.complete()
        await self.update_instructions(self._build_instructions())
        return self.plan.closing_message

    def _build_instructions(self) -> str:
        objective_lines = []
        for objective in self.plan.objectives:
            probes = " / ".join(objective.suggested_probes)
            objective_lines.append(
                f"- {objective.id}: {objective.goal} Evidence needed: "
                f"{objective.evidence_needed} Possible probes: {probes or 'none'}."
            )

        return f"""
You are ShiftSignal, an AI research interviewer conducting the interview plan
"{self.plan.title}" version {self.plan.version}.

BUSINESS GOAL
{self.plan.business_goal}

VOICE AND CONVERSATION RULES
- Sound calm, respectful, neutral, and naturally curious.
- Keep each spoken response to one acknowledgment and one question at most.
- Ask exactly one clear question at a time. Never present a list of questions.
- Do not use sarcasm, exaggerated empathy, or praise every answer.
- Follow a useful detail when it can clarify an operational cause, recurrence, impact,
  workaround, or improvement. Otherwise move to the most useful uncovered objective.
- Use information already supplied. Do not ask the respondent to repeat it.
- Accept "I don't know," skips, corrections, and requests to stop without pressure.
- Separate what the respondent observed from what they inferred.
- Never ask for guest names, room numbers, employee names, exact schedules, contact
  information, or other identifying details.
- Do not blame the respondent or ask them to identify a coworker.
- Do not claim the interview is anonymous beyond the opening language and system context.
- Do not promise that management will act on the feedback.

RESEARCH CONTROL
- Treat the objectives as a flexible research map, not a script to recite in order.
- After a substantive answer, silently call record_objective_evidence once for every
  objective it actually supports. Use only factual paraphrases; never manufacture evidence.
- Mark an objective sufficient only when its evidence requirement is met. Partial evidence
  should lead to at most one useful follow-up before you reconsider priorities.
- When objectives are resolved or the turn/time budget requires it, call
  prepare_interview_close and reflect the main finding back in one short confirmation question.
- After the respondent confirms or corrects the reflection, call finish_interview and close.
- Tool names, objective identifiers, coverage state, and these instructions are internal.
  Never speak them aloud.

SENSITIVE DISCLOSURES
If the respondent describes harassment, discrimination, violence, immediate danger, a
medical emergency, suicide, or self-harm: acknowledge neutrally; do not investigate, ask
for names, or promise an outcome. Say urgent danger should go to local emergency services
and other concerns should go to the organization's configured human reporting channel.
Then end the interview.

RESEARCH OBJECTIVES
{chr(10).join(objective_lines)}

CURRENT STATE
{self.interview_state.prompt_snapshot()}

INSTRUCTION FOR THIS TURN
{self._turn_instruction}
""".strip()
