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
