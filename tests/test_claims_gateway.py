from __future__ import annotations

import hashlib
import unittest
from email.message import Message
from unittest.mock import patch

from ai_agent_template.developer_kit.sdk.fraud_agent_sdk.gateway import ClaimsGatewayError, HttpClaimsGateway


class Response:
    def __init__(self, content: bytes, content_type="application/json"):
        self.content = content
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.headers["Content-Length"] = str(len(content))
        self.headers["X-Content-Hash"] = hashlib.sha256(content).hexdigest()
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self, size=-1): return self.content if size < 0 else self.content[:size]


class ClaimsGatewayTests(unittest.TestCase):
    def test_context_path_and_bearer_auth(self):
        gateway = HttpClaimsGateway("http://claims", "internal-secret")
        with patch("ai_agent_template.developer_kit.sdk.fraud_agent_sdk.gateway.urlopen", return_value=Response(b'{"claim_id":"C 1"}')) as call:
            result = gateway.get_fraud_context("C 1")
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, "http://claims/internal/v1/fraud-context/claims/C%201")
        self.assertEqual(request.get_header("Authorization"), "Bearer internal-secret")
        self.assertEqual(result["claim_id"], "C 1")

    def test_pdf_hash_and_size_are_enforced(self):
        content = b"%PDF-1.4\n%%EOF"
        gateway = HttpClaimsGateway("http://claims", None, max_document_bytes=100)
        with patch("ai_agent_template.developer_kit.sdk.fraud_agent_sdk.gateway.urlopen", return_value=Response(content, "application/pdf")):
            document = gateway.get_document_content("DOC-1", hashlib.sha256(content).hexdigest())
        self.assertEqual(document.content, content)
        with patch("ai_agent_template.developer_kit.sdk.fraud_agent_sdk.gateway.urlopen", return_value=Response(content, "application/pdf")):
            with self.assertRaises(ClaimsGatewayError) as caught:
                gateway.get_document_content("DOC-1", "wrong")
        self.assertEqual(caught.exception.code, "DOCUMENT_HASH_MISMATCH")


if __name__ == "__main__": unittest.main()
