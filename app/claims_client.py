from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ClaimsServiceError(RuntimeError):
    pass


class ClaimsClient:
    def __init__(self, base_url: str, timeout_seconds: float, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def run_review(self, claim: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/reviews", {"claim": claim})

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
                if not isinstance(result, dict):
                    raise ClaimsServiceError("Claims service returned a non-object response")
                return result
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ClaimsServiceError(f"Claims service HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ClaimsServiceError(f"Claims service unavailable: {exc}") from exc

