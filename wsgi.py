"""WSGI entrypoint - lets PyUI run on serverless hosts such as Vercel.

`python server.py` (stdlib HTTP server) remains the local development path;
both front ends talk to the same App and the same event machinery.

Routing:
    GET  /        -> the full HTML page
    POST /event   -> run the callback, return the fresh HTML
    anything else -> 404 (500 with a friendly page on internal errors)
"""

import json
import sys
import traceback

from app.todo import app as todo_app
from server import ERROR_PAGE

MAX_BODY = 256 * 1024


def _respond(start_response, status, body, content_type="text/html; charset=utf-8"):
    if isinstance(body, str):
        body = body.encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/")
    try:
        if method == "GET" and path in ("/", "/index.html"):
            return _respond(start_response, "200 OK", todo_app.render_page())

        if method == "POST" and path == "/event":
            try:
                length = min(int(environ.get("CONTENT_LENGTH") or 0), MAX_BODY)
            except ValueError:
                length = 0
            raw = environ["wsgi.input"].read(length) if length > 0 else b""
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            return _respond(start_response, "200 OK", todo_app.handle_event(payload))

        return _respond(
            start_response, "404 Not Found", b"Not found",
            "text/plain; charset=utf-8",
        )
    except Exception:
        print(f"[pyui] error:\n{traceback.format_exc()}", file=sys.stderr)
        return _respond(start_response, "500 Internal Server Error", ERROR_PAGE)
