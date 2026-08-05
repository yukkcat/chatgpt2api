from __future__ import annotations

import threading
import time
import unittest

from services.bounded_task_runner import BoundedTaskRunner, TaskCancelledError


class BoundedTaskRunnerTests(unittest.TestCase):
    def test_total_admission_is_workers_plus_queue_size(self) -> None:
        runner = BoundedTaskRunner(name="test-task", max_workers=2, queue_size=3)
        reservations = [runner.reserve() for _ in range(5)]

        self.assertTrue(all(reservation is not None for reservation in reservations))
        self.assertIsNone(runner.reserve())
        self.assertEqual(runner.status()["total_capacity"], 5)
        self.assertEqual(runner.status()["accepted"], 5)
        self.assertEqual(runner.status()["reserved"], 5)

        for reservation in reservations:
            self.assertIsNotNone(reservation)
            self.assertTrue(reservation.rollback())
        self.assertEqual(runner.status()["accepted"], 0)
        runner.shutdown(wait=True)

    def test_reservation_commits_or_rolls_back_exactly_once(self) -> None:
        runner = BoundedTaskRunner(name="test-task", max_workers=1, queue_size=1)
        completed = threading.Event()

        committed = runner.reserve()
        self.assertIsNotNone(committed)
        self.assertTrue(committed.commit(completed.set))
        self.assertEqual(committed.state, "committed")
        self.assertFalse(committed.commit(completed.set))
        self.assertFalse(committed.rollback())
        self.assertTrue(completed.wait(timeout=1))

        rolled_back = runner.reserve()
        self.assertIsNotNone(rolled_back)
        self.assertTrue(runner.rollback(rolled_back))
        self.assertEqual(rolled_back.state, "rolled_back")
        self.assertFalse(runner.rollback(rolled_back))
        runner.shutdown(wait=True)

    def test_submit_remains_compatible_and_bounded(self) -> None:
        runner = BoundedTaskRunner(name="test-task", max_workers=1, queue_size=1)
        started = threading.Event()
        release = threading.Event()
        completed = threading.Event()

        def blocking_task() -> None:
            started.set()
            release.wait(timeout=2)

        self.assertTrue(runner.submit(blocking_task))
        self.assertTrue(started.wait(timeout=1))
        self.assertTrue(runner.submit(completed.set))
        self.assertFalse(runner.submit(lambda: None))
        status = runner.status()
        self.assertEqual(status["max_workers"], 1)
        self.assertEqual(status["queue_capacity"], 1)
        self.assertEqual(status["total_capacity"], 2)
        self.assertEqual(status["active"], 1)
        self.assertEqual(status["queued"], 1)

        release.set()
        self.assertTrue(completed.wait(timeout=1))
        runner.shutdown(wait=True)

    def test_submit_keeps_on_cancel_as_a_callback_keyword(self) -> None:
        runner = BoundedTaskRunner(name="test-task", max_workers=1, queue_size=1)
        received: list[str] = []

        def callback(*, on_cancel: str) -> None:
            received.append(on_cancel)

        self.assertTrue(runner.submit(callback, on_cancel="callback value"))
        runner.shutdown(wait=True)
        self.assertEqual(received, ["callback value"])

    def test_callback_failure_is_reported_and_worker_survives(self) -> None:
        errors: list[BaseException] = []
        runner = BoundedTaskRunner(
            name="test-task",
            max_workers=1,
            queue_size=2,
            error_handler=errors.append,
        )
        completed = threading.Event()

        def fail() -> None:
            raise RuntimeError("expected")

        self.assertTrue(runner.submit(fail))
        self.assertTrue(runner.submit(completed.set))
        self.assertTrue(completed.wait(timeout=1))
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)
        self.assertEqual(str(errors[0]), "expected")
        runner.shutdown(wait=True)

    def test_default_error_reporting_uses_logging(self) -> None:
        runner = BoundedTaskRunner(name="logged-task", max_workers=1, queue_size=1)

        def fail() -> None:
            raise ValueError("logged failure")

        with self.assertLogs("services.bounded_task_runner", level="ERROR") as captured:
            self.assertTrue(runner.submit(fail))
            runner.shutdown(wait=True)

        self.assertIn("logged-task callback failed", "\n".join(captured.output))

    def test_non_waiting_shutdown_cancels_queued_and_reserved_work(self) -> None:
        runner = BoundedTaskRunner(name="test-task", max_workers=1, queue_size=2)
        started = threading.Event()
        release = threading.Event()
        queued_ran = threading.Event()

        def blocking_task() -> None:
            started.set()
            release.wait(timeout=2)

        self.assertTrue(runner.submit(blocking_task))
        self.assertTrue(started.wait(timeout=1))
        self.assertTrue(runner.submit(queued_ran.set))
        reservation = runner.reserve()
        self.assertIsNotNone(reservation)

        before = time.perf_counter()
        runner.shutdown(wait=False)
        self.assertLess(time.perf_counter() - before, 0.1)
        self.assertEqual(reservation.state, "cancelled")
        self.assertFalse(reservation.commit(queued_ran.set))
        self.assertFalse(runner.submit(queued_ran.set))
        release.set()
        runner.shutdown(wait=True)

        self.assertFalse(queued_ran.is_set())
        self.assertEqual(runner.status()["accepted"], 0)

    def test_non_waiting_shutdown_notifies_committed_task_cancellation(self) -> None:
        runner = BoundedTaskRunner(name="test-task", max_workers=1, queue_size=1)
        started = threading.Event()
        release = threading.Event()
        cancelled: list[BaseException] = []
        queued_ran = threading.Event()

        def blocking_task() -> None:
            started.set()
            release.wait(timeout=2)

        self.assertTrue(runner.submit(blocking_task))
        self.assertTrue(started.wait(timeout=1))
        reservation = runner.reserve()
        self.assertIsNotNone(reservation)
        self.assertTrue(
            reservation.commit(queued_ran.set, on_cancel=cancelled.append)
        )

        runner.shutdown(wait=False)
        release.set()
        runner.shutdown(wait=True)

        self.assertFalse(queued_ran.is_set())
        self.assertEqual(len(cancelled), 1)
        self.assertIsInstance(cancelled[0], TaskCancelledError)

    def test_cancel_pending_and_wait_finishes_active_without_running_queued_work(self) -> None:
        runner = BoundedTaskRunner(name="test-task", max_workers=1, queue_size=2)
        active_started = threading.Event()
        release_active = threading.Event()
        active_finished = threading.Event()
        queued_ran = threading.Event()
        queued_cancelled = threading.Event()

        def active_task() -> None:
            active_started.set()
            release_active.wait(timeout=2)
            active_finished.set()

        self.assertTrue(runner.submit(active_task))
        self.assertTrue(active_started.wait(timeout=1))
        queued = runner.reserve()
        self.assertIsNotNone(queued)
        self.assertTrue(
            queued.commit(queued_ran.set, on_cancel=lambda _exc: queued_cancelled.set())
        )
        reserved = runner.reserve()
        self.assertIsNotNone(reserved)

        shutdown_thread = threading.Thread(target=runner.shutdown_cancel_pending_and_wait)
        shutdown_thread.start()
        self.assertTrue(queued_cancelled.wait(timeout=1))
        self.assertTrue(shutdown_thread.is_alive())
        self.assertEqual(reserved.state, "cancelled")
        self.assertFalse(queued_ran.is_set())

        release_active.set()
        shutdown_thread.join(timeout=1)

        self.assertFalse(shutdown_thread.is_alive())
        self.assertTrue(active_finished.is_set())
        self.assertFalse(queued_ran.is_set())
        self.assertEqual(runner.status()["accepted"], 0)

    def test_submit_shutdown_race_releases_reserved_capacity(self) -> None:
        runner = BoundedTaskRunner(name="test-task", max_workers=1, queue_size=1)
        reservation_created = threading.Event()
        allow_submit_to_commit = threading.Event()
        callback_ran = threading.Event()
        original_reserve = runner.reserve

        def delayed_reserve():  # type: ignore[no-untyped-def]
            reservation = original_reserve()
            reservation_created.set()
            allow_submit_to_commit.wait(timeout=2)
            return reservation

        runner.reserve = delayed_reserve  # type: ignore[method-assign]
        result: list[bool] = []
        submit_thread = threading.Thread(
            target=lambda: result.append(runner.submit(callback_ran.set))
        )
        submit_thread.start()
        self.assertTrue(reservation_created.wait(timeout=1))

        runner.shutdown(wait=False)
        allow_submit_to_commit.set()
        submit_thread.join(timeout=1)

        self.assertEqual(result, [False])
        self.assertFalse(callback_ran.is_set())
        self.assertEqual(runner.status()["accepted"], 0)

    def test_start_and_restart_accept_work_after_shutdown(self) -> None:
        runner = BoundedTaskRunner(name="test-task", max_workers=1, queue_size=1)
        first = threading.Event()
        second = threading.Event()

        runner.shutdown(wait=False)
        self.assertFalse(runner.submit(first.set))
        self.assertTrue(runner.start())
        self.assertTrue(runner.submit(first.set))
        self.assertTrue(first.wait(timeout=1))

        self.assertTrue(runner.restart())
        self.assertTrue(runner.submit(second.set))
        self.assertTrue(second.wait(timeout=1))
        runner.shutdown(wait=True)

    def test_restart_cancels_old_queue_without_exceeding_worker_limit(self) -> None:
        runner = BoundedTaskRunner(name="test-task", max_workers=1, queue_size=2)
        first_started = threading.Event()
        release_first = threading.Event()
        old_queued_ran = threading.Event()
        new_started = threading.Event()
        active = 0
        max_active = 0
        active_lock = threading.Lock()

        def blocking_task() -> None:
            nonlocal active, max_active
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            first_started.set()
            release_first.wait(timeout=2)
            with active_lock:
                active -= 1

        def new_task() -> None:
            nonlocal active, max_active
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            new_started.set()
            with active_lock:
                active -= 1

        self.assertTrue(runner.submit(blocking_task))
        self.assertTrue(first_started.wait(timeout=1))
        self.assertTrue(runner.submit(old_queued_ran.set))
        self.assertTrue(runner.restart())
        self.assertTrue(runner.submit(new_task))
        self.assertFalse(new_started.wait(timeout=0.1))

        release_first.set()
        self.assertTrue(new_started.wait(timeout=1))
        self.assertFalse(old_queued_ran.is_set())
        self.assertEqual(max_active, 1)
        runner.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
