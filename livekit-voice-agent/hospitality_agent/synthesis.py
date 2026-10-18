"""Evidence-grounded post-interview synthesis and deterministic validation."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Awaitable, Callable, Literal

from livekit.agents import llm
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import TranscriptTurn
from .state import InterviewState


class SynthesisError(RuntimeError):
    """Base class for synthesis failures that must not destroy the transcript artifact."""


class SynthesisGenerationError(SynthesisError):
    pass


class SynthesisValidationError(SynthesisError):
    pass


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceBackedStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    evidence_turn_ids: list[str] = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("statement cannot be blank")
        return normalized

    @field_validator("evidence_turn_ids")
    @classmethod
    def unique_evidence_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("evidence turn IDs must be unique")
        return values


class RecommendedAction(EvidenceBackedStatement):
    scope: Literal["review", "investigate", "pilot"]


class RepresentativeQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    turn_id: str

    @field_validator("text")
    @classmethod
    def normalize_quote(cls, value: str) -> str:
        return " ".join(value.split())


class InterviewSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operational_issue: EvidenceBackedStatement
    guest_impact: EvidenceBackedStatement | None = None
    root_cause_hypotheses: list[EvidenceBackedStatement] = Field(default_factory=list)
    reported_frequency: EvidenceBackedStatement | None = None
    reported_severity: EvidenceBackedStatement | None = None
    workaround: EvidenceBackedStatement | None = None
    positive_practice: EvidenceBackedStatement | None = None
    recommended_action: RecommendedAction | None = None
    representative_quotes: list[RepresentativeQuote] = Field(default_factory=list)
    confidence: Confidence
    evidence_gaps: list[str] = Field(default_factory=list)

    @field_validator("evidence_gaps")
    @classmethod
    def normalize_gaps(cls, values: list[str]) -> list[str]:
        normalized = [" ".join(value.split()) for value in values if value.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("evidence gaps must be unique")
        return normalized


TextGenerator = Callable[[str], Awaitable[str]]
