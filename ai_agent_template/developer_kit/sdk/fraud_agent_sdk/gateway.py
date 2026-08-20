from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class ClaimsGatewayError(RuntimeError):
    def __init__(self, code: str, message: str, *, recoverable: bool = False):
        self.code = code
        self.recoverable = recoverable
        super().__init__(message)


@dataclass(frozen=True)
class DocumentContent:
    content: bytes
    mime_type: str
    content_hash: str


class ClaimsGateway(Protocol):
    def get_fraud_context(self, claim_id: str) -> dict[str, Any]: ...
    def list_documents(self, claim_id: str) -> list[dict[str, Any]]: ...
    def get_document_content(self, document_id: str, expected_hash: str = "") -> DocumentContent: ...


class HttpClaimsGateway:
    def __init__(self, base_url: str, api_key: str | None, timeout_seconds: float = 5.0, max_document_bytes: int = 10_000_000):
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("Claims Gateway base URL must use HTTP(S)")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_document_bytes = max_document_bytes

    def get_fraud_context(self, claim_id: str) -> dict[str, Any]:
        return self._get_json(f"/internal/v1/fraud-context/claims/{quote(claim_id, safe='')}")

    def list_documents(self, claim_id: str) -> list[dict[str, Any]]:
        result = self._get_json(f"/internal/v1/claims/{quote(claim_id, safe='')}/documents")
        documents = result.get("documents")
        if not isinstance(documents, list):
            raise ClaimsGatewayError("INVALID_CONTEXT_RESPONSE", "documents must be an array")
        return [item for item in documents if isinstance(item, dict)]

    def get_document_content(self, document_id: str, expected_hash: str = "") -> DocumentContent:
        request = self._request(f"/internal/v1/documents/{quote(document_id, safe='')}/content")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                length = int(response.headers.get("Content-Length") or 0)
                if length > self.max_document_bytes:
                    raise ClaimsGatewayError("DOCUMENT_TOO_LARGE", "Document exceeds configured size limit", recoverable=True)
                content = response.read(self.max_document_bytes + 1)
                if len(content) > self.max_document_bytes:
                    raise ClaimsGatewayError("DOCUMENT_TOO_LARGE", "Document exceeds configured size limit", recoverable=True)
                mime_type = response.headers.get_content_type()
                if mime_type != "application/pdf":
                    raise ClaimsGatewayError("UNSUPPORTED_DOCUMENT_TYPE", f"Unsupported MIME type: {mime_type}", recoverable=True)
                actual_hash = hashlib.sha256(content).hexdigest()
                header_hash = response.headers.get("X-Content-Hash", "")
                trusted_hash = expected_hash or header_hash
                if trusted_hash and actual_hash != trusted_hash:
                    raise ClaimsGatewayError("DOCUMENT_HASH_MISMATCH", "Downloaded document hash does not match metadata", recoverable=True)
                return DocumentContent(content, mime_type, actual_hash)
        except ClaimsGatewayError:
            raise
        except HTTPError as exc:
            raise self._http_error(exc, recoverable=exc.code in {404, 409, 413, 422}) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ClaimsGatewayError("CLAIMS_GATEWAY_UNAVAILABLE", str(exc)) from exc

    def _get_json(self, path: str) -> dict[str, Any]:
        try:
            with urlopen(self._request(path), timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
                if not isinstance(result, dict):
                    raise ClaimsGatewayError("INVALID_CONTEXT_RESPONSE", "Claims Gateway response must be an object")
                return result
        except ClaimsGatewayError:
            raise
        except HTTPError as exc:
            raise self._http_error(exc) from exc
        except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ClaimsGatewayError("CLAIMS_GATEWAY_UNAVAILABLE", str(exc)) from exc

    def _request(self, path: str) -> Request:
        headers = {"Accept": "application/json, application/pdf"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return Request(self.base_url + path, headers=headers, method="GET")

    @staticmethod
    def _http_error(exc: HTTPError, recoverable: bool = False) -> ClaimsGatewayError:
        code = {401: "CLAIMS_AUTH_REQUIRED", 403: "CLAIMS_AUTH_FORBIDDEN", 404: "CLAIMS_RESOURCE_NOT_FOUND"}.get(exc.code, "CLAIMS_GATEWAY_HTTP_ERROR")
        return ClaimsGatewayError(code, f"Claims Gateway returned HTTP {exc.code}", recoverable=recoverable)
