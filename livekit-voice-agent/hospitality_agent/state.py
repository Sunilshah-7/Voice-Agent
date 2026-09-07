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
_SENSITIVE_PATTERNS = (
    re.compile(r"\b(?:sexual\s+harassment|harassed|discrimination|discriminated)\b", re.IGNORECASE),
    re.compile(r"\b(?:assault|violence|threatened|immediate danger)\b", re.IGNORECASE),
    re.compile(r"\b(?:i|we)\s+(?:feel|are)\s+unsafe\b", re.IGNORECASE),
    re.compile(r"\b(?:medical emergency|suicide|self[- ]harm)\b", re.IGNORECASE),
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

    def mark_question_asked(self, objective_id: str) -> None:
        self.plan.objective(objective_id)
        if self.coverage[objective_id] not in {
            ObjectiveStatus.NOT_STARTED,
            ObjectiveStatus.PARTIAL,
        }:
            raise ValueError(f"Objective is already resolved: {objective_id}")
        self.asked_objective_id = objective_id

    def observe_respondent_turn(self, text: str) -> TurnDecision:
        """Apply deterministic safety and budget transitions before the LLM responds."""
        self.start_interview()
        self.respondent_turns += 1
        normalized = " ".join(text.split())

        if self._matches(_SENSITIVE_PATTERNS, normalized):
            self.sensitive_disclosure = True
            self.phase = InterviewPhase.CLOSING
            self.completion_reason = CompletionReason.SENSITIVE_DISCLOSURE
            return TurnDecision(
                kind="sensitive_disclosure",
                instruction=(
                    "Acknowledge the concern neutrally. Do not investigate, ask for names, "
                    "or promise an outcome. Say that urgent danger should go to local emergency "
                    "services and other concerns should go to the organization's configured "
                    "human reporting channel. Then end the interview."
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

    def record_evidence(
        self,
        objective_id: str,
        summary: str,
        *,
        sufficient: bool,
        source_turn_id: str | None = None,
    ) -> EvidenceNote:
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
            f"asked_objective={self.asked_objective_id or 'none'}"
        )

    @staticmethod
    def _matches(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
        return any(pattern.search(text) for pattern in patterns)
