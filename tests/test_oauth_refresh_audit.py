from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from services.account_processing import AccountProcessingLimiter
from services.account_service import (
    AccountService,
    RefreshCredentialsChangedError,
    TerminalRefreshTokenError,
)
from services.image_failure import InvalidAccessTokenError, image_failure
from tests.support.account_repository import TestAccountRepository


class OAuthRefreshAuditTests(unittest.TestCase):
    def _service(self, tmp_dir: str, accounts: list[dict]) -> AccountService:
        storage = TestAccountRepository(Path(tmp_dir) / "accounts.json")
        storage.save_accounts(accounts)
        return AccountService(storage)

    def test_same_credentials_share_one_oauth_exchange(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
            }])
            entered = threading.Event()
            release = threading.Event()
            calls = 0
            lock = threading.Lock()

            def exchange(refresh_token: str, _account: dict) -> dict[str, str]:
                nonlocal calls
                with lock:
                    calls += 1
                entered.set()
                self.assertTrue(release.wait(2))
                return {
                    "access_token": "token-a",
                    "refresh_token": refresh_token,
                    "id_token": "",
                }

            with mock.patch.object(service, "_request_access_token_refresh", side_effect=exchange):
                with ThreadPoolExecutor(max_workers=8) as pool:
                    futures = [
                        pool.submit(service.refresh_access_token, "token-a", force=True)
                        for _ in range(8)
                    ]
                    self.assertTrue(entered.wait(1))
                    time.sleep(0.05)
                    self.assertEqual(calls, 1)
                    release.set()
                    self.assertEqual([future.result() for future in futures], ["token-a"] * 8)

    def test_non_force_caller_joins_existing_forced_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
            }])
            entered = threading.Event()
            release = threading.Event()

            def exchange(refresh_token: str, _account: dict) -> dict[str, str]:
                entered.set()
                self.assertTrue(release.wait(2))
                return {
                    "access_token": "token-b",
                    "refresh_token": refresh_token,
                    "id_token": "",
                }

            with (
                mock.patch.object(service, "_request_access_token_refresh", side_effect=exchange),
                mock.patch.object(
                    service,
                    "_token_needs_refresh",
                    side_effect=lambda _token, *, force=False: force,
                ),
                ThreadPoolExecutor(max_workers=2) as pool,
            ):
                forced = pool.submit(service.refresh_access_token, "token-a", force=True)
                self.assertTrue(entered.wait(1))
                regular = pool.submit(service.refresh_access_token, "token-a")
                time.sleep(0.05)
                self.assertFalse(regular.done())
                release.set()
                self.assertEqual(forced.result(), "token-b")
                self.assertEqual(regular.result(), "token-b")

    def test_oauth_http_concurrency_uses_shared_account_processing_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            accounts = [
                {"access_token": f"token-{index}", "refresh_token": f"refresh-{index}"}
                for index in range(8)
            ]
            service = self._service(tmp_dir, accounts)
            lock = threading.Lock()
            release = threading.Event()
            four_entered = threading.Event()
            active = 0
            maximum = 0

            class Response:
                status_code = 200
                text = json.dumps({"access_token": "placeholder"})

                def __init__(self, access_token: str, refresh_token: str) -> None:
                    self._payload = {
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                    }

                def json(self) -> dict[str, str]:
                    return dict(self._payload)

            class Session:
                def post(self, _url: str, *, data: dict, **_kwargs) -> Response:
                    nonlocal active, maximum
                    refresh_token = str(data["refresh_token"])
                    index = refresh_token.rsplit("-", 1)[-1]
                    with lock:
                        active += 1
                        maximum = max(maximum, active)
                        if active >= 4:
                            four_entered.set()
                    try:
                        if not release.wait(2):
                            raise TimeoutError("audit release timed out")
                        return Response(f"token-{index}", refresh_token)
                    finally:
                        with lock:
                            active -= 1

                def close(self) -> None:
                    return None

            with (
                mock.patch(
                    "services.config.ConfigStore.account_processing_concurrency",
                    new_callable=mock.PropertyMock,
                    return_value=4,
                ),
                mock.patch(
                    "services.account_processing.account_processing_limiter",
                    AccountProcessingLimiter(),
                ),
                mock.patch("curl_cffi.requests.Session", side_effect=lambda **_kwargs: Session()),
            ):
                with ThreadPoolExecutor(max_workers=8) as pool:
                    futures = [
                        pool.submit(
                            service.force_refresh_access_token,
                            f"token-{index}",
                        )
                        for index in range(8)
                    ]
                    self.assertTrue(four_entered.wait(1))
                    time.sleep(0.05)
                    self.assertEqual(maximum, 4)
                    release.set()
                    for future in futures:
                        future.result()

    def test_rotated_credentials_join_their_existing_refresh_flight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
            }])
            first_entered = threading.Event()
            second_entered = threading.Event()
            release_first = threading.Event()
            release_second = threading.Event()
            calls = {"refresh-a": 0, "refresh-b": 0}

            def exchange(refresh_token: str, _account: dict) -> dict[str, str]:
                calls[refresh_token] += 1
                if refresh_token == "refresh-a":
                    first_entered.set()
                    self.assertTrue(release_first.wait(2))
                    raise TerminalRefreshTokenError(401, "invalid_grant")
                second_entered.set()
                self.assertTrue(release_second.wait(2))
                return {
                    "access_token": "token-b",
                    "refresh_token": "refresh-b",
                    "id_token": "",
                }

            with (
                mock.patch.object(service, "_request_access_token_refresh", side_effect=exchange),
                ThreadPoolExecutor(max_workers=2) as pool,
            ):
                old_credentials = pool.submit(service.refresh_access_token, "token-a", force=True)
                self.assertTrue(first_entered.wait(1))
                service.update_account("token-a", {"refresh_token": "refresh-b"}, quiet=True)
                new_credentials = pool.submit(service.refresh_access_token, "token-a", force=True)
                self.assertTrue(second_entered.wait(1))
                release_first.set()
                time.sleep(0.05)
                refresh_b_calls_while_in_flight = calls["refresh-b"]
                release_second.set()
                self.assertEqual(refresh_b_calls_while_in_flight, 1)
                self.assertEqual(old_credentials.result(), "token-b")
                self.assertEqual(new_credentials.result(), "token-b")

            self.assertEqual(calls, {"refresh-a": 1, "refresh-b": 1})

    def test_structured_terminal_oauth_errors_are_not_limited_to_400_or_401(self) -> None:
        terminal_cases = (
            (403, "invalid_grant", ""),
            (422, "refresh_token_invalidated", ""),
            (403, "", "Your session has ended."),
        )
        for status_code, error_code, description in terminal_cases:
            with self.subTest(status_code=status_code, error_code=error_code):
                self.assertTrue(
                    AccountService._is_terminal_refresh_error(
                        status_code,
                        error_code,
                        description,
                    )
                )

        for status_code in (408, 429, 500, 503):
            with self.subTest(transient_status_code=status_code):
                self.assertFalse(
                    AccountService._is_terminal_refresh_error(
                        status_code,
                        "invalid_grant",
                        "Your session has ended.",
                    )
                )

    def test_restart_preserves_pending_and_resume_schedules_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "status": "\u6b63\u5e38",
                "last_remote_check_result": "pending",
                "last_remote_check_event": "image_failure",
                "pending_auth_scope": "image",
            }])
            self.assertEqual(service.list_pending_auth_verification_tokens(), ["token-a"])
            self.assertFalse(service._is_account_selectable(service.get_account("token-a") or {}, allow_limited=True))
            with mock.patch.object(service, "_schedule_account_refresh_after_image_failure", return_value=True) as schedule:
                self.assertEqual(service.resume_pending_auth_verifications(), 1)
            schedule.assert_called_once_with("token-a")

    def test_stale_refresh_snapshot_cannot_mark_current_account_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "status": "\u6b63\u5e38",
            }])
            service.update_account("token-a", {"refresh_token": "refresh-b"}, quiet=True)
            service.mark_image_result(
                "token-a",
                False,
                failure=image_failure("auth_invalid"),
                expected_access_token="token-a",
                expected_refresh_token="refresh-a",
            )
            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("status"), "\u6b63\u5e38")
            self.assertNotEqual(account.get("last_remote_check_result"), "pending")
            self.assertEqual(account.get("fail"), 0)

    def test_pending_verification_uses_credentials_captured_before_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "status": "\u6b63\u5e38",
                "last_remote_check_result": "pending",
                "last_remote_check_event": "image_failure",
                "pending_auth_scope": "image",
            }])

            class Backend:
                def __init__(self, _access_token: str) -> None:
                    pass

                def __enter__(self) -> "Backend":
                    return self

                def __exit__(self, *_args: object) -> None:
                    return None

                def get_user_info(self) -> dict:
                    service.update_account("token-a", {"refresh_token": "refresh-b"}, quiet=True)
                    raise InvalidAccessTokenError("token invalidated")

            with (
                mock.patch.object(
                    service,
                    "force_refresh_access_token",
                    return_value="token-a",
                ) as refresh,
                mock.patch.object(
                    service,
                    "_schedule_account_refresh_after_image_failure",
                    return_value=True,
                ) as schedule,
                mock.patch("services.openai_backend_api.OpenAIBackendAPI", Backend),
            ):
                service._verify_pending_auth("token-a", "image_failure")

            refresh.assert_not_called()
            schedule.assert_called_once_with("token-a", force=True)
            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("refresh_token"), "refresh-b")
            self.assertEqual(account.get("status"), "\u6b63\u5e38")
            self.assertEqual(account.get("last_remote_check_result"), "pending")

    def test_remote_info_retries_when_credentials_change_during_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "status": "\u6b63\u5e38",
            }])
            requests = 0

            class Backend:
                def __init__(self, _access_token: str) -> None:
                    pass

                def __enter__(self) -> "Backend":
                    return self

                def __exit__(self, *_args: object) -> None:
                    return None

                def get_user_info(self) -> dict:
                    nonlocal requests
                    requests += 1
                    if requests == 1:
                        service.update_account("token-a", {"refresh_token": "refresh-b"}, quiet=True)
                        raise InvalidAccessTokenError("token invalidated")
                    return {"status": "\u6b63\u5e38", "quota": 3}

            with (
                mock.patch.object(service, "force_refresh_access_token", return_value="token-a") as refresh,
                mock.patch("services.openai_backend_api.OpenAIBackendAPI", Backend),
            ):
                result = service.fetch_remote_info("token-a", "audit")

            self.assertEqual(requests, 2)
            refresh.assert_not_called()
            self.assertEqual((result or {}).get("refresh_token"), "refresh-b")
            self.assertEqual((result or {}).get("status"), "\u6b63\u5e38")

    def test_stale_remote_success_cannot_clear_new_pending_auth_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "",
                "status": "\u6b63\u5e38",
            }])
            self_test = self

            class Backend:
                def __init__(self, _access_token: str) -> None:
                    pass

                def __enter__(self) -> "Backend":
                    return self

                def __exit__(self, *_args: object) -> None:
                    return None

                def get_user_info(self) -> dict:
                    self_test.assertTrue(
                        service.schedule_auth_verification(
                            "token-a",
                            "image_failure",
                            expected_access_token="token-a",
                            expected_refresh_token="",
                            remove_invalid=False,
                        )
                    )
                    return {"status": "\u6b63\u5e38", "quota": 3}

            with (
                mock.patch.object(
                    service,
                    "_schedule_account_refresh_after_image_failure",
                    return_value=True,
                ),
                mock.patch("services.openai_backend_api.OpenAIBackendAPI", Backend),
            ):
                result = service.fetch_remote_info("token-a", "audit")

            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("last_remote_check_result"), "pending")
            self.assertEqual((result or {}).get("last_remote_check_result"), "pending")

    def test_active_auth_verification_rechecks_newer_pending_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "",
                "status": "\u6b63\u5e38",
            }])
            self_test = self
            entered = threading.Event()
            release = threading.Event()
            calls = 0
            calls_lock = threading.Lock()

            class Backend:
                def __init__(self, _access_token: str) -> None:
                    pass

                def __enter__(self) -> "Backend":
                    return self

                def __exit__(self, *_args: object) -> None:
                    return None

                def get_user_info(self) -> dict:
                    nonlocal calls
                    with calls_lock:
                        calls += 1
                        current_call = calls
                    if current_call == 1:
                        entered.set()
                        self_test.assertTrue(release.wait(2))
                    return {"status": "\u6b63\u5e38", "quota": 3}

            with mock.patch("services.openai_backend_api.OpenAIBackendAPI", Backend):
                self.assertTrue(service.schedule_auth_verification("token-a", "first"))
                self.assertTrue(entered.wait(1))
                self.assertTrue(service.schedule_auth_verification("token-a", "second"))
                release.set()

                deadline = time.time() + 2
                while time.time() < deadline:
                    account = service.get_account("token-a") or {}
                    with service._image_failure_refresh_lock:
                        busy = bool(
                            service._image_failure_refresh_active
                            or service._image_failure_refresh_pending
                        )
                    if calls >= 2 and not busy and account.get("last_remote_check_result") == "ok":
                        break
                    time.sleep(0.01)

            account = service.get_account("token-a") or {}
            self.assertEqual(calls, 2)
            self.assertEqual(account.get("last_remote_check_result"), "ok")

    def test_stale_remote_error_cannot_overwrite_new_pending_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "",
                "status": "\u6b63\u5e38",
            }])
            self_test = self
            entered = threading.Event()
            release = threading.Event()

            class Backend:
                def __init__(self, _access_token: str) -> None:
                    pass

                def __enter__(self) -> "Backend":
                    return self

                def __exit__(self, *_args: object) -> None:
                    return None

                def get_user_info(self) -> dict:
                    entered.set()
                    self_test.assertTrue(release.wait(2))
                    raise RuntimeError("stale network error")

            with (
                mock.patch.object(
                    service,
                    "_schedule_account_refresh_after_image_failure",
                    return_value=True,
                ),
                mock.patch("services.openai_backend_api.OpenAIBackendAPI", Backend),
            ):
                self.assertTrue(service.schedule_auth_verification("token-a", "first"))
                worker = threading.Thread(
                    target=service._verify_pending_auth,
                    args=("token-a", "first"),
                )
                worker.start()
                self.assertTrue(entered.wait(1))
                self.assertTrue(service.schedule_auth_verification("token-a", "second"))
                release.set()
                worker.join(2)
                self.assertFalse(worker.is_alive())

            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("last_remote_check_result"), "pending")
            self.assertEqual(account.get("last_remote_check_event"), "second")
            self.assertIsNone(account.get("last_remote_check_error"))

    def test_deleted_account_is_not_returned_by_stale_remote_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "",
                "status": "\u6b63\u5e38",
            }])

            class Backend:
                def __init__(self, _access_token: str) -> None:
                    pass

                def __enter__(self) -> "Backend":
                    return self

                def __exit__(self, *_args: object) -> None:
                    return None

                def get_user_info(self) -> dict:
                    service.delete_accounts(["token-a"])
                    return {"status": "\u6b63\u5e38", "quota": 3}

            with mock.patch("services.openai_backend_api.OpenAIBackendAPI", Backend):
                with self.assertRaises(RefreshCredentialsChangedError):
                    service.fetch_remote_info("token-a", "audit")

    def test_singleflight_terminal_refresh_marks_rt_invalid_without_removing_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "status": "\u6b63\u5e38",
            }])
            entered = threading.Event()
            release = threading.Event()

            def exchange(_refresh_token: str, _account: dict) -> dict[str, str]:
                entered.set()
                self.assertTrue(release.wait(2))
                raise TerminalRefreshTokenError(401, "invalid_grant")

            with mock.patch.object(service, "_request_access_token_refresh", side_effect=exchange):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    owner = pool.submit(
                        service.force_refresh_access_token,
                        "token-a",
                    )
                    self.assertTrue(entered.wait(1))
                    waiter = pool.submit(
                        service.force_refresh_access_token,
                        "token-a",
                    )
                    time.sleep(0.05)
                    release.set()
                    with self.assertRaises(TerminalRefreshTokenError):
                        owner.result()
                    with self.assertRaises(TerminalRefreshTokenError):
                        waiter.result()

            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("status"), "\u6b63\u5e38")
            self.assertTrue(account.get("refresh_token_invalid_at"))


    def test_async_auth_verification_preserves_remove_policy_snapshot(self) -> None:
        for explicit_remove, global_remove, should_exist in (
            (False, True, True),
            (True, False, False),
        ):
            with self.subTest(explicit_remove=explicit_remove, global_remove=global_remove):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    service = self._service(tmp_dir, [{
                        "access_token": "token-a",
                        "refresh_token": "",
                        "status": "正常",
                    }])

                    class Backend:
                        def __init__(self, _access_token: str) -> None:
                            pass

                        def __enter__(self) -> "Backend":
                            return self

                        def __exit__(self, *_args: object) -> None:
                            return None

                        def get_user_info(self) -> dict:
                            raise InvalidAccessTokenError("token revoked")

                    with mock.patch.object(
                        service,
                        "_schedule_account_refresh_after_image_failure",
                        return_value=True,
                    ):
                        service.schedule_auth_verification(
                            "token-a",
                            "audit",
                            remove_invalid=explicit_remove,
                        )

                    with (
                        mock.patch(
                            "services.config.ConfigStore.auto_remove_invalid_accounts",
                            new_callable=mock.PropertyMock,
                            return_value=global_remove,
                        ),
                        mock.patch("services.openai_backend_api.OpenAIBackendAPI", Backend),
                    ):
                        service._verify_pending_auth("token-a", "audit")

                    account = service.get_account("token-a")
                    self.assertEqual(account is not None, should_exist)
                    if account is not None:
                        self.assertEqual(account.get("status"), "异常")

    def test_keep_account_policy_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "",
                "status": "\u6b63\u5e38",
            }])
            with mock.patch.object(
                service,
                "_schedule_account_refresh_after_image_failure",
                return_value=True,
            ):
                service.schedule_auth_verification(
                    "token-a",
                    "audit",
                    remove_invalid=False,
                    scope="image",
                )

            reloaded = AccountService(
                TestAccountRepository(Path(tmp_dir) / "accounts.json")
            )
            pending = reloaded.get_account("token-a") or {}
            self.assertEqual(pending.get("last_remote_check_result"), "pending")
            self.assertIs(pending.get("pending_auth_remove_invalid"), False)

            class Backend:
                def __init__(self, _access_token: str) -> None:
                    pass

                def __enter__(self) -> "Backend":
                    return self

                def __exit__(self, *_args: object) -> None:
                    return None

                def get_user_info(self) -> dict:
                    raise InvalidAccessTokenError("token revoked")

            with (
                mock.patch(
                    "services.config.ConfigStore.auto_remove_invalid_accounts",
                    new_callable=mock.PropertyMock,
                    return_value=True,
                ),
                mock.patch("services.openai_backend_api.OpenAIBackendAPI", Backend),
            ):
                reloaded._verify_pending_auth("token-a", "audit")

            account = reloaded.get_account("token-a") or {}
            self.assertEqual(account.get("status"), "\u5f02\u5e38")
            self.assertIsNone(account.get("pending_auth_remove_invalid"))

    def test_token_rotation_deduplicates_pending_and_active_auth_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "status": "正常",
            }])
            service._image_failure_refresh_pending.append("token-a")
            service._image_failure_refresh_pending_set.add("token-a")
            service._image_failure_refresh_active.add("token-a")
            service._image_failure_refresh_started_at["token-a"] = 1.0

            service._apply_refreshed_tokens(
                "token-a",
                {"access_token": "token-b", "refresh_token": "refresh-b"},
                "audit",
                expected_access_token="token-a",
                expected_refresh_token="refresh-a",
            )

            self.assertEqual(list(service._image_failure_refresh_pending), ["token-b"])
            self.assertEqual(service._image_failure_refresh_pending_set, {"token-b"})
            self.assertNotIn("token-a", service._image_failure_refresh_started_at)
            self.assertIn("token-b", service._image_failure_refresh_started_at)
            with mock.patch.object(service, "_start_pending_image_failure_refreshes"):
                self.assertTrue(
                    service._schedule_account_refresh_after_image_failure(
                        "token-b", force=True
                    )
                )
            self.assertEqual(list(service._image_failure_refresh_pending), ["token-b"])

    def test_token_rotation_deduplicates_a_running_auth_recovery_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "status": "\u6b63\u5e38",
            }])
            entered = threading.Event()
            release = threading.Event()
            calls: list[str] = []

            def verify(token: str) -> None:
                calls.append(token)
                entered.set()
                self.assertTrue(release.wait(2))

            with mock.patch.object(
                service,
                "_refresh_account_after_image_failure",
                side_effect=verify,
            ):
                self.assertTrue(
                    service._schedule_account_refresh_after_image_failure(
                        "token-a", force=True
                    )
                )
                self.assertTrue(entered.wait(1))
                service._apply_refreshed_tokens(
                    "token-a",
                    {"access_token": "token-b", "refresh_token": "refresh-b"},
                    "audit",
                    expected_access_token="token-a",
                    expected_refresh_token="refresh-a",
                )
                self.assertTrue(
                    service._schedule_account_refresh_after_image_failure(
                        "token-b", force=True
                    )
                )
                release.set()
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    with service._image_failure_refresh_lock:
                        if not service._image_failure_refresh_active:
                            break
                    time.sleep(0.01)

            self.assertEqual(calls, ["token-a"])
            self.assertEqual(service._image_failure_refresh_active, set())
            self.assertEqual(list(service._image_failure_refresh_pending), [])

    def test_pending_auth_account_is_not_counted_as_normal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [
                {
                    "access_token": "token-a",
                    "status": "正常",
                    "last_remote_check_result": "pending",
                    "pending_auth_scope": "image",
                },
                {"access_token": "token-b", "status": "正常"},
            ])

            self.assertEqual(service.list_normal_tokens(), ["token-b"])


if __name__ == "__main__":
    unittest.main()
