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


class ArtifactStatus(StrEnum):
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"


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
    source_turn_id: str | None = None
    active: bool = True
    superseded_by: str | None = None


@dataclass(frozen=True, slots=True)
class RespondentContext:
    property_id: str | None = None
    department: str | None = None
    role_category: str | None = None
    shift_type: str | None = None
    tenure_band: str | None = None
    language: str | None = None
    anonymous_participation: bool | None = None

    @classmethod
    def from_mapping(cls, values: dict[str, object] | None) -> "RespondentContext":
        if not values:
            return cls()
        allowed = set(cls.__dataclass_fields__)
        unexpected = set(values) - allowed
        if unexpected:
            raise ValueError(
                "Unsupported respondent metadata: " + ", ".join(sorted(unexpected))
            )
        normalized: dict[str, object] = {}
        for key, value in values.items():
            if isinstance(value, str):
                value = " ".join(value.split()) or None
            normalized[key] = value
        return cls(**normalized)


@dataclass(frozen=True, slots=True)
class TranscriptTurn:
    id: str
    role: str
    text: str
    created_at: float
    interrupted: bool = False
    transcript_confidence: float | None = None


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
