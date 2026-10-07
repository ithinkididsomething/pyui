"""PyUI HTTP server - Python standard library only (no Flask, no Django).

    python server.py          # serves on http://localhost:8000
    python server.py 8080     # custom port

Two routes:

    GET  /        -> the full HTML page (rendered from the component tree)
    POST /event   -> {handler: id, inputs: {...}} from the browser;
                     runs the Python callback and returns fresh HTML

Run this file from the project root so that `framework` and `app`
packages are importable.
"""

import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.todo import app

MAX_BODY = 256 * 1024  # bytes; plenty for normal use, blocks silly payloads

# Shown to the browser when a request blows up; the traceback goes to the log.
ERROR_PAGE = (
    "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
    "<title>Error</title></head>"
    "<body style='margin:0;min-height:100vh;display:flex;"
    "align-items:center;justify-content:center;background:#f5f6f8;"
    "font-family:-apple-system,Segoe UI,Roboto,sans-serif;'>"
    "<div style='background:#fff;border:1px solid #e5e7eb;"
    "border-radius:14px;padding:32px 36px;max-width:420px;"
    "text-align:center;box-shadow:0 10px 30px -12px rgba(15,23,42,.18);'>"
    "<h1 style='margin:0 0 8px;font-size:1.15rem;color:#111827;'>"
    "Something went wrong</h1>"
    "<p style='margin:0;color:#6b7280;font-size:.95rem;'>"
    "The server hit an error. Check the server logs for details."
    "</p></div></body></html>"
)


class PyUIRequestHandler(BaseHTTPRequestHandler):
    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _send(self, body, status=200, content_type="text/html; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    def do_GET(self):
        try:
            if self.path in ("/", "/index.html"):
                self._send(app.render_page())
            else:
                self._send("Not found", 404, "text/plain; charset=utf-8")
        except Exception:
            self._send_error()

    def do_POST(self):
        if self.path != "/event":
            self._send("Not found", 404, "text/plain; charset=utf-8")
            return
        try:
            length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            payload = {}

        try:
            html = app.handle_event(payload)
            self._send(html)
        except Exception:
            self._send_error()

    def _send_error(self):
        print(f"[pyui] error:\n{traceback.format_exc()}", file=sys.stderr)
        self._send(ERROR_PAGE, 500)

    def log_message(self, fmt, *args):
        print(f"[pyui] {self.address_string()} {fmt % args}", file=sys.stderr)

    def log_error(self, fmt, *args):
        print(f"[pyui] ERROR {fmt % args}", file=sys.stderr)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), PyUIRequestHandler)
    print(f"PyUI running at http://localhost:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping PyUI server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
