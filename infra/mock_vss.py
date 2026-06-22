# Local-testing stand-in for a real VSS deployment. Implements the same
# endpoints app.vss_client.VSSClient calls — health, chat, realtime alert
# rules, realtime incidents — with canned hazard incidents and canned chat
# answers, so the full pipeline (poll -> triage -> persist -> SSE -> chat)
# can be exercised without a real Brev GPU instance. See docs/local-testing.md.
import json
import uuid
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

BASE_TIME = datetime(2026, 1, 1, 0, 0, 0)

INCIDENTS = [
    {"id": "c1", "category": "PPE Violation", "sensor_id": "dock-1", "timestamp": (BASE_TIME).isoformat() + "Z", "description": "Worker without a hard hat near the loading dock"},
    {"id": "c2", "category": "Near Miss Violation", "sensor_id": "aisle-2", "timestamp": (BASE_TIME + timedelta(seconds=10)).isoformat() + "Z", "description": "Forklift within 2m of a pedestrian"},
    {"id": "c3", "category": "Pathway Obstruction Violation", "sensor_id": "aisle-1", "timestamp": (BASE_TIME + timedelta(seconds=20)).isoformat() + "Z", "description": "Liquid spill blocking the walkway"},
    {"id": "c4", "category": "Spillover Violation", "sensor_id": "aisle-3", "timestamp": (BASE_TIME + timedelta(seconds=30)).isoformat() + "Z", "description": "Dropped pallet blocking the walkway"},
    {"id": "c5", "category": "PPE Violation", "sensor_id": "restricted-a", "timestamp": (BASE_TIME + timedelta(seconds=40)).isoformat() + "Z", "description": "Person entered the marked restricted zone without a vest"},
]


def incidents_after(start_time):
    if not start_time:
        return INCIDENTS
    return [i for i in INCIDENTS if i["timestamp"] > start_time]


def chat_reply(message: str) -> str:
    lowered = message.lower()
    if "hazard type:" in lowered and "severity:" in lowered:
        return "Mock incident report: hazard observed and logged for follow-up; no further action required at this time."
    if "summar" in lowered:
        return "Mock summary: 5 hazards detected today across PPE, near-miss, and spill categories. No critical escalations."
    if "search" in lowered or "find" in lowered:
        return "Mock search results: 5 matching incidents found — PPE violation (dock-1), near-miss (aisle-2), pathway obstruction (aisle-1), spillover (aisle-3), PPE violation (restricted-a)."
    for keyword in ("ppe", "forklift", "spill", "fall", "zone"):
        if keyword in lowered:
            return f"Mock answer about {keyword}: this hazard type has been observed today, see the incident feed for details."
    return f"Mock answer to: {message}"


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw)
        except ValueError:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"status": "ok"})
        elif parsed.path == "/api/v1/realtime/incidents":
            query = parse_qs(parsed.query)
            start_time = query.get("start_time", [None])[0]
            limit = int(query.get("limit", [100])[0])
            incidents = incidents_after(start_time)[:limit]
            self._send_json({
                "status": "success", "count": len(incidents), "total": len(INCIDENTS),
                "timestamp": datetime.utcnow().isoformat() + "Z", "incidents": incidents,
            })
        else:
            self._send_json({"detail": "not found"}, status=404)

    def do_POST(self):
        body = self._read_json_body()
        if self.path == "/chat":
            messages = body.get("messages", [])
            last_user_message = messages[-1]["content"] if messages else ""
            self._send_json({
                "id": "mock", "object": "chat.completion", "model": "mock", "created": 0,
                "choices": [{"finish_reason": "stop", "index": 0, "message": {
                    "role": "assistant", "content": chat_reply(last_user_message),
                }}],
            })
        elif self.path == "/api/v1/realtime":
            self._send_json({"id": str(uuid.uuid4()), "status": "success", "message": "created"})
        else:
            self._send_json({"detail": "not found"}, status=404)

    def do_DELETE(self):
        if self.path.startswith("/api/v1/realtime/"):
            rule_id = self.path.rsplit("/", 1)[-1]
            self._send_json({"id": rule_id, "status": "success", "message": "deleted"})
        else:
            self._send_json({"detail": "not found"}, status=404)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
