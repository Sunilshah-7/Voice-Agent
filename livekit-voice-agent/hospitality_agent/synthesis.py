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
_NUMBER_TOKENS = re.compile(
    r"\b(?:\d+(?:\.\d+)?|zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|dozen|hundred|thousand|once|twice)\b",
    re.IGNORECASE,
)
_OVERREACH_PHRASES = (
    "all properties",
    "across the company",
    "company-wide",
    "organization-wide",
    "this proves",
    "definitely caused",
    "always happens",
)


class LiveKitTextGenerator:
    """Small adapter that turns a LiveKit streaming LLM into one text response."""

    def __init__(self, model: llm.LLM) -> None:
        self.model = model

    async def __call__(self, prompt: str) -> str:
        chat_ctx = llm.ChatContext.empty()
        chat_ctx.add_message(
            role="system",
            content=(
                "You are a careful hospitality research analyst. Return only valid JSON "
                "matching the supplied schema. Never invent evidence, quotations, frequency, "
                "severity, causes, or actions."
            ),
        )
        chat_ctx.add_message(role="user", content=prompt)
        chunks: list[str] = []
        try:
            async with self.model.chat(chat_ctx=chat_ctx) as stream:
                async for chunk in stream:
                    if chunk.delta and chunk.delta.content:
                        chunks.append(chunk.delta.content)
        except Exception as exc:
            raise SynthesisGenerationError("The synthesis model request failed") from exc
        response = "".join(chunks).strip()
        if not response:
            raise SynthesisGenerationError("The synthesis model returned no content")
        return response


class SynthesisService:
    def __init__(self, generator: TextGenerator) -> None:
        self.generator = generator

    async def synthesize(
        self,
        *,
        turns: list[TranscriptTurn],
        state: InterviewState,
    ) -> InterviewSynthesis:
        respondent_turns = [
            turn for turn in turns if turn.role == "respondent" and not turn.interrupted
        ]
        if not respondent_turns:
            raise SynthesisValidationError("No finalized respondent turns are available")

        prompt = self.build_prompt(turns=turns, state=state)
        raw_response = await self.generator(prompt)
        try:
            payload = json.loads(_strip_json_fence(raw_response))
            synthesis = InterviewSynthesis.model_validate(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            raise SynthesisValidationError(
                "The synthesis response did not match the required schema"
            ) from exc
        validate_synthesis(synthesis, turns=turns)
        return synthesis

    def build_prompt(self, *, turns: list[TranscriptTurn], state: InterviewState) -> str:
        transcript_lines = [
            f"{turn.id} | {turn.role} | interrupted={str(turn.interrupted).lower()} | {turn.text}"
            for turn in turns
        ]
        evidence_lines: list[str] = []
        for objective in state.plan.objectives:
            for note in state.active_evidence(objective.id):
                evidence_lines.append(
                    f"{objective.id} | source={note.source_turn_id or 'none'} | {note.summary}"
                )

        schema = json.dumps(InterviewSynthesis.model_json_schema(), indent=2)
        return f"""
Create an evidence-grounded synthesis of this single hospitality interview.

Rules:
- Treat this as one respondent's perspective, never as a property-wide trend.
- Cite only finalized, non-interrupted respondent turn IDs.
- A representative quote must be an exact substring of its cited respondent turn.
- Put possible causes only in root_cause_hypotheses; do not present them as proven.
- Preserve frequency and severity exactly as reported. Do not add numbers.
- Recommended actions must be scoped as review, investigate, or pilot.
- Omit optional fields when the transcript does not support them.
- Describe missing evidence explicitly.
- Do not repeat names, room numbers, contact details, or other identifiers in the synthesis.

FINALIZED TRANSCRIPT
{chr(10).join(transcript_lines)}

ACTIVE INTERVIEW EVIDENCE
{chr(10).join(evidence_lines) or 'No active structured evidence was recorded.'}

REQUIRED JSON SCHEMA
{schema}
""".strip()


def validate_synthesis(
    synthesis: InterviewSynthesis,
    *,
    turns: list[TranscriptTurn],
) -> None:
    respondent_turns = {
        turn.id: turn
        for turn in turns
        if turn.role == "respondent" and not turn.interrupted
    }

    statements: list[EvidenceBackedStatement] = [synthesis.operational_issue]
    for optional_statement in (
        synthesis.guest_impact,
        synthesis.reported_frequency,
        synthesis.reported_severity,
        synthesis.workaround,
        synthesis.positive_practice,
        synthesis.recommended_action,
    ):
        if optional_statement is not None:
            statements.append(optional_statement)
    statements.extend(synthesis.root_cause_hypotheses)

    for statement in statements:
        _validate_evidence_ids(statement.evidence_turn_ids, respondent_turns)
        lowered = statement.text.casefold()
        if any(phrase in lowered for phrase in _OVERREACH_PHRASES):
            raise SynthesisValidationError(
                f"Unsupported organization-wide claim: {statement.text}"
            )

    if synthesis.reported_frequency is not None:
        source_text = " ".join(
            respondent_turns[turn_id].text
            for turn_id in synthesis.reported_frequency.evidence_turn_ids
        )
        claim_numbers = {
            token.casefold()
            for token in _NUMBER_TOKENS.findall(synthesis.reported_frequency.text)
        }
        source_numbers = {token.casefold() for token in _NUMBER_TOKENS.findall(source_text)}
        if not claim_numbers.issubset(source_numbers):
            raise SynthesisValidationError("Reported frequency contains an unsupported number")

    for quote in synthesis.representative_quotes:
        _validate_evidence_ids([quote.turn_id], respondent_turns)
        if quote.text not in respondent_turns[quote.turn_id].text:
            raise SynthesisValidationError(
                f"Representative quote is not verbatim in {quote.turn_id}"
            )


def _validate_evidence_ids(
    turn_ids: list[str], respondent_turns: dict[str, TranscriptTurn]
) -> None:
    invalid = [turn_id for turn_id in turn_ids if turn_id not in respondent_turns]
    if invalid:
        raise SynthesisValidationError(
            "Unsupported evidence turn IDs: " + ", ".join(invalid)
        )


def _strip_json_fence(response: str) -> str:
    stripped = response.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped
