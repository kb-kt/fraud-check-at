from __future__ import annotations

import hashlib
import unittest

from ai_agent_template.developer_kit.sdk.fraud_agent_sdk.contracts import ContractError, validate_v2_request
from ai_agent_template.developer_kit.sdk.fraud_agent_sdk.engine import FraudEngine
from ai_agent_template.developer_kit.sdk.fraud_agent_sdk.evaluation import evaluate_scenarios
from ai_agent_template.developer_kit.sdk.fraud_agent_sdk.gateway import ClaimsGatewayError, DocumentContent


def request_payload(**claim_overrides):
    claim = {
        "receipt_id": "RCT-1", "receipt_hash": "RH-1", "provider_id": "PROV-1",
        "claimed_amount": 1000, "claim_date": "2026-01-03", "treatment_start_date": "2026-01-01",
        "treatment_end_date": "2026-01-01", "diagnosis_code": "SYN-J10", "treatment_code": "TRT-1",
    }
    claim.update(claim_overrides)
    return {
        "schema_version": "2.0.0", "request_id": "REQ-TEST-0001", "claim_id": "CLM-1",
        "source_system": "synthetic_test_harness", "analysis_mode": "raw_evidence", "claim": claim,
        "insured_profile": {"insured_id": "INS-1"}, "document_refs": [],
        "inline_context": {"claim_history": {}, "document_metadata": [], "historical_document_fingerprints": []},
        "upstream_signals": {}, "options": {"include_evidence": True, "strict_schema": True},
    }


class FakeGateway:
    def __init__(self, docs=None, contents=None): self.docs, self.contents = docs or [], contents or {}
    def get_fraud_context(self, claim_id): return {"claim_history": {}, "document_metadata": self.docs, "historical_document_fingerprints": []}
    def list_documents(self, claim_id): return self.docs
    def get_document_content(self, document_id, expected_hash=""):
        content = self.contents[document_id]
        return DocumentContent(content, "application/pdf", hashlib.sha256(content).hexdigest())


class FailedGateway(FakeGateway):
    def get_fraud_context(self, claim_id): raise ClaimsGatewayError("CLAIMS_GATEWAY_UNAVAILABLE", "offline")


class V2FraudTests(unittest.TestCase):
    def test_contract_rejects_source_mode_and_label_leakage(self):
        payload = request_payload()
        payload["source_system"] = "unknown"
        payload["expected_fraud"] = True
        with self.assertRaises(ContractError) as caught:
            validate_v2_request(payload)
        self.assertIn("source_system is not supported", caught.exception.errors)
        self.assertTrue(any("label leakage" in error for error in caught.exception.errors))

    def test_history_behavior_provider_and_composite_scoring(self):
        payload = request_payload()
        payload["inline_context"]["claim_history"] = {
            "prior_receipt_hashes": ["RH-1"], "same_insured_provider_claims_30d": 3, "same_provider_claims_30d": 50,
        }
        result = FraudEngine(None).analyze(validate_v2_request(payload))
        self.assertTrue(result["fraud_suspected"])
        self.assertTrue(result["requires_human_review"])
        self.assertEqual(result["risk_score"], 100)
        self.assertIn("MULTIPLE_FRAUD_SIGNALS", result["fraud_reason_codes"])

    def test_pdf_amount_mismatch_generates_evidence(self):
        pdf = synthetic_pdf({"claimed_amount": 1431, "provider_id": "PROV-1", "receipt_id": "RCT-1", "treatment_start_date": "2026-01-01"})
        digest = hashlib.sha256(pdf).hexdigest()
        payload = request_payload()
        meta = {"document_id": "DOC-1", "document_type": "medical_receipt", "content_hash": digest, "mime_type": "application/pdf", "document_status": "available"}
        payload["document_refs"] = [meta]
        payload["inline_context"]["document_metadata"] = [meta]
        result = FraudEngine(FakeGateway([meta], {"DOC-1": pdf})).analyze(validate_v2_request(payload))
        self.assertIn("DOCUMENT_AMOUNT_MISMATCH", result["fraud_reason_codes"])
        self.assertTrue(any(item.get("field") == "claimed_amount" for item in result["evidence"]))

    def test_context_failure_is_failed_and_review_only(self):
        payload = request_payload()
        payload["inline_context"] = {}
        result = FraudEngine(FailedGateway()).analyze(validate_v2_request(payload))
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["fraud_suspected"])
        self.assertTrue(result["requires_human_review"])
        self.assertTrue(result["tool_failures"])

    def test_evaluation_reports_precision_and_recall(self):
        clean = request_payload()
        duplicate = request_payload()
        duplicate["request_id"] = "REQ-TEST-0002"
        duplicate["inline_context"]["claim_history"] = {"prior_receipt_ids": ["RCT-1"]}
        engine = FraudEngine(None)
        metrics = evaluate_scenarios([
            {"request": clean, "expected_fraud_suspected": False},
            {"request": duplicate, "expected_fraud_suspected": True},
        ], lambda value: engine.analyze(validate_v2_request(value)))
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["routing_invariant_violations"], 0)


def synthetic_pdf(fields):
    lines = ["SYNTHETIC TEST DOCUMENT", "DOCUMENT_TITLE: receipt", "RENDER_MODE: text"] + [f"{key}: {value}" for key, value in fields.items()]
    commands = ["BT", "/F1 9 Tf", "50 790 Td"]
    for index, line in enumerate(lines):
        if index: commands.append("0 -14 Td")
        commands.append(f"({line}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>", b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    chunks, offsets = [b"%PDF-1.4\n"], []
    for index, body in enumerate(objects, 1):
        offsets.append(sum(map(len, chunks))); chunks += [f"{index} 0 obj\n".encode(), body, b"\nendobj\n"]
    xref = sum(map(len, chunks)); chunks += [f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode()]
    chunks += [b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets), f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()]
    return b"".join(chunks)


if __name__ == "__main__": unittest.main()
