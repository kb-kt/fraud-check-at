from __future__ import annotations

import unittest

from app.orchestrator import process_claim


class FakeClient:
    def run_review(self, claim):
        return {
            "claim_id": claim["claim_id"],
            "review_status": "completed",
            "output": {
                "requires_human_review": False,
                "reason_codes": ["COVERED"],
            },
        }


class OrchestratorTests(unittest.TestCase):
    def test_fraud_overrides_routing_but_never_auto_denies(self):
        claim = {
            "claim_id": "CLM-1",
            "claim": {"receipt_id": "R-1", "receipt_hash": "H-1"},
            "claim_history": {
                "prior_receipt_ids": ["R-1"],
                "prior_receipt_hashes": [],
            },
            "signals": {},
            "insured_profile": {"insured_id": "I-1"},
        }
        result = process_claim(claim, FakeClient())
        self.assertEqual("human_review", result["final_routing"])
        self.assertFalse(result["safety"]["automatic_denial_allowed"])


if __name__ == "__main__":
    unittest.main()

