from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from app.config import Settings
from app.main import create_app
from tests.test_v2_fraud import FakeGateway, request_payload


class V2ApiTests(unittest.TestCase):
    def setUp(self):
        settings = Settings(fraud_check_api_key="secret")
        app = create_app(settings, gateway_factory=lambda source: FakeGateway())
        self.endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/v2/fraud/check")

    def request(self, token=None):
        headers = {} if token is None else {"authorization": f"Bearer {token}"}
        return SimpleNamespace(headers=headers)

    def test_authentication_and_contract(self):
        with self.assertRaises(HTTPException) as missing:
            self.endpoint(request_payload(), self.request())
        self.assertEqual(missing.exception.status_code, 401)
        with self.assertRaises(HTTPException) as wrong:
            self.endpoint(request_payload(), self.request("wrong"))
        self.assertEqual(wrong.exception.status_code, 403)
        response = self.endpoint(request_payload(), self.request("secret"))
        self.assertEqual(response["schema_version"], "2.0.0")

    def test_request_id_validation(self):
        payload = request_payload(); payload["request_id"] = "x"
        with self.assertRaises(HTTPException) as caught:
            self.endpoint(payload, self.request("secret"))
        self.assertEqual(caught.exception.status_code, 422)


if __name__ == "__main__": unittest.main()
