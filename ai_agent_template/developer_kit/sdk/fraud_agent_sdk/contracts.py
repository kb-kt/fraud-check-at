from __future__ import annotations

import re
from typing import Any


SCHEMA_VERSION = "2.0.0"
SOURCE_SYSTEMS = {
    "automated_claims_processing_template",
    "automated_claims_processing_mvp",
    "synthetic_test_harness",
}
ANALYSIS_MODES = {"raw_evidence", "upstream_signal_assisted"}
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{5,127}$")
FORBIDDEN_LABEL_FIELDS = {"expected_fraud", "fraud_label", "is_fraud", "ground_truth", "label"}
TOP_LEVEL_FIELDS = {"schema_version", "request_id", "claim_id", "source_system", "analysis_mode", "claim", "insured_profile", "document_refs", "inline_context", "upstream_signals", "options"}


class ContractError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_v2_request(payload: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        raise ContractError(["request body must be an object"])
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must equal {SCHEMA_VERSION}")
    unknown = sorted(set(payload) - TOP_LEVEL_FIELDS)
    if unknown:
        errors.append("unknown top-level fields: " + ", ".join(unknown))
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_PATTERN.fullmatch(request_id):
        errors.append("request_id must be 6-128 safe identifier characters")
    claim_id = payload.get("claim_id")
    if not isinstance(claim_id, str) or not claim_id.strip():
        errors.append("claim_id is required")
    if payload.get("source_system") not in SOURCE_SYSTEMS:
        errors.append("source_system is not supported")
    if payload.get("analysis_mode") not in ANALYSIS_MODES:
        errors.append("analysis_mode is not supported")
    for field in ("claim", "insured_profile", "inline_context", "upstream_signals", "options"):
        if not isinstance(payload.get(field), dict):
            errors.append(f"{field} must be an object")
    if not isinstance(payload.get("document_refs"), list):
        errors.append("document_refs must be an array")
    claim = payload.get("claim") if isinstance(payload.get("claim"), dict) else {}
    if claim.get("claim_id") not in (None, claim_id):
        errors.append("claim.claim_id must match claim_id")
    if payload.get("analysis_mode") == "raw_evidence" and payload.get("upstream_signals"):
        errors.append("upstream_signals must be empty in raw_evidence mode")
    leaked = sorted(_find_forbidden_fields(payload))
    if leaked:
        errors.append("label leakage fields are forbidden: " + ", ".join(leaked))
    if errors:
        raise ContractError(errors)
    return payload


def _find_forbidden_fields(value: Any, prefix: str = "") -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if key.lower() in FORBIDDEN_LABEL_FIELDS:
                found.add(path)
            found.update(_find_forbidden_fields(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.update(_find_forbidden_fields(item, f"{prefix}[{index}]"))
    return found
