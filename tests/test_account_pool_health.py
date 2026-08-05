from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("CHATGPT2API_AUTH_KEY", "test-auth")

import services.account_service as account_service_module
from services.account_service import AccountService
from services.openai_backend_api import InvalidAccessTokenError
from tests.support.account_repository import TestAccountRepository


class _Backend:
    def __init__(self, token: str, result_or_error):
        self.token = token
        self.result_or_error = result_or_error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get_user_info(self):
        if isinstance(self.result_or_error, Exception):
            raise self.result_or_error
        return dict(self.result_or_error)


class AccountPoolHealthTests(unittest.TestCase):
    def _service(self, tmp_dir: str) -> AccountService:
        return AccountService(TestAccountRepository(Path(tmp_dir) / "accounts.json"))

    def test_unchecked_local_quota_is_unknown_and_not_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["token-1"])
            service.update_account("token-1", {"status": "正常", "quota": 5}, quiet=True)

            metrics = service.evaluate_account_pool(refresh_stale=False, freshness_seconds=60)

            self.assertEqual(metrics["current_available"], 0)
            self.assertEqual(metrics["current_quota"], 0)
            self.assertEqual(metrics["estimated_available"], 1)
            self.assertEqual(metrics["estimated_quota"], 0)
            self.assertEqual(metrics["unconfirmed_available"], 1)
            self.assertIs((service.get_account("token-1") or {}).get("image_quota_unknown"), True)

    def test_refresh_stale_accounts_until_target_is_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service._POOL_HEALTH_REFRESH_BATCH_SIZE = 1
            service.add_accounts(["token-1", "token-2"])
            service.update_account("token-1", {"status": "正常", "quota": 5}, quiet=True)
            service.update_account("token-2", {"status": "正常", "quota": 5}, quiet=True)
            constructed_tokens: list[str] = []

            def backend_factory(token: str):
                constructed_tokens.append(token)
                return _Backend(token, {
                    "status": "正常",
                    "quota": 7,
                    "image_quota_unknown": False,
                    "restore_at": None,
                })

            with (
                mock.patch.object(service, "refresh_access_token", side_effect=lambda token, **_: token),
                mock.patch("services.openai_backend_api.OpenAIBackendAPI", side_effect=backend_factory),
            ):
                metrics = service.evaluate_account_pool(
                    refresh_stale=True,
                    target_available=1,
                    freshness_seconds=60,
                )

            self.assertEqual(metrics["current_available"], 1)
            self.assertEqual(metrics["current_quota"], 7)
            self.assertEqual(metrics["pool_refreshed"], 1)
            self.assertEqual(constructed_tokens, ["token-1"])

    def test_invalid_token_obeys_auto_remove_during_pool_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["bad-token"])
            service.update_account("bad-token", {"status": "正常", "quota": 5}, quiet=True)

            with (
                mock.patch.object(
                    account_service_module.config.__class__,
                    "auto_remove_invalid_accounts",
                    new_callable=mock.PropertyMock,
                    return_value=True,
                ),
                mock.patch.object(service, "refresh_access_token", side_effect=lambda token, **_: token),
                mock.patch(
                    "services.openai_backend_api.OpenAIBackendAPI",
                    return_value=_Backend("bad-token", InvalidAccessTokenError("invalid access token")),
                ),
            ):
                metrics = service.evaluate_account_pool(
                    refresh_stale=True,
                    target_available=1,
                    freshness_seconds=60,
                )

            account = service.get_account("bad-token")
            self.assertIsNone(account)
            self.assertEqual(metrics["current_available"], 0)
            self.assertEqual(metrics["estimated_available"], 0)
            self.assertEqual(len(metrics["pool_refresh_errors"]), 1)

    def test_transient_refresh_error_records_attempt_without_counting_as_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["token-1"])
            service.update_account("token-1", {"status": "正常", "quota": 5}, quiet=True)
            backend_factory = mock.Mock(return_value=_Backend("token-1", RuntimeError("upstream unavailable")))

            with (
                mock.patch.object(service, "refresh_access_token", side_effect=lambda token, **_: token),
                mock.patch("services.openai_backend_api.OpenAIBackendAPI", backend_factory),
            ):
                first = service.evaluate_account_pool(
                    refresh_stale=True,
                    target_available=1,
                    freshness_seconds=60,
                )
                second = service.evaluate_account_pool(
                    refresh_stale=True,
                    target_available=1,
                    freshness_seconds=60,
                )

            account = service.get_account("token-1")
            self.assertEqual(account["status"], "正常")
            self.assertTrue(account["last_remote_check_attempt_at"])
            self.assertEqual(first["current_available"], 0)
            self.assertEqual(first["estimated_available"], 1)
            self.assertEqual(second["current_available"], 0)
            self.assertEqual(backend_factory.call_count, 1)


if __name__ == "__main__":
    unittest.main()
