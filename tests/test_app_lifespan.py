from __future__ import annotations

import asyncio
import importlib
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch


app_module = importlib.import_module("api.app")
log_service_module = importlib.import_module("services.log_service")
retention_cleanup_module = importlib.import_module("services.retention_cleanup_service")
support_module = importlib.import_module("api.support")


class AppLifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_cleans_logs_before_syncing_dashboard_metrics(self) -> None:
        calls: list[str] = []
        fake_thread = SimpleNamespace(join=lambda timeout=None: None)

        with (
            patch.object(app_module, "_configure_threadpool"),
            patch.object(
                app_module.retention_cleanup_coordinator,
                "run_startup_automatic",
                side_effect=lambda **_kwargs: calls.append("cleanup") or {"errors": {}},
            ),
            patch.object(
                app_module.dashboard_metrics_service,
                "sync_from_log_service",
                side_effect=lambda _logs: calls.append("sync"),
            ),
            patch.object(app_module.account_service, "cleanup_auto_remove_accounts"),
            patch.object(app_module, "start_account_lifecycle_watcher", return_value=fake_thread),
            patch.object(app_module, "start_retention_cleanup_scheduler", return_value=fake_thread),
            patch.object(app_module.image_task_service, "start") as image_tasks_start,
            patch.object(app_module.image_task_service, "shutdown") as image_tasks_shutdown,
            patch.object(
                app_module.image_task_service,
                "shutdown_cancel_pending_and_wait",
            ) as image_tasks_shutdown_cancel_pending,
            patch.object(app_module.backup_service, "start"),
            patch.object(app_module.backup_service, "stop"),
        ):
            app = app_module.create_app()
            async with app.router.lifespan_context(app):
                self.assertEqual(calls, ["cleanup", "sync"])

        self.assertEqual(calls, ["cleanup", "sync", "sync"])
        image_tasks_start.assert_called_once_with()
        image_tasks_shutdown.assert_not_called()
        image_tasks_shutdown_cancel_pending.assert_called_once_with()

    async def test_shutdown_bounds_retention_cleanup_wait(self) -> None:
        join_called = threading.Event()
        lifespan_entered = asyncio.Event()
        begin_shutdown = asyncio.Event()
        watcher_thread = SimpleNamespace(join=lambda timeout=None: None)
        join_timeouts: list[float | None] = []
        shutdown_timeout = 0.05

        class ControlledCleanupThread:
            def join(self, timeout=None) -> None:
                join_timeouts.append(timeout)
                join_called.set()
                if timeout is not None:
                    threading.Event().wait(timeout)

        cleanup_thread = ControlledCleanupThread()

        with (
            patch.object(app_module, "_configure_threadpool"),
            patch.object(
                app_module.retention_cleanup_coordinator,
                "run_startup_automatic",
                return_value={"errors": {}},
            ),
            patch.object(app_module.dashboard_metrics_service, "sync_from_log_service"),
            patch.object(app_module.account_service, "cleanup_auto_remove_accounts"),
            patch.object(app_module, "start_account_lifecycle_watcher", return_value=watcher_thread),
            patch.object(app_module, "start_retention_cleanup_scheduler", return_value=cleanup_thread),
            patch.object(app_module, "RETENTION_SHUTDOWN_TIMEOUT_SECS", shutdown_timeout),
            patch.object(app_module.image_task_service, "start"),
            patch.object(app_module.image_task_service, "shutdown_cancel_pending_and_wait"),
            patch.object(app_module.backup_service, "start"),
            patch.object(app_module.backup_service, "stop"),
        ):
            app = app_module.create_app()

            async def run_lifespan() -> None:
                async with app.router.lifespan_context(app):
                    lifespan_entered.set()
                    await begin_shutdown.wait()

            lifespan_task = asyncio.create_task(run_lifespan())
            await asyncio.wait_for(lifespan_entered.wait(), timeout=3)
            begin_shutdown.set()
            self.assertTrue(await asyncio.to_thread(join_called.wait, 3))
            await asyncio.wait_for(lifespan_task, timeout=2)

        self.assertEqual(join_timeouts, [shutdown_timeout])

    async def test_shutdown_waits_for_active_image_tasks_off_the_event_loop(self) -> None:
        shutdown_started = threading.Event()
        release_shutdown = threading.Event()
        shutdown_finished = threading.Event()
        shutdown_thread_ids: list[int] = []
        lifespan_entered = asyncio.Event()
        begin_shutdown = asyncio.Event()
        fake_thread = SimpleNamespace(join=lambda timeout=None: None)
        event_loop_thread_id = threading.get_ident()

        def controlled_image_shutdown() -> None:
            shutdown_thread_ids.append(threading.get_ident())
            shutdown_started.set()
            release_shutdown.wait(timeout=3)
            shutdown_finished.set()

        with (
            patch.object(app_module, "_configure_threadpool"),
            patch.object(
                app_module.retention_cleanup_coordinator,
                "run_startup_automatic",
                return_value={"errors": {}},
            ),
            patch.object(app_module.dashboard_metrics_service, "sync_from_log_service"),
            patch.object(app_module.account_service, "cleanup_auto_remove_accounts"),
            patch.object(app_module, "start_account_lifecycle_watcher", return_value=fake_thread),
            patch.object(app_module, "start_retention_cleanup_scheduler", return_value=fake_thread),
            patch.object(app_module.image_task_service, "start"),
            patch.object(
                app_module.image_task_service,
                "shutdown_cancel_pending_and_wait",
                side_effect=controlled_image_shutdown,
            ),
            patch.object(app_module.backup_service, "start"),
            patch.object(app_module.backup_service, "stop"),
        ):
            app = app_module.create_app()

            async def run_lifespan() -> None:
                async with app.router.lifespan_context(app):
                    lifespan_entered.set()
                    await begin_shutdown.wait()

            lifespan_task = asyncio.create_task(run_lifespan())
            await asyncio.wait_for(lifespan_entered.wait(), timeout=3)
            begin_shutdown.set()
            try:
                self.assertTrue(await asyncio.to_thread(shutdown_started.wait, 3))
                await asyncio.sleep(0)
                self.assertFalse(lifespan_task.done())
                self.assertNotEqual(shutdown_thread_ids, [event_loop_thread_id])
            finally:
                release_shutdown.set()
            await asyncio.wait_for(lifespan_task, timeout=1)

        self.assertTrue(shutdown_finished.is_set())


