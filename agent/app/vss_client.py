import time

import httpx

from app.chat_format import clean_chat_response

# The real alert-bridge incident feed uses its own human-readable category
# names (observed live against the deployed warehouse-blueprint sample
# dataset), not our HazardType enum values. Map known categories here;
# anything absent passes through unmapped and is dropped by the poller's
# existing unrecognized-category skip (see app/poller.py).
CATEGORY_MAP = {
    "ppe violation": "ppe",
    "spillover violation": "spill",
    "pathway obstruction violation": "spill",
    "near miss violation": "forklift_proximity",
}


class VSSClient:
    def __init__(
        self,
        agent_base_url: str,
        alert_bridge_base_url: str,
        client: httpx.Client | None = None,
        max_retries: int = 3,
    ):
        self.agent_base_url = agent_base_url.rstrip("/")
        self.alert_bridge_base_url = alert_bridge_base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=10.0)
        self.max_retries = max_retries

    def _request_with_retry(self, method: str, base_url: str, path: str, **kwargs) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.request(method, f"{base_url}{path}", **kwargs)
                response.raise_for_status()
                return response
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt * 0.1)
        raise last_exc

    def get_new_alerts(self, since_timestamp: str | None) -> list[dict]:
        params = {"limit": 100}
        if since_timestamp:
            params["start_time"] = since_timestamp
        response = self._request_with_retry(
            "GET", self.alert_bridge_base_url, "/api/v1/realtime/incidents", params=params
        )
        incidents = response.json()["incidents"]
        incidents.sort(key=lambda incident: incident["timestamp"])
        return [self._normalize_alert(incident) for incident in incidents]

    @staticmethod
    def _normalize_alert(incident: dict) -> dict:
        raw_category = incident.get("category", "")
        category = CATEGORY_MAP.get(raw_category.strip().lower(), raw_category)
        return {
            "id": incident.get("id") or incident.get("Id") or incident.get("_id"),
            "category": category,
            "sensor_id": incident.get("sensor_id") or incident.get("sensorId", ""),
            "timestamp": incident["timestamp"],
            "description": incident.get("description") or raw_category,
        }

    def chat(self, message: str) -> str:
        response = self._request_with_retry(
            "POST",
            self.agent_base_url,
            "/chat",
            json={"messages": [{"role": "user", "content": message}]},
        )
        content = response.json()["choices"][0]["message"]["content"]
        return clean_chat_response(content)

    def generate_report(self, incident: dict) -> str:
        prompt = (
            "Write a short incident report for this warehouse safety incident.\n"
            f"Hazard type: {incident['hazard_type']}\n"
            f"Severity: {incident['severity']}\n"
            f"Zone: {incident['zone']}\n"
            f"Description: {incident['caption']}\n"
            f"Detected at: {incident['created_at']}\n"
        )
        return self.chat(prompt)

    def register_alert_rules(self, stream_url: str, sensor_id: str, rules: list[dict]) -> list[str]:
        rule_ids = []
        for rule in rules:
            response = self._request_with_retry(
                "POST",
                self.alert_bridge_base_url,
                "/api/v1/realtime",
                json={
                    "live_stream_url": stream_url,
                    "sensor_id": sensor_id,
                    "alert_type": rule["alert_type"],
                    "prompt": rule["prompt"],
                    "system_prompt": rule["system_prompt"],
                },
            )
            rule_ids.append(response.json()["id"])
        return rule_ids

    def delete_alert_rules(self, rule_ids: list[str]) -> None:
        for rule_id in rule_ids:
            self._request_with_retry(
                "DELETE", self.alert_bridge_base_url, f"/api/v1/realtime/{rule_id}"
            )

    def health_check(self) -> bool:
        try:
            self._request_with_retry("GET", self.agent_base_url, "/health")
            self._request_with_retry("GET", self.alert_bridge_base_url, "/health")
        except (httpx.TransportError, httpx.HTTPStatusError):
            return False
        return True
