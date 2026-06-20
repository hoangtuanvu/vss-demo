# Local-testing stand-in for a real VSS deployment. Implements the same
# endpoints app.vss_client.VSSClient calls, with canned hazard alerts and
# answers, so the full pipeline (poll -> triage -> persist -> SSE -> chat)
# can be exercised without a real Brev GPU instance. See docs/local-testing.md.
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

ALERTS = [
    {"hazard_type": "ppe", "zone": "dock-1", "caption": "Worker without a hard hat near the loading dock", "cursor": "c1"},
    {"hazard_type": "zone_intrusion", "zone": "restricted-a", "caption": "Person entered the marked restricted zone", "cursor": "c2"},
    {"hazard_type": "forklift_proximity", "zone": "aisle-2", "caption": "Forklift within 2m of a pedestrian", "cursor": "c3"},
    {"hazard_type": "fall", "zone": "aisle-3", "caption": "Person on the ground, not moving", "cursor": "c4"},
    {"hazard_type": "spill", "zone": "aisle-1", "caption": "Liquid spill blocking the walkway", "cursor": "c5"},
]


def alerts_after(since):
    if since is None:
        return ALERTS
    for i, a in enumerate(ALERTS):
        if a["cursor"] == since:
            return ALERTS[i + 1:]
    return []


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"status": "ok"})
        elif parsed.path == "/alerts":
            since = parse_qs(parsed.query).get("since", [None])[0]
            self._send_json({"alerts": alerts_after(since)})
        else:
            self._send_json({"detail": "not found"}, status=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw)
        except ValueError:
            body = {}

        if self.path == "/ask-video":
            self._send_json({"answer": f"Mock answer to: {body.get('question', '')}"})
        elif self.path == "/query-analytics":
            self._send_json({"count": len(ALERTS), "by_hazard": {a["hazard_type"]: 1 for a in ALERTS}})
        elif self.path == "/search-archive":
            self._send_json({"results": [{"clip": a["hazard_type"], "zone": a["zone"]} for a in ALERTS]})
        elif self.path == "/generate-report":
            incident_id = body.get("incident_id")
            self._send_json({"report_text": f"Mock incident report for incident #{incident_id}."})
        else:
            self._send_json({"detail": "not found"}, status=404)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
