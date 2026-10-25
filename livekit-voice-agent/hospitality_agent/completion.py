"""Idempotent incident submission and simulated reviewer notification."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable, Mapping

from .intelligence import IntelligenceStore, IntelligenceStoreError
from .state import InterviewState
from .synthesis import IncidentRecord, SynthesisError, SynthesisService
from .transcript import ArtifactWriteError, TranscriptRecorder


class NotificationStatus(StrEnum):
    DELIVERED = "delivered"
    QUEUED = "queued"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OperatorNotification:
    notification_id: str
    incident_id: str
    category: str
    summary: str
    location: str | None
    urgency: str
    status: NotificationStatus
    simulated: bool
    created_at: float
    delivered_at: float | None = None
    failure_reason: str | None = None


class SimulatedOperatorNotifier:
    """Return a configured delivery outcome without contacting an external service."""

    def __init__(
        self,
        mode: str | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        selected = (mode or os.getenv("SHIFT_SIGNAL_NOTIFICATION_MODE", "delivered")).strip()
        try:
            self.mode = NotificationStatus(selected)
        except ValueError as exc:
            raise ValueError(
                "SHIFT_SIGNAL_NOTIFICATION_MODE must be delivered, queued, or failed"
            ) from exc
        self.clock = clock

    async def notify(
        self,
        *,
        incident_id: str,
        incident: IncidentRecord,
    ) -> OperatorNotification:
        created_at = float(self.clock())
        return OperatorNotification(
            notification_id=f"NTF-{uuid.uuid4()}",
            incident_id=incident_id,
            category=incident.incident_type,
            summary=incident.summary.value,
            location=incident.location.value if incident.location else None,
            urgency=incident.urgency.classification.value,
            status=self.mode,
            simulated=True,
            created_at=created_at,
            delivered_at=(created_at if self.mode == NotificationStatus.DELIVERED else None),
            failure_reason=(
                "simulated_notification_failure"
                if self.mode == NotificationStatus.FAILED
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    success: bool
    incident_id: str
    submission_status: str
    notification_status: str | None
    confirmation: str
    artifact_path: Path | None = None
    error_code: str | None = None


class CompletionCoordinator:
    """Generate, persist, notify, and confirm one call exactly once."""

    def __init__(
        self,
        *,
        recorder: TranscriptRecorder,
        synthesis_service: SynthesisService,
        database_path: str | Path,
        notifier: SimulatedOperatorNotifier | None = None,
        usage_provider: Callable[[], Mapping[str, int | float]] | None = None,
    ) -> None:
        self.recorder = recorder
        self.synthesis_service = synthesis_service
        self.database_path = Path(database_path)
        self.notifier = notifier or SimulatedOperatorNotifier()
        self.usage_provider = usage_provider or (lambda: {})
        self._lock = asyncio.Lock()
        self._result: SubmissionResult | None = None

    @property
    def result(self) -> SubmissionResult | None:
        return self._result

    async def submit(self, state: InterviewState) -> SubmissionResult:
        async with self._lock:
            if self._result is not None:
                return self._result
            try:
                incident = await self.synthesis_service.synthesize(
                    turns=self.recorder.turns,
                    state=state,
                )
            except SynthesisError as exc:
                self._result = self._failure(type(exc).__name__)
                return self._result

            notification = await self.notifier.notify(
                incident_id=self.recorder.incident_id,
                incident=incident,
            )
            notification_payload = asdict(notification)
            notification_payload["status"] = notification.status.value
            synthesis = {
                "status": "completed",
                "result": incident.model_dump(mode="json"),
            }
            artifact = self.recorder.build_artifact(
                state,
                usage=self.usage_provider(),
                synthesis=synthesis,
                submission_status="Submitted for Review",
                notification=notification_payload,
            )

            try:
                store = IntelligenceStore(self.database_path)
            except IntelligenceStoreError:
                self._result = self._failure("database_persistence_failed")
                return self._result
            try:
                try:
                    store.index_artifact(self.recorder.artifact_id, artifact)
                except IntelligenceStoreError:
                    self._result = self._failure("database_persistence_failed")
                    return self._result
            finally:
                store.close()

            artifact_path: Path | None
            try:
                artifact_path = self.recorder.write_artifact(artifact)
            except ArtifactWriteError:
                artifact_path = None

            confirmation = self._confirmation(notification.status)
            self._result = SubmissionResult(
                success=True,
                incident_id=self.recorder.incident_id,
                submission_status="Submitted for Review",
                notification_status=notification.status.value,
                confirmation=confirmation,
                artifact_path=artifact_path,
            )
            return self._result

    def _failure(self, error_code: str) -> SubmissionResult:
        return SubmissionResult(
            success=False,
            incident_id=self.recorder.incident_id,
            submission_status="Not Submitted",
            notification_status=None,
            confirmation=(
                "I couldn't submit the report for review. No dispatcher, police department, "
                "or emergency service has received it."
            ),
            error_code=error_code,
        )

    def _confirmation(self, status: NotificationStatus) -> str:
        base = (
            f"Your report {self.recorder.incident_id} has been recorded and submitted "
            "for human review."
        )
        if status == NotificationStatus.DELIVERED:
            notification = " The simulated reviewer notification was delivered."
        elif status == NotificationStatus.QUEUED:
            notification = " The simulated reviewer notification is queued."
        else:
            notification = " The simulated reviewer notification failed."
        return (
            base
            + notification
            + " No dispatcher, police department, or emergency service was contacted."
        )
