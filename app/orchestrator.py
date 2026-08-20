from __future__ import annotations

from typing import Any

from .claims_client import ClaimsClient
from .fraud_engine import check_fraud


def process_claim(claim: dict[str, Any], client: ClaimsClient) -> dict[str, Any]:
    fraud_input = {
        "claim": claim.get("claim", {}),
        "claim_history": claim.get("claim_history", {}),
        "signals": claim.get("signals", {}),
        "insured_profile": claim.get("insured_profile", {}),
    }
    fraud = check_fraud(fraud_input)
    claims_review = client.run_review(claim)
    upstream_output = claims_review.get("output", {})

    if fraud["fraud_suspected"]:
        final_routing = "human_review"
        reasons = list(
            dict.fromkeys(
                list(upstream_output.get("reason_codes", []))
                + list(fraud["fraud_reason_codes"])
            )
        )
    else:
        final_routing = (
            "human_review"
            if upstream_output.get("requires_human_review")
            else "claims_recommendation"
        )
        reasons = list(upstream_output.get("reason_codes", []))

    return {
        "claim_id": claim.get("claim_id"),
        "status": "completed",
        "final_routing": final_routing,
        "reason_codes": reasons,
        "fraud_check": fraud,
        "claims_review": claims_review,
        "safety": {
            "automatic_denial_allowed": False,
            "fraud_suspicion_requires_human_review": True,
        },
    }

