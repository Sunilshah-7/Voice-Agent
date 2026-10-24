"""Local read-only web review surface for ShiftSignal artifacts."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from hospitality_agent.intelligence import IntelligenceStore
from hospitality_agent.review import ReviewArtifactError, ReviewStore


STATIC_DIR = Path(__file__).with_name("review")


@dataclass(frozen=True, slots=True)
class Response:
    status: HTTPStatus
    content_type: str
    body: bytes


class ReviewApplication:
    def __init__(
        self,
        store: ReviewStore,
        static_dir: str | Path = STATIC_DIR,
        intelligence: IntelligenceStore | None = None,
    ) -> None:
        self.store = store
        self.static_dir = Path(static_dir)
        self.intelligence = intelligence
        self.static_files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
        }

    def handle(self, method: str, target: str) -> Response:
        if method not in {"GET", "HEAD"}:
            return self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Method not allowed"})
        parsed = urlsplit(target)
        path = parsed.path
        if path == "/api/sessions":
            return self._json(HTTPStatus.OK, {"sessions": self.store.list_sessions()})
        if path == "/api/intelligence":
            if self.intelligence is None:
                return self._json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "Cross-interview intelligence is unavailable"},
                )
            group_by = parse_qs(parsed.query).get("group_by", ["department"])[0]
            sync = self.intelligence.sync_artifact_files(self.store.artifact_paths())
            try:
                snapshot = self.intelligence.intelligence_snapshot(group_by=group_by)
            except ValueError as exc:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            snapshot["artifact_sync"] = sync
            return self._json(HTTPStatus.OK, snapshot)
        if path.startswith("/api/sessions/"):
            artifact_id = unquote(path.removeprefix("/api/sessions/"))
            try:
                artifact = self.store.load_session(artifact_id)
            except ReviewArtifactError as exc:
                status = (
                    HTTPStatus.BAD_REQUEST
                    if "Invalid artifact" in str(exc)
                    else HTTPStatus.NOT_FOUND
                )
                return self._json(status, {"error": str(exc)})
            return self._json(HTTPStatus.OK, artifact)
        static = self.static_files.get(path)
        if static is None:
            return self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        filename, content_type = static
        try:
            body = (self.static_dir / filename).read_bytes()
        except OSError:
            return self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Review interface asset is unavailable"},
            )
        return Response(HTTPStatus.OK, content_type, body)

    @staticmethod
    def _json(status: HTTPStatus, payload: object) -> Response:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return Response(status, "application/json; charset=utf-8", body)


def handler_for(application: ReviewApplication) -> type[BaseHTTPRequestHandler]:
    class ReviewHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._respond(include_body=True)

        def do_HEAD(self) -> None:
            self._respond(include_body=False)

        def do_POST(self) -> None:
            self._respond(include_body=True)

        def _respond(self, *, include_body: bool) -> None:
            response = application.handle(self.command, self.path)
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            if include_body:
                self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            print(f"review {self.address_string()} - {format % args}")

    return ReviewHandler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--output-dir",
        default=os.getenv("SHIFT_SIGNAL_OUTPUT_DIR", "outputs"),
    )
    parser.add_argument(
        "--database",
        default=os.getenv("SHIFT_SIGNAL_DB_PATH"),
        help="SQLite path; defaults to <output-dir>/shiftsignal.db",
    )
    args = parser.parse_args()
    database_path = args.database or str(Path(args.output_dir) / "shiftsignal.db")
    intelligence = IntelligenceStore(database_path)
    application = ReviewApplication(
        ReviewStore(args.output_dir),
        intelligence=intelligence,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler_for(application))
    print(f"ShiftSignal review: http://{args.host}:{args.port}")
    print(f"Reading artifacts from: {Path(args.output_dir).resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping review server")
    finally:
        server.server_close()
        intelligence.close()


if __name__ == "__main__":
    main()
