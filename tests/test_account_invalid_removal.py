from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("CHATGPT2API_AUTH_KEY", "test-auth")

import services.account_service as account_service_module
from services.account_service import AccountService
from services.config import ConfigStore
from services.openai_backend_api import InvalidAccessTokenError
from tests.support.account_repository import TestAccountRepository


class AccountInvalidRemovalTests(unittest.TestCase):
    def test_missing_auto_remove_settings_use_documented_defaults(self) -> None:
        config_store = object.__new__(ConfigStore)
        config_store.data = {}

        self.assertIs(config_store.auto_remove_invalid_accounts, True)
        self.assertIs(config_store.auto_remove_rate_limited_accounts, False)

    def test_confirmed_invalid_access_token_is_removed_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = AccountService(TestAccountRepository(Path(tmp_dir) / "accounts.json"))
            service.add_accounts(["token-1"])
            service.update_account(
                "token-1",
                {
                    "created_at": "2026-01-01 00:00:00",
                    "invalid_count": 2,
                    "last_invalid_at": "2026-01-01T00:00:00+00:00",
                },
                quiet=True,
            )

            backend = mock.MagicMock()
            backend.__enter__.return_value.get_user_info.side_effect = InvalidAccessTokenError("invalid access token")

            with (
                mock.patch.object(
                    account_service_module.config.__class__,
                    "auto_remove_invalid_accounts",
                    new_callable=mock.PropertyMock,
                    return_value=True,
                ),
                mock.patch.object(service, "refresh_access_token", return_value="token-1"),
                mock.patch("services.openai_backend_api.OpenAIBackendAPI", return_value=backend),
            ):
                with self.assertRaises(InvalidAccessTokenError):
                    service.fetch_remote_info("token-1", "test")

            self.assertIsNone(service.get_account("token-1"))

    def test_cleanup_policy_removes_all_matching_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = AccountService(TestAccountRepository(Path(tmp_dir) / "accounts.json"))
            service.add_accounts(["normal-1", "bad-1", "bad-2"])
            with mock.patch.object(
                account_service_module.config.__class__,
                "auto_remove_invalid_accounts",
                new_callable=mock.PropertyMock,
                return_value=False,
            ):
                service.update_account("bad-1", {"status": "异常"})
                service.update_account("bad-2", {"status": "异常"})

            result = service.cleanup_auto_remove_accounts(
                remove_invalid=True,
                remove_rate_limited=False,
            )

            self.assertEqual(result["total_removed"], 2)
            self.assertIsNotNone(service.get_account("normal-1"))
            self.assertIsNone(service.get_account("bad-1"))
            self.assertIsNone(service.get_account("bad-2"))
            saved = TestAccountRepository(Path(tmp_dir) / "accounts.json").load_accounts()
            self.assertEqual([item["access_token"] for item in saved], ["normal-1"])


if __name__ == "__main__":
    unittest.main()
