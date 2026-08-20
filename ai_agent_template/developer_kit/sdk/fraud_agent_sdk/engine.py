from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .documents import DocumentPipeline, ExtractionResult, compare_fields, similarity
from .gateway import ClaimsGateway, ClaimsGatewayError, DocumentContent


WEIGHTS = {
    "DUPLICATE_RECEIPT_SUSPECTED": 70,
    "ALTERED_DUPLICATE_RECEIPT_SUSPECTED": 65,
    "FRAUDULENT_DOCUMENT_SUSPECTED": 80,
    "DOCUMENT_AMOUNT_MISMATCH": 70,
    "DOCUMENT_DATE_MISMATCH": 70,
    "DOCUMENT_PROVIDER_MISMATCH": 70,
    "DOCUMENT_IDENTITY_MISMATCH": 70,
    "SAME_INSURED_PROVIDER_REPEAT_SUSPECTED": 50,
    "PROVIDER_PATTERN_ANOMALY_SUSPECTED": 60,
    "MULTIPLE_FRAUD_SIGNALS": 15,
}
REVIEW_ONLY_CODES = {"DOCUMENT_UNAVAILABLE", "DOCUMENT_EXTRACTION_INCOMPLETE", "CLAIMS_CONTEXT_INCOMPLETE"}


@dataclass
class Finding:
    code: str
    category: str
    message: str
    evidence: list[dict[str, Any]] = field(default_factory=list)


