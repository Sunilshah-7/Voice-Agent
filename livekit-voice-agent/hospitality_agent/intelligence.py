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
INCIDENT_REVIEW_STATUSES = (
    "Pending Review",
    "Under Review",
    "Escalated",
    "Resolved",
)


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

            CREATE TABLE IF NOT EXISTS incident_records (
                session_id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL UNIQUE,
                submission_status TEXT NOT NULL,
                incident_schema_version TEXT NOT NULL,
                incident_type TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                caller_name TEXT,
                caller_contact TEXT,
                incident_location TEXT,
                incident_description TEXT NOT NULL,
                occurred_at TEXT,
                urgency TEXT NOT NULL,
                summary TEXT NOT NULL,
                human_review_required INTEGER NOT NULL DEFAULT 0,
                escalation_status TEXT,
                incident_json TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS operator_notifications (
                notification_id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                category TEXT NOT NULL,
                summary TEXT NOT NULL,
                location TEXT,
                urgency TEXT NOT NULL,
                status TEXT NOT NULL,
                simulated INTEGER NOT NULL,
                created_at REAL NOT NULL,
                delivered_at REAL,
                failure_reason TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS incident_reviews (
                incident_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                acknowledged_at REAL,
                updated_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_signals_lookup
                ON signals(signal_type, signal_key);
            CREATE INDEX IF NOT EXISTS idx_sessions_created
                ON sessions(artifact_created_at);
            """
        )
        incident_columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(incident_records)")
        }
        if "human_review_required" not in incident_columns:
            self.connection.execute(
                "ALTER TABLE incident_records ADD COLUMN "
                "human_review_required INTEGER NOT NULL DEFAULT 0"
            )
        if "escalation_status" not in incident_columns:
            self.connection.execute(
                "ALTER TABLE incident_records ADD COLUMN escalation_status TEXT"
            )
        if "incident_id" not in incident_columns:
            self.connection.execute(
                "ALTER TABLE incident_records ADD COLUMN incident_id TEXT"
            )
        if "submission_status" not in incident_columns:
            self.connection.execute(
                "ALTER TABLE incident_records ADD COLUMN submission_status TEXT"
            )
        self.connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_incident_records_incident_id "
            "ON incident_records(incident_id) WHERE incident_id IS NOT NULL"
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
        incident_record = artifact.get("incident_record")
        incident_wrapper = artifact.get("incident") or {
            "id": session.get("incident_id") or f"LEGACY-{session_id}",
            "status": "Legacy Imported",
        }
        notification = artifact.get("operator_notification")
        safety = artifact.get("safety") or {}
        if incident_record is not None and not isinstance(incident_record, dict):
            raise IntelligenceStoreError(
                f"Artifact {artifact_id} has an invalid incident record"
            )
        if not isinstance(incident_wrapper, dict):
            raise IntelligenceStoreError(f"Artifact {artifact_id} has invalid incident metadata")
        if notification is not None and not isinstance(notification, dict):
            raise IntelligenceStoreError(f"Artifact {artifact_id} has invalid notification")
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
                self.connection.execute(
                    "DELETE FROM incident_records WHERE session_id = ?",
                    (session_id,),
                )
                self.connection.execute(
                    "DELETE FROM operator_notifications WHERE session_id = ?",
                    (session_id,),
                )
                if incident_record is not None:
                    self._insert_incident_record(
                        session_id,
                        incident_record,
                        incident_wrapper,
                        safety,
                    )
                    self.connection.execute(
                        """
                        INSERT OR IGNORE INTO incident_reviews (
                            incident_id, status, acknowledged_at, updated_at
                        ) VALUES (?, ?, NULL, ?)
                        """,
                        (
                            incident_wrapper["id"],
                            "Pending Review",
                            time.time(),
                        ),
                    )
                if notification is not None:
                    self._insert_notification(session_id, notification)
                self.connection.executemany(
                    """
                    INSERT INTO signals (
                        session_id, signal_type, signal_key, text,
                        evidence_turn_ids_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            session_id,
                            signal_type,
                            normalize_signal(statement["text"]),
                            statement["text"],
                            json.dumps(statement["evidence_turn_ids"]),
                        )
                        for signal_type, statement in signals
                    ),
                )
        except sqlite3.Error as exc:
            raise IntelligenceStoreError(
                f"Could not index artifact: {artifact_id}"
            ) from exc

    def _insert_incident_record(
        self,
        session_id: str,
        incident: dict[str, Any],
        incident_wrapper: dict[str, Any],
        safety: object,
    ) -> None:
        try:
            caller = incident.get("caller") or {}
            urgency = incident["urgency"]
            incident_type = incident["incident_type"]
            subcategory = incident["subcategory"]
            description = self._field_value(incident["description"], required=True)
            summary = self._field_value(incident["summary"], required=True)
            urgency_value = urgency["classification"]
            if not all(
                isinstance(value, str) and value
                for value in (incident_type, subcategory, urgency_value)
            ):
                raise ValueError("required incident fields must be non-empty strings")
            if not isinstance(caller, dict) or not isinstance(urgency, dict):
                raise ValueError("caller and urgency must be objects")
            caller_name = self._field_value(caller.get("name"))
            caller_contact = self._field_value(caller.get("contact"))
            incident_location = self._field_value(incident.get("location"))
            occurred_at = self._field_value(incident.get("occurred_at"))
            if not isinstance(safety, dict):
                raise ValueError("safety must be an object")
            human_review_required = bool(safety.get("human_review_required", False))
            escalation = safety.get("escalation") or {}
            if not isinstance(escalation, dict):
                raise ValueError("safety escalation must be an object")
            escalation_status = escalation.get("status")
            if escalation_status is not None and not isinstance(escalation_status, str):
                raise ValueError("escalation status must be a string")
            incident_id = incident_wrapper["id"]
            submission_status = incident_wrapper["status"]
            if not all(
                isinstance(value, str) and value
                for value in (incident_id, submission_status)
            ):
                raise ValueError("incident id and submission status are required")
        except (KeyError, TypeError, ValueError) as exc:
            raise IntelligenceStoreError(
                f"Incident record for session {session_id} is not indexable"
            ) from exc

        self.connection.execute(
            """
            INSERT INTO incident_records (
                session_id, incident_id, submission_status,
                incident_schema_version, incident_type, subcategory,
                caller_name, caller_contact, incident_location,
                incident_description, occurred_at, urgency, summary,
                human_review_required, escalation_status, incident_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                incident_id,
                submission_status,
                str(incident.get("schema_version", "unknown")),
                incident_type,
                subcategory,
                caller_name,
                caller_contact,
                incident_location,
                description,
                occurred_at,
                urgency_value,
                summary,
                int(human_review_required),
                escalation_status,
                json.dumps(incident, ensure_ascii=False, sort_keys=True),
            ),
        )

    def _insert_notification(
        self,
        session_id: str,
        notification: dict[str, Any],
    ) -> None:
        required = (
            "notification_id",
            "incident_id",
            "category",
            "summary",
            "urgency",
            "status",
            "created_at",
        )
        if any(notification.get(key) in {None, ""} for key in required):
            raise IntelligenceStoreError(
                f"Operator notification for session {session_id} is not indexable"
            )
        if notification["status"] not in {"delivered", "queued", "failed"}:
            raise IntelligenceStoreError(
                f"Operator notification for session {session_id} has an invalid status"
            )
        self.connection.execute(
            """
            INSERT INTO operator_notifications (
                notification_id, incident_id, session_id, category, summary,
                location, urgency, status, simulated, created_at, delivered_at,
                failure_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                notification["notification_id"],
                notification["incident_id"],
                session_id,
                notification["category"],
                notification["summary"],
                notification.get("location"),
                notification["urgency"],
                notification["status"],
                int(bool(notification.get("simulated", True))),
                float(notification["created_at"]),
                notification.get("delivered_at"),
                notification.get("failure_reason"),
            ),
        )

    @staticmethod
    def _field_value(field: object, *, required: bool = False) -> str | None:
        if field is None and not required:
            return None
        if not isinstance(field, dict):
            raise ValueError("incident field must be an object")
        value = field.get("value")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("incident field value must be a non-empty string")
        return value

    @staticmethod
    def _signals_from_synthesis(
        synthesis: dict[str, Any],
        eligible_turn_ids: set[str],
    ) -> Iterable[tuple[str, dict[str, Any]]]:
        if synthesis.get("status") != "completed":
            return
        result = synthesis.get("result")
        if not isinstance(result, dict):
            return
        for signal_type, field in (
            ("operational_issue", "operational_issue"),
            ("positive_practice", "positive_practice"),
        ):
            statement = result.get(field)
            if (
                isinstance(statement, dict)
                and isinstance(statement.get("text"), str)
                and statement["text"].strip()
                and isinstance(statement.get("evidence_turn_ids"), list)
                and statement["evidence_turn_ids"]
                and set(statement["evidence_turn_ids"]).issubset(eligible_turn_ids)
            ):
                yield signal_type, statement

    def sync_artifact_files(self, paths: Iterable[str | Path]) -> dict[str, int]:
        indexed = 0
        failed = 0
        for path in paths:
            try:
                self.index_artifact_file(path)
            except IntelligenceStoreError:
                failed += 1
            else:
                indexed += 1
        return {"indexed": indexed, "failed": failed}

    def load_artifact(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute(
                "SELECT artifact_json FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise IntelligenceStoreError(f"Indexed session not found: {session_id}")
        try:
            artifact = json.loads(row["artifact_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise IntelligenceStoreError(
                f"Indexed session is unreadable: {session_id}"
            ) from exc
        if not isinstance(artifact, dict):
            raise IntelligenceStoreError(f"Indexed session is unreadable: {session_id}")
        return artifact

    def load_incident_record(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute(
                "SELECT incident_json FROM incident_records WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise IntelligenceStoreError(f"Incident record not found: {session_id}")
        try:
            incident = json.loads(row["incident_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise IntelligenceStoreError(
                f"Incident record is unreadable: {session_id}"
            ) from exc
        if not isinstance(incident, dict):
            raise IntelligenceStoreError(f"Incident record is unreadable: {session_id}")
        return incident

    def get_incident_review(self, incident_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute(
                """
                SELECT incident_id, status, acknowledged_at, updated_at
                FROM incident_reviews
                WHERE incident_id = ?
                """,
                (incident_id,),
            ).fetchone()
        if row is None:
            raise IntelligenceStoreError(f"Incident review not found: {incident_id}")
        return dict(row)

    def acknowledge_incident(self, incident_id: str) -> dict[str, Any]:
        now = time.time()
        try:
            with self._lock, self.connection:
                cursor = self.connection.execute(
                    """
                    UPDATE incident_reviews
                    SET acknowledged_at = COALESCE(acknowledged_at, ?),
                        status = CASE
                            WHEN status = 'Pending Review' THEN 'Under Review'
                            ELSE status
                        END,
                        updated_at = ?
                    WHERE incident_id = ?
                    """,
                    (now, now, incident_id),
                )
                if cursor.rowcount != 1:
                    raise IntelligenceStoreError(
                        f"Incident review not found: {incident_id}"
                    )
        except sqlite3.Error as exc:
            raise IntelligenceStoreError(
                f"Could not acknowledge incident: {incident_id}"
            ) from exc
        return self.get_incident_review(incident_id)

    def update_incident_status(
        self,
        incident_id: str,
        status: str,
    ) -> dict[str, Any]:
        if status not in INCIDENT_REVIEW_STATUSES:
            raise ValueError(f"Unsupported incident status: {status}")
        now = time.time()
        try:
            with self._lock, self.connection:
                cursor = self.connection.execute(
                    """
                    UPDATE incident_reviews
                    SET status = ?, updated_at = ?
                    WHERE incident_id = ?
                    """,
                    (status, now, incident_id),
                )
                if cursor.rowcount != 1:
                    raise IntelligenceStoreError(
                        f"Incident review not found: {incident_id}"
                    )
        except sqlite3.Error as exc:
            raise IntelligenceStoreError(
                f"Could not update incident status: {incident_id}"
            ) from exc
        return self.get_incident_review(incident_id)

    def intelligence_snapshot(
        self,
        *,
        group_by: str = "department",
        minimum_sample_size: int = MIN_AGGREGATE_SAMPLE_SIZE,
        as_of: float | None = None,
        recent_days: int = 30,
    ) -> dict[str, Any]:
        if group_by not in ALLOWED_GROUP_DIMENSIONS:
            raise ValueError(f"Unsupported grouping dimension: {group_by}")
        if minimum_sample_size < MIN_AGGREGATE_SAMPLE_SIZE:
            raise ValueError(
                f"Minimum sample size cannot be below {MIN_AGGREGATE_SAMPLE_SIZE}"
            )
        with self._lock:
            return {
                "group_by": group_by,
                "minimum_sample_size": minimum_sample_size,
                "indexed_sessions": self._indexed_session_count(),
                "recurring_issues": self._aggregate(
                    "operational_issue",
                    group_by,
                    minimum_sample_size,
                ),
                "positive_practices": self._aggregate(
                    "positive_practice",
                    group_by,
                    minimum_sample_size,
                ),
                "trends": self._trends(
                    group_by=group_by,
                    minimum_sample_size=minimum_sample_size,
                    as_of=time.time() if as_of is None else as_of,
                    recent_days=recent_days,
                ),
                "limitations": [
                    "Only completed, evidence-linked syntheses become signals.",
                    "Findings group only when their normalized wording matches; semantic clustering is not inferred.",
                    "Groups below the minimum sample size are withheld.",
                    "Counts represent interviews, not unique employees or verified incidents.",
                ],
            }

    def _indexed_session_count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM sessions").fetchone()
        return int(row["count"])

    def _aggregate(
        self,
        signal_type: str,
        group_by: str,
        minimum_sample_size: int,
    ) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"""
            SELECT
                COALESCE(s.{group_by}, 'not_recorded') AS dimension_value,
                g.signal_key,
                MIN(g.text) AS representative_text,
                COUNT(DISTINCT s.session_id) AS sample_size,
                MIN(s.artifact_created_at) AS first_seen_at,
                MAX(s.artifact_created_at) AS last_seen_at
            FROM signals AS g
            JOIN sessions AS s ON s.session_id = g.session_id
            WHERE g.signal_type = ?
            GROUP BY dimension_value, g.signal_key
            HAVING COUNT(DISTINCT s.session_id) >= ?
            ORDER BY sample_size DESC, last_seen_at DESC
            """,
            (signal_type, minimum_sample_size),
        ).fetchall()
        aggregates = []
        for row in rows:
            sources = self._supporting_sessions(
                signal_type=signal_type,
                signal_key=row["signal_key"],
                group_by=group_by,
                dimension_value=row["dimension_value"],
            )
            aggregates.append({
                "dimension_value": row["dimension_value"],
                "signal_key": row["signal_key"],
                "text": row["representative_text"],
                "sample_size": row["sample_size"],
                "supporting_session_ids": [source["session_id"] for source in sources],
                "supporting_artifact_ids": [source["artifact_id"] for source in sources],
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
            })
        return aggregates

    def _trends(
        self,
        *,
        group_by: str,
        minimum_sample_size: int,
        as_of: float,
        recent_days: int,
    ) -> list[dict[str, Any]]:
        window = recent_days * 86400
        recent_start = as_of - window
        baseline_start = recent_start - window
        rows = self.connection.execute(
            f"""
            SELECT
                COALESCE(s.{group_by}, 'not_recorded') AS dimension_value,
                g.signal_key,
                MIN(g.text) AS representative_text,
                COUNT(DISTINCT CASE
                    WHEN s.artifact_created_at > ? AND s.artifact_created_at <= ?
                    THEN s.session_id END) AS recent_count,
                COUNT(DISTINCT CASE
                    WHEN s.artifact_created_at > ? AND s.artifact_created_at <= ?
                    THEN s.session_id END) AS baseline_count
            FROM signals AS g
            JOIN sessions AS s ON s.session_id = g.session_id
            WHERE g.signal_type = 'operational_issue'
              AND s.artifact_created_at > ?
              AND s.artifact_created_at <= ?
            GROUP BY dimension_value, g.signal_key
            """,
            (
                recent_start,
                as_of,
                baseline_start,
                recent_start,
                baseline_start,
                as_of,
            ),
        ).fetchall()
        trends = []
        for row in rows:
            recent_count = int(row["recent_count"])
            baseline_count = int(row["baseline_count"])
            if recent_count < minimum_sample_size or recent_count <= baseline_count:
                continue
            sources = self._supporting_sessions(
                signal_type="operational_issue",
                signal_key=row["signal_key"],
                group_by=group_by,
                dimension_value=row["dimension_value"],
                after=recent_start,
                through=as_of,
            )
            trends.append(
                {
                    "classification": "emerging" if baseline_count == 0 else "increasing",
                    "dimension_value": row["dimension_value"],
                    "signal_key": row["signal_key"],
                    "text": row["representative_text"],
                    "recent_count": recent_count,
                    "baseline_count": baseline_count,
                    "supporting_session_ids": [
                        source["session_id"] for source in sources
                    ],
                    "supporting_artifact_ids": [
                        source["artifact_id"] for source in sources
                    ],
                    "recent_window_days": recent_days,
                }
            )
        trends.sort(key=lambda item: (-item["recent_count"], item["text"]))
        return trends

    def _supporting_sessions(
        self,
        *,
        signal_type: str,
        signal_key: str,
        group_by: str,
        dimension_value: str,
        after: float | None = None,
        through: float | None = None,
    ) -> list[sqlite3.Row]:
        conditions = [
            "g.signal_type = ?",
            "g.signal_key = ?",
            f"COALESCE(s.{group_by}, 'not_recorded') = ?",
        ]
        parameters: list[object] = [signal_type, signal_key, dimension_value]
        if after is not None:
            conditions.append("s.artifact_created_at > ?")
            parameters.append(after)
        if through is not None:
            conditions.append("s.artifact_created_at <= ?")
            parameters.append(through)
        return self.connection.execute(
            f"""
            SELECT s.session_id, s.artifact_id
            FROM signals AS g
            JOIN sessions AS s ON s.session_id = g.session_id
            WHERE {" AND ".join(conditions)}
            ORDER BY s.session_id
            """,
            parameters,
        ).fetchall()
