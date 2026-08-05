from __future__ import annotations

import unittest

from services.account_import_credentials import extract_import_credentials
from services.sub2api_service import _account_access_token, _account_credential_meta


class AccountImportCredentialTests(unittest.TestCase):
    def test_extracts_snake_case_credentials_from_record_root(self) -> None:
        self.assertEqual(
            extract_import_credentials(
                {
                    "access_token": " access ",
                    "refresh_token": " refresh ",
                    "id_token": " id ",
                    "proxy": "http://ignored.example",
                }
            ),
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "id_token": "id",
            },
        )

    def test_nested_camel_case_credentials_take_precedence(self) -> None:
        self.assertEqual(
            extract_import_credentials(
                {
                    "access_token": "stale",
                    "credentials": {
                        "accessToken": "current",
                        "refreshToken": "refresh",
                        "idToken": "id",
                    },
                }
            ),
            {
                "access_token": "current",
                "refresh_token": "refresh",
                "id_token": "id",
            },
        )

    def test_sub2api_meta_preserves_rotatable_credentials(self) -> None:
        self.assertEqual(
            _account_credential_meta(
                {
                    "credentials": {
                        "access_token": "access",
                        "refresh_token": "refresh",
                        "id_token": "id",
                    }
                }
            ),
            {"refresh_token": "refresh", "id_token": "id"},
        )

    def test_sub2api_accepts_json_encoded_credential_section(self) -> None:
        account = {
            "credentials": (
                '{"access_token":"access","refresh_token":"refresh",'
                '"id_token":"id"}'
            )
        }
        self.assertEqual(_account_access_token(account), "access")
        self.assertEqual(
            _account_credential_meta(account),
            {"refresh_token": "refresh", "id_token": "id"},
        )

if __name__ == "__main__":
    unittest.main()
