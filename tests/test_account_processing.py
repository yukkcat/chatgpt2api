from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from services.account_processing import (
    AccountProcessingLimiter,
    account_processing_batch_slot,
    account_processing_slot,
)
from services.account_service import AccountService
from tests.support.account_repository import TestAccountRepository


class AccountProcessingLimiterTests(unittest.TestCase):
    def test_shared_limit_caps_distinct_workers(self) -> None:
        limiter = AccountProcessingLimiter()
        release = threading.Event()
        two_entered = threading.Event()
        lock = threading.Lock()
        active = 0
        maximum = 0

        def work() -> None:
            nonlocal active, maximum
            with limiter.slot():
                with lock:
                    active += 1
                    maximum = max(maximum, active)
                    if active == 2:
                        two_entered.set()
                try:
                    self.assertTrue(release.wait(2))
                finally:
                    with lock:
                        active -= 1

        with (
            mock.patch(
                "services.config.ConfigStore.account_processing_concurrency",
                new_callable=mock.PropertyMock,
                return_value=2,
            ),
            ThreadPoolExecutor(max_workers=6) as executor,
        ):
            futures = [executor.submit(work) for _ in range(6)]
            self.assertTrue(two_entered.wait(1))
            time.sleep(0.05)
            self.assertEqual(maximum, 2)
            release.set()
            for future in futures:
                future.result()

        self.assertEqual(maximum, 2)

    def test_nested_use_on_one_thread_consumes_one_slot(self) -> None:
        limiter = AccountProcessingLimiter()
        with mock.patch(
            "services.config.ConfigStore.account_processing_concurrency",
            new_callable=mock.PropertyMock,
            return_value=1,
        ):
            with limiter.slot():
                with limiter.slot():
                    pass

    def test_batch_slot_waits_for_remote_slot_at_concurrency_one(self) -> None:
        limiter = AccountProcessingLimiter()
        remote_entered = threading.Event()
        remote_release = threading.Event()
        batch_entered = threading.Event()

        def hold_remote_slot() -> None:
            with limiter.slot():
                remote_entered.set()
                self.assertTrue(remote_release.wait(2))

        def enter_batch() -> None:
            with limiter.batch_slot():
                batch_entered.set()

        with mock.patch(
            "services.config.ConfigStore.account_processing_concurrency",
            new_callable=mock.PropertyMock,
            return_value=1,
        ):
            remote = threading.Thread(target=hold_remote_slot)
            remote.start()
            self.assertTrue(remote_entered.wait(1))

            batch = threading.Thread(target=enter_batch)
            batch.start()
            self.assertFalse(batch_entered.wait(0.1))

            remote_release.set()
            self.assertTrue(batch_entered.wait(1))
            remote.join(1)
            batch.join(1)

        self.assertFalse(remote.is_alive())
        self.assertFalse(batch.is_alive())

    def test_batch_slot_nested_regular_slot_is_reentrant(self) -> None:
        limiter = AccountProcessingLimiter()
        with mock.patch(
            "services.config.ConfigStore.account_processing_concurrency",
            new_callable=mock.PropertyMock,
            return_value=1,
        ):
            with limiter.batch_slot():
                with limiter.slot():
                    with limiter.batch_slot():
                        with limiter._condition:
                            self.assertEqual(limiter._active, 1)

            # Exercise the public module-level batch entry point as well.
            with account_processing_batch_slot():
                with account_processing_slot():
                    with account_processing_batch_slot():
                        pass


class AccountProcessingBatchMutationTests(unittest.TestCase):
    @staticmethod
    def _service(tmp_dir: str) -> AccountService:
        storage = TestAccountRepository(Path(tmp_dir) / "accounts.json")
        storage.save_accounts([
            {"access_token": "token-a", "refresh_token": "refresh-a"},
            {"access_token": "token-b", "refresh_token": "refresh-b"},
        ])
        return AccountService(storage)

    def test_local_batch_mutation_waits_for_remote_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            finished = threading.Event()
            result: dict = {}

            def mutate() -> None:
                result.update(service.update_accounts(
                    ["token-a", "token-b"],
                    {"group_id": "group-a"},
                ))
                finished.set()

            with mock.patch(
                "services.config.ConfigStore.account_processing_concurrency",
                new_callable=mock.PropertyMock,
                return_value=1,
            ):
                with account_processing_slot():
                    worker = threading.Thread(target=mutate)
                    worker.start()
                    self.assertFalse(finished.wait(0.1))

                self.assertTrue(finished.wait(1))
                worker.join(1)

            self.assertFalse(worker.is_alive())
            self.assertEqual(len(result["updated_ids"]), 2)

    def test_local_batch_mutation_still_saves_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            with mock.patch.object(
                service,
                "_save_accounts",
                wraps=service._save_accounts,
            ) as save_accounts:
                result = service.update_accounts(
                    ["token-a", "token-b"],
                    {"group_id": "group-a"},
                )

            self.assertEqual(len(result["updated_ids"]), 2)
            self.assertEqual(save_accounts.call_count, 1)


