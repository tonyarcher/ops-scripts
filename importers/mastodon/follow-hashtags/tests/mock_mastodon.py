#!/usr/bin/env python3
"""Shared mock Mastodon HTTP server for tests. Loopback only."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse


@dataclass
class MockCall:
    method: str
    url: str
    path: str


@dataclass
class MockMastodon:
    url: str
    calls: list[MockCall] = field(default_factory=list)
    _server: HTTPServer | None = None
    _thread: threading.Thread | None = None

    def close(self) -> None:
        """Shut down the mock server."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


def start_mock_mastodon(
    handler: Callable[[object, object, object], None],
) -> MockMastodon:
    """Start a loopback HTTP server. Returns url, calls, and close()."""
    mock = MockMastodon(url="")
    calls: list[MockCall] = mock.calls

    class _Handler(BaseHTTPRequestHandler):
        def _record(self) -> object:
            parsed = urlparse(self.path)
            calls.append(MockCall(method=self.command, url=self.path, path=parsed.path))
            return parsed

        def _run(self) -> None:
            url = self._record()
            handler(self, self.wfile, url)

        def do_GET(self) -> None:
            """Handle GET."""
            self._run()

        def do_POST(self) -> None:
            """Handle POST."""
            self._run()

        def log_message(self, fmt: str, *args: object) -> None:
            """Suppress access logs."""

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    mock.url = f"http://127.0.0.1:{port}"
    mock._server = server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    mock._thread = thread
    thread.start()
    return mock


def send_json(
    handler: BaseHTTPRequestHandler,
    status: int,
    body: object,
    headers: dict[str, str] | None = None,
) -> None:
    """Send a JSON response from a mock handler."""
    data = json.dumps(body).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    for key, value in (headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(data)
