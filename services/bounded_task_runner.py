from __future__ import annotations

import logging
import os
import queue
import threading
from collections.abc import Callable, Iterable
from typing import Any, Literal


logger = logging.getLogger(__name__)


def env_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(str(os.getenv(name, "") or default).strip()))
    except (TypeError, ValueError):
        return max(minimum, default)


_ReservationState = Literal["reserved", "committed", "rolled_back", "cancelled"]
_RunnerMode = Literal["running", "draining", "cancelled"]
_CancelHandler = Callable[[BaseException], Any]
_Task = tuple[
    Callable[..., Any],
    tuple[Any, ...],
    dict[str, Any],
    _CancelHandler | None,
]


class TaskCancelledError(RuntimeError):
    """Raised through ``on_cancel`` when committed work never starts."""


class _RunState:
    def __init__(self, generation: int, capacity: int) -> None:
        self.generation = generation
        self.queue: queue.Queue[_Task] = queue.Queue(maxsize=capacity)
        self.mode: _RunnerMode = "running"
        self.threads: list[threading.Thread] = []


class TaskReservation:
    """One admission slot that can be committed once or rolled back."""

    def __init__(self, runner: BoundedTaskRunner, run_state: _RunState) -> None:
        self._runner = runner
        self._run_state = run_state
        self._state: _ReservationState = "reserved"

    @property
    def state(self) -> str:
        return self._state

    def commit(
        self,
        callback: Callable[..., Any],
        /,
        *args: Any,
        on_cancel: _CancelHandler | None = None,
        **kwargs: Any,
    ) -> bool:
        return self._runner.commit(
            self,
            callback,
            *args,
            on_cancel=on_cancel,
            **kwargs,
        )

    def rollback(self) -> bool:
        return self._runner.rollback(self)


