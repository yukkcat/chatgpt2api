from __future__ import annotations

import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import services.account_service as account_service_module
from services.account_service import AccountService, ImageAccountSelectionError
from tests.support.account_repository import TestAccountRepository


class ImageAccountSlotDeadlineTests(unittest.TestCase):
    @staticmethod
    def _service(root: Path) -> AccountService:
        storage = TestAccountRepository(root / "accounts.json")
        storage.save_accounts([{"access_token": "token-a", "quota": 5}])
        return AccountService(storage)

    @staticmethod
    def _fill_only_slot(service: AccountService) -> None:
        with service._image_slot_condition:
            service._image_inflight["token-a"] = 1

    def test_full_slot_expires_without_mutating_account_or_inflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))
            self._fill_only_slot(service)
            account_before = service.get_account("token-a")
            inflight_before = dict(service._image_inflight)

            with mock.patch.object(
                account_service_module.config.__class__,
                "image_account_concurrency",
                new_callable=mock.PropertyMock,
                return_value=1,
            ):
                started_at = time.monotonic()
                with self.assertRaises(ImageAccountSelectionError) as raised:
                    service.get_available_access_token(
                        deadline_monotonic=time.monotonic() + 0.1,
                    )
                elapsed = time.monotonic() - started_at

            self.assertLess(elapsed, 0.75)
            self.assertEqual(raised.exception.kind, "deadline_exceeded")
            self.assertEqual(raised.exception.code, "task_interrupted")
            self.assertEqual(service.get_account("token-a"), account_before)
            self.assertEqual(service._image_inflight, inflight_before)

    def test_releasing_slot_before_deadline_wakes_waiter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))
            waiter_blocked = threading.Event()

            class ObservableCondition(threading.Condition):
                def wait(self, timeout: float | None = None) -> bool:
                    waiter_blocked.set()
                    return super().wait(timeout)

            service._image_slot_condition = ObservableCondition(service._lock)
            self._fill_only_slot(service)

            with (
                mock.patch.object(
                    account_service_module.config.__class__,
                    "image_account_concurrency",
                    new_callable=mock.PropertyMock,
                    return_value=1,
                ),
                mock.patch.object(
                    service,
                    "fetch_remote_info",
                    side_effect=lambda token, _event, **_kwargs: service.get_account(token),
                ),
                ThreadPoolExecutor(max_workers=1) as executor,
            ):
                future = executor.submit(
                    service.get_available_access_token,
                    deadline_monotonic=time.monotonic() + 2.0,
                )
                self.assertTrue(waiter_blocked.wait(timeout=0.75))

                service.release_image_slot("token-a")

                self.assertEqual(future.result(timeout=0.75), "token-a")

            self.assertEqual(service._image_inflight, {"token-a": 1})
            service.release_image_slot("token-a")
            self.assertEqual(service._image_inflight, {})

    def test_busy_account_at_deadline_is_not_reported_as_quota_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = TestAccountRepository(Path(temp_dir) / "accounts.json")
            storage.save_accounts([
                {"access_token": "token-a", "quota": 5},
                {"access_token": "token-b", "quota": 5},
            ])
            service = AccountService(storage)
            service._image_inflight["token-b"] = 1
            limited_account = dict(service.get_account("token-a") or {})
            limited_account["status"] = "限流"

            with (
                mock.patch.object(
                    account_service_module.config.__class__,
                    "image_account_concurrency",
                    new_callable=mock.PropertyMock,
                    return_value=1,
                ),
                mock.patch.object(service, "fetch_remote_info", return_value=limited_account),
            ):
                with self.assertRaises(ImageAccountSelectionError) as raised:
                    service.get_available_access_token(
                        deadline_monotonic=time.monotonic() + 0.05,
                    )

            self.assertEqual(raised.exception.kind, "deadline_exceeded")
            self.assertEqual(raised.exception.code, "task_interrupted")
            self.assertEqual(raised.exception.status_code, 503)
            self.assertEqual(service._image_inflight, {"token-b": 1})

    def test_remote_validation_crossing_deadline_releases_acquired_slot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))

            def slow_remote_info(token: str, _event: str, **_kwargs) -> dict:
                time.sleep(0.08)
                return dict(service.get_account(token) or {})

            with mock.patch.object(service, "fetch_remote_info", side_effect=slow_remote_info):
                with self.assertRaises(ImageAccountSelectionError) as raised:
                    service.get_available_access_token(
                        deadline_monotonic=time.monotonic() + 0.03,
                    )

            self.assertEqual(raised.exception.kind, "deadline_exceeded")
            self.assertEqual(raised.exception.code, "task_interrupted")
            self.assertEqual(service._image_inflight, {})


if __name__ == "__main__":
    unittest.main()
