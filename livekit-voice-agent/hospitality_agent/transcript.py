"""Finalized transcript capture and durable local session artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Mapping

from livekit.agents import llm

from .models import ArtifactStatus, InterviewPlan, RespondentContext, TranscriptTurn
from .state import InterviewState


ARTIFACT_SCHEMA_VERSION = "1.1"
_ALLOWED_ROLES = {"user": "respondent", "assistant": "interviewer"}


class ArtifactWriteError(RuntimeError):
    """Raised when a session artifact cannot be durably written."""


def respondent_context_from_job_metadata(raw_metadata: str | None) -> RespondentContext:
    """Load only explicitly allowed respondent context from LiveKit job metadata."""
    if not raw_metadata:
        return RespondentContext()
    try:
        payload = json.loads(raw_metadata)
    except json.JSONDecodeError as exc:
        raise ValueError("LiveKit job metadata must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("LiveKit job metadata must be a JSON object")
    context = payload.get("respondent_context")
    if context is None:
        return RespondentContext()
    if not isinstance(context, dict):
        raise ValueError("respondent_context must be a JSON object")
    return RespondentContext.from_mapping(context)


class TranscriptRecorder:
    def __init__(
        self,
        *,
        plan: InterviewPlan,
        session_id: str | None = None,
        output_dir: str | Path | None = None,
        respondent_context: RespondentContext | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.plan = plan
        self.session_id = session_id or str(uuid.uuid4())
        self.output_dir = Path(
            output_dir or os.getenv("SHIFT_SIGNAL_OUTPUT_DIR", "outputs")
        )
        self.respondent_context = respondent_context or RespondentContext()
        self.clock = clock
        self.started_at = float(clock())
        self.turns: list[TranscriptTurn] = []
        self.close_reason: str | None = None
        self.ended_at: float | None = None
        self._provider_turns: dict[str, TranscriptTurn] = {}
        self._finalized_path: Path | None = None

    @property
    def latest_respondent_turn_id(self) -> str | None:
        for turn in reversed(self.turns):
            if turn.role == "respondent":
                return turn.id
        return None

    def record_chat_message(self, message: llm.ChatMessage) -> TranscriptTurn | None:
        role = _ALLOWED_ROLES.get(message.role)
        text = " ".join((message.text_content or "").split())
        if role is None or not text:
            return None

        provider_item_id = message.id
        if provider_item_id and provider_item_id in self._provider_turns:
            return self._provider_turns[provider_item_id]

        turn = TranscriptTurn(
            id=f"turn-{len(self.turns) + 1:04d}",
            role=role,
            text=text,
            created_at=float(message.created_at),
            interrupted=bool(message.interrupted),
            transcript_confidence=message.transcript_confidence,
        )
        self.turns.append(turn)
        if provider_item_id:
            self._provider_turns[provider_item_id] = turn
        return turn
