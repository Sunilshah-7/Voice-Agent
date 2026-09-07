from __future__ import annotations

import json
import tempfile
import unittest
from http import HTTPStatus
from pathlib import Path

from hospitality_agent.review import ReviewArtifactError, ReviewStore
from review_app import ReviewApplication


def artifact(
    session_id: str,
    *,
    created_at: float,
    status: str = "completed",
) -> dict[str, object]:
    return {
        "schema_version": "1.1",
        "session": {
            "id": session_id,
            "status": status,
            "completion_reason": "objectives_covered",
            "started_at": created_at - 60,
            "artifact_created_at": created_at,
            "transcript_turns": 1,
        },
        "interview_plan": {
            "id": "post_shift_guest_experience",
            "version": "1.0",
            "title": "Post-shift guest-experience debrief",
        },
        "respondent_context": {"department": "front_desk"},
        "transcript": [
            {
                "id": "turn-0001",
                "role": "respondent",
                "text": "Guests waited at check-in.",
                "created_at": created_at,
                "interrupted": False,
                "transcript_confidence": None,
            }
        ],
        "objective_coverage": [],
        "synthesis": {"status": "not_run"},
        "usage": {},
    }


class ReviewStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output_dir = Path(self.temp_dir.name)
        self.store = ReviewStore(self.output_dir)

    def write(self, name: str, payload: object) -> None:
        (self.output_dir / name).write_text(json.dumps(payload), encoding="utf-8")

    def test_lists_newest_sessions_first_with_review_metadata(self) -> None:
        self.write("session-older.json", artifact("older", created_at=100))
        self.write("session-newer.json", artifact("newer", created_at=200))

        sessions = self.store.list_sessions()

        self.assertEqual([item["session_id"] for item in sessions], ["newer", "older"])
        self.assertEqual(sessions[0]["synthesis_status"], "not_run")
        self.assertEqual(sessions[0]["respondent_context"]["department"], "front_desk")

    def test_loads_only_known_session_artifact_names(self) -> None:
        self.write("session-safe.json", artifact("safe", created_at=100))

        loaded = self.store.load_session("session-safe.json")

        self.assertEqual(loaded["session"]["id"], "safe")
        with self.assertRaisesRegex(ReviewArtifactError, "Invalid artifact"):
            self.store.load_session("../session-safe.json")
        with self.assertRaisesRegex(ReviewArtifactError, "not found"):
            self.store.load_session("session-missing.json")

    def test_malformed_artifact_is_visible_but_cannot_be_opened(self) -> None:
        (self.output_dir / "session-broken.json").write_text("not json", encoding="utf-8")

        sessions = self.store.list_sessions()

        self.assertEqual(sessions[0]["review_status"], "unreadable")
        self.assertIn("Could not read", sessions[0]["error"])
        with self.assertRaises(ReviewArtifactError):
            self.store.load_session("session-broken.json")

    def test_non_session_json_files_are_not_exposed(self) -> None:
        self.write("settings.json", {"secret": "not an artifact"})

        self.assertEqual(self.store.list_sessions(), [])

    def test_symlinked_artifact_is_not_exposed(self) -> None:
        outside = self.output_dir.parent / "session-outside.json"
        outside.write_text(json.dumps(artifact("outside", created_at=100)), encoding="utf-8")
        self.addCleanup(outside.unlink)
        (self.output_dir / "session-linked.json").symlink_to(outside)

        self.assertEqual(self.store.list_sessions(), [])


class ReviewApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.static_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.static_dir.cleanup)
        output_dir = Path(self.temp_dir.name)
        (output_dir / "session-demo.json").write_text(
            json.dumps(artifact("demo", created_at=200)),
            encoding="utf-8",
        )
        static_path = Path(self.static_dir.name)
        for name in ("index.html", "app.js", "styles.css"):
            (static_path / name).write_text(name, encoding="utf-8")
        self.application = ReviewApplication(ReviewStore(output_dir), static_path)

    def test_session_list_and_detail_routes_return_json(self) -> None:
        listing = self.application.handle("GET", "/api/sessions")
        detail = self.application.handle("GET", "/api/sessions/session-demo.json")

        self.assertEqual(listing.status, HTTPStatus.OK)
        self.assertEqual(detail.status, HTTPStatus.OK)
        self.assertIn("application/json", listing.content_type)
        self.assertEqual(json.loads(detail.body)["session"]["id"], "demo")

    def test_encoded_path_traversal_and_unknown_routes_are_rejected(self) -> None:
        traversal = self.application.handle(
            "GET",
            "/api/sessions/%2E%2E%2Fsession-demo.json",
        )
        missing = self.application.handle("GET", "/unknown")

        self.assertEqual(traversal.status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(missing.status, HTTPStatus.NOT_FOUND)

    def test_server_is_read_only(self) -> None:
        response = self.application.handle("POST", "/api/sessions")

        self.assertEqual(response.status, HTTPStatus.METHOD_NOT_ALLOWED)

    def test_static_assets_are_served_from_explicit_routes(self) -> None:
        index = self.application.handle("GET", "/")
        script = self.application.handle("GET", "/app.js")

        self.assertEqual(index.status, HTTPStatus.OK)
        self.assertIn("text/html", index.content_type)
        self.assertIn("text/javascript", script.content_type)


if __name__ == "__main__":
    unittest.main()
