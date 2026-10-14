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

    @llm.function_tool
    async def record_turn_evidence(
        self,
        objective_ids: list[str],
        evidence_summaries: list[str],
        sufficient_flags: list[bool],
    ) -> str:
        """Record every research objective supported by the respondent's latest answer.

        Args:
            objective_ids: All exact objective identifiers supported by the latest answer.
            evidence_summaries: One short factual paraphrase for each objective, in the same order.
            sufficient_flags: One flag per objective; true only when no follow-up is needed.
        """
        if not objective_ids:
            return "No evidence recorded: include every objective supported by the latest answer."
        if not (
            len(objective_ids) == len(evidence_summaries) == len(sufficient_flags)
        ):
            return "No evidence recorded: objective, summary, and sufficiency lists must align."
        if len(set(objective_ids)) != len(objective_ids):
            return "No evidence recorded: each objective may appear only once per respondent turn."
        if any(not summary.strip() for summary in evidence_summaries):
            return "No evidence recorded: every objective requires a factual summary."

        try:
            for objective_id in objective_ids:
                self.plan.objective(objective_id)
            for objective_id, summary, sufficient in zip(
                objective_ids,
                evidence_summaries,
                sufficient_flags,
                strict=True,
            ):
                self.interview_state.record_evidence(
                    objective_id,
                    summary,
                    sufficient=sufficient,
                    source_turn_id=(
                        self.recorder.latest_respondent_turn_id if self.recorder else None
                    ),
                )
        except ValueError as exc:
            return f"Evidence was not recorded: {exc}."

        self.interview_state.asked_objective_id = None
        await self.update_instructions(self._build_instructions())
        current = self.interview_state.current_objective_id
        if self.interview_state.phase == InterviewPhase.CONFIRMATION:
            return "All supported evidence recorded. The plan is resolved; confirm the main finding next."
        return f"All supported evidence recorded. The next uncovered objective is {current}."

    @llm.function_tool
    async def correct_objective_evidence(
        self,
        objective_id: str,
        corrected_summary: str,
        sufficient: bool,
    ) -> str:
        """Replace stale evidence when the respondent corrects an earlier statement.

        Args:
            objective_id: Exact identifier for an objective affected by the correction.
            corrected_summary: Factual replacement based only on the correction.
            sufficient: True only when the corrected evidence needs no follow-up.
        """
        try:
            replacement = self.interview_state.correct_evidence(
                objective_id,
                corrected_summary,
                sufficient=sufficient,
                source_turn_id=(
                    self.recorder.latest_respondent_turn_id if self.recorder else None
                ),
            )
        except ValueError as exc:
            return f"Correction was not recorded: {exc}."
        await self.update_instructions(self._build_instructions())
        return f"Correction recorded as {replacement.id}; earlier evidence is superseded."

    @llm.function_tool
    async def select_next_objective(self, objective_id: str) -> str:
        """Bind the next spoken research question to one unresolved objective.

        Args:
            objective_id: Exact unresolved objective identifier the next question will address.
        """
        try:
            self.interview_state.mark_question_asked(objective_id)
        except ValueError as exc:
            return f"Do not ask that question: {exc}. Choose an unresolved objective."
        await self.update_instructions(self._build_instructions())
        return f"Ask one concise question for {objective_id}, using facts already provided."