class FraudEngine:
    def __init__(self, gateway: ClaimsGateway | None, *, fraud_threshold: int = 50, max_pdf_pages: int = 30):
        self.gateway = gateway
        self.fraud_threshold = fraud_threshold
        self.documents = DocumentPipeline(max_pages=max_pdf_pages)

    def analyze(self, request: dict[str, Any]) -> dict[str, Any]:
        claim = request["claim"]
        inline = request["inline_context"]
        warnings: list[dict[str, Any]] = []
        tool_failures: list[dict[str, Any]] = []
        findings: list[Finding] = []

        context = dict(inline)
        if _context_needs_fetch(request, context) and self.gateway is not None:
            try:
                remote_context = self.gateway.get_fraud_context(request["claim_id"])
                context = {**remote_context, **{k: v for k, v in context.items() if v}}
            except ClaimsGatewayError as exc:
                return self._failed_response(request, exc.code, str(exc))
        history = _mapping(context.get("claim_history"))
        metadata = _documents(request, context)
        historical = [item for item in context.get("historical_document_fingerprints", []) if isinstance(item, dict)]

        self._history_findings(claim, request["insured_profile"], history, findings)
        self._upstream_findings(request, findings)
        self._metadata_duplicate_findings(claim, history, metadata, historical, findings)

        extracted: list[tuple[dict[str, Any], ExtractionResult]] = []
        for meta in metadata:
            document_id = str(meta.get("document_id") or "")
            status = str(meta.get("document_status") or "available")
            if status in {"missing", "corrupted", "password_protected"}:
                warnings.append(_warning("DOCUMENT_UNAVAILABLE", f"{document_id}: {status}", document_id))
                continue
            if self.gateway is None:
                warnings.append(_warning("DOCUMENT_UNAVAILABLE", f"{document_id}: Claims Gateway is not configured", document_id))
                continue
            try:
                content = self.gateway.get_document_content(document_id, str(meta.get("content_hash") or ""))
                result = self.documents.extract(content.content)
                extracted.append((meta, result))
                for warning in result.warnings:
                    warnings.append(_warning("DOCUMENT_EXTRACTION_INCOMPLETE", warning, document_id))
                self._document_findings(claim, meta, result, historical, findings)
            except (ClaimsGatewayError, ValueError) as exc:
                code = exc.code if isinstance(exc, ClaimsGatewayError) else "DOCUMENT_EXTRACTION_INCOMPLETE"
                warnings.append(_warning(code, str(exc), document_id))

        findings = _deduplicate_findings(findings)
        fraud_codes = [finding.code for finding in findings if finding.code not in REVIEW_ONLY_CODES]
        if len(set(fraud_codes)) >= 2:
            findings.append(Finding("MULTIPLE_FRAUD_SIGNALS", "composite", "Two or more independent fraud signals were combined."))
        reason_codes = list(dict.fromkeys(finding.code for finding in findings))
        risk_score = min(100, sum(WEIGHTS.get(code, 0) for code in reason_codes))
        fraud_suspected = bool(fraud_codes) and risk_score >= self.fraud_threshold
        requires_review = fraud_suspected or bool(warnings) or bool(tool_failures)
        evidence = [item for finding in findings for item in finding.evidence]
        return {
            "schema_version": "2.0.0",
            "request_id": request["request_id"],
            "claim_id": request["claim_id"],
            "status": "completed",
            "fraud_suspected": fraud_suspected,
            "fraud_reason_codes": reason_codes,
            "risk_score": risk_score,
            "routing": "human_review" if requires_review else "continue_claim_review",
            "requires_human_review": requires_review,
            "engine_version": "2.0.0",
            "workflow_version": "1.0.0",
            "findings": [_finding_dict(item) for item in findings],
            "evidence": evidence if request["options"].get("include_evidence", True) else [],
            "analysis_warnings": warnings,
            "tool_failures": tool_failures,
            "review_summary": _review_summary(fraud_suspected, reason_codes, warnings),
        }

    def _history_findings(self, claim: dict[str, Any], insured: dict[str, Any], history: dict[str, Any], findings: list[Finding]) -> None:
        receipt_id, receipt_hash = claim.get("receipt_id"), claim.get("receipt_hash")
        if (receipt_id and receipt_id in set(history.get("prior_receipt_ids") or [])) or (receipt_hash and receipt_hash in set(history.get("prior_receipt_hashes") or [])):
            findings.append(Finding("DUPLICATE_RECEIPT_SUSPECTED", "duplicate", "Receipt identifier or hash matches prior claim history.", [{"type": "claim_history", "receipt_id": receipt_id, "receipt_hash": receipt_hash}]))
        if insured.get("insured_id") and _integer(history.get("same_insured_provider_claims_30d")) >= 3:
            findings.append(Finding("SAME_INSURED_PROVIDER_REPEAT_SUSPECTED", "behavior", "Same insured/provider pair has at least 3 claims in 30 days.", [{"type": "aggregate", "metric": "same_insured_provider_claims_30d", "value": _integer(history.get("same_insured_provider_claims_30d")), "threshold": 3}]))
        if claim.get("provider_id") and _integer(history.get("same_provider_claims_30d")) >= 50:
            findings.append(Finding("PROVIDER_PATTERN_ANOMALY_SUSPECTED", "provider", "Provider has at least 50 claims in 30 days.", [{"type": "aggregate", "metric": "same_provider_claims_30d", "value": _integer(history.get("same_provider_claims_30d")), "threshold": 50}]))

    def _upstream_findings(self, request: dict[str, Any], findings: list[Finding]) -> None:
        if request["analysis_mode"] != "upstream_signal_assisted":
            return
        signals = request.get("upstream_signals") or {}
        for name, code in (("suspected_duplicate_receipt", "DUPLICATE_RECEIPT_SUSPECTED"), ("fraudulent_document", "FRAUDULENT_DOCUMENT_SUSPECTED")):
            item = signals.get(name)
            value = item.get("value") if isinstance(item, dict) else item
            if value is True:
                findings.append(Finding(code, "upstream_signal", f"Provenanced upstream signal {name} is true.", [{"type": "upstream_signal", "name": name, "provenance": item if isinstance(item, dict) else {}}]))

    def _metadata_duplicate_findings(self, claim: dict[str, Any], history: dict[str, Any], current: list[dict[str, Any]], historical: list[dict[str, Any]], findings: list[Finding]) -> None:
        for meta in current:
            for prior in historical:
                if meta.get("document_id") == prior.get("document_id"):
                    continue
                if meta.get("content_hash") and meta.get("content_hash") == prior.get("content_hash"):
                    findings.append(Finding("DUPLICATE_RECEIPT_SUSPECTED", "duplicate", "Document content hash exactly matches historical evidence.", [_pair_evidence(meta, prior, "content_hash", 1.0)]))
                elif meta.get("text_fingerprint") and meta.get("text_fingerprint") == prior.get("text_fingerprint"):
                    findings.append(Finding("ALTERED_DUPLICATE_RECEIPT_SUSPECTED", "duplicate", "Text fingerprint matches historical evidence while binary content differs.", [_pair_evidence(meta, prior, "text_fingerprint", 1.0)]))
                elif similarity(str(meta.get("perceptual_hash") or ""), str(prior.get("perceptual_hash") or "")) >= 0.90:
                    findings.append(Finding("ALTERED_DUPLICATE_RECEIPT_SUSPECTED", "duplicate", "Perceptual fingerprint is highly similar to historical evidence.", [_pair_evidence(meta, prior, "perceptual_hash", similarity(str(meta.get("perceptual_hash")), str(prior.get("perceptual_hash"))))]))

    def _document_findings(self, claim: dict[str, Any], meta: dict[str, Any], result: ExtractionResult, historical: list[dict[str, Any]], findings: list[Finding]) -> None:
        mismatches = compare_fields(claim, result.fields)
        groups = {
            "claimed_amount": "DOCUMENT_AMOUNT_MISMATCH",
            "provider_id": "DOCUMENT_PROVIDER_MISMATCH",
            "receipt_id": "DOCUMENT_IDENTITY_MISMATCH",
            "treatment_start_date": "DOCUMENT_DATE_MISMATCH",
            "treatment_end_date": "DOCUMENT_DATE_MISMATCH",
        }
        for mismatch in mismatches:
            code = groups.get(mismatch["field"])
            if code:
                findings.append(Finding(code, "document_mismatch", f"Claim and document differ for {mismatch['field']}.", [{"type": "document_field", "document_id": meta.get("document_id"), "extraction_method": result.method, **mismatch}]))
        for prior in historical:
            if result.text_fingerprint and result.text_fingerprint == prior.get("text_fingerprint") and meta.get("content_hash") != prior.get("content_hash"):
                findings.append(Finding("ALTERED_DUPLICATE_RECEIPT_SUSPECTED", "duplicate", "Extracted text fingerprint matches a historical document.", [_pair_evidence(meta, prior, "extracted_text_fingerprint", 1.0)]))

    @staticmethod
    def _failed_response(request: dict[str, Any], code: str, message: str) -> dict[str, Any]:
        return {
            "schema_version": "2.0.0", "request_id": request["request_id"], "claim_id": request["claim_id"],
            "status": "failed", "fraud_suspected": False, "fraud_reason_codes": ["CLAIMS_CONTEXT_INCOMPLETE"],
            "risk_score": 0, "routing": "human_review", "requires_human_review": True,
            "engine_version": "2.0.0", "workflow_version": "1.0.0", "findings": [], "evidence": [],
            "analysis_warnings": [], "tool_failures": [{"tool": "claims_gateway", "code": code, "message": message}],
            "review_summary": "Fraud context could not be loaded; manual review is required.",
        }


