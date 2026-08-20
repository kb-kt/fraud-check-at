from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    claims_service_url: str = "http://127.0.0.1:8000"
    request_timeout_seconds: float = 5.0
    api_key: str | None = None
    fraud_check_api_key: str | None = None
    claims_internal_api_key: str | None = None
    claims_template_base_url: str | None = None
    claims_mvp_base_url: str | None = None
    max_document_bytes: int = 10_000_000
    max_pdf_pages: int = 30
    fraud_threshold: int = 50

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            claims_service_url=os.getenv(
                "CLAIMS_SERVICE_URL", "http://127.0.0.1:8000"
            ).rstrip("/"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5")),
            api_key=os.getenv("CLAIMS_SERVICE_API_KEY") or None,
            fraud_check_api_key=os.getenv("FRAUD_CHECK_API_KEY") or None,
            claims_internal_api_key=os.getenv("CLAIMS_INTERNAL_API_KEY") or None,
            claims_template_base_url=(os.getenv("CLAIMS_TEMPLATE_BASE_URL") or os.getenv("CLAIMS_INTERNAL_BASE_URL") or "").rstrip("/") or None,
            claims_mvp_base_url=(os.getenv("CLAIMS_MVP_BASE_URL") or os.getenv("CLAIMS_INTERNAL_BASE_URL") or "").rstrip("/") or None,
            max_document_bytes=int(os.getenv("MAX_DOCUMENT_BYTES", "10000000")),
            max_pdf_pages=int(os.getenv("MAX_PDF_PAGES", "30")),
            fraud_threshold=int(os.getenv("FRAUD_THRESHOLD", "50")),
        )
