from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.account_service import AccountService
from tests.support.account_repository import TestAccountRepository


class AccountManagementIdTests(unittest.TestCase):
    @staticmethod
    def _service(tmp_dir: str, initial: list[dict] | None = None) -> AccountService:
        storage = TestAccountRepository(Path(tmp_dir) / "accounts.json")
        if initial is not None:
            storage.save_accounts(initial)
        return AccountService(storage)

    def test_id_is_stable_across_updates_and_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{"access_token": "token-a", "email": "first@example.test"}])

            account = service.get_account("token-a") or {}
            account_id = account.get("management_id")
            self.assertRegex(str(account_id), r"^acct_[0-9a-f]{24}$")

            service.update_account("token-a", {"email": "second@example.test"}, quiet=True)
            self.assertEqual((service.get_account("token-a") or {}).get("management_id"), account_id)
            self.assertEqual((self._service(tmp_dir).get_account("token-a") or {}).get("management_id"), account_id)

    def test_different_tokens_receive_different_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["token-a", "token-b"])

            first_id = (service.get_account("token-a") or {}).get("management_id")
            second_id = (service.get_account("token-b") or {}).get("management_id")
            self.assertNotEqual(first_id, second_id)

    def test_imported_management_id_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            supplied_id = "acct_ffffffffffffffffffffffff"
            service.add_account_items([{
                "access_token": "token-a",
                "management_id": supplied_id,
            }])

            account = service.get_account("token-a") or {}
            self.assertEqual(
                account.get("management_id"),
                AccountService._management_id_for_token("token-a"),
            )
            self.assertNotEqual(account.get("management_id"), supplied_id)

    def test_duplicate_ids_are_repaired_deterministically_on_load(self) -> None:
        duplicate_id = "acct_aaaaaaaaaaaaaaaaaaaaaaaa"
        initial = [
            {"access_token": "token-a", "management_id": duplicate_id},
            {"access_token": "token-b", "management_id": duplicate_id},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, initial)
            ids = {
                token: (service.get_account(token) or {}).get("management_id")
                for token in ("token-a", "token-b")
            }

            self.assertEqual(ids["token-a"], duplicate_id)
            self.assertNotEqual(ids["token-b"], duplicate_id)
            self.assertEqual(len(set(ids.values())), 2)

            reloaded = self._service(tmp_dir)
            self.assertEqual(
                {
                    token: (reloaded.get_account(token) or {}).get("management_id")
                    for token in ("token-a", "token-b")
                },
                ids,
            )

    def test_token_rotation_preserves_id_and_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "old-token",
                "refresh_token": "refresh-a",
                "id_token": "id-a",
            }])
            account_id = (service.get_account("old-token") or {}).get("management_id")

            active_token = service._apply_refreshed_tokens(
                "old-token",
                {
                    "access_token": "new-token",
                    "refresh_token": "refresh-b",
                    "id_token": "id-b",
                },
                "test",
                expected_access_token="old-token",
                expected_refresh_token="refresh-a",
            )

            self.assertEqual(active_token, "new-token")
            self.assertEqual((service.get_account("new-token") or {}).get("management_id"), account_id)
            self.assertEqual((service.get_account_by_id(str(account_id)) or {}).get("access_token"), "new-token")
            self.assertEqual((self._service(tmp_dir).get_account("new-token") or {}).get("management_id"), account_id)

    def test_reimporting_rotated_old_token_does_not_duplicate_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "old-token",
                "refresh_token": "refresh-a",
            }])
            service._apply_refreshed_tokens(
                "old-token",
                {"access_token": "new-token", "refresh_token": "refresh-b"},
                "test",
                expected_access_token="old-token",
                expected_refresh_token="refresh-a",
            )

            result = service.add_account_items([{"access_token": "old-token"}])

            self.assertEqual(result.get("added"), 0)
            self.assertEqual(result.get("skipped"), 1)
            self.assertEqual(len(service.list_accounts()), 1)
            self.assertIsNotNone(service.get_account("new-token"))

    def test_reimporting_rotated_old_token_after_restart_does_not_duplicate_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "old-token",
                "refresh_token": "refresh-a",
            }])
            service._apply_refreshed_tokens(
                "old-token",
                {"access_token": "new-token", "refresh_token": "refresh-b"},
                "test",
                expected_access_token="old-token",
                expected_refresh_token="refresh-a",
            )

            reloaded = self._service(tmp_dir)
            result = reloaded.add_account_items([{"access_token": "old-token"}])

            self.assertEqual(result.get("added"), 0)
            self.assertEqual(result.get("skipped"), 1)
            self.assertEqual(len(reloaded.list_accounts()), 1)
            self.assertIsNone(reloaded.get_account("old-token"))
            self.assertIsNotNone(reloaded.get_account("new-token"))

    def test_multiple_rotations_keep_first_and_recent_token_fingerprints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-1",
                "refresh_token": "refresh-1",
            }])
            for index in range(2, 13):
                current = service.get_account(f"token-{index - 1}") or {}
                service._apply_refreshed_tokens(
                    f"token-{index - 1}",
                    {
                        "access_token": f"token-{index}",
                        "refresh_token": f"refresh-{index}",
                    },
                    "test",
                    expected_access_token=f"token-{index - 1}",
                    expected_refresh_token=f"refresh-{index - 1}",
                    expected_last_token_refresh_at=current.get("last_token_refresh_at"),
                )

            reloaded = self._service(tmp_dir)
            account = reloaded.get_account("token-12") or {}
            fingerprints = account.get("access_token_fingerprints") or []

            self.assertEqual(len(fingerprints), service._ACCESS_TOKEN_FINGERPRINT_LIMIT)
            self.assertEqual(
                fingerprints,
                [
                    service._access_token_fingerprint("token-1"),
                    *[
                        service._access_token_fingerprint(f"token-{index}")
                        for index in range(6, 13)
                    ],
                ],
            )

            result = reloaded.add_account_items([{"access_token": "token-1"}])
            self.assertEqual(result.get("added"), 0)
            self.assertEqual(result.get("skipped"), 1)

    def test_refresh_progress_expires_completed_and_stale_active_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            with mock.patch("services.account_service.time.monotonic", return_value=100.0):
                service.init_refresh_progress("completed", 1)
                service.finish_refresh_progress("completed", {"refreshed": 1})
                service.init_refresh_progress("active", 1)

            with mock.patch(
                "services.account_service.time.monotonic",
                return_value=100.0 + service._REFRESH_PROGRESS_COMPLETED_TTL_SECONDS - 1,
            ):
                completed = service.get_refresh_progress("completed")
                self.assertIsNotNone(completed)
                self.assertNotIn("_updated_at_monotonic", completed or {})

            with mock.patch(
                "services.account_service.time.monotonic",
                return_value=100.0 + service._REFRESH_PROGRESS_COMPLETED_TTL_SECONDS,
            ):
                self.assertIsNone(service.get_refresh_progress("completed"))
                self.assertIsNotNone(service.get_refresh_progress("active"))

            with mock.patch(
                "services.account_service.time.monotonic",
                return_value=100.0 + service._REFRESH_PROGRESS_ACTIVE_TTL_SECONDS,
            ):
                self.assertIsNone(service.get_refresh_progress("active"))


if __name__ == "__main__":
    unittest.main()
