"""Drop-in plugin for Automated_Claims_Processing.

Register this class as `fraud_signal_checker` in that project's plugins.yaml.
The response envelope exactly follows its ToolPlugin contract.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class RemoteFraudSignalCheckerPlugin:
    name = "fraud_signal_checker"
    version = "1.0.0"
    contract_name = "fraud_signal_checker"
    contract_version = "1.0.0"
    owner = "fraud-check"
    timeout_ms = 3000
    failure_policy = "human_review"

    def __init__(self, service_url: str | None = None):
        self.service_url = (
            service_url
            or os.getenv("FRAUD_CHECK_URL")
            or "http://127.0.0.1:8010"
        ).rstrip("/")

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        request = Request(
            self.service_url + "/v1/fraud/check",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_ms / 1000) as response:
                result = json.loads(response.read().decode("utf-8"))
            required = {"fraud_suspected", "fraud_reason_codes"}
            if not isinstance(result, dict) or not required.issubset(result):
                return self._failure(
                    "INVALID_REMOTE_RESPONSE", "Fraud service response violates the contract", started
                )
            return self._success(result, started)
        except HTTPError as exc:
            return self._failure("REMOTE_HTTP_ERROR", f"HTTP {exc.code}", started)
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            return self._failure("REMOTE_UNAVAILABLE", str(exc), started, retryable=True)

    def _success(self, result: dict[str, Any], started: float) -> dict[str, Any]:
        return {
            "tool_name": self.name,
            "plugin_version": self.version,
            "status": "success",
            "result": result,
            "error": None,
            "duration_ms": self._duration(started),
            "metadata": {
                "contract_version": self.contract_version,
                "service_url": self.service_url,
            },
        }

    def _failure(
        self,
        code: str,
        message: str,
        started: float,
        retryable: bool = False,
    ) -> dict[str, Any]:
        return {
            "tool_name": self.name,
            "plugin_version": self.version,
            "status": "failed",
            "result": None,
            "error": {"error_code": code, "message": message, "retryable": retryable},
            "duration_ms": self._duration(started),
            "metadata": {
                "contract_version": self.contract_version,
                "failure_policy": self.failure_policy,
            },
        }

    @staticmethod
    def _duration(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

