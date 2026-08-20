from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from typing import Any, Protocol


class OcrProvider(Protocol):
    def extract_text(self, pdf_content: bytes) -> str: ...


class VlmProvider(Protocol):
    def extract_fields(self, pdf_content: bytes) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    fields: dict[str, Any]
    method: str
    confidence: float
    text_fingerprint: str
    perceptual_hash: str
    page_count: int
    warnings: list[str]


class DocumentPipeline:
    def __init__(self, max_pages: int = 30, ocr: OcrProvider | None = None, vlm: VlmProvider | None = None):
        self.max_pages = max_pages
        self.ocr = ocr
        self.vlm = vlm

    def extract(self, content: bytes) -> ExtractionResult:
        if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-1024:]:
            raise ValueError("invalid or truncated PDF")
        if b"/Encrypt" in content:
            raise ValueError("encrypted PDF is not supported")
        text, page_count, warnings = self._extract_text_layer(content)
        method = "pdf_text"
        confidence = 0.95
        if len(_normalize(text)) < 20 and self.ocr is not None:
            text = self.ocr.extract_text(content)
            method, confidence = "ocr", 0.75
        fields = _extract_fields(text)
        if (len(fields) < 3 or not text.strip()) and self.vlm is not None:
            vlm_fields = self.vlm.extract_fields(content)
            fields = {**vlm_fields, **fields}
            method, confidence = "vlm_fallback", 0.60
        if not text.strip() and not fields:
            warnings.append("DOCUMENT_TEXT_UNAVAILABLE")
        normalized = _normalize(text)
        return ExtractionResult(
            text=text,
            fields=fields,
            method=method,
            confidence=confidence if text.strip() or fields else 0.0,
            text_fingerprint=hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else "",
            perceptual_hash=hashlib.sha256(("visual:" + normalized).encode("utf-8")).hexdigest()[:32] if normalized else "",
            page_count=page_count,
            warnings=warnings,
        )

    def _extract_text_layer(self, content: bytes) -> tuple[str, int, list[str]]:
        warnings: list[str] = []
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content), strict=False)
            if len(reader.pages) > self.max_pages:
                raise ValueError("PDF page count exceeds configured limit")
            return "\n".join(page.extract_text() or "" for page in reader.pages), len(reader.pages), warnings
        except ModuleNotFoundError:
            pass
        except ValueError:
            raise
        except Exception as exc:
            warnings.append(f"PDF_TEXT_EXTRACTION_FAILED:{type(exc).__name__}")
        page_count = len(re.findall(rb"/Type\s*/Page\b", content))
        if page_count > self.max_pages:
            raise ValueError("PDF page count exceeds configured limit")
        strings = re.findall(rb"\(((?:\\.|[^\\)])*)\)\s*Tj", content)
        decoded = [_unescape_pdf_string(item).decode("utf-8", errors="replace") for item in strings]
        return "\n".join(decoded), page_count, warnings


def compare_fields(claim: dict[str, Any], fields: dict[str, Any]) -> list[dict[str, Any]]:
    comparisons = [
        ("claimed_amount", _integer),
        ("provider_id", str),
        ("receipt_id", str),
        ("treatment_start_date", str),
        ("treatment_end_date", str),
        ("diagnosis_code", str),
        ("treatment_code", str),
    ]
    mismatches: list[dict[str, Any]] = []
    for name, converter in comparisons:
        if name not in claim or name not in fields:
            continue
        try:
            expected, observed = converter(claim[name]), converter(fields[name])
        except (TypeError, ValueError):
            continue
        if expected != observed:
            mismatches.append({"field": name, "claim_value": expected, "document_value": observed})
    return mismatches


def similarity(left: str, right: str) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    differing = sum(a != b for a, b in zip(left.lower(), right.lower()))
    return 1.0 - differing / len(left)


def _extract_fields(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for line in text.splitlines():
        match = re.match(r"\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$", line)
        if not match:
            continue
        key, value = match.group(1).lower(), match.group(2)
        fields[key] = _integer(value) if key == "claimed_amount" else value
    return fields


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^0-9a-z가-힣]+", " ", text)
    return " ".join(text.split())


def _integer(value: Any) -> int:
    return int(re.sub(r"[^0-9-]", "", str(value)))


def _unescape_pdf_string(value: bytes) -> bytes:
    return value.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
