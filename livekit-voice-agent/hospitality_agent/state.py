"""Inspectable interview progression independent of the voice providers."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable

from .models import (
    CompletionReason,
    EvidenceNote,
    InterviewPhase,
    InterviewPlan,
    ObjectiveStatus,
    UrgencyClassification,
)


_SKIP_PATTERNS = (
    re.compile(r"\b(?:skip|pass)(?:\s+(?:it|that|this|question))?\b", re.IGNORECASE),
    re.compile(r"\b(?:i\s+)?(?:don't|do not)\s+(?:know|want to answer)\b", re.IGNORECASE),
)
_END_PATTERNS = (
    re.compile(r"\b(?:stop|end)\s+(?:the\s+)?(?:interview|conversation|call)\b", re.IGNORECASE),
    re.compile(r"\bi\s+(?:want|need|have)\s+to\s+(?:stop|go|leave)\b", re.IGNORECASE),
    re.compile(r"\bno\s+more\s+questions\b", re.IGNORECASE),
)
_CORRECTION_PATTERNS = (
    re.compile(r"\b(?:actually|correction|to clarify)\b", re.IGNORECASE),
    re.compile(r"\bthat's\s+not\s+(?:right|correct|what i meant)\b", re.IGNORECASE),
)
_URGENT_PATTERNS = (
    re.compile(
        r"\b(?:injur(?:y|ies|ed)|seriously hurt|bleeding|unconscious|not breathing|"
        r"medical emergency)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:assault|violence|violent|attack(?:ed|ing)?|fight(?:ing)?|shooting|stabbing)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:threat(?:en|ened|ening)?|weapon|gun|knife|bomb)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:there(?:'s| is)\s+(?:a\s+)?fire|on fire|smoke|flames|explosion)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:immediate danger|danger right now|help me now|trapped)\b", re.IGNORECASE),
    re.compile(r"\b(?:suicide|suicidal|self[- ]harm)\b", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class TurnDecision:
    kind: str
    instruction: str


@dataclass(slots=True)
class InterviewState:
    plan: InterviewPlan
    clock: Callable[[], float] = time.monotonic
    phase: InterviewPhase = InterviewPhase.OPENING
    completion_reason: CompletionReason | None = None
    respondent_turns: int = 0
    corrections: int = 0
    sensitive_disclosure: bool = False
    urgency: UrgencyClassification = UrgencyClassification.ROUTINE
    urgency_rationale: str = "No potential emergency has been identified."
    human_review_required: bool = False
    escalation_status: str | None = None
    escalation_source_turn_id: str | None = None
    escalation_elapsed_seconds: float | None = None
    main_finding: str | None = None
    asked_objective_id: str | None = None
    coverage: dict[str, ObjectiveStatus] = field(init=False)
    evidence_notes: dict[str, list[EvidenceNote]] = field(init=False)
    started_at: float | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.coverage = {
            objective.id: ObjectiveStatus.NOT_STARTED for objective in self.plan.objectives
        }
        self.evidence_notes = {objective.id: [] for objective in self.plan.objectives}

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        return max(0.0, self.clock() - self.started_at)

    @property
    def current_objective_id(self) -> str | None:
        for objective in self.plan.objectives:
            if self.coverage[objective.id] in {
                ObjectiveStatus.NOT_STARTED,
                ObjectiveStatus.PARTIAL,
            }:
                return objective.id
        return None

    @property
    def uncovered_objective_ids(self) -> tuple[str, ...]:
        return tuple(
            objective.id
            for objective in self.plan.objectives
            if self.coverage[objective.id]
            in {ObjectiveStatus.NOT_STARTED, ObjectiveStatus.PARTIAL}
        )

    @property
    def should_confirm(self) -> bool:
        core_resolved = all(
            self.coverage[objective_id]
            in {ObjectiveStatus.SUFFICIENT, ObjectiveStatus.SKIPPED}
            for objective_id in self.plan.core_objective_ids
        )
        return core_resolved and not self.uncovered_objective_ids

    def start_interview(self) -> None:
        if self.phase == InterviewPhase.OPENING:
            self.started_at = self.clock()
            self.phase = InterviewPhase.INTERVIEWING

    def replace_plan(self, plan: InterviewPlan) -> None:
        """Switch intake objectives while preserving the active call's timing and budgets."""
        if self.phase in {
            InterviewPhase.CONFIRMATION,
            InterviewPhase.CLOSING,
            InterviewPhase.COMPLETED,
        }:
            raise ValueError("Cannot change the intake category while closing the call")
        self.plan = plan
        self.coverage = {
            objective.id: ObjectiveStatus.NOT_STARTED for objective in plan.objectives
        }
        self.evidence_notes = {objective.id: [] for objective in plan.objectives}
        self.asked_objective_id = None

    def mark_question_asked(self, objective_id: str) -> None:
        if self.human_review_required or self.phase in {
            InterviewPhase.CLOSING,
            InterviewPhase.COMPLETED,
        }:
            raise ValueError("Routine questioning is blocked after urgent escalation")
        self.plan.objective(objective_id)
        if self.coverage[objective_id] not in {
            ObjectiveStatus.NOT_STARTED,
            ObjectiveStatus.PARTIAL,
        }:
            raise ValueError(f"Objective is already resolved: {objective_id}")
        self.asked_objective_id = objective_id

    def observe_respondent_turn(
        self,
        text: str,
        *,
        source_turn_id: str | None = None,
    ) -> TurnDecision:
        """Apply deterministic safety and budget transitions before the LLM responds."""
        self.start_interview()
        self.respondent_turns += 1
        normalized = " ".join(text.split())

        if self._matches(_URGENT_PATTERNS, normalized):
            self.sensitive_disclosure = True
            self.update_urgency(
                UrgencyClassification.URGENT,
                "The caller described a potential emergency requiring immediate human review.",
                source_turn_id=source_turn_id,
            )
            return TurnDecision(
                kind="urgent_escalation",
                instruction=(
                    "Stop routine intake immediately. Say the call has been flagged Urgent — "
                    "Human Review Required and a simulated operator escalation has started. "
                    "Clearly direct immediate danger to 911 or the local emergency number. "
                    "Do not ask another routine question or imply that help was dispatched."
                ),
            )

        if self._matches(_END_PATTERNS, normalized):
            self.phase = InterviewPhase.CLOSING
            self.completion_reason = CompletionReason.RESPONDENT_ENDED
            return TurnDecision(
                kind="early_exit",
                instruction="Respect the request immediately. Do not ask another question; give the closing only.",
            )

        if self.respondent_turns >= self.plan.max_respondent_turns:
            self.phase = InterviewPhase.CONFIRMATION
            self.completion_reason = CompletionReason.TURN_LIMIT
            return TurnDecision(
                kind="turn_limit",
                instruction="The turn budget is exhausted. Briefly confirm the main finding, then close.",
            )

        if self.elapsed_seconds >= self.plan.target_duration_seconds:
            self.phase = InterviewPhase.CONFIRMATION
            self.completion_reason = CompletionReason.TIME_LIMIT
            return TurnDecision(
                kind="time_limit",
                instruction="The time budget is exhausted. Briefly confirm the main finding, then close.",
            )

        if self._matches(_CORRECTION_PATTERNS, normalized):
            self.corrections += 1
            return TurnDecision(
                kind="correction",
                instruction=(
                    "Accept the correction without defensiveness, use the corrected information, "
                    "call correct_objective_evidence for every affected objective, and ask at "
                    "most one necessary follow-up."
                ),
            )

        if self._matches(_SKIP_PATTERNS, normalized):
            skipped = self.asked_objective_id or self.current_objective_id
            if skipped is not None:
                self.coverage[skipped] = ObjectiveStatus.SKIPPED
            self.asked_objective_id = None
            if not self.uncovered_objective_ids:
                self.phase = InterviewPhase.CONFIRMATION
            return TurnDecision(
                kind="skip",
                instruction="Honor the skip without asking why. Move to the most useful uncovered objective.",
            )

        return TurnDecision(
            kind="continue",
            instruction="Continue with one useful probe or the most useful uncovered objective.",
        )

    def update_urgency(
        self,
        classification: UrgencyClassification,
        rationale: str,
        *,
        source_turn_id: str | None = None,
    ) -> bool:
        """Raise urgency and create an idempotent simulated escalation when required."""
        cleaned = " ".join(rationale.split())
        if not cleaned:
            raise ValueError("Urgency rationale cannot be empty")
        rank = {
            UrgencyClassification.ROUTINE: 0,
            UrgencyClassification.PRIORITY: 1,
            UrgencyClassification.URGENT: 2,
            UrgencyClassification.EMERGENCY: 3,
        }
        if rank[classification] < rank[self.urgency]:
            return False
        self.urgency = classification
        self.urgency_rationale = cleaned
        if classification in {
            UrgencyClassification.URGENT,
            UrgencyClassification.EMERGENCY,
        }:
            self.human_review_required = True
            if self.escalation_status is None:
                self.escalation_status = "simulated_operator_notified"
                self.escalation_source_turn_id = source_turn_id
                self.escalation_elapsed_seconds = self.elapsed_seconds
            self.phase = InterviewPhase.CLOSING
            self.completion_reason = CompletionReason.URGENT_ESCALATION
        return True

    def record_evidence(
        self,
        objective_id: str,
        summary: str,
        *,
        sufficient: bool,
        source_turn_id: str | None = None,
    ) -> EvidenceNote:
        if self.human_review_required:
            raise ValueError("Routine evidence capture is blocked after urgent escalation")
        self.plan.objective(objective_id)
        cleaned = " ".join(summary.split())
        if not cleaned:
            raise ValueError("Evidence summary cannot be empty")
        note = EvidenceNote(
            id=f"{objective_id}:{len(self.evidence_notes[objective_id]) + 1}",
            objective_id=objective_id,
            summary=cleaned,
            source_turn_id=source_turn_id,
        )
        self.evidence_notes[objective_id].append(note)
        self.coverage[objective_id] = (
            ObjectiveStatus.SUFFICIENT if sufficient else ObjectiveStatus.PARTIAL
        )
        if self.should_confirm:
            self.phase = InterviewPhase.CONFIRMATION
        return note

    def correct_evidence(
        self,
        objective_id: str,
        corrected_summary: str,
        *,
        sufficient: bool,
        source_turn_id: str | None = None,
    ) -> EvidenceNote:
        self.plan.objective(objective_id)
        active_notes = [note for note in self.evidence_notes[objective_id] if note.active]
        replacement = self.record_evidence(
            objective_id,
            corrected_summary,
            sufficient=sufficient,
            source_turn_id=source_turn_id,
        )
        for note in active_notes:
            note.active = False
            note.superseded_by = replacement.id
        return replacement

    def active_evidence(self, objective_id: str) -> tuple[EvidenceNote, ...]:
        self.plan.objective(objective_id)
        return tuple(note for note in self.evidence_notes[objective_id] if note.active)

    def begin_confirmation(self, main_finding: str) -> None:
        if self.phase != InterviewPhase.CONFIRMATION and not self.should_confirm:
            raise ValueError("Interview objectives are not resolved and the budget is not exhausted")
        cleaned = " ".join(main_finding.split())
        if not cleaned:
            raise ValueError("Main finding cannot be empty")
        self.main_finding = cleaned
        self.phase = InterviewPhase.CONFIRMATION

    def complete(self) -> None:
        if self.completion_reason is None:
            self.completion_reason = CompletionReason.OBJECTIVES_COVERED
        self.phase = InterviewPhase.COMPLETED

    def prompt_snapshot(self) -> str:
        coverage = ", ".join(
            f"{objective.id}={self.coverage[objective.id].value}"
            for objective in self.plan.objectives
        )
        return (
            f"phase={self.phase.value}; respondent_turns={self.respondent_turns}/"
            f"{self.plan.max_respondent_turns}; coverage=[{coverage}]; "
            f"current_objective={self.current_objective_id or 'none'}; "
            f"asked_objective={self.asked_objective_id or 'none'}; "
            f"urgency={self.urgency.value}; "
            f"human_review_required={str(self.human_review_required).lower()}; "
            f"escalation_status={self.escalation_status or 'none'}"
        )

    @staticmethod
    def _matches(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
        return any(pattern.search(text) for pattern in patterns)