class AccountProcessingOAuthTests(unittest.TestCase):
    @staticmethod
    def _service(tmp_dir: str, accounts: list[dict]) -> AccountService:
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
            lock = threading.Lock()
            calls = 0

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

            with mock.patch.object(
                service,
                "_request_access_token_refresh",
                side_effect=exchange,
            ):
                with ThreadPoolExecutor(max_workers=8) as executor:
                    futures = [
                        executor.submit(
                            service.force_refresh_access_token,
                            "token-a",
                        )
                        for _ in range(8)
                    ]
                    self.assertTrue(entered.wait(1))
                    time.sleep(0.05)
                    self.assertEqual(calls, 1)
                    release.set()
                    self.assertEqual(
                        [future.result() for future in futures],
                        ["token-a"] * 8,
                    )

    def test_distinct_oauth_exchanges_run_in_parallel_within_shared_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            accounts = [
                {
                    "access_token": f"token-{index}",
                    "refresh_token": f"refresh-{index}",
                }
                for index in range(6)
            ]
            service = self._service(tmp_dir, accounts)
            lock = threading.Lock()
            release = threading.Event()
            three_entered = threading.Event()
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
                        if active == 3:
                            three_entered.set()
                    try:
                        self_test.assertTrue(release.wait(2))
                        return Response(f"token-{index}", refresh_token)
                    finally:
                        with lock:
                            active -= 1

                def close(self) -> None:
                    return None

            self_test = self
            with (
                mock.patch(
                    "services.config.ConfigStore.account_processing_concurrency",
                    new_callable=mock.PropertyMock,
                    return_value=3,
                ),
                mock.patch(
                    "curl_cffi.requests.Session",
                    side_effect=lambda **_kwargs: Session(),
                ),
                ThreadPoolExecutor(max_workers=6) as executor,
            ):
                futures = [
                    executor.submit(
                        service.force_refresh_access_token,
                        f"token-{index}",
                    )
                    for index in range(6)
                ]
                self.assertTrue(three_entered.wait(1))
                time.sleep(0.05)
                self.assertEqual(maximum, 3)
                release.set()
                for future in futures:
                    future.result()

            self.assertEqual(maximum, 3)

    def test_account_sync_worker_pool_uses_configured_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            accounts = [
                {"access_token": f"token-{index}", "refresh_token": ""}
                for index in range(4)
            ]
            service = self._service(tmp_dir, accounts)
            lock = threading.Lock()
            release = threading.Event()
            two_entered = threading.Event()
            active = 0
            maximum = 0
            result: dict = {}

            def fetch(access_token: str, *_args, **_kwargs) -> dict:
                nonlocal active, maximum
                with lock:
                    active += 1
                    maximum = max(maximum, active)
                    if active == 2:
                        two_entered.set()
                try:
                    self.assertTrue(release.wait(2))
                    return service.get_account(access_token) or {}
                finally:
                    with lock:
                        active -= 1

            def sync() -> None:
                result.update(
                    service.sync_accounts_and_quota(
                        [account["access_token"] for account in accounts]
                    )
                )

            with (
                mock.patch(
                    "services.config.ConfigStore.account_processing_concurrency",
                    new_callable=mock.PropertyMock,
                    return_value=2,
                ),
                mock.patch.object(service, "fetch_remote_info", side_effect=fetch),
            ):
                worker = threading.Thread(target=sync)
                worker.start()
                self.assertTrue(two_entered.wait(1))
                time.sleep(0.05)
                self.assertEqual(maximum, 2)
                release.set()
                worker.join(3)

            self.assertFalse(worker.is_alive())
            self.assertEqual(result["synced"], 4)

    def test_account_sync_errors_include_backend_account_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "email": "account@example.com",
            }])

            with mock.patch.object(
                service,
                "fetch_remote_info",
                side_effect=RuntimeError("quota failed"),
            ):
                result = service.sync_accounts_and_quota(["token-a"])

            error = result["errors"][0]
            self.assertTrue(error["account_id"])
            self.assertEqual(error["account_label"], "account@example.com")
            self.assertNotEqual(error["account_id"], error["token"])

    def test_image_verification_scheduler_uses_configured_limit(self) -> None:
        class DeferredThread:
            started: list[object] = []

            def __init__(self, *, target, **_options: object) -> None:
                self.target = target

            def start(self) -> None:
                self.started.append(self.target)

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [
                {"access_token": "token-a", "quota": 5},
                {"access_token": "token-b", "quota": 5},
            ])
            refreshed: list[str] = []
            DeferredThread.started = []

            with (
                mock.patch(
                    "services.config.ConfigStore.account_processing_concurrency",
                    new_callable=mock.PropertyMock,
                    return_value=1,
                ),
                mock.patch("services.account_service.Thread", DeferredThread),
                mock.patch.object(
                    service,
                    "_refresh_account_after_image_failure",
                    side_effect=refreshed.append,
                ),
            ):
                service._schedule_account_refresh_after_image_failure("token-a")
                service._schedule_account_refresh_after_image_failure("token-b")

                self.assertEqual(len(DeferredThread.started), 1)
                DeferredThread.started.pop(0)()
                self.assertEqual(len(DeferredThread.started), 1)
                DeferredThread.started.pop(0)()

            self.assertEqual(refreshed, ["token-a", "token-b"])

    def test_image_generation_slots_keep_their_independent_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir, [{
                "access_token": "token-a",
                "quota": 5,
            }])
            service._image_inflight["token-a"] = 1

            with (
                mock.patch(
                    "services.config.ConfigStore.account_processing_concurrency",
                    new_callable=mock.PropertyMock,
                    return_value=1,
                ),
                mock.patch(
                    "services.config.ConfigStore.image_account_concurrency",
                    new_callable=mock.PropertyMock,
                    return_value=2,
                ),
            ):
                self.assertEqual(
                    service._list_available_candidate_tokens(),
                    ["token-a"],
                )


if __name__ == "__main__":
    unittest.main()
