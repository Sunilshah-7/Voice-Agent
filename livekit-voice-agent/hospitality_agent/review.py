"""Read-only access to local ShiftSignal session artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReviewArtifactError(RuntimeError):
    """Raised when an artifact cannot be safely loaded for review."""


class ReviewStore:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for path in self._artifact_paths():
            try:
                artifact = self._read_artifact(path)
            except ReviewArtifactError as exc:
                sessions.append(
                    {
                        "artifact_id": path.name,
                        "review_status": "unreadable",
                        "error": str(exc),
                    }
                )
                continue
            session = artifact["session"]
            plan = artifact["interview_plan"]
            context = artifact.get("respondent_context", {})
            synthesis = artifact.get("synthesis", {"status": "not_run"})
            sessions.append(
                {
                    "artifact_id": path.name,
                    "review_status": "ready",
                    "session_id": session.get("id"),
                    "status": session.get("status"),
                    "completion_reason": session.get("completion_reason"),
                    "started_at": session.get("started_at"),
                    "artifact_created_at": session.get("artifact_created_at"),
                    "transcript_turns": session.get("transcript_turns", 0),
                    "plan": plan,
                    "respondent_context": context,
                    "synthesis_status": synthesis.get("status", "not_run"),
                }
            )
        sessions.sort(
            key=lambda item: item.get("artifact_created_at") or 0,
            reverse=True,
        )
        return sessions

    def load_session(self, artifact_id: str) -> dict[str, Any]:
        if not artifact_id or Path(artifact_id).name != artifact_id:
            raise ReviewArtifactError("Invalid artifact identifier")
        known_paths = {path.name: path for path in self._artifact_paths()}
        path = known_paths.get(artifact_id)
        if path is None:
            raise ReviewArtifactError("Session artifact not found")
        return self._read_artifact(path)

    def artifact_paths(self) -> tuple[Path, ...]:
        return tuple(self._artifact_paths())

    def _artifact_paths(self) -> list[Path]:
        if not self.output_dir.is_dir():
            return []
        output_root = self.output_dir.resolve()
        return [
            path
            for path in self.output_dir.glob("session-*.json")
            if path.is_file()
            and not path.is_symlink()
            and path.resolve().parent == output_root
        ]

    @staticmethod
    def _read_artifact(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReviewArtifactError(f"Could not read {path.name}") from exc
        if not isinstance(payload, dict):
            raise ReviewArtifactError(f"Artifact {path.name} is not a JSON object")
        required = {
            "schema_version",
            "session",
            "interview_plan",
            "transcript",
            "objective_coverage",
            "synthesis",
        }
        missing = required - set(payload)
        if missing:
            raise ReviewArtifactError(
                f"Artifact {path.name} is missing: {', '.join(sorted(missing))}"
            )
        if not isinstance(payload["session"], dict) or not isinstance(
            payload["interview_plan"], dict
        ):
            raise ReviewArtifactError(f"Artifact {path.name} has invalid session metadata")
        if not isinstance(payload["transcript"], list) or not isinstance(
            payload["objective_coverage"], list
        ):
            raise ReviewArtifactError(f"Artifact {path.name} has invalid review data")
        return payload
