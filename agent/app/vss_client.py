import time

import httpx


class VSSClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None, max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=10.0)
        self.max_retries = max_retries

    def _request_with_retry(self, method: str, path: str, **kwargs) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.request(method, f"{self.base_url}{path}", **kwargs)
                response.raise_for_status()
                return response
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt * 0.1)
        raise last_exc

    def get_new_alerts(self, since_cursor: str | None) -> list[dict]:
        params = {"since": since_cursor} if since_cursor else {}
        response = self._request_with_retry("GET", "/alerts", params=params)
        return response.json()["alerts"]

    def ask_video(self, question: str, clip_ref: str) -> str:
        response = self._request_with_retry(
            "POST", "/ask-video", json={"question": question, "clip_ref": clip_ref}
        )
        return response.json()["answer"]

    def query_analytics(self, query: str) -> dict:
        response = self._request_with_retry("POST", "/query-analytics", json={"query": query})
        return response.json()

    def search_archive(self, query: str) -> list[dict]:
        response = self._request_with_retry("POST", "/search-archive", json={"query": query})
        return response.json()["results"]

    def generate_report(self, incident_id: int) -> str:
        response = self._request_with_retry(
            "POST", "/generate-report", json={"incident_id": incident_id}
        )
        return response.json()["report_text"]

    def health_check(self) -> bool:
        try:
            self._request_with_retry("GET", "/health")
        except (httpx.TransportError, httpx.HTTPStatusError):
            return False
        return True
