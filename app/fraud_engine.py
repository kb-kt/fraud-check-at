from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Rule:
    code: str
    weight: int


def check_fraud(payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the claims project's fraud_signal_checker contract.

    The decision is deterministic and explainable. A score at or above 50 is
    routed to human review; it is never treated as an automatic denial.
    """
    claim = _mapping(payload.get("claim"))
    history = _mapping(payload.get("claim_history"))
    signals = _mapping(payload.get("signals"))
    insured_profile = _mapping(payload.get("insured_profile"))

    matched: list[Rule] = []
    receipt_id = claim.get("receipt_id")
    receipt_hash = claim.get("receipt_hash")
    prior_ids = set(history.get("prior_receipt_ids") or [])
    prior_hashes = set(history.get("prior_receipt_hashes") or [])

    if (
        signals.get("suspected_duplicate_receipt") is True
        or (receipt_id and receipt_id in prior_ids)
        or (receipt_hash and receipt_hash in prior_hashes)
    ):
        matched.append(Rule("DUPLICATE_RECEIPT_SUSPECTED", 70))
    if signals.get("fraudulent_document") is True:
        matched.append(Rule("FRAUD_SIGNAL", 80))
    if signals.get("document_claim_mismatch") is True:
        matched.append(Rule("DOCUMENT_CLAIM_MISMATCH", 45))
    if signals.get("abnormal_document_dates") is True:
        matched.append(Rule("ABNORMAL_DOCUMENT_DATES", 45))
    if _as_int(history.get("same_insured_provider_claims_30d")) >= 3 and insured_profile.get(
        "insured_id"
    ):
        matched.append(Rule("SAME_INSURED_PROVIDER_REPEAT_SUSPECTED", 50))
    if _as_int(history.get("same_provider_claims_30d")) >= 50 and claim.get("provider_id"):
        matched.append(Rule("PROVIDER_PATTERN_ANOMALY_SUSPECTED", 60))

    reason_codes = list(dict.fromkeys(rule.code for rule in matched))
    risk_score = min(100, sum(rule.weight for rule in matched))
    fraud_suspected = risk_score >= 50
    return {
        "fraud_suspected": fraud_suspected,
        "fraud_reason_codes": reason_codes,
        "risk_score": risk_score,
        "routing": "human_review" if fraud_suspected else "continue_claim_review",
        "engine_version": "1.0.0",
    }


def validate_contract_payload(payload: dict[str, Any]) -> list[str]:
    errors = []
    for field in ("claim", "claim_history", "signals", "insured_profile"):
        if not isinstance(payload.get(field), dict):
            errors.append(f"{field} must be an object")
    return errors


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