class BoundedTaskRunner:
    """Run blocking background work with bounded admission and fixed concurrency."""

    def __init__(
        self,
        *,
        name: str,
        max_workers: int,
        queue_size: int,
        error_handler: Callable[[BaseException], Any] | None = None,
    ) -> None:
        self.name = str(name or "background-task").strip() or "background-task"
        self.max_workers = max(1, int(max_workers))
        self.queue_size = max(1, int(queue_size))
        self.capacity = self.max_workers + self.queue_size
        self.error_handler = error_handler
        self._lock = threading.Lock()
        self._worker_slots = threading.Semaphore(self.max_workers)
        self._generation = 1
        self._state = _RunState(self._generation, self.capacity)
        self._reservations: set[TaskReservation] = set()
        self._all_threads: set[threading.Thread] = set()
        self._accepted = 0
        self._active = 0
        self._closed = False

    def start(self) -> bool:
        """Open admission after shutdown and ensure workers are running."""
        with self._lock:
            if self._closed or self._state.mode != "running":
                self._generation += 1
                self._state = _RunState(self._generation, self.capacity)
                self._closed = False
            self._start_locked(self._state)
            return True

    def restart(self) -> bool:
        """Cancel pending work from the current run and start a fresh queue."""
        with self._lock:
            cancelled = self._close_locked(wait=False)
            self._generation += 1
            self._state = _RunState(self._generation, self.capacity)
            self._closed = False
            self._start_locked(self._state)
        self._notify_cancelled(cancelled)
        return True

    def reserve(self) -> TaskReservation | None:
        """Reserve capacity before preparing or persisting a task."""
        with self._lock:
            if self._closed or self._state.mode != "running":
                return None
            if self._accepted >= self.capacity:
                return None
            self._start_locked(self._state)
            reservation = TaskReservation(self, self._state)
            self._reservations.add(reservation)
            self._accepted += 1
            return reservation

    def commit(
        self,
        reservation: TaskReservation,
        callback: Callable[..., Any],
        /,
        *args: Any,
        on_cancel: _CancelHandler | None = None,
        **kwargs: Any,
    ) -> bool:
        """Commit a reservation to the queue exactly once."""
        return self._commit_reserved(
            reservation,
            callback,
            args,
            kwargs,
            on_cancel=on_cancel,
        )

    def _commit_reserved(
        self,
        reservation: TaskReservation,
        callback: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        on_cancel: _CancelHandler | None,
    ) -> bool:
        with self._lock:
            if not self._owns_pending_reservation_locked(reservation):
                return False
            if self._closed or reservation._run_state is not self._state:
                self._cancel_reservation_locked(reservation)
                return False
            run_state = reservation._run_state
            if run_state.mode != "running":
                self._cancel_reservation_locked(reservation)
                return False
            try:
                run_state.queue.put_nowait((callback, args, kwargs, on_cancel))
            except queue.Full:
                self._cancel_reservation_locked(reservation)
                return False
            self._reservations.remove(reservation)
            reservation._state = "committed"
            return True

    def rollback(self, reservation: TaskReservation) -> bool:
        """Release an unused reservation exactly once."""
        with self._lock:
            if not self._owns_pending_reservation_locked(reservation):
                return False
            self._reservations.remove(reservation)
            reservation._state = "rolled_back"
            self._accepted -= 1
            return True

    def submit(self, callback: Callable[..., Any], /, *args: Any, **kwargs: Any) -> bool:
        """Compatibility helper that reserves and commits in one call."""
        reservation = self.reserve()
        if reservation is None:
            return False
        committed = self._commit_reserved(
            reservation,
            callback,
            args,
            kwargs,
            on_cancel=None,
        )
        if not committed:
            reservation.rollback()
        return committed

    def status(self) -> dict[str, int | bool]:
        with self._lock:
            current_threads = self._state.threads
            return {
                "max_workers": self.max_workers,
                "queue_capacity": self.queue_size,
                "total_capacity": self.capacity,
                "queued": self._state.queue.qsize(),
                "reserved": len(self._reservations),
                "accepted": self._accepted,
                "active": self._active,
                "started": any(thread.is_alive() for thread in current_threads),
                "closed": self._closed,
            }

    def shutdown(self, *, wait: bool = False) -> None:
        with self._lock:
            run_state = self._state
            cancelled = self._close_locked(wait=wait)
            threads = list(self._all_threads)
        self._notify_cancelled(cancelled)
        if wait:
            self._wait_for_shutdown(run_state, threads)

    def shutdown_cancel_pending_and_wait(self) -> None:
        """Cancel work that has not started, then wait for active callbacks to finish."""

        with self._lock:
            run_state = self._state
            cancelled = self._close_locked(wait=False)
            threads = list(self._all_threads)
        self._notify_cancelled(cancelled)
        self._wait_for_shutdown(run_state, threads)

    @staticmethod
    def _wait_for_shutdown(run_state: _RunState, threads: list[threading.Thread]) -> None:
        current = threading.current_thread()
        if current in threads:
            return
        run_state.queue.join()
        for thread in threads:
            if thread is not current:
                thread.join()

    def _owns_pending_reservation_locked(self, reservation: object) -> bool:
        return (
            isinstance(reservation, TaskReservation)
            and reservation._runner is self
            and reservation._state == "reserved"
            and reservation in self._reservations
        )

    def _cancel_reservation_locked(self, reservation: TaskReservation) -> None:
        self._reservations.discard(reservation)
        if reservation._state == "reserved":
            reservation._state = "cancelled"
            self._accepted -= 1

    def _close_locked(self, *, wait: bool) -> list[_Task]:
        self._closed = True
        run_state = self._state
        cancelled: list[_Task] = []
        if not wait:
            run_state.mode = "cancelled"
        elif run_state.mode == "running":
            run_state.mode = "draining"

        for reservation in tuple(self._reservations):
            if reservation._run_state is run_state:
                self._cancel_reservation_locked(reservation)

        if run_state.mode == "cancelled":
            while True:
                try:
                    task = run_state.queue.get_nowait()
                except queue.Empty:
                    break
                cancelled.append(task)
                self._accepted -= 1
                run_state.queue.task_done()
        return cancelled

    def _start_locked(self, run_state: _RunState) -> None:
        if run_state.threads:
            return
        for index in range(self.max_workers):
            thread = threading.Thread(
                target=self._worker,
                args=(run_state,),
                name=f"{self.name}-{run_state.generation}-{index + 1}",
                daemon=True,
            )
            run_state.threads.append(thread)
            self._all_threads.add(thread)
            thread.start()

    def _worker(self, run_state: _RunState) -> None:
        self._worker_slots.acquire()
        try:
            self._worker_loop(run_state)
        finally:
            self._worker_slots.release()
            with self._lock:
                self._all_threads.discard(threading.current_thread())

    def _worker_loop(self, run_state: _RunState) -> None:
        while True:
            try:
                callback, args, kwargs, on_cancel = run_state.queue.get(timeout=0.1)
            except queue.Empty:
                with self._lock:
                    if run_state.mode != "running":
                        return
                continue

            with self._lock:
                should_run = run_state.mode != "cancelled"
                if should_run:
                    self._active += 1
                else:
                    self._accepted -= 1
            if not should_run:
                run_state.queue.task_done()
                self._notify_cancelled(((callback, args, kwargs, on_cancel),))
                return

            try:
                callback(*args, **kwargs)
            except BaseException as exc:
                self._report_error(exc)
            finally:
                with self._lock:
                    self._active -= 1
                    self._accepted -= 1
                run_state.queue.task_done()

    def _notify_cancelled(self, tasks: Iterable[_Task]) -> None:
        for _, _, _, on_cancel in tasks:
            if on_cancel is None:
                continue
            try:
                on_cancel(
                    TaskCancelledError(
                        f"{self.name} task was cancelled before it started"
                    )
                )
            except BaseException as exc:
                self._report_error(exc)

    def _report_error(self, exc: BaseException) -> None:
        if self.error_handler is None:
            logger.error(
                "%s callback failed",
                self.name,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            return
        try:
            self.error_handler(exc)
        except BaseException:
            logger.exception(
                "%s error handler failed while reporting %r",
                self.name,
                exc,
            )
