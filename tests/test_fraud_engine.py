from __future__ import annotations

import unittest

from app.fraud_engine import check_fraud, validate_contract_payload


def payload() -> dict:
    return {
        "claim": {
            "receipt_id": "RCT-1",
            "receipt_hash": "HASH-1",
            "provider_id": "PROV-1",
        },
        "claim_history": {
            "prior_receipt_ids": [],
            "prior_receipt_hashes": [],
            "same_insured_provider_claims_30d": 0,
            "same_provider_claims_30d": 0,
        },
        "signals": {},
        "insured_profile": {"insured_id": "INS-1"},
    }


class FraudEngineTests(unittest.TestCase):
    def test_clean_claim_continues(self):
        result = check_fraud(payload())
        self.assertFalse(result["fraud_suspected"])
        self.assertEqual("continue_claim_review", result["routing"])

    def test_duplicate_hash_routes_to_human(self):
        value = payload()
        value["claim_history"]["prior_receipt_hashes"] = ["HASH-1"]
        result = check_fraud(value)
        self.assertTrue(result["fraud_suspected"])
        self.assertIn("DUPLICATE_RECEIPT_SUSPECTED", result["fraud_reason_codes"])
        self.assertEqual("human_review", result["routing"])

    def test_repeated_provider_is_flagged(self):
        value = payload()
        value["claim_history"]["same_insured_provider_claims_30d"] = 3
        result = check_fraud(value)
        self.assertTrue(result["fraud_suspected"])

    def test_contract_requires_four_objects(self):
        self.assertEqual(4, len(validate_contract_payload({})))


if __name__ == "__main__":
    unittest.main()

