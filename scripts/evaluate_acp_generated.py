from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_agent_template.developer_kit.sdk.fraud_agent_sdk.contracts import validate_v2_request
from ai_agent_template.developer_kit.sdk.fraud_agent_sdk.engine import FraudEngine
from ai_agent_template.developer_kit.sdk.fraud_agent_sdk.evaluation import evaluate_scenarios
from ai_agent_template.developer_kit.sdk.fraud_agent_sdk.gateway import DocumentContent


PUBLIC_FIELDS = {"document_id", "claim_id", "document_type", "content_hash", "text_fingerprint", "perceptual_hash", "mime_type", "file_size", "page_count", "document_status", "receipt_id", "provider_id", "insured_id", "issued_at", "render_mode", "readable"}


class FileGateway:
    def __init__(self, root: Path, metadata: dict[str, dict[str, Any]]): self.root, self.metadata = root, metadata
    def get_fraud_context(self, claim_id): raise RuntimeError("inline context is required by evaluation harness")
    def list_documents(self, claim_id): return []
    def get_document_content(self, document_id, expected_hash=""):
        meta = self.metadata[document_id]
        content = (self.root / meta["file_path"]).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if expected_hash and digest != expected_hash: raise ValueError("fixture content hash mismatch")
        return DocumentContent(content, "application/pdf", digest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Fraud Check using ACP generated artifacts without leaking labels into inference.")
    parser.add_argument("generated_dir", type=Path)
    args = parser.parse_args()
    root = args.generated_dir.resolve()
    claims = {row["claim_id"]: row for row in read_jsonl(root / "claims_eval.jsonl")}
    labels = list(read_jsonl(root / "fraud_labels_eval.jsonl"))
    metadata = list(read_jsonl(root / "document_metadata_eval.jsonl"))
    by_claim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_id = {}
    for item in metadata:
        by_id[item["document_id"]] = item
        by_claim[item["claim_id"]].append({key: value for key, value in item.items() if key in PUBLIC_FIELDS})
    engine = FraudEngine(FileGateway(root, by_id))
    records = []
    for index, label in enumerate(labels, 1):
        row = claims[label["claim_id"]]
        documents = by_claim[row["claim_id"]]
        history = row.get("claim_history") or {}
        historical = [{"claim_id": "historical", "document_id": f"history:{i}", "receipt_id": value} for i, value in enumerate(history.get("prior_receipt_ids") or [])]
        request = {
            "schema_version": "2.0.0", "request_id": f"REQ-EVAL-{index:06d}", "claim_id": row["claim_id"],
            "source_system": "synthetic_test_harness", "analysis_mode": "upstream_signal_assisted",
            "claim": row["claim"], "insured_profile": row["insured_profile"],
            "document_refs": [{key: doc.get(key) for key in ("document_id", "document_type", "content_hash", "mime_type")} for doc in documents],
            "inline_context": {"claim_history": history, "document_metadata": documents, "historical_document_fingerprints": historical},
            "upstream_signals": provenanced_signals(row.get("signals") or {}),
            "options": {"include_evidence": True, "include_tool_trace": False, "strict_schema": True},
        }
        records.append({"request": request, "expected_fraud_suspected": label["fraud_suspected"]})
    metrics = evaluate_scenarios(records, lambda value: engine.analyze(validate_v2_request(value)))
    print(json.dumps({key: value for key, value in metrics.items() if key != "results"}, ensure_ascii=False, indent=2))


def provenanced_signals(signals: dict[str, Any]) -> dict[str, Any]:
    return {key: {"value": value, "source": "acp_generated_claim", "observed_at": "evaluation"} for key, value in signals.items() if key in {"suspected_duplicate_receipt", "fraudulent_document"}}


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip(): yield json.loads(line)


if __name__ == "__main__": main()
