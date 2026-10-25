"""Evidence-grounded incident extraction and deterministic validation."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Awaitable, Callable, Literal

from livekit.agents import llm
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import TranscriptTurn, UrgencyClassification
from .state import InterviewState


class SynthesisError(RuntimeError):
    """Base class for extraction failures that must not destroy the transcript artifact."""


class SynthesisGenerationError(SynthesisError):
    pass


class SynthesisValidationError(SynthesisError):
    pass


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceBackedValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1)
    evidence_turn_ids: list[str] = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @field_validator("evidence_turn_ids")
    @classmethod
    def unique_evidence_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("evidence turn IDs must be unique")
        return values


class CallerInformation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: EvidenceBackedValue | None = None
    contact: EvidenceBackedValue | None = None


class UrgencyAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: UrgencyClassification
    rationale: str = Field(min_length=1)
    evidence_turn_ids: list[str] = Field(default_factory=list)

    @field_validator("rationale")
    @classmethod
    def normalize_rationale(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("evidence_turn_ids")
    @classmethod
    def unique_evidence_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("evidence turn IDs must be unique")
        return values


class IncidentRecord(BaseModel):
    """Versioned structured result produced from one finalized call transcript."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    incident_type: Literal[
        "parking_complaint",
        "lost_pet",
        "noise_complaint",
        "general_inquiry",
    ]
    subcategory: str = Field(min_length=1)
    classification_evidence_turn_ids: list[str] = Field(min_length=1)
    caller: CallerInformation = Field(default_factory=CallerInformation)
    location: EvidenceBackedValue | None = None
    description: EvidenceBackedValue
    occurred_at: EvidenceBackedValue | None = None
    relevant_details: list[EvidenceBackedValue] = Field(default_factory=list)
    urgency: UrgencyAssessment
    summary: EvidenceBackedValue
    confidence: Confidence
    evidence_gaps: list[str] = Field(default_factory=list)

    @field_validator("subcategory")
    @classmethod
    def normalize_subcategory(cls, value: str) -> str:
        normalized = "_".join(value.casefold().split())
        if not normalized:
            raise ValueError("subcategory cannot be blank")
        return normalized

    @field_validator("classification_evidence_turn_ids")
    @classmethod
    def unique_classification_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("classification evidence turn IDs must be unique")
        return values

    @field_validator("evidence_gaps")
    @classmethod
    def normalize_gaps(cls, values: list[str]) -> list[str]:
        normalized = [" ".join(value.split()) for value in values if value.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("evidence gaps must be unique")
        return normalized


TextGenerator = Callable[[str], Awaitable[str]]
_OVERREACH_PHRASES = (
    "this proves",
    "definitely happened",
    "definitely caused",
    "everyone knows",
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
                "You are a careful non-emergency public-safety intake analyst. Return "
                "only valid JSON matching the supplied schema. Never invent incident "
                "details, identity, contact information, time, location, urgency facts, "
                "or quotations."
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
            raise SynthesisGenerationError("The incident extraction request failed") from exc
        response = "".join(chunks).strip()
        if not response:
            raise SynthesisGenerationError("The incident extraction model returned no content")
        return response


class SynthesisService:
    def __init__(self, generator: TextGenerator) -> None:
        self.generator = generator

    async def synthesize(
        self,
        *,
        turns: list[TranscriptTurn],
        state: InterviewState,
    ) -> IncidentRecord:
        respondent_turns = [
            turn for turn in turns if turn.role == "respondent" and not turn.interrupted
        ]
        if not respondent_turns:
            raise SynthesisValidationError("No finalized respondent turns are available")

        prompt = self.build_prompt(turns=turns, state=state)
        raw_response = await self.generator(prompt)
        try:
            payload = json.loads(_strip_json_fence(raw_response))
            incident = IncidentRecord.model_validate(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            raise SynthesisValidationError(
                "The incident extraction response did not match the required schema"
            ) from exc
        if incident.incident_type != state.plan.id:
            raise SynthesisValidationError(
                "Extracted incident type does not match the selected intake category"
            )
        if state.human_review_required and incident.urgency.classification not in {
            UrgencyClassification.URGENT,
            UrgencyClassification.EMERGENCY,
        }:
            raise SynthesisValidationError(
                "Incident urgency cannot downgrade an active human-review escalation"
            )
        validate_incident_record(incident, turns=turns)
        return incident

    def build_prompt(self, *, turns: list[TranscriptTurn], state: InterviewState) -> str:
        transcript_lines = [
            f"{turn.id} | {turn.created_at:.3f} | {turn.role} | "
            f"interrupted={str(turn.interrupted).lower()} | {turn.text}"
            for turn in turns
        ]
        evidence_lines: list[str] = []
        for objective in state.plan.objectives:
            for note in state.active_evidence(objective.id):
                evidence_lines.append(
                    f"{objective.id} | source={note.source_turn_id or 'none'} | {note.summary}"
                )

        schema = json.dumps(IncidentRecord.model_json_schema(), indent=2)
        return f"""
Create one evidence-grounded incident record from this non-emergency call.

Selected incident type: {state.plan.id}
Runtime urgency: {state.urgency.value}
Human review required: {str(state.human_review_required).lower()}

Rules:
- incident_type must exactly match the selected incident type above.
- Use a concise snake_case subcategory supported by the caller's words.
- Caller name and contact are optional. Include them only when the caller voluntarily
  provided them; preserve the value exactly and never infer missing identity information.
- Preserve locations and occurrence dates or times as caller-reported text. Do not treat a
  transcript capture timestamp as the incident occurrence time.
- The transcript timestamps are Unix timestamps for when each finalized turn was captured.
- Cite only finalized, non-interrupted respondent turn IDs.
- relevant_details should contain useful observable facts not already represented elsewhere.
- Classify urgency as routine, priority, urgent, or emergency. The rationale must distinguish
  caller-reported facts from model judgment. Emergency classification does not imply that
  help was dispatched.
- Never downgrade an urgent runtime escalation in the incident record.
- The summary must be concise, factual, suitable for human review, and evidence-linked.
- Do not make legal conclusions or present an allegation as independently verified.
- State missing required information in evidence_gaps rather than inventing it.

TIMESTAMPED FINALIZED TRANSCRIPT
{chr(10).join(transcript_lines)}

ACTIVE INTAKE EVIDENCE
{chr(10).join(evidence_lines) or 'No active structured evidence was recorded.'}

REQUIRED JSON SCHEMA
{schema}
""".strip()


def validate_incident_record(
    incident: IncidentRecord,
    *,
    turns: list[TranscriptTurn],
) -> None:
    respondent_turns = {
        turn.id: turn
        for turn in turns
        if turn.role == "respondent" and not turn.interrupted
    }
    _validate_evidence_ids(incident.classification_evidence_turn_ids, respondent_turns)

    values: list[EvidenceBackedValue] = [incident.description, incident.summary]
    values.extend(incident.relevant_details)
    if incident.location is not None:
        values.append(incident.location)
    if incident.occurred_at is not None:
        values.append(incident.occurred_at)
    if incident.caller.name is not None:
        values.append(incident.caller.name)
        _validate_verbatim_value(incident.caller.name, respondent_turns)
    if incident.caller.contact is not None:
        values.append(incident.caller.contact)
        _validate_verbatim_value(incident.caller.contact, respondent_turns)

    for value in values:
        _validate_evidence_ids(value.evidence_turn_ids, respondent_turns)
        lowered = value.value.casefold()
        if any(phrase in lowered for phrase in _OVERREACH_PHRASES):
            raise SynthesisValidationError(f"Unsupported overclaim: {value.value}")

    _validate_evidence_ids(incident.urgency.evidence_turn_ids, respondent_turns)


def _validate_verbatim_value(
    field: EvidenceBackedValue,
    respondent_turns: dict[str, TranscriptTurn],
) -> None:
    _validate_evidence_ids(field.evidence_turn_ids, respondent_turns)
    if not any(
        field.value.casefold() in respondent_turns[turn_id].text.casefold()
        for turn_id in field.evidence_turn_ids
    ):
        raise SynthesisValidationError(
            "Caller identity and contact values must appear verbatim in cited evidence"
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