class LogCleanupSchedulerTests(unittest.TestCase):
    def test_scheduler_stops_before_its_first_cleanup(self) -> None:
        class StopImmediately:
            def __init__(self) -> None:
                self.waits: list[float] = []
                self.stopped = False

            def is_set(self) -> bool:
                return self.stopped

            def wait(self, timeout: float) -> bool:
                self.waits.append(timeout)
                self.stopped = True
                return True

        stop_event = StopImmediately()
        coordinator = retention_cleanup_module.RetentionCleanupCoordinator(interval_seconds=60)
        with (
            patch.object(retention_cleanup_module, "retention_cleanup_coordinator", coordinator),
            patch.object(coordinator, "run_automatic") as cleanup,
        ):
            log_service_module._auto_cleanup_worker(stop_event)

        self.assertEqual(len(stop_event.waits), 1)
        self.assertLessEqual(stop_event.waits[0], retention_cleanup_module.RETENTION_STOP_POLL_SECS)
        cleanup.assert_not_called()


class AccountWatcherTests(unittest.TestCase):
    def test_each_cycle_syncs_limited_accounts_and_only_renews_expiring_access_tokens(self) -> None:
        class TwoCycleStopEvent:
            def __init__(self) -> None:
                self.waits: list[float] = []

            def is_set(self) -> bool:
                return len(self.waits) >= 2

            def wait(self, timeout: float) -> bool:
                self.waits.append(timeout)
                return self.is_set()

        class AccountServiceDouble:
            def __init__(self) -> None:
                self.sync_calls: list[list[str]] = []
                self.renew_calls: list[list[str]] = []

            @staticmethod
            def list_pending_auth_verification_tokens() -> list[str]:
                return []

            @staticmethod
            def list_limited_tokens() -> list[str]:
                return ["limited-token", "limited-and-expiring-token"]

            @staticmethod
            def list_normal_tokens() -> list[str]:
                return ["healthy-token"]

            @staticmethod
            def list_expiring_access_tokens() -> list[str]:
                return ["expiring-token", "limited-and-expiring-token"]

            def sync_accounts_and_quota(self, tokens: list[str]) -> None:
                self.sync_calls.append(tokens)

            def renew_expiring_access_tokens(self, tokens: list[str]) -> dict[str, object]:
                self.renew_calls.append(tokens)
                return {"refreshed": len(tokens), "errors": []}

        stop_event = TwoCycleStopEvent()
        account_service = AccountServiceDouble()
        with (
            patch.object(
                type(support_module.config),
                "refresh_account_interval_minute",
                new_callable=PropertyMock,
                side_effect=(2, 7),
            ) as refresh_interval,
            patch.object(support_module, "account_service", account_service),
        ):
            thread = support_module.start_account_lifecycle_watcher(stop_event)
            thread.join(timeout=2)

        self.assertFalse(thread.is_alive())
        self.assertEqual(stop_event.waits, [120, 420])
        self.assertEqual(refresh_interval.call_count, 2)
        self.assertEqual(
            account_service.sync_calls,
            [
                ["limited-token", "limited-and-expiring-token"],
                ["limited-token", "limited-and-expiring-token"],
            ],
        )
        self.assertEqual(
            account_service.renew_calls,
            [
                ["expiring-token", "limited-and-expiring-token"],
                ["expiring-token", "limited-and-expiring-token"],
            ],
        )

    def test_expiring_limited_account_is_renewed_before_current_token_is_synced(self) -> None:
        class StopAfterOneCycle:
            def __init__(self) -> None:
                self.waits: list[float] = []

            def is_set(self) -> bool:
                return bool(self.waits)

            def wait(self, timeout: float) -> bool:
                self.waits.append(timeout)
                return True

        class AccountServiceDouble:
            def __init__(self) -> None:
                self.events: list[str] = []
                self.tokens_rotated = False
                self.sync_calls: list[list[str]] = []
                self.renew_calls: list[list[str]] = []

            @staticmethod
            def list_pending_auth_verification_tokens() -> list[str]:
                return []

            def list_expiring_access_tokens(self) -> list[str]:
                self.events.append("list_expiring")
                return ["expiring-token", "limited-and-expiring-token"]

            def renew_expiring_access_tokens(self, tokens: list[str]) -> dict[str, object]:
                self.events.append("renew")
                self.renew_calls.append(tokens)
                self.tokens_rotated = True
                return {"refreshed": len(tokens), "errors": []}

            def list_limited_tokens(self) -> list[str]:
                self.events.append("list_limited")
                rotating_token = (
                    "limited-rotated-token"
                    if self.tokens_rotated
                    else "limited-and-expiring-token"
                )
                return ["limited-token", rotating_token]

            @staticmethod
            def list_normal_tokens() -> list[str]:
                return ["healthy-token"]

            def sync_accounts_and_quota(self, tokens: list[str]) -> None:
                self.events.append("sync")
                self.sync_calls.append(tokens)

        stop_event = StopAfterOneCycle()
        account_service = AccountServiceDouble()
        with (
            patch.object(
                type(support_module.config),
                "refresh_account_interval_minute",
                new_callable=PropertyMock,
                return_value=2,
            ),
            patch.object(support_module, "account_service", account_service),
        ):
            thread = support_module.start_account_lifecycle_watcher(stop_event)
            thread.join(timeout=2)

        self.assertFalse(thread.is_alive())
        self.assertEqual(stop_event.waits, [120])
        self.assertEqual(
            account_service.renew_calls,
            [["expiring-token", "limited-and-expiring-token"]],
        )
        self.assertEqual(
            account_service.sync_calls,
            [["limited-token", "limited-rotated-token"]],
        )
        self.assertLess(
            account_service.events.index("renew"),
            account_service.events.index("list_limited"),
        )
        self.assertLess(
            account_service.events.index("renew"),
            account_service.events.index("sync"),
        )


if __name__ == "__main__":
    unittest.main()
