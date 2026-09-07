"""Typed domain models for a structured hospitality interview."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InterviewPhase(StrEnum):
    OPENING = "opening"
    INTERVIEWING = "interviewing"
    CONFIRMATION = "confirmation"
    CLOSING = "closing"
    COMPLETED = "completed"


class ObjectiveStatus(StrEnum):
    NOT_STARTED = "not_started"
    PARTIAL = "partial"
    SUFFICIENT = "sufficient"
    SKIPPED = "skipped"


class CompletionReason(StrEnum):
    OBJECTIVES_COVERED = "objectives_covered"
    TURN_LIMIT = "turn_limit"
    TIME_LIMIT = "time_limit"
    RESPONDENT_ENDED = "respondent_ended"
    SENSITIVE_DISCLOSURE = "sensitive_disclosure"


@dataclass(frozen=True, slots=True)
class ResearchObjective:
    id: str
    goal: str
    evidence_needed: str
    suggested_probes: tuple[str, ...] = ()


@dataclass(slots=True)
class EvidenceNote:
    id: str
    objective_id: str
    summary: str
    active: bool = True
    superseded_by: str | None = None


@dataclass(frozen=True, slots=True)
class InterviewPlan:
    id: str
    version: str
    title: str
    business_goal: str
    respondent_type: str
    target_duration_seconds: int
    max_respondent_turns: int
    opening_message: str
    closing_message: str
    objectives: tuple[ResearchObjective, ...]

    def objective(self, objective_id: str) -> ResearchObjective:
        for objective in self.objectives:
            if objective.id == objective_id:
                return objective
        raise ValueError(f"Unknown research objective: {objective_id}")

    @property
    def objective_ids(self) -> tuple[str, ...]:
        return tuple(objective.id for objective in self.objectives)
