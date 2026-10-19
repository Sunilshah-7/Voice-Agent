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
