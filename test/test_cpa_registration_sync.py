from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("CHATGPT2API_AUTH_KEY", "test-auth")

from services.account_service import AccountService
from services.cpa_service import build_registered_cpa_auth_payload, registered_cpa_auth_filename
from services.storage.json_storage import JSONStorageBackend


def _jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}
    header_part = (
        base64.urlsafe_b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )
    payload_part = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )
    return f"{header_part}.{payload_part}.sig"


class RegisteredCPASyncTests(unittest.TestCase):
    def test_add_account_records_preserves_registration_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = AccountService(JSONStorageBackend(Path(tmp_dir) / "accounts.json"))

            service.add_account_records(
                [
                    {
                        "email": "alice@example.com",
                        "password": "secret",
                        "access_token": "access-1",
                        "refresh_token": "refresh-1",
                        "id_token": "id-1",
                        "created_at": "2026-04-30T00:00:00+00:00",
                    }
                ]
            )

            account = service.get_account("access-1")

            self.assertIsNotNone(account)
            self.assertEqual(account["email"], "alice@example.com")
            self.assertEqual(account["password"], "secret")
            self.assertEqual(account["refresh_token"], "refresh-1")
            self.assertEqual(account["id_token"], "id-1")
            self.assertEqual(account["created_at"], "2026-04-30T00:00:00+00:00")

    def test_build_registered_cpa_auth_payload_matches_codex_auth_shape(self) -> None:
        access_token = _jwt(
            {
                "exp": 1893456000,
                "https://api.openai.com/auth.chatgpt_account_id": "acc_123",
            }
        )
        id_token = _jwt({"email": "alice@example.com"})

        payload = build_registered_cpa_auth_payload(
            {
                "access_token": access_token,
                "refresh_token": "refresh-1",
                "id_token": id_token,
                "created_at": "2026-04-30T00:00:00+00:00",
            }
        )

        self.assertEqual(payload["type"], "codex")
        self.assertEqual(payload["access_token"], access_token)
        self.assertEqual(payload["refresh_token"], "refresh-1")
        self.assertEqual(payload["id_token"], id_token)
        self.assertEqual(payload["email"], "alice@example.com")
        self.assertEqual(payload["account_id"], "acc_123")
        self.assertEqual(payload["last_refresh"], "2026-04-30T00:00:00+00:00")
        self.assertEqual(payload["expired"], "2030-01-01T00:00:00+00:00")

    def test_registered_cpa_auth_filename_is_safe_json_name(self) -> None:
        name = registered_cpa_auth_filename(
            {
                "email": "alice/example@example.com",
                "access_token": "access-1",
            }
        )

        self.assertTrue(name.startswith("codex-alice-example@example.com-"))
        self.assertTrue(name.endswith(".json"))
        self.assertNotIn("/", name)


if __name__ == "__main__":
    unittest.main()
