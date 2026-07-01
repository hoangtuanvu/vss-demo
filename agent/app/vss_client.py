import time
import uuid

import httpx

from app.chat_format import clean_chat_response

# Maps VSS warehouse-blueprint alert-bridge category strings → HazardType enum
# values. VSS 3.2 warehouse ships 5 reference categories (docs confirmed):
#   PPE Violation, Near Miss, Spillover Violation,
#   Pathway Obstruction Violation, Load Quality Violation
# All 5 are mapped below. Anything absent passes through unmapped and is
# dropped by the poller unless it already equals a HazardType value.
#
# TODO(real-vss): the exact category strings VSS emits for restricted-zone
# intrusion and fall/man-down are unconfirmed (custom alert rules, never fired
# against the sample dataset). Until verified, zone_intrusion and fall from
# real VSS pass through only if VSS emits those exact canonical strings.
# The mock server emits them directly so all 5 hazards appear in offline demos.
CATEGORY_MAP = {
    "ppe violation": "ppe",
    "near miss": "forklift_proximity",
    "near miss violation": "forklift_proximity",
    "spillover violation": "spill",
    "pathway obstruction violation": "spill",
    # Load Quality Violation = damaged/falling/unstable cargo → spill hazard type
    "load quality violation": "spill",
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
        self._sensor_id_map: dict[str, str] = {}

    def resolve_sensor_id(self, raw_sensor_id: str) -> str:
        """Translate a VSS-facing UUID sensor_id back to the human-readable
        name we registered it under, if known (see register_alert_rules)."""
        return self._sensor_id_map.get(raw_sensor_id, raw_sensor_id)

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

    def register_alert_rules(self, stream_url: str, sensor_id: str, rules: list[dict]) -> list[str]:
        # RTVI-VLM's streams/add rejects non-UUID stream ids, so register
        # under a UUID and remember the mapping (see resolve_sensor_id) so
        # incoming alerts can be displayed under the original human-readable
        # sensor_id again.
        vss_sensor_id = str(uuid.uuid4())
        self._sensor_id_map[vss_sensor_id] = sensor_id
        rule_ids = []
        for rule in rules:
            response = self._request_with_retry(
                "POST",
                self.alert_bridge_base_url,
                "/api/v1/realtime",
                json={
                    "live_stream_url": stream_url,
                    "sensor_id": vss_sensor_id,
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

    def delete_all_alert_rules(self) -> int:
        """Delete every rule in VSS. Called on startup to clear orphaned rules from prior sessions."""
        response = self._request_with_retry(
            "GET", self.alert_bridge_base_url, "/api/v1/realtime"
        )
        rules = response.json().get("rules", [])
        for rule in rules:
            try:
                self._request_with_retry(
                    "DELETE", self.alert_bridge_base_url, f"/api/v1/realtime/{rule['id']}"
                )
            except Exception:
                pass
        return len(rules)

    def health_check(self) -> bool:
        try:
            self._request_with_retry("GET", self.agent_base_url, "/health")
            self._request_with_retry("GET", self.alert_bridge_base_url, "/health")
        except (httpx.TransportError, httpx.HTTPStatusError):
            return False
        return True
