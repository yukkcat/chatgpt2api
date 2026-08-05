from __future__ import annotations

import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from services import image_service, log_service
from services.retention_cleanup_service import RetentionCleanupCoordinator


def _database_url(directory: str) -> str:
    return f"sqlite:///{(Path(directory) / 'application.db').as_posix()}"


class RetentionCleanupCoordinatorTests(unittest.TestCase):
    def test_combined_cleanup_preserves_result_contract(self) -> None:
        calls: list[tuple[str, int, bool]] = []

        def logs(days: int, dry_run: bool) -> dict[str, int | bool]:
            calls.append(("logs", days, dry_run))
            return {"removed": 2, "kept": 3, "removed_size_bytes": 20, "dry_run": dry_run}

        def images(days: int, dry_run: bool) -> dict[str, int | bool]:
            calls.append(("images", days, dry_run))
            return {"removed": 1, "removed_size_bytes": 10, "dry_run": dry_run}

        coordinator = RetentionCleanupCoordinator(log_runner=logs, image_runner=images)
        result = coordinator.run_retention(
            log_retention_days=7,
            image_retention_days=9,
            dry_run=True,
        )

        self.assertEqual(calls, [("logs", 7, True), ("images", 9, True)])
        self.assertEqual(result["total_removed"], 3)
        self.assertEqual(result["total_size_bytes"], 30)
        self.assertEqual(result["logs"]["retention_days"], 7)
        self.assertEqual(result["images"]["retention_days"], 9)
        self.assertTrue(result["dry_run"])

    def test_log_and_image_cleanup_cannot_overlap(self) -> None:
        first_entered = threading.Event()
        release_first = threading.Event()
        image_entered = threading.Event()

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            first_entered.set()
            release_first.wait(1)
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        def images(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            image_entered.set()
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        coordinator = RetentionCleanupCoordinator(log_runner=logs, image_runner=images)
        log_thread = threading.Thread(target=coordinator.run_logs, args=(7,))
        image_attempted = threading.Event()

        def run_images() -> None:
            image_attempted.set()
            coordinator.run_images(7)

        image_thread = threading.Thread(target=run_images)

        log_thread.start()
        self.assertTrue(first_entered.wait(1))
        image_thread.start()
        self.assertTrue(image_attempted.wait(1))
        self.assertFalse(image_entered.wait(0.05))
        release_first.set()
        log_thread.join(1)
        image_thread.join(1)

        self.assertFalse(log_thread.is_alive())
        self.assertFalse(image_thread.is_alive())
        self.assertTrue(image_entered.is_set())

    def test_cleanup_to_target_cannot_overlap_retention_cleanup(self) -> None:
        retention_entered = threading.Event()
        release_retention = threading.Event()
        target_entered = threading.Event()

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            retention_entered.set()
            release_retention.wait(1)
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        def target(target_free_mb: int, dry_run: bool) -> dict[str, int | bool]:
            target_entered.set()
            return {"removed": 0, "target_free_mb": target_free_mb, "dry_run": dry_run}

        coordinator = RetentionCleanupCoordinator(log_runner=logs, image_target_runner=target)
        retention_thread = threading.Thread(target=coordinator.run_logs, args=(7,))
        target_thread = threading.Thread(
            target=coordinator.cleanup_images_to_target,
            args=(500,),
            kwargs={"dry_run": True},
        )

        retention_thread.start()
        self.assertTrue(retention_entered.wait(1))
        target_thread.start()
        self.assertFalse(target_entered.wait(0.05))
        release_retention.set()
        retention_thread.join(1)
        target_thread.join(1)

        self.assertFalse(retention_thread.is_alive())
        self.assertFalse(target_thread.is_alive())
        self.assertTrue(target_entered.is_set())

    def test_automatic_cleanup_isolates_log_failure(self) -> None:
        image_calls: list[tuple[int, bool]] = []

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            raise RuntimeError("log cleanup failed")

        def images(days: int, dry_run: bool) -> dict[str, int | bool]:
            image_calls.append((days, dry_run))
            return {"removed": 1, "removed_size_bytes": 10, "dry_run": False}

        coordinator = RetentionCleanupCoordinator(log_runner=logs, image_runner=images)
        result = coordinator.run_automatic(enforce_image_free_space=False)

        self.assertEqual(len(image_calls), 1)
        self.assertEqual(result["errors"], {"logs": "log cleanup failed"})
        self.assertEqual(result["images"]["removed"], 1)
        status = coordinator.runtime_status()
        self.assertFalse(status["running"])
        self.assertIsNotNone(status["last_started_at"])
        self.assertIsNotNone(status["last_finished_at"])
        self.assertEqual(status["last_removed"], {"logs": 0, "images": 1})
        self.assertEqual(status["last_error"], {"logs": "log cleanup failed", "images": None})

    def test_runtime_status_reports_cleanup_while_it_is_running(self) -> None:
        entered = threading.Event()
        release = threading.Event()

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            entered.set()
            release.wait(1)
            return {"removed": 2, "removed_size_bytes": 20, "dry_run": False}

        def images(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        coordinator = RetentionCleanupCoordinator(log_runner=logs, image_runner=images)
        thread = threading.Thread(
            target=coordinator.run_automatic,
            kwargs={"enforce_image_free_space": False},
        )
        thread.start()
        self.assertTrue(entered.wait(1))

        status = coordinator.runtime_status()
        self.assertTrue(status["running"])
        self.assertIsNotNone(status["last_started_at"])
        self.assertIsNone(status["last_finished_at"])

        release.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertFalse(coordinator.runtime_status()["running"])

    def test_notify_wakes_scheduler_without_waiting_for_periodic_deadline(self) -> None:
        cleanup_ran = threading.Event()

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            cleanup_ran.set()
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        def images(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        coordinator = RetentionCleanupCoordinator(
            log_runner=logs,
            image_runner=images,
            image_space_runner=lambda: None,
            interval_seconds=60,
        )
        stop_event = threading.Event()
        thread = coordinator.start_scheduler(stop_event)
        self.assertIsNotNone(coordinator.runtime_status()["next_run_at"])

        coordinator.notify_retention_change()
        self.assertTrue(cleanup_ran.wait(1))

        stop_event.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertIsNone(coordinator.runtime_status()["next_run_at"])

    def test_notification_during_cleanup_is_not_lost(self) -> None:
        first_entered = threading.Event()
        release_first = threading.Event()
        second_ran = threading.Event()
        calls = 0

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            nonlocal calls
            calls += 1
            if calls == 1:
                first_entered.set()
                release_first.wait(1)
            else:
                second_ran.set()
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        def images(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        coordinator = RetentionCleanupCoordinator(
            log_runner=logs,
            image_runner=images,
            image_space_runner=lambda: None,
            interval_seconds=60,
        )
        stop_event = threading.Event()
        thread = coordinator.start_scheduler(stop_event)

        coordinator.notify_retention_change()
        self.assertTrue(first_entered.wait(1))
        coordinator.notify_retention_change()
        release_first.set()
        self.assertTrue(second_ran.wait(1))

        stop_event.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())

    def test_scheduler_keeps_periodic_cleanup_as_a_safety_net(self) -> None:
        cleanup_ran = threading.Event()

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            cleanup_ran.set()
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        def images(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        coordinator = RetentionCleanupCoordinator(
            log_runner=logs,
            image_runner=images,
            image_space_runner=lambda: None,
            interval_seconds=1,
        )
        stop_event = threading.Event()
        thread = coordinator.start_scheduler(stop_event)

        self.assertFalse(cleanup_ran.wait(0.1))
        self.assertTrue(cleanup_ran.wait(1.2))

        stop_event.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())

    def test_scheduler_recovers_after_an_unexpected_loop_error(self) -> None:
        first_cleanup_finished = threading.Event()
        recovered_cleanup_ran = threading.Event()
        image_space_calls = 0

        def image_space() -> dict[str, object] | None:
            nonlocal image_space_calls
            image_space_calls += 1
            if image_space_calls == 1:
                first_cleanup_finished.set()
                return {"cleanup": {}}
            recovered_cleanup_ran.set()
            return None

        coordinator = RetentionCleanupCoordinator(
            log_runner=lambda _days, _dry_run: {
                "removed": 0,
                "removed_size_bytes": 0,
                "dry_run": False,
            },
            image_runner=lambda _days, _dry_run: {
                "removed": 0,
                "removed_size_bytes": 0,
                "dry_run": False,
            },
            image_space_runner=image_space,
            interval_seconds=60,
        )
        stop_event = threading.Event()
        thread = coordinator.start_scheduler(stop_event)

        coordinator.notify_retention_change()
        self.assertTrue(first_cleanup_finished.wait(1))
        coordinator.notify_retention_change()
        recovered = recovered_cleanup_ran.wait(1)
        thread_alive_after_recovery = thread.is_alive()
        stop_event.set()
        thread.join(1)

        self.assertTrue(recovered)
        self.assertTrue(thread_alive_after_recovery)
        self.assertFalse(thread.is_alive())
        self.assertEqual(image_space_calls, 2)

    def test_stop_after_scheduler_wait_prevents_cleanup_start(self) -> None:
        cleanup_ran = threading.Event()
        wait_entered = threading.Event()
        release_wait = threading.Event()

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            cleanup_ran.set()
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        coordinator = RetentionCleanupCoordinator(
            log_runner=logs,
            image_runner=lambda _days, _dry_run: {
                "removed": 0,
                "removed_size_bytes": 0,
                "dry_run": False,
            },
            image_space_runner=lambda: None,
            interval_seconds=60,
        )
        stop_event = threading.Event()

        def controlled_wait(_stop_event: threading.Event, _deadline: float) -> bool:
            wait_entered.set()
            release_wait.wait(1)
            return True

        with patch.object(coordinator, "_wait_for_cleanup", side_effect=controlled_wait):
            thread = coordinator.start_scheduler(stop_event)
            self.assertTrue(wait_entered.wait(1))
            stop_event.set()
            release_wait.set()
            thread.join(1)

        self.assertFalse(thread.is_alive())
        self.assertFalse(cleanup_ran.is_set())

    def test_stop_while_scheduler_waits_for_cleanup_lock_prevents_cleanup_start(self) -> None:
        cleanup_ran = threading.Event()
        automatic_entered = threading.Event()

        class ObservedCoordinator(RetentionCleanupCoordinator):
            def run_automatic(
                self,
                *,
                enforce_image_free_space: bool,
                stop_event: threading.Event | None = None,
            ) -> dict[str, object]:
                automatic_entered.set()
                return super().run_automatic(
                    enforce_image_free_space=enforce_image_free_space,
                    stop_event=stop_event,
                )

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            cleanup_ran.set()
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        coordinator = ObservedCoordinator(
            log_runner=logs,
            image_runner=lambda _days, _dry_run: {
                "removed": 0,
                "removed_size_bytes": 0,
                "dry_run": False,
            },
            image_space_runner=lambda: None,
            interval_seconds=60,
        )
        stop_event = threading.Event()
        thread: threading.Thread | None = None

        coordinator._run_lock.acquire()
        try:
            thread = coordinator.start_scheduler(stop_event)
            coordinator.notify_retention_change()
            self.assertTrue(automatic_entered.wait(1))
            stop_event.set()
        finally:
            coordinator._run_lock.release()

        assert thread is not None
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertFalse(cleanup_ran.is_set())

    def test_stop_during_log_cleanup_skips_remaining_cleanup_steps(self) -> None:
        log_cleanup_entered = threading.Event()
        release_log_cleanup = threading.Event()
        image_cleanup_ran = threading.Event()
        image_space_cleanup_ran = threading.Event()

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            log_cleanup_entered.set()
            release_log_cleanup.wait(1)
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        def images(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            image_cleanup_ran.set()
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        coordinator = RetentionCleanupCoordinator(
            log_runner=logs,
            image_runner=images,
            image_space_runner=lambda: image_space_cleanup_ran.set() or None,
            interval_seconds=60,
        )
        stop_event = threading.Event()
        thread = coordinator.start_scheduler(stop_event)

        coordinator.notify_retention_change()
        self.assertTrue(log_cleanup_entered.wait(1))
        stop_event.set()
        release_log_cleanup.set()
        thread.join(1)

        self.assertFalse(thread.is_alive())
        self.assertFalse(image_cleanup_ran.is_set())
        self.assertFalse(image_space_cleanup_ran.is_set())
        self.assertFalse(coordinator.runtime_status()["running"])

    def test_shared_runtime_status_is_visible_from_every_coordinator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database_url = _database_url(tmp)
            first = RetentionCleanupCoordinator(
                log_runner=lambda _days, _dry_run: {
                    "removed": 2,
                    "removed_size_bytes": 20,
                    "dry_run": False,
                },
                image_runner=lambda _days, _dry_run: {
                    "removed": 1,
                    "removed_size_bytes": 10,
                    "dry_run": False,
                },
                database_url=database_url,
            )
            second = RetentionCleanupCoordinator(database_url=database_url)

            first.run_automatic(enforce_image_free_space=False)

            status = second.runtime_status()
            self.assertFalse(status["running"])
            self.assertIsNotNone(status["last_started_at"])
            self.assertIsNotNone(status["last_finished_at"])
            self.assertEqual(status["last_removed"], {"logs": 2, "images": 1})

    def test_startup_cleanup_is_deduplicated_across_coordinators(self) -> None:
        calls = 0

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            nonlocal calls
            calls += 1
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        with tempfile.TemporaryDirectory() as tmp:
            database_url = _database_url(tmp)
            first = RetentionCleanupCoordinator(
                log_runner=logs,
                image_runner=lambda _days, _dry_run: {
                    "removed": 0,
                    "removed_size_bytes": 0,
                    "dry_run": False,
                },
                database_url=database_url,
            )
            second = RetentionCleanupCoordinator(
                log_runner=logs,
                image_runner=lambda _days, _dry_run: {
                    "removed": 0,
                    "removed_size_bytes": 0,
                    "dry_run": False,
                },
                database_url=database_url,
            )

            first_result = first.run_startup_automatic(enforce_image_free_space=False)
            second_result = second.run_startup_automatic(enforce_image_free_space=False)

            self.assertNotIn("skipped", first_result)
            self.assertTrue(second_result["skipped"])
            self.assertEqual(calls, 1)

    def test_notification_during_startup_cleanup_is_not_delayed(self) -> None:
        startup_entered = threading.Event()
        release_startup = threading.Event()
        follow_up_cleanup_ran = threading.Event()
        calls = 0

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            nonlocal calls
            calls += 1
            if calls == 1:
                startup_entered.set()
                release_startup.wait(1)
            else:
                follow_up_cleanup_ran.set()
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        with tempfile.TemporaryDirectory() as tmp:
            database_url = _database_url(tmp)
            startup = RetentionCleanupCoordinator(
                log_runner=logs,
                image_runner=lambda _days, _dry_run: {
                    "removed": 0,
                    "removed_size_bytes": 0,
                    "dry_run": False,
                },
                image_space_runner=lambda: None,
                interval_seconds=60,
                database_url=database_url,
            )
            follower = RetentionCleanupCoordinator(database_url=database_url)
            startup_thread = threading.Thread(
                target=startup.run_startup_automatic,
                kwargs={"enforce_image_free_space": False},
            )

            startup_thread.start()
            self.assertTrue(startup_entered.wait(1))
            follower.notify_retention_change()
            release_startup.set()
            startup_thread.join(1)
            self.assertFalse(startup_thread.is_alive())

            stop_event = threading.Event()
            scheduler_thread = startup.start_scheduler(stop_event)
            follow_up_ran = follow_up_cleanup_ran.wait(1)
            stop_event.set()
            scheduler_thread.join(1)

            self.assertTrue(follow_up_ran)
            self.assertFalse(scheduler_thread.is_alive())
            self.assertEqual(calls, 2)

    def test_non_leader_notification_wakes_shared_scheduler_once(self) -> None:
        cleanup_ran = threading.Event()
        calls_lock = threading.Lock()
        calls = 0

        def logs(_days: int, _dry_run: bool) -> dict[str, int | bool]:
            nonlocal calls
            with calls_lock:
                calls += 1
            cleanup_ran.set()
            return {"removed": 0, "removed_size_bytes": 0, "dry_run": False}

        with tempfile.TemporaryDirectory() as tmp:
            database_url = _database_url(tmp)
            coordinators = [
                RetentionCleanupCoordinator(
                    log_runner=logs,
                    image_runner=lambda _days, _dry_run: {
                        "removed": 0,
                        "removed_size_bytes": 0,
                        "dry_run": False,
                    },
                    image_space_runner=lambda: None,
                    interval_seconds=60,
                    database_url=database_url,
                )
                for _ in range(2)
            ]
            stop_events = [threading.Event(), threading.Event()]
            threads = [
                coordinator.start_scheduler(stop_event)
                for coordinator, stop_event in zip(coordinators, stop_events)
            ]
            deadline = time.monotonic() + 1
            follower: RetentionCleanupCoordinator | None = None
            while time.monotonic() < deadline:
                active = [coordinator for coordinator in coordinators if coordinator._scheduler_active]
                if len(active) == 1:
                    follower = next(coordinator for coordinator in coordinators if coordinator is not active[0])
                    break
                time.sleep(0.01)
            self.assertIsNotNone(follower)

            assert follower is not None
            follower.notify_retention_change()
            self.assertTrue(cleanup_ran.wait(1))
            time.sleep(0.1)

            for stop_event in stop_events:
                stop_event.set()
            for thread in threads:
                thread.join(1)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(calls, 1)

    def test_settings_change_only_notifies_for_retention_fields(self) -> None:
        from api import system

        with patch.object(system.retention_cleanup_coordinator, "notify_retention_change") as notify:
            system._notify_retention_cleanup_if_changed(["image_retention_days"])
            notify.assert_called_once_with()

            notify.reset_mock()
            system._notify_retention_cleanup_if_changed(["proxy_url", "image_min_free_mb"])
            notify.assert_not_called()

    def test_repeated_start_for_same_lifespan_returns_one_thread(self) -> None:
        coordinator = RetentionCleanupCoordinator(interval_seconds=60)
        stop_event = threading.Event()

        first = coordinator.start_scheduler(stop_event)
        second = coordinator.start_scheduler(stop_event)
        self.assertTrue(first.is_alive())

        stop_event.set()
        first.join(1)

        self.assertIs(first, second)
        self.assertEqual(first.name, "retention-cleanup")
        self.assertFalse(first.is_alive())

    def test_repeated_start_replaces_a_dead_cached_thread(self) -> None:
        coordinator = RetentionCleanupCoordinator(interval_seconds=60)
        stop_event = threading.Event()
        stop_event.set()
        first = coordinator.start_scheduler(stop_event)
        first.join(1)
        self.assertFalse(first.is_alive())

        stop_event.clear()
        second = coordinator.start_scheduler(stop_event)
        second_started = second.is_alive()
        stop_event.set()
        second.join(1)

        self.assertIsNot(first, second)
        self.assertTrue(second_started)
        self.assertFalse(second.is_alive())

    def test_new_lifespan_starts_a_new_scheduler_after_shutdown(self) -> None:
        coordinator = RetentionCleanupCoordinator(interval_seconds=60)
        first_stop_event = threading.Event()
        first = coordinator.start_scheduler(first_stop_event)

        first_stop_event.set()
        first.join(1)
        self.assertFalse(first.is_alive())

        second_stop_event = threading.Event()
        second = coordinator.start_scheduler(second_stop_event)
        self.assertIsNot(first, second)
        self.assertTrue(second.is_alive())

        second_stop_event.set()
        second.join(1)
        self.assertFalse(second.is_alive())

    def test_legacy_scheduler_entry_points_share_the_coordinator(self) -> None:
        coordinator = RetentionCleanupCoordinator(interval_seconds=1)
        stop_event = threading.Event()
        stop_event.set()

        with patch("services.retention_cleanup_service.retention_cleanup_coordinator", coordinator):
            image_thread = image_service.start_image_cleanup_scheduler(stop_event)
            log_thread = log_service.start_log_cleanup_scheduler(stop_event)
        image_thread.join(1)

        self.assertIs(image_thread, log_thread)

    def test_gallery_listing_does_not_trigger_retention_cleanup(self) -> None:
        with (
            patch.object(image_service.image_storage_service, "list_items", return_value=[]),
            patch.object(image_service, "load_tags", return_value={}),
            patch.object(image_service, "gallery_page", return_value={"items": []}),
            patch.object(image_service, "cleanup_image_retention") as cleanup,
        ):
            result = image_service.list_images("", limit=24)

        self.assertEqual(result, {"items": []})
        cleanup.assert_not_called()

if __name__ == "__main__":
    unittest.main()
