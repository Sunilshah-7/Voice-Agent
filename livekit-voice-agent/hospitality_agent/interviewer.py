"""LiveKit Agent specialization for non-emergency call intake."""

from __future__ import annotations

from typing import Awaitable, Callable, Literal

from livekit.agents import Agent, llm

from .completion import SubmissionResult
from .models import InterviewPhase, InterviewPlan, UrgencyClassification
from .plans import GENERAL_INQUIRY, get_interview_plan
from .state import InterviewState
from .transcript import TranscriptRecorder


class NonEmergencyIntakeAgent(Agent):
    """A concise intake agent whose evidence collection is explicit and inspectable."""

    def __init__(
        self,
        plan: InterviewPlan = GENERAL_INQUIRY,
        recorder: TranscriptRecorder | None = None,
        completion_handler: Callable[[InterviewState], Awaitable[SubmissionResult]] | None = None,
    ) -> None:
        self.plan = plan
        self.interview_state = InterviewState(plan)
        self.recorder = recorder
        self.completion_handler = completion_handler
        self._category_confirmed = plan.id != GENERAL_INQUIRY.id
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
        recorded_turn = (
            self.recorder.record_chat_message(new_message)
            if self.recorder is not None
            else None
        )
        decision = self.interview_state.observe_respondent_turn(
            new_message.text_content or "",
            source_turn_id=recorded_turn.id if recorded_turn else None,
        )
        self._turn_instruction = decision.instruction
        await self.update_instructions(self._build_instructions())

    @llm.function_tool
    async def update_call_urgency(
        self,
        classification: Literal["routine", "priority", "urgent", "emergency"],
        rationale: str,
    ) -> str:
        """Update urgency from the latest caller disclosure before routine intake continues.

        Args:
            classification: Current urgency supported by the conversation. Use urgent or
                emergency whenever an emergency is possible or uncertain.
            rationale: Concise factual reason, distinguishing caller facts from inference.
        """
        changed = self.interview_state.update_urgency(
            UrgencyClassification(classification),
            rationale,
            source_turn_id=(
                self.recorder.latest_respondent_turn_id if self.recorder else None
            ),
        )
        if not changed:
            return (
                f"Urgency remains {self.interview_state.urgency.value}; never downgrade an "
                "existing safety classification automatically."
            )
        if self.interview_state.human_review_required:
            self._turn_instruction = (
                "Stop routine intake. State: Urgent — Human Review Required. Say a "
                "simulated operator escalation has started, direct immediate danger to "
                "911 or the local emergency number, and do not imply help was dispatched."
            )
            await self.update_instructions(self._build_instructions())
            return self._turn_instruction
        await self.update_instructions(self._build_instructions())
        return (
            f"Urgency updated to {classification}. Continue naturally, reassessing safety "
            "before every routine follow-up."
        )

    @llm.function_tool
    async def set_call_category(
        self,
        category: Literal[
            "parking_complaint",
            "lost_pet",
            "noise_complaint",
            "general_inquiry",
        ],
    ) -> str:
        """Select the intake category from facts in the caller's own description.

        Args:
            category: Best supported category. Use general_inquiry when none of the three
                primary categories fits or the caller's intent remains unclear.
        """
        selected_plan = get_interview_plan(category)
        if selected_plan.id == self.plan.id:
            self._category_confirmed = True
            await self.update_instructions(self._build_instructions())
            return (
                f"Call category confirmed as {category}. Record every supported fact, "
                "then ask only for the highest-value missing detail."
            )

        previous_category = self.plan.id
        try:
            self.interview_state.replace_plan(selected_plan)
        except ValueError as exc:
            return f"Call category was not changed: {exc}."
        self.plan = selected_plan
        self._category_confirmed = True
        if self.recorder is not None:
            self.recorder.plan = selected_plan
        self._turn_instruction = (
            f"The call was categorized as {category}. Record all category-relevant facts "
            "already supplied before choosing one missing detail to ask about."
        )
        await self.update_instructions(self._build_instructions())
        return (
            f"Call category changed from {previous_category} to {category}. Record all "
            "supported facts from the caller's latest turn before asking a question."
        )

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
        if self.interview_state.human_review_required:
            return "Do not record routine evidence: urgent operator escalation is active."
        if not self._category_confirmed:
            return (
                "No evidence recorded: call set_call_category first using the caller's "
                "description, then record evidence against that category's objectives."
            )
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
        if self.interview_state.human_review_required:
            return "Do not ask another question: urgent operator escalation is active."
        if not self._category_confirmed:
            return (
                "Do not ask another question yet: call set_call_category from the caller's "
                "description first."
            )
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
        if self.interview_state.human_review_required:
            return (
                "Urgent — Human Review Required. A simulated operator escalation has been "
                "started. If anyone may be in immediate danger, contact 911 or your local "
                "emergency number now. This system has not dispatched emergency help."
            )
        if self.completion_handler is not None:
            result = await self.completion_handler(self.interview_state)
            return result.confirmation
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
You are ShiftSignal, an AI non-emergency call intake agent conducting the intake plan
"{self.plan.title}" version {self.plan.version}.

