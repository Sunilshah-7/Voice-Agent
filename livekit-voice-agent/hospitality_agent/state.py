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
