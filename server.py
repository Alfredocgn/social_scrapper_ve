#!/usr/bin/env python3
"""Servidor HTTP: sirve el dashboard y una API JSON de tendencias."""
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler

from config import env_int
from render import render_dashboard
from trends import compute_trends


class Handler(BaseHTTPRequestHandler):
    db_path = ""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            params = urllib.parse.parse_qs(parsed.query)
            query = (params.get("q", [None])[0] or "").strip() or None
            self._send_html(render_dashboard(self.db_path, query=query))
        elif self.path.startswith("/api/trends"):
            trends = compute_trends(
                self.db_path,
                window_hours=env_int("TREND_WINDOW_HOURS", 24),
                half_life_hours=env_int("TREND_HALF_LIFE_HOURS", 6),
            )
            self._send_json({"trends": trends})
        else:
            self.send_error(404)

    def _send_html(self, text):
        self._send_bytes(text.encode("utf-8"), "text/html; charset=utf-8")

    def _send_json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8")

    def _send_bytes(self, body, content_type):
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return
