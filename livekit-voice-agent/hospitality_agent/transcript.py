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

    def set_close(self, reason: object, *, created_at: float | None = None) -> None:
        self.close_reason = getattr(reason, "value", str(reason))
        self.ended_at = float(created_at if created_at is not None else self.clock())

    def build_artifact(
        self,
        state: InterviewState,
        *,
        usage: Mapping[str, int | float] | None = None,
        synthesis: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        status = (
            ArtifactStatus.COMPLETED
            if state.phase.value == ArtifactStatus.COMPLETED.value
            else ArtifactStatus.INCOMPLETE
        )
        context = {
            key: value
            for key, value in asdict(self.respondent_context).items()
            if value is not None
        }
        coverage = []
        for objective in self.plan.objectives:
            coverage.append(
                {
                    "objective_id": objective.id,
                    "status": state.coverage[objective.id].value,
                    "evidence": [asdict(note) for note in state.evidence_notes[objective.id]],
                }
            )

        return {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "session": {
                "id": self.session_id,
                "status": status.value,
                "interview_phase": state.phase.value,
                "started_at": self.started_at,
                "ended_at": self.ended_at,
                "artifact_created_at": float(self.clock()),
                "completion_reason": (
                    state.completion_reason.value if state.completion_reason else None
                ),
                "close_reason": self.close_reason,
                "respondent_turns": state.respondent_turns,
                "transcript_turns": len(self.turns),
            },
            "interview_plan": {
                "id": self.plan.id,
                "version": self.plan.version,
                "title": self.plan.title,
            },
            "respondent_context": context,
            "transcript": [asdict(turn) for turn in self.turns],
            "objective_coverage": coverage,
            "synthesis": dict(synthesis or {"status": "not_run"}),
            "usage": dict(usage or {}),
        }

    def finalize(
        self,
        state: InterviewState,
        *,
        usage: Mapping[str, int | float] | None = None,
        synthesis: Mapping[str, object] | None = None,
    ) -> Path:
        if self._finalized_path is not None:
            return self._finalized_path

        artifact = self.build_artifact(state, usage=usage, synthesis=synthesis)
        final_path = self.output_dir / self._artifact_filename()
        temp_path: Path | None = None
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.output_dir,
                prefix=".shift-signal-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(artifact, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, final_path)
        except OSError as exc:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise ArtifactWriteError(
                f"Could not write session artifact to {final_path}: {exc}"
            ) from exc

        self._finalized_path = final_path
        return final_path

    def _artifact_filename(self) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", self.session_id).strip("-.")
        safe = safe[:48] or "session"
        digest = hashlib.sha256(self.session_id.encode("utf-8")).hexdigest()[:8]
        return f"session-{safe}-{digest}.json"