def _context_needs_fetch(request: dict[str, Any], context: dict[str, Any]) -> bool:
    required_types_ok = isinstance(context.get("claim_history"), dict) and isinstance(context.get("document_metadata"), list) and isinstance(context.get("historical_document_fingerprints"), list)
    no_document_context = not context.get("document_metadata") and not request.get("document_refs")
    return not required_types_ok or no_document_context


def _documents(request: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = [item for item in context.get("document_metadata", []) if isinstance(item, dict)]
    by_id = {str(item.get("document_id")): dict(item) for item in metadata}
    for ref in request.get("document_refs", []):
        if isinstance(ref, dict) and ref.get("document_id"):
            by_id.setdefault(str(ref["document_id"]), dict(ref))
    return list(by_id.values())


def _mapping(value: Any) -> dict[str, Any]: return value if isinstance(value, dict) else {}
def _integer(value: Any) -> int:
    try: return int(value)
    except (TypeError, ValueError): return 0
def _warning(code: str, message: str, document_id: str) -> dict[str, Any]: return {"code": code, "message": message, "document_id": document_id, "requires_human_review": True}
def _pair_evidence(current: dict[str, Any], prior: dict[str, Any], method: str, score: float) -> dict[str, Any]: return {"type": "document_pair", "document_id": current.get("document_id"), "reference_document_id": prior.get("document_id"), "reference_claim_id": prior.get("claim_id"), "comparison_method": method, "similarity": round(score, 4)}
def _finding_dict(item: Finding) -> dict[str, Any]: return {"reason_code": item.code, "category": item.category, "message": item.message, "evidence_refs": [e.get("document_id") or e.get("reference_document_id") for e in item.evidence if e.get("document_id") or e.get("reference_document_id")]}
def _deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    result: list[Finding] = []
    by_code: dict[str, Finding] = {}
    for item in findings:
        if item.code in by_code:
            by_code[item.code].evidence.extend(e for e in item.evidence if e not in by_code[item.code].evidence)
        else:
            by_code[item.code] = item
            result.append(item)
    return result
def _review_summary(fraud: bool, codes: list[str], warnings: list[dict[str, Any]]) -> str:
    if fraud: return "Fraud indicators require human review: " + ", ".join(codes)
    if warnings: return "Analysis completed with document limitations; human review is required."
    return "No configured fraud threshold was met; continue claim review."
