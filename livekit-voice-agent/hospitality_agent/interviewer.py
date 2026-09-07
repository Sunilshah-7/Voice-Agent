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
        self.interview_state.mark_question_asked("primary_event")
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
            "In no more than 28 spoken words, state only the main issue and proposed "
            "improvement, then ask: Did I get that right? Do not list every detail."
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
- Keep ordinary turns under 25 spoken words when possible.
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
- Before choosing the next question, scan the respondent's complete latest answer against
  every objective. A phrase such as "at check-in" already supports guest_journey, and a
  phrase such as "we called the supervisor" already supports workaround.
- After a substantive answer, silently call record_turn_evidence exactly once with every
  objective the answer actually supports, not merely the objective you asked about. Use
  only factual paraphrases; never manufacture evidence.
- If the respondent corrects earlier information, call correct_objective_evidence for each
  affected objective. Corrected evidence replaces earlier evidence; never retain both as
  simultaneously true.
- Mark an objective sufficient only when its evidence requirement is met. Partial evidence
  should lead to at most one useful follow-up before you reconsider priorities.
- Before speaking any research question, call select_next_objective with the exact objective
  that question addresses. This binding ensures a later skip applies to the asked question.
- When objectives are resolved or the turn/time budget requires it, call
  prepare_interview_close and reflect only the main issue and proposed improvement in no more
  than 28 spoken words, ending with "Did I get that right?"
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
