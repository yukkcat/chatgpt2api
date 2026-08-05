from __future__ import annotations

import base64
import json
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from services.account_service import (
    AccountService,
    ImageAccountSelectionError,
    OAuthRefreshError,
    RefreshCredentialsChangedError,
    TerminalRefreshTokenError,
)
from services.account_view import account_row
from services.image_failure import InvalidAccessTokenError
from services.storage.base import StorageMutation, StorageRevisionConflictError
from tests.support.account_repository import TestAccountRepository


def _access_token(*, expires_at: int) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"iat": expires_at - 3600, "exp": expires_at}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"header.{payload}.signature"


class RecordingTestAccountRepository(TestAccountRepository):
    def __init__(self, file_path: Path, auth_keys_path: Path):
        super().__init__(file_path, auth_keys_path)
        self.account_mutations: list[StorageMutation] = []

    def mutate_accounts(self, mutation: StorageMutation):
        self.account_mutations.append(mutation)
        return super().mutate_accounts(mutation)


class AlwaysConflictingTestAccountRepository(TestAccountRepository):
    def __init__(self, file_path: Path, auth_keys_path: Path):
        super().__init__(file_path, auth_keys_path)
        self.force_conflicts = False
        self.conflict_count = 0

    def mutate_accounts(self, mutation: StorageMutation):
        if not self.force_conflicts:
            return super().mutate_accounts(mutation)
        self.conflict_count += 1
        actual = self.load_accounts_snapshot().revision
        raise StorageRevisionConflictError(
            "accounts",
            str(mutation.expected_revision or ""),
            actual,
        )


class ToggleFailingTestAccountRepository(TestAccountRepository):
    def __init__(self, file_path: Path, auth_keys_path: Path):
        super().__init__(file_path, auth_keys_path)
        self.fail_mutations = False

    def mutate_accounts(self, mutation: StorageMutation):
        if self.fail_mutations:
            raise OSError("storage unavailable")
        return super().mutate_accounts(mutation)


class ConflictThenUnreadableTestAccountRepository(TestAccountRepository):
    def __init__(self, file_path: Path, auth_keys_path: Path):
        super().__init__(file_path, auth_keys_path)
        self.conflict_once = False
        self.fail_snapshot_loads = False

    def load_accounts_snapshot(self):  # type: ignore[no-untyped-def]
        if self.fail_snapshot_loads:
            raise OSError("snapshot unavailable")
        return super().load_accounts_snapshot()

    def mutate_accounts(self, mutation: StorageMutation):
        if not self.conflict_once:
            return super().mutate_accounts(mutation)
        actual = super().load_accounts_snapshot().revision
        self.conflict_once = False
        self.fail_snapshot_loads = True
        raise StorageRevisionConflictError(
            "accounts",
            str(mutation.expected_revision or ""),
            actual,
        )


class BlockingSnapshotTestAccountRepository(TestAccountRepository):
    def __init__(self, file_path: Path, auth_keys_path: Path):
        super().__init__(file_path, auth_keys_path)
        self.snapshot_load_count = 0
        self.block_next_snapshot = False
        self.snapshot_loaded = Event()
        self.allow_snapshot_return = Event()

    def load_accounts_snapshot(self):  # type: ignore[no-untyped-def]
        self.snapshot_load_count += 1
        snapshot = super().load_accounts_snapshot()
        if self.block_next_snapshot:
            self.block_next_snapshot = False
            self.snapshot_loaded.set()
            if not self.allow_snapshot_return.wait(timeout=5):
                raise TimeoutError("snapshot test barrier timed out")
        return snapshot


class AccountStorageMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.log_patch = patch("services.account_service.log_service.add")
        self.log_add = self.log_patch.start()

    def tearDown(self) -> None:
        self.log_patch.stop()

    @staticmethod
    def _backend(root: Path) -> TestAccountRepository:
        return TestAccountRepository(root / "accounts.json", root / "auth_keys.json")

    def test_concurrent_additions_preserve_both_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            first = AccountService(backend)
            second = AccountService(backend)

            first.add_accounts(["token-a"], return_items=False)
            second.add_accounts(["token-b"], return_items=False)

            self.assertEqual(
                {item["access_token"] for item in backend.load_accounts()},
                {"token-a", "token-b"},
            )

    def test_concurrent_same_account_reports_one_add_and_one_skip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            first = AccountService(backend)
            second = AccountService(backend)

            first_result = first.add_account_items(
                [{"access_token": "shared-token"}],
                return_items=False,
                return_item_results=True,
            )
            second_result = second.add_account_items(
                [{"access_token": "shared-token"}],
                return_items=False,
                return_item_results=True,
            )

            self.assertEqual(first_result["added"], 1)
            self.assertEqual(first_result["item_results"], ["added"])
            self.assertEqual(second_result["added"], 0)
            self.assertEqual(second_result["skipped"], 1)
            self.assertEqual(second_result["item_results"], ["skipped"])
            self.assertEqual(
                [item["access_token"] for item in backend.load_accounts()],
                ["shared-token"],
            )

    def test_account_import_can_return_non_sensitive_results_in_input_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AccountService(self._backend(Path(temp_dir)))
            service.add_accounts(["existing-secret"], return_items=False)

            result = service.add_account_items(
                [
                    {"access_token": "existing-secret"},
                    {
                        "access_token": "new-secret",
                        "refresh_token": "refresh-secret",
                    },
                    {"access_token": "new-secret", "email": "merged@example.test"},
                    {"email": "missing-token@example.test"},
                ],
                return_items=False,
                return_item_results=True,
            )

            self.assertEqual(result["added"], 1)
            self.assertEqual(result["skipped"], 2)
            self.assertEqual(
                result["item_results"],
                ["skipped", "added", "skipped", "invalid"],
            )
            self.assertEqual(result["items"], [])
            self.assertNotIn("existing-secret", repr(result))
            self.assertNotIn("new-secret", repr(result))
            self.assertNotIn("refresh-secret", repr(result))

            default_result = service.add_account_items(
                [{"access_token": "another-secret"}],
                return_items=False,
            )
            self.assertNotIn("item_results", default_result)

    def test_full_account_export_round_trips_credentials_and_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = AccountService(self._backend(root / "source"))
            source.add_account_items(
                [
                    {
                        "access_token": "access-token",
                        "refresh_token": "refresh-token",
                        "id_token": "id-token",
                        "password": "secret",
                        "source_type": "codex",
                        "status": "禁用",
                        "quota": 7,
                        "proxy": "group:proxy-a",
                        "group_id": "group-a",
                    }
                ],
                return_items=False,
            )
            source.update_account(
                "access-token",
                {
                    "last_token_refresh_at": "2026-07-30T01:02:03+00:00",
                    "last_token_refresh_error": "invalid_grant",
                    "last_token_refresh_error_at": "2026-07-30T02:03:04+00:00",
                    "refresh_token_invalid_at": "2026-07-30T02:03:04+00:00",
                    "last_remote_checked_at": "2026-07-30T02:04:05+00:00",
                    "last_remote_check_result": "invalid",
                },
                quiet=True,
            )

            exported = source.build_export_items(["access-token"], full=True)
            self.assertEqual(len(exported), 1)

            restored = AccountService(self._backend(root / "restored"))
            restored.add_account_items(
                exported,
                return_items=False,
                restore=True,
            )
            account = restored.get_account("access-token")

            self.assertIsNotNone(account)
            assert account is not None
            for key in (
                "refresh_token",
                "id_token",
                "password",
                "source_type",
                "status",
                "quota",
                "proxy",
                "group_id",
                "management_id",
                "access_token_fingerprints",
                "last_token_refresh_at",
                "last_token_refresh_error",
                "last_token_refresh_error_at",
                "refresh_token_invalid_at",
                "last_remote_checked_at",
                "last_remote_check_result",
            ):
                self.assertEqual(account[key], exported[0][key])

    def test_filter_account_selection_is_resolved_by_backend(self) -> None:
        from api.accounts import AccountSelectionScope, _account_selection_targets

        accounts = [
            {
                "management_id": "acct_first",
                "access_token": "token-first",
                "email": "plus@example.com",
                "status": "正常",
                "group_id": "group-a",
            },
            {
                "management_id": "acct_second",
                "access_token": "token-second",
                "email": "plus-2@example.com",
                "status": "正常",
                "group_id": "group-a",
            },
            {
                "management_id": "acct_other",
                "access_token": "token-other",
                "email": "free@example.com",
                "status": "禁用",
                "group_id": "group-b",
            },
        ]
        selection = AccountSelectionScope(
            mode="filter",
            keyword="plus",
            status="normal",
            group_id="group-a",
            excluded_account_ids=["acct_second"],
        )

        with patch("api.accounts.account_service.list_accounts", return_value=accounts):
            targets, missing = _account_selection_targets(selection)

        self.assertEqual(targets, [("token-first", "acct_first")])
        self.assertEqual(missing, [])

    def test_batch_update_persists_all_accounts_in_one_storage_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = RecordingTestAccountRepository(
                root / "accounts.json",
                root / "auth_keys.json",
            )
            service = AccountService(backend)
            service.add_accounts(["token-a", "token-b"], return_items=False)
            backend.account_mutations.clear()

            result = service.update_accounts(
                ["token-a", "token-b"],
                {"status": "\u7981\u7528"},
            )

            self.assertEqual(len(backend.account_mutations), 1)
            self.assertEqual(len(backend.account_mutations[0].upserts), 2)
            self.assertEqual(len(result["updated_ids"]), 2)
            self.assertEqual(result["removed_ids"], [])
            self.assertEqual(result["missing_tokens"], [])
            self.assertEqual(
                {item["status"] for item in backend.load_accounts()},
                {"\u7981\u7528"},
            )

    def test_selection_preview_discards_exclusions_no_longer_in_filter(self) -> None:
        from api.accounts import AccountSelectionScope, _account_selection_preview

        selection = AccountSelectionScope(
            mode="filter",
            keyword="plus",
            status="normal",
            group_id="group-a",
            excluded_account_ids=["acct_still_matching", "acct_no_longer_matching"],
        )
        accounts = [
            {
                "management_id": "acct_selected",
                "access_token": "token-selected",
                "email": "plus@example.com",
                "status": "\u6b63\u5e38",
                "group_id": "group-a",
            },
            {
                "management_id": "acct_still_matching",
                "access_token": "token-excluded",
                "email": "plus-2@example.com",
                "status": "\u6b63\u5e38",
                "group_id": "group-a",
            },
            {
                "management_id": "acct_no_longer_matching",
                "access_token": "token-disabled",
                "email": "plus-3@example.com",
                "status": "\u7981\u7528",
                "group_id": "group-a",
            },
        ]

        with patch("api.accounts.account_service.list_accounts", return_value=accounts):
            preview = _account_selection_preview(selection)

        self.assertEqual(preview["matching_count"], 2)
        self.assertEqual(preview["selected_count"], 1)
        self.assertEqual(preview["excluded_account_ids"], ["acct_still_matching"])

    def test_conflict_merges_only_locally_changed_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_accounts(["token"], return_items=False)
            first = AccountService(backend)
            second = AccountService(backend)

            first.update_account(
                "token",
                {"remote_only": "remote", "shared": "remote"},
                quiet=True,
            )
            second.update_account(
                "token",
                {"local_only": "local", "shared": "local"},
                quiet=True,
            )

            account = backend.load_accounts()[0]
            self.assertEqual(account["remote_only"], "remote")
            self.assertEqual(account["local_only"], "local")
            self.assertEqual(account["shared"], "local")

    def test_concurrent_result_counters_apply_both_instance_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_accounts(["token"], return_items=False)
            first = AccountService(backend)
            second = AccountService(backend)

            first.update_account(
                "token",
                {"success": 1, "fail": 1},
                quiet=True,
            )
            second.update_account(
                "token",
                {"success": 1, "fail": 1},
                quiet=True,
            )

            account = backend.load_accounts()[0]
            self.assertEqual(account["success"], 2)
            self.assertEqual(account["fail"], 2)

    def test_concurrent_image_results_apply_both_quota_consumption_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [
                    {
                        "access_token": "token",
                        "quota": 4,
                        "image_quota_unknown": False,
                        "last_remote_checked_at": "2026-01-01T00:00:00+00:00",
                    }
                ],
                return_items=False,
            )
            first = AccountService(backend)
            second = AccountService(backend)

            first.mark_image_result("token", True)
            second.mark_image_result("token", True)

            account = backend.load_accounts()[0]
            self.assertEqual(account["success"], 2)
            self.assertEqual(account["quota"], 2)

    def test_concurrent_quota_consumption_never_goes_below_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [
                    {
                        "access_token": "token",
                        "quota": 1,
                        "image_quota_unknown": False,
                        "last_remote_checked_at": "2026-01-01T00:00:00+00:00",
                    }
                ],
                return_items=False,
            )
            first = AccountService(backend)
            second = AccountService(backend)

            first.mark_image_result("token", True)
            second.mark_image_result("token", True)

            account = backend.load_accounts()[0]
            self.assertEqual(account["success"], 2)
            self.assertEqual(account["quota"], 0)

    def test_concurrent_absolute_quota_refresh_keeps_local_absolute_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [{"access_token": "token", "quota": 5}],
                return_items=False,
            )
            first = AccountService(backend)
            second = AccountService(backend)

            first.update_account("token", {"quota": 9}, quiet=True)
            second.update_account("token", {"quota": 8}, quiet=True)

            self.assertEqual(backend.load_accounts()[0]["quota"], 8)

    def test_remote_deletion_beats_stale_background_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_accounts(["token"], return_items=False)
            stale_updater = AccountService(backend)
            remover = AccountService(backend)

            remover.delete_accounts(["token"], return_items=False)
            updated = stale_updater.update_account(
                "token",
                {"last_remote_check_result": "ok"},
                quiet=True,
            )

            self.assertIsNone(updated)
            self.assertEqual(backend.load_accounts(), [])
            self.assertIsNone(stale_updater.get_account("token"))

    def test_remote_deletion_reaches_stale_account_list_after_refresh_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_accounts(["token"], return_items=False)
            stale = AccountService(backend)
            remover = AccountService(backend)
            stale._ACCOUNT_SNAPSHOT_TTL_SECONDS = 0

            remover.delete_accounts(["token"], return_items=False)

            self.assertEqual(stale.list_accounts(), [])

    def test_remote_disable_stops_new_image_selection_after_refresh_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_accounts(["token"], return_items=False)
            stale = AccountService(backend)
            updater = AccountService(backend)
            stale._ACCOUNT_SNAPSHOT_TTL_SECONDS = 0

            updater.update_account("token", {"status": "禁用"}, quiet=True)

            with patch.object(stale, "fetch_remote_info") as fetch_remote_info:
                with self.assertRaises(ImageAccountSelectionError):
                    stale.get_available_access_token()
            fetch_remote_info.assert_not_called()

    def test_remote_deletion_preserves_and_releases_an_active_image_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_accounts(["token"], return_items=False)
            stale = AccountService(backend)
            remover = AccountService(backend)

            with patch.object(
                stale,
                "fetch_remote_info",
                return_value=stale.get_account("token"),
            ):
                leased_token = stale.get_available_access_token()
            stale._ACCOUNT_SNAPSHOT_TTL_SECONDS = 0
            remover.delete_accounts(["token"], return_items=False)

            self.assertEqual(stale.list_accounts(), [])
            self.assertEqual(stale._image_inflight, {"token": 1})

            stale.release_image_slot(leased_token)

            self.assertEqual(stale._image_inflight, {})

    def test_passive_token_rotation_preserves_active_image_slot_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [{"access_token": "old-token", "refresh_token": "refresh"}],
                return_items=False,
            )
            stale = AccountService(backend)
            rotator = AccountService(backend)

            with patch.object(
                stale,
                "fetch_remote_info",
                return_value=stale.get_account("old-token"),
            ):
                leased_token = stale.get_available_access_token()
            rotator._apply_refreshed_tokens(
                "old-token",
                {"access_token": "new-token", "refresh_token": "refresh-2"},
                "test",
                expected_access_token="old-token",
                expected_refresh_token="refresh",
            )
            stale._ACCOUNT_SNAPSHOT_TTL_SECONDS = 0

            accounts = stale.list_accounts()

            self.assertEqual([item["access_token"] for item in accounts], ["new-token"])
            self.assertEqual(accounts[0]["image_inflight"], 1)
            self.assertEqual(stale._token_aliases["old-token"], "new-token")

            stale.release_image_slot(leased_token)

            self.assertEqual(stale._image_inflight, {})

    def test_remote_token_rotation_merges_local_update_and_moves_active_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [{"access_token": "old-token", "refresh_token": "refresh"}],
                return_items=False,
            )
            stale = AccountService(backend)
            rotator = AccountService(backend)
            stale._image_inflight["old-token"] = 1

            rotator._apply_refreshed_tokens(
                "old-token",
                {"access_token": "new-token", "refresh_token": "refresh-2"},
                "test",
                expected_access_token="old-token",
                expected_refresh_token="refresh",
            )
            updated = stale.update_account(
                "old-token",
                {"local_only": "local"},
                quiet=True,
            )

            self.assertIsNotNone(updated)
            self.assertEqual(updated["access_token"], "new-token")
            self.assertEqual(updated["local_only"], "local")
            self.assertEqual(
                backend.load_accounts()[0]["local_only"],
                "local",
            )
            self.assertEqual(stale._image_inflight, {"new-token": 1})
            self.assertEqual(stale._token_aliases["old-token"], "new-token")

            stale.release_image_slot("old-token")

            self.assertEqual(stale._image_inflight, {})

    def test_remote_token_rotation_discards_stale_refresh_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [{"access_token": "old-token", "refresh_token": "old-refresh"}],
                return_items=False,
            )
            stale = AccountService(backend)
            rotator = AccountService(backend)

            rotator._apply_refreshed_tokens(
                "old-token",
                {"access_token": "new-token", "refresh_token": "new-refresh"},
                "test",
                expected_access_token="old-token",
                expected_refresh_token="old-refresh",
            )
            recorded = stale._record_token_refresh_error(
                "old-token",
                "test",
                "invalid_grant",
                expected_access_token="old-token",
                expected_refresh_token="old-refresh",
                terminal=True,
            )

            self.assertFalse(recorded)
            account = backend.load_accounts()[0]
            self.assertEqual(account["access_token"], "new-token")
            self.assertEqual(account["refresh_token"], "new-refresh")
            self.assertIsNone(account.get("last_token_refresh_error"))
            self.assertIsNone(account.get("last_token_refresh_error_at"))
            self.assertIsNone(account.get("refresh_token_invalid_at"))

    def test_remote_in_place_refresh_success_discards_stale_refresh_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [{"access_token": "token", "refresh_token": "refresh"}],
                return_items=False,
            )
            stale = AccountService(backend)
            winner = AccountService(backend)

            def lose_after_remote_success(*_args, **_kwargs):  # type: ignore[no-untyped-def]
                winner._apply_refreshed_tokens(
                    "token",
                    {"access_token": "token", "refresh_token": "refresh"},
                    "winner",
                    expected_access_token="token",
                    expected_refresh_token="refresh",
                )
                raise TerminalRefreshTokenError(
                    400,
                    "invalid_grant",
                    "refresh token was already exchanged",
                )

            with patch.object(
                stale,
                "_request_access_token_refresh",
                side_effect=lose_after_remote_success,
            ):
                active_token = stale.refresh_access_token(
                    "token",
                    force=True,
                    raise_on_error=True,
                )

            self.assertEqual(active_token, "token")
            account = backend.load_accounts()[0]
            self.assertTrue(account.get("last_token_refresh_at"))
            self.assertIsNone(account.get("last_token_refresh_error"))
            self.assertIsNone(account.get("last_token_refresh_error_at"))
            self.assertIsNone(account.get("refresh_token_invalid_at"))

    def test_remote_refresh_success_beats_stale_refresh_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [{"access_token": "old-token", "refresh_token": "old-refresh"}],
                return_items=False,
            )
            stale = AccountService(backend)
            winner = AccountService(backend)

            def return_after_remote_success(*_args, **_kwargs):  # type: ignore[no-untyped-def]
                winner._apply_refreshed_tokens(
                    "old-token",
                    {
                        "access_token": "winner-token",
                        "refresh_token": "winner-refresh",
                    },
                    "winner",
                    expected_access_token="old-token",
                    expected_refresh_token="old-refresh",
                )
                return {
                    "access_token": "loser-token",
                    "refresh_token": "loser-refresh",
                }

            with patch.object(
                stale,
                "_request_access_token_refresh",
                side_effect=return_after_remote_success,
            ) as request_refresh:
                active_token = stale.refresh_access_token(
                    "old-token",
                    force=True,
                    raise_on_error=True,
                )

            self.assertEqual(active_token, "winner-token")
            request_refresh.assert_called_once()
            account = backend.load_accounts()[0]
            self.assertEqual(account["access_token"], "winner-token")
            self.assertEqual(account["refresh_token"], "winner-refresh")

    def test_refresh_flights_are_scoped_to_credential_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [{"access_token": "token", "refresh_token": "refresh"}],
                return_items=False,
            )
            first_started = Event()
            release_first = Event()
            second_started = Event()
            calls: list[str] = []
            outcomes: list[str] = []
            errors: list[BaseException] = []

            def request_refresh(_refresh_token: str, account: dict) -> dict[str, str]:
                calls.append(str(account.get("last_token_refresh_at") or ""))
                if len(calls) == 1:
                    first_started.set()
                    self.assertTrue(release_first.wait(timeout=2))
                else:
                    second_started.set()
                return {"access_token": "token", "refresh_token": "refresh"}

            def refresh() -> None:
                try:
                    outcomes.append(service.force_refresh_access_token("token"))
                except BaseException as exc:  # pragma: no branch - asserted below
                    errors.append(exc)

            with patch.object(
                service,
                "_request_access_token_refresh",
                side_effect=request_refresh,
            ):
                first = Thread(target=refresh)
                first.start()
                self.assertTrue(first_started.wait(timeout=2))
                initial = service.get_account("token") or {}
                service._apply_refreshed_tokens(
                    "token",
                    {"access_token": "token", "refresh_token": "refresh"},
                    "concurrent-refresh",
                    expected_access_token="token",
                    expected_refresh_token="refresh",
                    expected_last_token_refresh_at=initial.get("last_token_refresh_at"),
                )
                second = Thread(target=refresh)
                second.start()
                self.assertTrue(second_started.wait(timeout=2))
                release_first.set()
                first.join(timeout=2)
                second.join(timeout=2)

            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(outcomes, ["token", "token"])
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0], "")
            self.assertTrue(calls[1])

    def test_remote_rotation_discards_stale_remote_check_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [{"access_token": "old-token", "refresh_token": "old-refresh"}],
                return_items=False,
            )
            stale = AccountService(backend)
            winner = AccountService(backend)

            class LosingBackend:
                def __init__(self, _access_token: str) -> None:
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *_args) -> None:
                    return None

                def get_user_info(self):
                    winner._apply_refreshed_tokens(
                        "old-token",
                        {
                            "access_token": "new-token",
                            "refresh_token": "new-refresh",
                        },
                        "winner",
                        expected_access_token="old-token",
                        expected_refresh_token="old-refresh",
                    )
                    raise RuntimeError("stale remote check failed")

            with (
                patch(
                    "services.openai_backend_api.OpenAIBackendAPI",
                    LosingBackend,
                ),
                self.assertRaisesRegex(RuntimeError, "stale remote check failed"),
            ):
                stale.fetch_remote_info(
                    "old-token",
                    allow_refresh_token_exchange=False,
                )

            account = backend.load_accounts()[0]
            self.assertEqual(account["access_token"], "new-token")
            self.assertEqual(account["refresh_token"], "new-refresh")
            self.assertIsNone(account.get("last_remote_check_error"))
            self.assertIsNone(account.get("last_remote_check_error_at"))
            self.assertIsNone(account.get("last_remote_check_result"))

    def test_remote_rotation_does_not_schedule_stale_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [{"access_token": "old-token", "refresh_token": "old-refresh"}],
                return_items=False,
            )
            stale = AccountService(backend)
            winner = AccountService(backend)
            winner._apply_refreshed_tokens(
                "old-token",
                {
                    "access_token": "new-token",
                    "refresh_token": "new-refresh",
                },
                "winner",
                expected_access_token="old-token",
                expected_refresh_token="old-refresh",
            )

            with patch.object(
                stale,
                "_schedule_account_refresh_after_image_failure",
                return_value=True,
            ) as schedule:
                scheduled = stale.schedule_auth_verification(
                    "old-token",
                    "stale-check",
                    expected_access_token="old-token",
                    expected_refresh_token="old-refresh",
                )

            self.assertFalse(scheduled)
            schedule.assert_not_called()
            account = backend.load_accounts()[0]
            self.assertEqual(account["access_token"], "new-token")
            self.assertIsNone(account.get("last_remote_check_result"))
            self.assertIsNone(account.get("pending_auth_verification_id"))

    def test_remote_rotation_survives_stale_automatic_invalid_removal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [{"access_token": "old-token", "refresh_token": "old-refresh"}],
                return_items=False,
            )
            stale = AccountService(backend)
            winner = AccountService(backend)
            winner._apply_refreshed_tokens(
                "old-token",
                {
                    "access_token": "new-token",
                    "refresh_token": "new-refresh",
                },
                "winner",
                expected_access_token="old-token",
                expected_refresh_token="old-refresh",
            )

            removed = stale.handle_invalid_token(
                "old-token",
                "stale-check",
                error="old credential was rejected",
                remove=True,
                expected_access_token="old-token",
                expected_refresh_token="old-refresh",
            )

            self.assertFalse(removed)
            accounts = backend.load_accounts()
            self.assertEqual(len(accounts), 1)
            self.assertEqual(accounts[0]["access_token"], "new-token")
            self.assertEqual(accounts[0]["refresh_token"], "new-refresh")
            self.assertEqual(accounts[0]["status"], "正常")

    def test_remote_rotation_discards_stale_remote_check_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [{"access_token": "old-token", "refresh_token": "old-refresh"}],
                return_items=False,
            )
            stale = AccountService(backend)
            winner = AccountService(backend)

            class LosingBackend:
                def __init__(self, _access_token: str) -> None:
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *_args) -> None:
                    return None

                def get_user_info(self):
                    winner._apply_refreshed_tokens(
                        "old-token",
                        {
                            "access_token": "new-token",
                            "refresh_token": "new-refresh",
                        },
                        "winner",
                        expected_access_token="old-token",
                        expected_refresh_token="old-refresh",
                    )
                    winner.update_account(
                        "new-token",
                        {"quota": 7, "image_quota_unknown": False},
                        quiet=True,
                    )
                    return {
                        "status": "正常",
                        "quota": 99,
                        "image_quota_unknown": False,
                    }

            with (
                patch(
                    "services.openai_backend_api.OpenAIBackendAPI",
                    LosingBackend,
                ),
                self.assertRaises(RefreshCredentialsChangedError),
            ):
                stale.fetch_remote_info(
                    "old-token",
                    allow_refresh_token_exchange=False,
                )

            account = backend.load_accounts()[0]
            self.assertEqual(account["access_token"], "new-token")
            self.assertEqual(account["refresh_token"], "new-refresh")
            self.assertEqual(account["quota"], 7)
            self.assertIsNone(account.get("last_remote_check_result"))

    def test_in_place_refresh_discards_stale_remote_auth_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [{"access_token": "token", "refresh_token": "refresh"}],
                return_items=False,
            )

            class RefreshingBackend:
                calls = 0

                def __init__(self, _access_token: str) -> None:
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *_args) -> None:
                    return None

                def get_user_info(self):
                    self.__class__.calls += 1
                    if self.__class__.calls == 1:
                        service._apply_refreshed_tokens(
                            "token",
                            {"access_token": "token", "refresh_token": "refresh"},
                            "concurrent-refresh",
                            expected_access_token="token",
                            expected_refresh_token="refresh",
                        )
                        raise InvalidAccessTokenError("stale credential was rejected")
                    return {
                        "status": "正常",
                        "quota": 7,
                        "image_quota_unknown": False,
                    }

            with patch(
                "services.openai_backend_api.OpenAIBackendAPI",
                RefreshingBackend,
            ):
                account = service.fetch_remote_info(
                    "token",
                    allow_refresh_token_exchange=False,
                )

            self.assertEqual(RefreshingBackend.calls, 2)
            self.assertIsNotNone(account)
            self.assertEqual(account["status"], "正常")
            self.assertEqual(account["quota"], 7)
            self.assertTrue(account.get("last_token_refresh_at"))
            self.assertIsNone(account.get("last_remote_check_error"))
            self.assertEqual(account.get("last_remote_check_result"), "ok")

    def test_remote_rotation_discards_stale_image_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [
                    {
                        "access_token": "old-token",
                        "refresh_token": "old-refresh",
                        "quota": 5,
                        "image_quota_unknown": False,
                    }
                ],
                return_items=False,
            )
            stale = AccountService(backend)
            winner = AccountService(backend)
            stale._image_inflight["old-token"] = 1
            winner._apply_refreshed_tokens(
                "old-token",
                {
                    "access_token": "new-token",
                    "refresh_token": "new-refresh",
                },
                "winner",
                expected_access_token="old-token",
                expected_refresh_token="old-refresh",
            )

            result = stale.mark_image_result(
                "old-token",
                True,
                expected_access_token="old-token",
                expected_refresh_token="old-refresh",
                expected_last_token_refresh_at=None,
            )

            self.assertIsNone(result)
            self.assertEqual(stale._image_inflight, {})
            account = backend.load_accounts()[0]
            self.assertEqual(account["access_token"], "new-token")
            self.assertEqual(account["quota"], 5)
            self.assertEqual(account["success"], 0)

    def test_waiting_image_selection_rechecks_remote_disable_before_leasing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_accounts(["token"], return_items=False)
            stale = AccountService(backend)
            updater = AccountService(backend)
            stale._ACCOUNT_SNAPSHOT_TTL_SECONDS = 0
            leased_token = stale._acquire_next_candidate_token()
            entered_selection = Event()
            original_list_ready = stale._list_ready_candidate_tokens
            outcome: dict[str, object] = {}

            def tracked_list_ready(*args, **kwargs):  # type: ignore[no-untyped-def]
                entered_selection.set()
                return original_list_ready(*args, **kwargs)

            def acquire_waiting_slot() -> None:
                try:
                    outcome["token"] = stale._acquire_next_candidate_token()
                except Exception as exc:  # pragma: no branch - asserted below
                    outcome["error"] = exc

            with patch.object(
                stale,
                "_list_ready_candidate_tokens",
                side_effect=tracked_list_ready,
            ):
                waiter = Thread(target=acquire_waiting_slot)
                waiter.start()
                self.assertTrue(entered_selection.wait(timeout=2))
                updater.update_account("token", {"status": "禁用"}, quiet=True)
                stale.release_image_slot(leased_token)
                waiter.join(timeout=2)

            self.assertFalse(waiter.is_alive())
            self.assertNotIn("token", outcome)
            self.assertIsInstance(outcome.get("error"), ImageAccountSelectionError)
            self.assertEqual(stale._image_inflight, {})

    def test_passive_refresh_does_not_overwrite_a_concurrent_local_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = BlockingSnapshotTestAccountRepository(
                root / "accounts.json",
                root / "auth_keys.json",
            )
            seed = AccountService(backend)
            seed.add_accounts(["existing-token"], return_items=False)
            service = AccountService(backend)
            service._ACCOUNT_SNAPSHOT_TTL_SECONDS = 0
            backend.block_next_snapshot = True
            observed: list[dict] = []

            reader = Thread(target=lambda: observed.extend(service.list_accounts()))
            reader.start()
            self.assertTrue(backend.snapshot_loaded.wait(timeout=2))
            service.add_accounts(["local-token"], return_items=False)
            backend.allow_snapshot_return.set()
            reader.join(timeout=2)

            self.assertFalse(reader.is_alive())
            self.assertEqual(
                {item["access_token"] for item in observed},
                {"existing-token", "local-token"},
            )
            self.assertEqual(
                {item["access_token"] for item in service.list_accounts()},
                {"existing-token", "local-token"},
            )

    def test_concurrent_stale_reads_share_one_passive_snapshot_load(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = BlockingSnapshotTestAccountRepository(
                root / "accounts.json",
                root / "auth_keys.json",
            )
            service = AccountService(backend)
            service._ACCOUNT_SNAPSHOT_TTL_SECONDS = 0
            baseline_loads = backend.snapshot_load_count
            backend.block_next_snapshot = True

            owner = Thread(target=service.list_accounts)
            owner.start()
            self.assertTrue(backend.snapshot_loaded.wait(timeout=2))

            followers = [Thread(target=service.list_accounts) for _ in range(8)]
            for follower in followers:
                follower.start()
            for follower in followers:
                follower.join(timeout=2)

            self.assertTrue(all(not follower.is_alive() for follower in followers))
            self.assertEqual(backend.snapshot_load_count, baseline_loads + 1)

            backend.allow_snapshot_return.set()
            owner.join(timeout=2)
            self.assertFalse(owner.is_alive())

    def test_git_account_snapshot_refresh_uses_a_longer_backend_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = BlockingSnapshotTestAccountRepository(
                root / "accounts.json",
                root / "auth_keys.json",
            )
            service = AccountService(backend)
            baseline_loads = backend.snapshot_load_count

            with patch.object(
                backend,
                "get_backend_info",
                return_value={"type": "git"},
            ):
                service._account_snapshot_checked_at = time.monotonic() - 10
                service.list_accounts()
                self.assertEqual(backend.snapshot_load_count, baseline_loads)

                service._account_snapshot_checked_at = time.monotonic() - 61
                service.list_accounts()
                self.assertEqual(backend.snapshot_load_count, baseline_loads + 1)

    def test_local_deletion_beats_concurrent_remote_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_accounts(["token"], return_items=False)
            remover = AccountService(backend)
            updater = AccountService(backend)

            updater.update_account("token", {"remote_only": "value"}, quiet=True)
            remover.delete_accounts(["token"], return_items=False)

            self.assertEqual(backend.load_accounts(), [])

    def test_bulk_delete_returns_authoritative_ids_and_progress_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AccountService(self._backend(Path(temp_dir)))
            service.add_account_items(
                [{"access_token": "token", "management_id": "acct_one"}],
                return_items=False,
            )
            management_id = service.get_account("token")["management_id"]
            progress_id = "bulk-delete-stages"
            service.init_refresh_progress(progress_id, 2)
            self.addCleanup(service.clean_refresh_progress, progress_id)
            stages: list[tuple[str, int, bool]] = []

            def record_stage(stage: str, total: int) -> None:
                service.update_refresh_progress_stage(progress_id, stage, stage)
                snapshot = service.get_refresh_progress(progress_id) or {}
                stages.append((str(snapshot.get("stage") or ""), total, bool(snapshot.get("done"))))

            result = service.delete_accounts(
                ["token", "already-missing"],
                return_items=False,
                progress_callback=record_stage,
            )

            self.assertEqual(result["removed"], 1)
            self.assertEqual(result["removed_ids"], [management_id])
            self.assertEqual(result["missing_tokens"], ["already-missing"])
            self.assertEqual(
                [stage for stage, _total, _done in stages],
                ["prepare_accounts", "save_accounts", "publish_results"],
            )
            self.assertTrue(all(not done for _stage, _total, done in stages))

    def test_auxiliary_log_failure_does_not_reverse_committed_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [
                    {"access_token": "delete-token", "management_id": "acct_delete"},
                    {"access_token": "update-token", "management_id": "acct_update"},
                ],
                return_items=False,
            )
            delete_id = service.get_account("delete-token")["management_id"]
            update_id = service.get_account("update-token")["management_id"]
            self.log_add.side_effect = RuntimeError("log unavailable")

            updated = service.update_accounts(
                ["update-token"],
                {"status": "\u7981\u7528"},
                quiet=False,
            )
            deleted = service.delete_accounts(["delete-token"], return_items=False)

            self.assertEqual(updated["updated_ids"], [update_id])
            self.assertEqual(deleted["removed_ids"], [delete_id])
            stored = {item["management_id"]: item for item in backend.load_accounts()}
            self.assertNotIn(delete_id, stored)
            self.assertEqual(stored[update_id]["status"], "\u7981\u7528")

    def test_local_deletion_also_deletes_concurrently_rotated_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [{"access_token": "old-token", "refresh_token": "refresh"}],
                return_items=False,
            )
            remover = AccountService(backend)
            rotator = AccountService(backend)

            rotator._apply_refreshed_tokens(
                "old-token",
                {"access_token": "new-token"},
                "test",
                expected_access_token="old-token",
                expected_refresh_token="refresh",
            )
            remover.delete_accounts(["old-token"], return_items=False)

            self.assertEqual(backend.load_accounts(), [])

    def test_remote_deletion_beats_stale_token_rotation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_account_items(
                [{"access_token": "old-token", "refresh_token": "refresh"}],
                return_items=False,
            )
            stale_rotator = AccountService(backend)
            remover = AccountService(backend)

            remover.delete_accounts(["old-token"], return_items=False)
            with self.assertRaises(RefreshCredentialsChangedError):
                stale_rotator._apply_refreshed_tokens(
                    "old-token",
                    {"access_token": "new-token"},
                    "test",
                    expected_access_token="old-token",
                    expected_refresh_token="refresh",
                )

            self.assertEqual(backend.load_accounts(), [])
            self.assertIsNone(stale_rotator.get_account("new-token"))
            self.assertNotIn("old-token", stale_rotator._token_aliases)

    def test_token_rotation_is_one_atomic_delete_and_upsert(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = RecordingTestAccountRepository(
                root / "accounts.json",
                root / "auth_keys.json",
            )
            service = AccountService(backend)
            service.add_account_items(
                [{"access_token": "old-token", "refresh_token": "refresh"}],
                return_items=False,
            )
            backend.account_mutations.clear()

            result = service._apply_refreshed_tokens(
                "old-token",
                {"access_token": "new-token", "refresh_token": "refresh-2"},
                "test",
                expected_access_token="old-token",
                expected_refresh_token="refresh",
            )

            self.assertEqual(result, "new-token")
            self.assertEqual(len(backend.account_mutations), 1)
            mutation = backend.account_mutations[0]
            self.assertEqual(tuple(mutation.delete_keys), ("old-token",))
            self.assertEqual(
                [item["access_token"] for item in mutation.upserts],
                ["new-token"],
            )
            self.assertEqual(
                [item["access_token"] for item in backend.load_accounts()],
                ["new-token"],
            )

    def test_terminal_refresh_failure_persists_explicit_refresh_token_invalidity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [{"access_token": "old-token", "refresh_token": "refresh-secret"}],
                return_items=False,
            )

            with (
                patch.object(
                    service,
                    "_request_access_token_refresh",
                    side_effect=TerminalRefreshTokenError(
                        400,
                        "invalid_grant",
                        "refresh-secret was revoked",
                    ),
                ),
                self.assertRaises(TerminalRefreshTokenError),
            ):
                service.refresh_access_token(
                    "old-token",
                    force=True,
                    raise_on_error=True,
                    remove_invalid=True,
                )

            account = service.get_account("old-token") or {}
            self.assertTrue(account.get("refresh_token_invalid_at"))
            self.assertNotIn("refresh-secret", str(account.get("last_token_refresh_error")))
            self.assertNotIn("refresh-secret", repr(self.log_add.call_args_list))
            self.assertEqual(account.get("status"), "正常")
            row = account_row(account, available=True, unlimited_quota=False)
            self.assertEqual(row["access_token_status"], "valid")
            self.assertEqual(row["refresh_token_status"], "invalid")

    def test_transient_refresh_failure_does_not_invalidate_refresh_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [{"access_token": "old-token", "refresh_token": "refresh-secret"}],
                return_items=False,
            )

            with (
                patch.object(
                    service,
                    "_request_access_token_refresh",
                    side_effect=OAuthRefreshError(503, "temporarily_unavailable", "try later"),
                ),
                self.assertRaises(OAuthRefreshError),
            ):
                service.refresh_access_token(
                    "old-token",
                    force=True,
                    raise_on_error=True,
                    remove_invalid=False,
                )

            account = service.get_account("old-token") or {}
            self.assertIsNone(account.get("refresh_token_invalid_at"))
            self.assertTrue(account.get("last_token_refresh_error_at"))

    def test_confirmed_access_token_rejection_and_terminal_rt_failure_invalidate_both(self) -> None:
        class RejectingBackend:
            def __init__(self, _access_token: str) -> None:
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            def get_user_info(self):
                raise InvalidAccessTokenError("access token rejected")

        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [{"access_token": "old-token", "refresh_token": "refresh-secret"}],
                return_items=False,
            )

            with (
                patch(
                    "services.openai_backend_api.OpenAIBackendAPI",
                    RejectingBackend,
                ),
                patch.object(
                    service,
                    "_request_access_token_refresh",
                    side_effect=TerminalRefreshTokenError(
                        400,
                        "invalid_grant",
                        "refresh-secret was revoked",
                    ),
                ),
                self.assertRaises(TerminalRefreshTokenError),
            ):
                service.fetch_remote_info("old-token", remove_invalid=False)

            account = service.get_account("old-token") or {}
            row = account_row(account, available=False, unlimited_quota=False)
            self.assertEqual(row["access_token_status"], "invalid")
            self.assertEqual(row["refresh_token_status"], "invalid")

    def test_successful_token_rotation_clears_invalidity_and_preserves_management_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [{"access_token": "old-token", "refresh_token": "refresh-secret"}],
                return_items=False,
            )
            before = service.get_account("old-token") or {}
            service.handle_invalid_token(
                "old-token",
                "old-check",
                error="old access token rejected",
                remove=False,
                expected_access_token="old-token",
                expected_refresh_token="refresh-secret",
                token_refresh_error="old refresh token rejected",
                refresh_token_terminal=True,
            )

            with patch.object(
                service,
                "_request_access_token_refresh",
                return_value={
                    "access_token": "new-token",
                    "refresh_token": "new-refresh-secret",
                    "id_token": "new-id-token",
                },
            ):
                active_token = service.refresh_access_token(
                    "old-token",
                    force=True,
                    raise_on_error=True,
                )

            account = service.get_account(active_token) or {}
            self.assertEqual(active_token, "new-token")
            self.assertEqual(account.get("management_id"), before.get("management_id"))
            self.assertIsNone(account.get("refresh_token_invalid_at"))
            self.assertTrue(account.get("last_token_refresh_at"))
            self.assertEqual(account.get("status"), "\u6b63\u5e38")
            self.assertIsNone(account.get("last_remote_check_result"))
            self.assertIsNone(account.get("last_remote_check_error"))
            self.assertIsNone(account.get("last_remote_check_error_at"))
            self.assertIsNone(account.get("last_remote_check_event"))
            row = account_row(account, available=True, unlimited_quota=False)
            self.assertEqual(row["access_token_status"], "valid")
            self.assertEqual(row["refresh_token_status"], "valid")

    def test_account_sync_uses_current_access_token_without_refresh_token_exchange(self) -> None:
        class AccountInfoBackend:
            requested_tokens: list[str] = []

            def __init__(self, access_token: str) -> None:
                self.access_token = access_token

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            def get_user_info(self) -> dict[str, object]:
                self.requested_tokens.append(self.access_token)
                return {
                    "status": "\u6b63\u5e38",
                    "quota": 3,
                    "image_quota_unknown": False,
                }

        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            expiring_token = _access_token(expires_at=int(time.time()) + 60)
            service.add_account_items(
                [{"access_token": expiring_token, "refresh_token": "refresh-secret"}],
                return_items=False,
            )

            with (
                patch(
                    "services.openai_backend_api.OpenAIBackendAPI",
                    AccountInfoBackend,
                ),
                patch.object(service, "_request_access_token_refresh") as request_refresh,
            ):
                result = service.sync_accounts_and_quota([expiring_token])

            self.assertEqual(result["synced"], 1)
            self.assertEqual(result["errors"], [])
            self.assertEqual(AccountInfoBackend.requested_tokens, [expiring_token])
            request_refresh.assert_not_called()

    def test_imported_refresh_token_clears_previous_terminal_invalidity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [{"access_token": "old-token", "refresh_token": "old-refresh"}],
                return_items=False,
            )
            service.update_account(
                "old-token",
                {"refresh_token_invalid_at": "2026-07-30T02:03:04+00:00"},
                quiet=True,
            )

            service.add_account_items(
                [{"access_token": "old-token", "refresh_token": "replacement-refresh"}],
                return_items=False,
            )

            account = service.get_account("old-token") or {}
            self.assertEqual(account.get("refresh_token"), "replacement-refresh")
            self.assertIsNone(account.get("refresh_token_invalid_at"))

    def test_reimporting_same_refresh_token_preserves_terminal_invalidity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [{"access_token": "old-token", "refresh_token": "same-refresh"}],
                return_items=False,
            )
            invalid_at = "2026-07-30T02:03:04+00:00"
            service.update_account(
                "old-token",
                {"refresh_token_invalid_at": invalid_at},
                quiet=True,
            )

            service.add_account_items(
                [{"access_token": "old-token", "refresh_token": "same-refresh"}],
                return_items=False,
            )
            service.update_account(
                "old-token",
                {"refresh_token": "same-refresh", "refresh_token_invalid_at": None},
                quiet=True,
            )

            account = service.get_account("old-token") or {}
            self.assertEqual(account.get("refresh_token"), "same-refresh")
            self.assertEqual(account.get("refresh_token_invalid_at"), invalid_at)

    def test_bulk_access_token_refresh_exchanges_credentials_without_syncing_quota(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [
                    {"access_token": "with-refresh", "refresh_token": "refresh-secret"},
                    {"access_token": "without-refresh"},
                    {"access_token": "failed-refresh", "refresh_token": "failing-secret"},
                ],
                return_items=False,
            )
            with_refresh = service.get_account("with-refresh") or {}
            without_refresh = service.get_account("without-refresh") or {}
            failed_refresh = service.get_account("failed-refresh") or {}

            def request_refresh(refresh_token: str, *_args, **_kwargs) -> dict[str, str]:
                if refresh_token == "failing-secret":
                    raise OAuthRefreshError(503, "temporarily_unavailable", "try later")
                return {
                    "access_token": "rotated-token",
                    "refresh_token": "rotated-refresh",
                    "id_token": "",
                }

            with (
                patch.object(
                    service,
                    "_request_access_token_refresh",
                    side_effect=request_refresh,
                ),
                patch.object(service, "fetch_remote_info") as fetch_remote_info,
            ):
                result = service.refresh_access_tokens(
                    ["with-refresh", "without-refresh", "failed-refresh"],
                )

            self.assertEqual(result["refreshed"], 1)
            self.assertEqual(result["skipped"], 0)
            self.assertEqual(result["updated_ids"], [with_refresh["management_id"]])
            errors_by_id = {item["id"]: item for item in result["errors"]}
            self.assertEqual(
                errors_by_id[without_refresh["management_id"]]["code"],
                "refresh_token_missing",
            )
            self.assertIn(failed_refresh["management_id"], errors_by_id)
            self.assertEqual(
                (service.get_account("rotated-token") or {}).get("management_id"),
                with_refresh["management_id"],
            )
            fetch_remote_info.assert_not_called()

    def test_bulk_access_token_refresh_skips_confirmed_invalid_refresh_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [{"access_token": "invalid-rt-account", "refresh_token": "revoked-secret"}],
                return_items=False,
            )
            service.update_account(
                "invalid-rt-account",
                {"refresh_token_invalid_at": "2026-07-30T02:03:04+00:00"},
                quiet=True,
            )
            account = service.get_account("invalid-rt-account") or {}

            with patch.object(service, "_request_access_token_refresh") as request_refresh:
                result = service.refresh_access_tokens(["invalid-rt-account"])

            self.assertEqual(result["refreshed"], 0)
            self.assertEqual(result["skipped"], 0)
            self.assertEqual(result["updated_ids"], [])
            self.assertEqual(len(result["errors"]), 1)
            self.assertEqual(result["errors"][0]["id"], account["management_id"])
            self.assertEqual(result["errors"][0]["code"], "refresh_token_invalid")
            request_refresh.assert_not_called()

    def test_bulk_access_token_refresh_counts_account_deleted_after_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            access_token = "deleted-before-refresh-secret"
            service.add_account_items(
                [{"access_token": access_token, "refresh_token": "refresh-secret"}],
                return_items=False,
            )
            progress_id = "deleted-before-refresh"
            service.init_refresh_progress(progress_id, 1)
            self.addCleanup(service.clean_refresh_progress, progress_id)

            service.delete_accounts([access_token], return_items=False)
            result = service.refresh_access_tokens([access_token], progress_id)
            progress = service.get_refresh_progress(progress_id) or {}

            self.assertEqual(result["errors"][0]["code"], "account_not_found")
            self.assertEqual(progress.get("processed"), 1)
            self.assertTrue(progress.get("done"))
            self.assertEqual(progress.get("status_counts", {}).get("\u5f02\u5e38"), 1)
            self.assertEqual(len(progress.get("events", [])), 1)
            self.assertEqual(progress["events"][0]["action"], "refresh_access_token")
            self.assertEqual(progress["events"][0]["status"], "failed")
            self.assertEqual(progress["events"][0]["message"], "account not found")
            self.assertNotIn(access_token, repr(progress))

    def test_account_sync_recovers_rejected_access_token_with_refresh_token(self) -> None:
        class RecoveringBackend:
            requested_tokens: list[str] = []

            def __init__(self, access_token: str) -> None:
                self.access_token = access_token

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            def get_user_info(self):
                self.requested_tokens.append(self.access_token)
                if self.access_token == "old-token":
                    raise InvalidAccessTokenError("access token rejected")
                return {
                    "status": "正常",
                    "quota": 3,
                    "image_quota_unknown": False,
                }

        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [{"access_token": "old-token", "refresh_token": "refresh-secret"}],
                return_items=False,
            )

            with (
                patch(
                    "services.openai_backend_api.OpenAIBackendAPI",
                    RecoveringBackend,
                ),
                patch.object(
                    service,
                    "_request_access_token_refresh",
                    return_value={
                        "access_token": "new-token",
                        "refresh_token": "rotated-refresh",
                        "id_token": "new-id-token",
                    },
                ) as exchange,
            ):
                result = service.sync_accounts_and_quota(["old-token"])

            self.assertEqual(result["synced"], 1)
            self.assertEqual(result["errors"], [])
            self.assertEqual(RecoveringBackend.requested_tokens, ["old-token", "new-token"])
            exchange.assert_called_once()
            account = service.get_account("new-token") or {}
            self.assertEqual(account.get("refresh_token"), "rotated-refresh")
            self.assertEqual(account.get("id_token"), "new-id-token")
            row = account_row(account, available=False, unlimited_quota=False)
            self.assertEqual(row["access_token_status"], "valid")
            self.assertEqual(row["refresh_token_status"], "valid")

    def test_background_renewal_rechecks_current_access_token_before_oauth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [{"access_token": "current-token", "refresh_token": "refresh-secret"}],
                return_items=False,
            )

            with patch.object(service, "_request_access_token_refresh") as request_refresh:
                result = service.renew_expiring_access_tokens(["current-token"])

            self.assertEqual(result["refreshed"], 0)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(result["errors"], [])
            request_refresh.assert_not_called()

    def test_background_renewal_scrubs_credentials_from_returned_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            expiring_token = _access_token(expires_at=int(time.time()) + 60)
            service.add_account_items(
                [
                    {
                        "access_token": expiring_token,
                        "refresh_token": "refresh-secret",
                    }
                ],
                return_items=False,
            )

            with patch.object(
                service,
                "_request_access_token_refresh",
                side_effect=TerminalRefreshTokenError(
                    400,
                    "invalid_grant",
                    "refresh-secret was revoked",
                ),
            ):
                result = service.renew_expiring_access_tokens([expiring_token])

            self.assertEqual(len(result["errors"]), 1)
            serialized = json.dumps(result["errors"])
            self.assertNotIn("refresh-secret", serialized)
            self.assertNotIn(expiring_token, serialized)
            self.assertIn("[credential]", serialized)

    def test_image_selection_does_not_force_a_second_preflight_token_exchange(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            service = AccountService(backend)
            service.add_account_items(
                [
                    {
                        "access_token": "image-token",
                        "refresh_token": "refresh-secret",
                        "quota": 10,
                        "image_quota_unknown": False,
                        "status": "正常",
                    }
                ],
                return_items=False,
            )
            account = service.get_account("image-token") or {}

            with (
                patch.object(
                    service,
                    "_acquire_next_candidate_token",
                    return_value="image-token",
                ),
                patch.object(service, "fetch_remote_info", return_value=account),
                patch.object(service, "refresh_access_token") as refresh_access_token,
            ):
                selected = service.get_available_access_token()

            self.assertEqual(selected, "image-token")
            refresh_access_token.assert_not_called()

    def test_conflict_retries_are_bounded_and_surface_the_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = AlwaysConflictingTestAccountRepository(
                root / "accounts.json",
                root / "auth_keys.json",
            )
            service = AccountService(backend)
            backend.force_conflicts = True

            with self.assertRaises(StorageRevisionConflictError):
                service.add_accounts(["token"], return_items=False)

            self.assertEqual(
                backend.conflict_count,
                AccountService._STORAGE_MUTATION_MAX_ATTEMPTS,
            )
            self.assertIsNone(service.get_account("token"))
            self.assertEqual(backend.load_accounts(), [])

            backend.force_conflicts = False
            service.add_accounts(["later-token"], return_items=False)
            self.assertEqual(
                [item["access_token"] for item in backend.load_accounts()],
                ["later-token"],
            )

    def test_generic_storage_failure_restores_the_last_durable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = ToggleFailingTestAccountRepository(
                root / "accounts.json",
                root / "auth_keys.json",
            )
            service = AccountService(backend)
            backend.fail_mutations = True

            with self.assertRaisesRegex(OSError, "storage unavailable"):
                service.add_accounts(["failed-token"], return_items=False)

            self.assertIsNone(service.get_account("failed-token"))
            self.assertEqual(backend.load_accounts(), [])

            backend.fail_mutations = False
            service.add_accounts(["later-token"], return_items=False)
            self.assertEqual(
                [item["access_token"] for item in backend.load_accounts()],
                ["later-token"],
            )

    def test_save_failure_does_not_recover_an_unrelated_pending_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = ToggleFailingTestAccountRepository(
                root / "accounts.json",
                root / "auth_keys.json",
            )
            service = AccountService(backend)
            service.add_accounts(["token"], return_items=False)
            service.update_account(
                "token",
                {
                    "last_remote_check_result": "pending",
                    "pending_auth_scope": "account",
                },
                quiet=True,
            )
            backend.fail_mutations = True

            with self.assertRaisesRegex(OSError, "storage unavailable"):
                service.add_accounts(["failed-token"], return_items=False)

            durable = backend.load_accounts()[0]
            self.assertEqual(durable["last_remote_check_result"], "pending")
            self.assertEqual(
                service.get_account("token")["last_remote_check_result"],
                "pending",
            )

    def test_conflict_snapshot_failure_restores_the_last_durable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = ConflictThenUnreadableTestAccountRepository(
                root / "accounts.json",
                root / "auth_keys.json",
            )
            service = AccountService(backend)
            backend.conflict_once = True

            with self.assertRaisesRegex(OSError, "snapshot unavailable"):
                service.add_accounts(["failed-token"], return_items=False)

            self.assertIsNone(service.get_account("failed-token"))
            backend.fail_snapshot_loads = False
            self.assertEqual(backend.load_accounts(), [])

    def test_failed_invalid_removal_keeps_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = ToggleFailingTestAccountRepository(
                root / "accounts.json",
                root / "auth_keys.json",
            )
            service = AccountService(backend)
            service.add_accounts(["token"], return_items=False)
            service._image_inflight["token"] = 1
            service._token_aliases["old-token"] = "token"
            service._index = 7
            backend.fail_mutations = True

            with self.assertRaisesRegex(OSError, "storage unavailable"):
                service._apply_invalid_token_state(
                    "token",
                    "test",
                    "invalid token",
                    remove=True,
                )

            self.assertIsNotNone(service.get_account("token"))
            self.assertEqual(service._image_inflight, {"token": 1})
            self.assertEqual(service._token_aliases, {"old-token": "token"})
            self.assertEqual(service._index, 7)

    def test_remote_deletion_discards_stale_refresh_error_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_accounts(["token"], return_items=False)
            stale = AccountService(backend)
            remover = AccountService(backend)
            remover.delete_accounts(["token"], return_items=False)
            self.log_add.reset_mock()

            recorded = stale._record_token_refresh_error(
                "token",
                "test",
                "refresh failed",
                expected_access_token="token",
                expected_refresh_token="",
            )

            self.assertFalse(recorded)
            self.assertIsNone(stale.get_account("token"))
            self.log_add.assert_not_called()

    def test_remote_deletion_discards_stale_remote_check_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_accounts(["token"], return_items=False)
            stale = AccountService(backend)
            remover = AccountService(backend)
            remover.delete_accounts(["token"], return_items=False)

            recorded = stale._record_remote_check_error(
                "token",
                "test",
                "check failed",
                expected_access_token="token",
                expected_refresh_token="",
            )

            self.assertFalse(recorded)
            self.assertIsNone(stale.get_account("token"))

    def test_remote_deletion_discards_stale_image_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_accounts(["token"], return_items=False)
            stale = AccountService(backend)
            remover = AccountService(backend)
            stale._image_inflight["token"] = 1
            remover.delete_accounts(["token"], return_items=False)

            result = stale.mark_image_result(
                "token",
                True,
                expected_access_token="token",
                expected_refresh_token="",
            )

            self.assertIsNone(result)
            self.assertEqual(stale._image_inflight, {})
            self.assertIsNone(stale.get_account("token"))

    def test_remote_deletion_does_not_schedule_stale_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = self._backend(Path(temp_dir))
            seed = AccountService(backend)
            seed.add_accounts(["token"], return_items=False)
            stale = AccountService(backend)
            remover = AccountService(backend)
            remover.delete_accounts(["token"], return_items=False)

            with patch.object(
                stale,
                "_schedule_account_refresh_after_image_failure",
            ) as schedule:
                result = stale.schedule_auth_verification(
                    "token",
                    "test",
                    expected_access_token="token",
                    expected_refresh_token="",
                    scope="image",
                )

            self.assertFalse(result)
            schedule.assert_not_called()


if __name__ == "__main__":
    unittest.main()
