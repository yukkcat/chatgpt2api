from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.account_service import AccountService
from services.openai_backend_api import OpenAIBackendAPI
from tests.support.account_repository import TestAccountRepository
from services.sub2api_service import _account_plan_type


class AccountSourcePlanTests(unittest.TestCase):
    @staticmethod
    def _service(tmp_dir: str) -> AccountService:
        return AccountService(TestAccountRepository(Path(tmp_dir) / "accounts.json"))

    def test_legacy_sources_are_canonicalized(self) -> None:
        expected = {
            "": "web",
            "web": "web",
            "microsoft": "web",
            "oauth_login": "web",
            "manual": "web",
            "session_json": "web",
            "codex": "codex",
            "cpa": "codex",
            "cpa_json": "codex",
            "remote_cpa": "codex",
            "sub2api": "codex",
        }

        for value, source in expected.items():
            with self.subTest(value=value):
                self.assertEqual(AccountService._normalize_source_type(value), source)

    def test_unknown_plan_values_stay_unknown(self) -> None:
        for value in ("", "active", "enabled", "microsoft", "codex"):
            with self.subTest(value=value):
                self.assertIsNone(AccountService._normalize_account_type(value))

    def test_sub2api_does_not_treat_entitlement_status_as_plan(self) -> None:
        self.assertEqual(
            _account_plan_type({}, {"entitlement_status": "active"}, {}),
            "",
        )
        self.assertEqual(
            _account_plan_type({}, {"plan_type": "plus", "entitlement_status": "active"}, {}),
            "plus",
        )

    def test_missing_plan_stays_unknown_and_legacy_source_is_persisted_as_web(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "source_type": "microsoft",
            }])

            account = service.get_account("token-a") or {}
            self.assertIsNone(account.get("type"))
            self.assertEqual(account.get("source_type"), "web")
            self.assertEqual(service.get_stats().get("by_type"), {"unknown": 1})

            reloaded = self._service(tmp_dir).get_account("token-a") or {}
            self.assertIsNone(reloaded.get("type"))
            self.assertEqual(reloaded.get("source_type"), "web")

    def test_reimport_without_plan_preserves_known_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "type": "plus",
                "source_type": "web",
            }])
            service.add_account_items([{
                "access_token": "token-a",
                "source_type": "oauth_login",
            }])

            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("type"), "Plus")
            self.assertEqual(account.get("source_type"), "web")

            service.add_account_items([{"access_token": "token-a", "type": "pro"}])
            self.assertEqual((service.get_account("token-a") or {}).get("type"), "Pro")

    def test_codex_export_marker_sets_source_without_becoming_a_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "type": "codex",
            }])

            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("source_type"), "codex")
            self.assertIsNone(account.get("type"))
            self.assertEqual(account.get("export_type"), "codex")

    def test_remote_info_does_not_guess_missing_plan_as_free(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend.access_token = "token-a"
        with (
            mock.patch.object(backend, "_get_me", return_value={"email": "a@example.test", "id": "user-a"}),
            mock.patch.object(backend, "_get_conversation_init", return_value={"limits_progress": []}),
            mock.patch.object(backend, "_get_default_account", return_value={}),
        ):
            result = backend.get_user_info()

        self.assertNotIn("type", result)
        self.assertEqual(result.get("status"), "正常")
        self.assertIs(result.get("image_quota_unknown"), True)


if __name__ == "__main__":
    unittest.main()
