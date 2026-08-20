from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Any

try:
    from fastapi import FastAPI, HTTPException, Request
except ModuleNotFoundError:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]

from .claims_client import ClaimsClient, ClaimsServiceError
from .config import Settings
from .fraud_engine import check_fraud, validate_contract_payload
from .orchestrator import process_claim
from ai_agent_template.developer_kit.sdk.fraud_agent_sdk import (
    ContractError,
    FraudEngine,
    HttpClaimsGateway,
    validate_v2_request,
)


GatewayFactory = Callable[[str], Any]


def create_app(settings: Settings | None = None, gateway_factory: GatewayFactory | None = None):
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Run: pip install -r requirements.txt")

    resolved = settings or Settings.load()
    client = ClaimsClient(
        resolved.claims_service_url,
        resolved.request_timeout_seconds,
        resolved.api_key,
    )
    app = FastAPI(title="Fraud Check Agent", version="2.0.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "fraud-check", "version": "2.0.0"}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        try:
            claims_health = client.health()
            return {"status": "ready", "claims_service": claims_health}
        except ClaimsServiceError as exc:
            return {"status": "degraded", "claims_service_error": str(exc)}

    @app.post("/v1/fraud/check")
    def fraud_check(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        _authorize(request, resolved.fraud_check_api_key)
        errors = validate_contract_payload(payload)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        return check_fraud(payload)

    @app.post("/v2/fraud/check")
    def fraud_check_v2(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        _authorize(request, resolved.fraud_check_api_key)
        try:
            valid = validate_v2_request(payload)
        except ContractError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_V2_CONTRACT", "errors": exc.errors}) from exc
        source_system = valid["source_system"]
        if gateway_factory is not None:
            gateway = gateway_factory(source_system)
        else:
            base_url = (
                resolved.claims_template_base_url
                if source_system == "automated_claims_processing_template"
                else resolved.claims_mvp_base_url
                if source_system == "automated_claims_processing_mvp"
                else None
            )
            gateway = HttpClaimsGateway(
                base_url,
                resolved.claims_internal_api_key,
                resolved.request_timeout_seconds,
                resolved.max_document_bytes,
            ) if base_url else None
        return FraudEngine(gateway, fraud_threshold=resolved.fraud_threshold, max_pdf_pages=resolved.max_pdf_pages).analyze(valid)

    @app.post("/v1/agent/process")
    def agent_process(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        _authorize(request, resolved.fraud_check_api_key)
        claim = payload.get("claim") if isinstance(payload.get("claim"), dict) else payload
        if not claim.get("claim_id"):
            raise HTTPException(status_code=422, detail="claim.claim_id is required")
        try:
            return process_claim(claim, client)
        except ClaimsServiceError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "CLAIMS_SERVICE_UNAVAILABLE",
                    "message": str(exc),
                    "routing": "human_review",
                },
            ) from exc

    return app


def _authorize(request: Request, expected: str | None) -> None:
    if not expected:
        return
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Bearer authorization is required."})
    if not hmac.compare_digest(authorization[7:], expected):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Invalid Fraud Check API key."})


app = create_app() if FastAPI is not None else None