BUSINESS GOAL
{self.plan.business_goal}

VOICE AND CONVERSATION RULES
- Sound calm, respectful, neutral, and naturally curious.
- Keep each spoken response to one acknowledgment and one question at most.
- Keep ordinary turns under 25 spoken words when possible.
- Ask exactly one clear question at a time. Never present a list of questions.
- Do not use sarcasm, exaggerated empathy, or praise every answer.
- Follow a useful detail when it clarifies the reported situation, location, timing,
  observable impact, or requested help. Otherwise move to the most useful uncovered objective.
- Use information already supplied. Do not ask the respondent to repeat it.
- Accept "I don't know," skips, corrections, and requests to stop without pressure.
- Separate what the respondent observed from what they inferred.
- Do not ask for people's names, contact information, or other personal identifiers unless
  a configured intake step explicitly requires them. Never request unnecessary identifiers.
- The caller_contact objective is optional. Offer it only after the incident facts are
  captured, state that it is optional, accept a skip immediately, and do not ask for any
  identity or contact detail beyond the caller's chosen name and one contact method.
- Do not make legal conclusions, blame the caller, or pressure them to identify a person.
- Do not claim the interview is anonymous beyond the opening language and system context.
- Do not claim to be a dispatcher, imply that help has been sent, or promise enforcement,
  follow-up, or any particular outcome.

RESEARCH CONTROL
- Treat the objectives as a flexible research map, not a script to recite in order.
- Before category selection, evidence capture, or any follow-up after every caller turn,
  assess whether injuries, threats, violence, fire, weapons, medical crisis, or immediate
  danger may be present. Obvious phrases are handled deterministically; for contextual or
  uncertain risk, silently call update_call_urgency. Never use routine intake to resolve
  uncertainty about a possible emergency.
- If urgency is urgent or emergency, stop all routine tools and questions immediately.
  State "Urgent — Human Review Required," say a simulated operator escalation has started,
  direct immediate danger to 911 or the local emergency number, and make clear that this
  system has not dispatched help. Preserve the transcript and evidence already collected.
- Urgency may increase as new facts arrive. Never automatically downgrade an existing
  safety classification or dismiss an uncertain emergency.
- Infer intent from the caller's own words. After the caller first describes the request,
  silently call set_call_category before recording evidence or asking a follow-up. Do not
  ask the caller to choose from a menu when their description already makes the category
  clear. Use general_inquiry when no primary category fits or the intent remains unclear.
- A single answer may contain the category, location, timing, description, and impact.
  Record every supported detail before choosing the next question. Never ask for a field
  whose objective is already sufficient, even if it would normally come next in a form.
- When the general plan is active, adapt the factual follow-up to the caller's category:
  - Parking: distinguish illegal parking, a blocked driveway, an abandoned vehicle, or
    another concern; collect location, vehicle description, timing, and observed impact.
  - Lost pets: distinguish a missing pet from a found animal; collect the animal's
    description, last known location, timing, direction of travel, and current situation.
  - Noise: distinguish a party, construction, a neighborhood disturbance, or another
    source; collect location, timing, duration, recurrence, and observed impact.
  - General inquiry: collect only the facts, location, timing, and requested help relevant
    to the routine request. Do not force it into one of the three primary categories.
- Before choosing the next question, scan the respondent's complete latest answer against
  every objective. Capture a detail against every objective it supports, even when the
  detail answers something other than the question that was asked.
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
If the caller describes immediate danger, an active crime, fire, a medical emergency,
suicide, self-harm, a weapon, or another situation needing an urgent response: acknowledge
neutrally; do not investigate, ask for names, or promise an outcome. Clearly say this agent
cannot dispatch help and the caller should contact 911 or their local emergency number now.
Then end the intake.

RESEARCH OBJECTIVES
{chr(10).join(objective_lines)}

CURRENT STATE
category={self.plan.id}; category_confirmed={str(self._category_confirmed).lower()}
{self.interview_state.prompt_snapshot()}

INSTRUCTION FOR THIS TURN
{self._turn_instruction}
""".strip()
