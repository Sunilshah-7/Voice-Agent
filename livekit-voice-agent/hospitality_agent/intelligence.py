"""Durable, thresholded cross-interview intelligence for ShiftSignal."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable


MIN_AGGREGATE_SAMPLE_SIZE = 3
ALLOWED_GROUP_DIMENSIONS = {
    "property_id",
    "department",
    "role_category",
    "shift_type",
}


class IntelligenceStoreError(RuntimeError):
    """Raised when durable indexing or aggregation cannot be completed."""


def normalize_signal(text: str) -> str:
    """Create a conservative key; only near-identical findings are grouped."""
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


class IntelligenceStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._lock = threading.RLock()
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(
                self.database_path,
                timeout=10,
                check_same_thread=False,
            )
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA busy_timeout = 10000")
            self._create_schema()
        except (OSError, sqlite3.Error) as exc:
            raise IntelligenceStoreError(
                f"Could not open intelligence database: {self.database_path}"
            ) from exc

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL UNIQUE,
                artifact_schema_version TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                plan_version TEXT NOT NULL,
                session_status TEXT NOT NULL,
                started_at REAL,
                artifact_created_at REAL NOT NULL,
                property_id TEXT,
                department TEXT,
                role_category TEXT,
                shift_type TEXT,
                synthesis_status TEXT NOT NULL,
                confidence TEXT,
                artifact_json TEXT NOT NULL,
                indexed_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS signals (
                session_id TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                signal_key TEXT NOT NULL,
                text TEXT NOT NULL,
                evidence_turn_ids_json TEXT NOT NULL,
                PRIMARY KEY (session_id, signal_type, signal_key),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_signals_lookup
                ON signals(signal_type, signal_key);
            CREATE INDEX IF NOT EXISTS idx_sessions_created
                ON sessions(artifact_created_at);
            """
        )
        self.connection.commit()

    def index_artifact_file(self, path: str | Path) -> None:
        artifact_path = Path(path)
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IntelligenceStoreError(
                f"Could not index artifact: {artifact_path.name}"
            ) from exc
        self.index_artifact(artifact_path.name, artifact)

    def index_artifact(self, artifact_id: str, artifact: dict[str, Any]) -> None:
        try:
            session = artifact["session"]
            plan = artifact["interview_plan"]
            context = artifact.get("respondent_context") or {}
            synthesis = artifact.get("synthesis") or {"status": "not_run"}
            session_id = session["id"]
            created_at = session.get("artifact_created_at")
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("session id is required")
            if not isinstance(created_at, (int, float)):
                raise ValueError("artifact creation time is required")
            artifact_json = json.dumps(artifact, ensure_ascii=False, sort_keys=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise IntelligenceStoreError(
                f"Artifact {artifact_id} is not indexable"
            ) from exc

        eligible_turn_ids = {
            turn.get("id")
            for turn in artifact.get("transcript", [])
            if isinstance(turn, dict)
            and turn.get("role") == "respondent"
            and not turn.get("interrupted", False)
            and isinstance(turn.get("id"), str)
        }
        signals = (
            list(self._signals_from_synthesis(synthesis, eligible_turn_ids))
            if session.get("status") == "completed"
            else []
        )
        try:
            with self._lock, self.connection:
                self.connection.execute(
                    """
                    INSERT INTO sessions (
                        session_id, artifact_id, artifact_schema_version,
                        plan_id, plan_version, session_status, started_at,
                        artifact_created_at, property_id, department,
                        role_category, shift_type, synthesis_status, confidence,
                        artifact_json, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        artifact_id = excluded.artifact_id,
                        artifact_schema_version = excluded.artifact_schema_version,
                        plan_id = excluded.plan_id,
                        plan_version = excluded.plan_version,
                        session_status = excluded.session_status,
                        started_at = excluded.started_at,
                        artifact_created_at = excluded.artifact_created_at,
                        property_id = excluded.property_id,
                        department = excluded.department,
                        role_category = excluded.role_category,
                        shift_type = excluded.shift_type,
                        synthesis_status = excluded.synthesis_status,
                        confidence = excluded.confidence,
                        artifact_json = excluded.artifact_json,
                        indexed_at = excluded.indexed_at
                    """,
                    (
                        session_id,
                        artifact_id,
                        str(artifact.get("schema_version", "unknown")),
                        str(plan.get("id", "unknown")),
                        str(plan.get("version", "unknown")),
                        str(session.get("status", "unknown")),
                        session.get("started_at"),
                        float(created_at),
                        context.get("property_id"),
                        context.get("department"),
                        context.get("role_category"),
                        context.get("shift_type"),
                        str(synthesis.get("status", "not_run")),
                        (synthesis.get("result") or {}).get("confidence"),
                        artifact_json,
                        time.time(),
                    ),
                )
                self.connection.execute(
                    "DELETE FROM signals WHERE session_id = ?",
                    (session_id,),
                )
