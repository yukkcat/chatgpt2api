from __future__ import annotations

import shutil
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, Iterator

from services.config import config
from services.image_service import cleanup_image_retention, delete_to_target, preview_image_retention_cleanup
from services.log_service import log_service
from services.storage.coordination_repository import RetentionCleanupRepository
from utils.log import logger
from utils.timezone import beijing_from_timestamp


RETENTION_CLEANUP_INTERVAL_SECS = 1800
RETENTION_STOP_POLL_SECS = 0.25
RETENTION_STARTUP_DEDUPE_SECS = 60
RETENTION_ERROR_BACKOFF_INITIAL_SECS = 0.25
RETENTION_ERROR_BACKOFF_MAX_SECS = 5.0
CleanupResult = dict[str, int | bool]
CleanupRunner = Callable[[int, bool], CleanupResult]
ImageSpaceRunner = Callable[[], dict[str, Any] | None]
ImageTargetRunner = Callable[[int, bool], dict[str, Any]]


def _run_log_cleanup(retention_days: int, dry_run: bool) -> CleanupResult:
    if dry_run:
        return log_service.preview_cleanup_old(retention_days)
    return log_service.cleanup_old(retention_days)


def _run_image_cleanup(retention_days: int, dry_run: bool) -> CleanupResult:
    if dry_run:
        return preview_image_retention_cleanup(retention_days)
    return cleanup_image_retention(retention_days)


def _enforce_image_free_space() -> dict[str, Any] | None:
    min_free_mb = config.image_min_free_mb
    usage = shutil.disk_usage(config.images_dir)
    free_mb = usage.free // (1024 * 1024)
    if free_mb >= min_free_mb:
        return None
    return {
        "free_mb": free_mb,
        "min_free_mb": min_free_mb,
        "cleanup": delete_to_target(min_free_mb),
    }


def _retention_days(value: int | None, fallback: int) -> int:
    try:
        return max(1, int(value or fallback))
    except (TypeError, ValueError):
        return max(1, int(fallback))


class RetentionCleanupCoordinator:
    def __init__(
        self,
        *,
        log_runner: CleanupRunner = _run_log_cleanup,
        image_runner: CleanupRunner = _run_image_cleanup,
        image_space_runner: ImageSpaceRunner = _enforce_image_free_space,
        image_target_runner: ImageTargetRunner = delete_to_target,
        interval_seconds: int = RETENTION_CLEANUP_INTERVAL_SECS,
        repository: RetentionCleanupRepository | None = None,
        database_url: str | None = None,
    ) -> None:
        if repository is not None and database_url is not None:
            raise ValueError("provide repository or database_url, not both")
        self._log_runner = log_runner
        self._image_runner = image_runner
        self._image_space_runner = image_space_runner
        self._image_target_runner = image_target_runner
        self.interval_seconds = max(1, int(interval_seconds))
        self._repository = repository or (
            RetentionCleanupRepository(database_url) if database_url is not None else None
        )
        self._run_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._scheduler_lock = threading.Lock()
        self._scheduler_stop_event: threading.Event | None = None
        self._scheduler_thread: threading.Thread | None = None
        self._wake_event = threading.Event()
        self._status_lock = threading.Lock()
        self._scheduler_active = False
        self._scheduler_status_owner: object | None = None
        self._running = False
        self._last_started_at: str | None = None
        self._last_finished_at: str | None = None
        self._next_run_at: str | None = None
        self._last_removed: dict[str, int] = {"logs": 0, "images": 0}
        self._last_error: dict[str, str | None] = {"logs": None, "images": None}

    @staticmethod
    def _timestamp(value: float | None = None) -> str:
        return beijing_from_timestamp(time.time() if value is None else value)

    @staticmethod
    def _empty_status() -> dict[str, Any]:
        return {
            "running": False,
            "last_started_at": None,
            "last_finished_at": None,
            "next_run_at": None,
            "last_removed": {"logs": 0, "images": 0},
            "last_error": {"logs": None, "images": None},
        }

    @contextmanager
    def _shared_state(self) -> Iterator[dict[str, Any]]:
        if self._repository is None:
            yield {}
            return
        with self._state_lock:
            with self._repository.edit() as state:
                yield state

    @contextmanager
    def _run_owner(self) -> Iterator[None]:
        with self._run_lock:
            if self._repository is None:
                yield
                return
            with self._repository.run_lock():
                yield

    def _shared_schedule_epoch(self, *, initialize: bool) -> float | None:
        if self._repository is None:
            return None
        with self._shared_state() as state:
            try:
                next_epoch = float(state.get("next_run_epoch") or 0)
            except (TypeError, ValueError):
                next_epoch = 0
            if initialize and next_epoch <= 0:
                next_epoch = time.time() + self.interval_seconds
                state["next_run_epoch"] = next_epoch
                state["next_run_at"] = self._timestamp(next_epoch)
            return next_epoch or None

    def _wake_revision(self) -> int:
        if self._repository is None:
            return 0
        with self._shared_state() as state:
            try:
                return int(state.get("wake_revision") or 0)
            except (TypeError, ValueError):
                return 0

    def _schedule_after_cleanup(self, expected_wake_revision: int) -> float:
        if self._repository is None:
            next_epoch = time.time() + self.interval_seconds
            self._set_next_run(next_epoch)
            return next_epoch
        with self._shared_state() as state:
            try:
                wake_revision = int(state.get("wake_revision") or 0)
            except (TypeError, ValueError):
                wake_revision = 0
            if wake_revision == expected_wake_revision:
                next_epoch = time.time() + self.interval_seconds
                state["next_run_epoch"] = next_epoch
                state["next_run_at"] = self._timestamp(next_epoch)
                return next_epoch
            try:
                return float(state.get("next_run_epoch") or time.time())
            except (TypeError, ValueError):
                return time.time()

    def _mark_started(self) -> None:
        with self._status_lock:
            self._running = True
            self._last_started_at = self._timestamp()
            if self._repository is not None:
                with self._shared_state() as state:
                    state["running"] = True
                    state["last_started_at"] = self._last_started_at

    def _mark_finished(
        self,
        *,
        results: dict[str, Any],
        errors: dict[str, str],
        domains: tuple[str, ...],
    ) -> None:
        with self._status_lock:
            for domain in domains:
                result = results.get(domain)
                self._last_removed[domain] = int(result.get("removed") or 0) if isinstance(result, dict) else 0
                self._last_error[domain] = errors.get(domain)
            self._last_finished_at = self._timestamp()
            self._running = False
            if self._repository is not None:
                with self._shared_state() as state:
                    last_removed = dict(state.get("last_removed") or {"logs": 0, "images": 0})
                    last_error = dict(state.get("last_error") or {"logs": None, "images": None})
                    for domain in domains:
                        last_removed[domain] = self._last_removed[domain]
                        last_error[domain] = self._last_error[domain]
                    state.update({
                        "running": False,
                        "last_finished_at": self._last_finished_at,
                        "last_removed": last_removed,
                        "last_error": last_error,
                    })

    def _set_next_run(self, timestamp: float | None) -> None:
        with self._status_lock:
            self._next_run_at = self._timestamp(timestamp) if timestamp is not None else None
            if self._repository is not None:
                with self._shared_state() as state:
                    state["next_run_epoch"] = timestamp
                    state["next_run_at"] = self._next_run_at

    def runtime_status(self) -> dict[str, Any]:
        if self._repository is not None:
            with self._shared_state() as state:
                status = self._empty_status()
                for field in ("running", "last_started_at", "last_finished_at", "next_run_at"):
                    if field in state:
                        status[field] = state[field]
                for field in ("last_removed", "last_error"):
                    if isinstance(state.get(field), dict):
                        status[field].update(state[field])
                return status
        with self._status_lock:
            return {
                "running": self._running,
                "last_started_at": self._last_started_at,
                "last_finished_at": self._last_finished_at,
                "next_run_at": self._next_run_at,
                "last_removed": dict(self._last_removed),
                "last_error": dict(self._last_error),
            }

    def notify_retention_change(self) -> None:
        with self._status_lock:
            if self._scheduler_active:
                self._next_run_at = self._timestamp()
        if self._repository is not None:
            now = time.time()
            with self._shared_state() as state:
                state["next_run_epoch"] = now
                state["next_run_at"] = self._timestamp(now)
                state["wake_revision"] = int(state.get("wake_revision") or 0) + 1
        self._wake_event.set()

    def run_retention(
        self,
        *,
        log_retention_days: int | None = None,
        image_retention_days: int | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        log_days = _retention_days(log_retention_days, config.log_retention_days)
        image_days = _retention_days(image_retention_days, config.image_retention_days)
        with self._run_owner():
            if dry_run:
                logs = self._log_runner(log_days, True)
                images = self._image_runner(image_days, True)
            else:
                self._mark_started()
                results: dict[str, Any] = {}
                errors: dict[str, str] = {}
                try:
                    logs = self._log_runner(log_days, False)
                    results["logs"] = logs
                    images = self._image_runner(image_days, False)
                    results["images"] = images
                except Exception as exc:
                    domain = "images" if "logs" in results else "logs"
                    errors[domain] = str(exc)
                    domains = ("logs", "images") if domain == "images" else ("logs",)
                    self._mark_finished(results=results, errors=errors, domains=domains)
                    raise
                self._mark_finished(results=results, errors=errors, domains=("logs", "images"))
        total_removed = int(logs.get("removed") or 0) + int(images.get("removed") or 0)
        total_size = int(logs.get("removed_size_bytes") or 0) + int(images.get("removed_size_bytes") or 0)
        return {
            "dry_run": dry_run,
            "logs": {**logs, "retention_days": log_days},
            "images": {**images, "retention_days": image_days},
            "total_removed": total_removed,
            "total_size_bytes": total_size,
        }

    def run_logs(self, retention_days: int | None = None, *, dry_run: bool = False) -> CleanupResult:
        days = _retention_days(retention_days, config.log_retention_days)
        with self._run_owner():
            if dry_run:
                return self._log_runner(days, True)
            self._mark_started()
            try:
                result = self._log_runner(days, False)
            except Exception as exc:
                self._mark_finished(results={}, errors={"logs": str(exc)}, domains=("logs",))
                raise
            self._mark_finished(results={"logs": result}, errors={}, domains=("logs",))
            return result

    def run_images(self, retention_days: int | None = None, *, dry_run: bool = False) -> CleanupResult:
        days = _retention_days(retention_days, config.image_retention_days)
        with self._run_owner():
            if dry_run:
                return self._image_runner(days, True)
            self._mark_started()
            try:
                result = self._image_runner(days, False)
            except Exception as exc:
                self._mark_finished(results={}, errors={"images": str(exc)}, domains=("images",))
                raise
            self._mark_finished(results={"images": result}, errors={}, domains=("images",))
            return result

    def cleanup_images_to_target(self, target_free_mb: int, *, dry_run: bool = False) -> dict[str, Any]:
        with self._run_owner():
            if dry_run:
                return self._image_target_runner(int(target_free_mb), True)
            self._mark_started()
            try:
                result = self._image_target_runner(int(target_free_mb), False)
            except Exception as exc:
                self._mark_finished(results={}, errors={"images": str(exc)}, domains=("images",))
                raise
            self._mark_finished(results={"images": result}, errors={}, domains=("images",))
            return result

    def run_automatic(
        self,
        *,
        enforce_image_free_space: bool,
        stop_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        with self._run_owner():
            if stop_event is not None and stop_event.is_set():
                return self._empty_automatic_result()
            return self._run_automatic_owned(
                enforce_image_free_space=enforce_image_free_space,
                stop_event=stop_event,
            )

    @staticmethod
    def _empty_automatic_result() -> dict[str, Any]:
        return {"logs": None, "images": None, "image_space": None, "errors": {}}

    def _run_automatic_owned(
        self,
        *,
        enforce_image_free_space: bool,
        stop_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        result = self._empty_automatic_result()
        self._mark_started()
        if stop_event is None or not stop_event.is_set():
            try:
                result["logs"] = self._log_runner(config.log_retention_days, False)
            except Exception as exc:
                result["errors"]["logs"] = str(exc)
        if stop_event is None or not stop_event.is_set():
            try:
                result["images"] = self._image_runner(config.image_retention_days, False)
                if enforce_image_free_space and (stop_event is None or not stop_event.is_set()):
                    result["image_space"] = self._image_space_runner()
            except Exception as exc:
                result["errors"]["images"] = str(exc)
        status_results = {"logs": result.get("logs"), "images": result.get("images")}
        image_space = result.get("image_space")
        if isinstance(image_space, dict) and isinstance(image_space.get("cleanup"), dict):
            image_result = dict(status_results.get("images") or {})
            image_result["removed"] = int(image_result.get("removed") or 0) + int(
                image_space["cleanup"].get("removed") or 0
            )
            status_results["images"] = image_result
        self._mark_finished(
            results=status_results,
            errors=result["errors"],
            domains=("logs", "images"),
        )
        return result

    def run_startup_automatic(self, *, enforce_image_free_space: bool) -> dict[str, Any]:
        with self._run_owner():
            now = time.time()
            if self._repository is not None:
                with self._shared_state() as state:
                    try:
                        last_startup = float(state.get("last_startup_epoch") or 0)
                    except (TypeError, ValueError):
                        last_startup = 0
                    if now - last_startup < RETENTION_STARTUP_DEDUPE_SECS:
                        return {**self._empty_automatic_result(), "skipped": True}
            wake_revision = self._wake_revision()
            result = self._run_automatic_owned(enforce_image_free_space=enforce_image_free_space)
            self._schedule_after_cleanup(wake_revision)
            if self._repository is not None:
                with self._shared_state() as state:
                    state["last_startup_epoch"] = time.time()
            return result

    def _wait_for_cleanup(self, stop_event: threading.Event, deadline: float) -> bool:
        while not stop_event.is_set():
            if self._wake_event.is_set():
                self._wake_event.clear()
                return not stop_event.is_set()
            remaining = deadline - time.monotonic()
            shared_epoch = self._shared_schedule_epoch(initialize=False)
            if shared_epoch is not None:
                remaining = min(remaining, shared_epoch - time.time())
            if remaining <= 0:
                return True
            if stop_event.wait(min(remaining, RETENTION_STOP_POLL_SECS)):
                return False
        return False

    def _scheduler_leader_loop(self, stop_event: threading.Event) -> None:
        next_epoch = self._shared_schedule_epoch(initialize=True)
        if next_epoch is None:
            next_epoch = time.time() + self.interval_seconds
            self._set_next_run(next_epoch)
        deadline = time.monotonic() + max(0.0, next_epoch - time.time())
        status_owner = object()
        with self._status_lock:
            self._scheduler_active = True
            self._scheduler_status_owner = status_owner
        try:
            while self._wait_for_cleanup(stop_event, deadline):
                # Coalesce a settings notification that races with a periodic wake.
                self._wake_event.clear()
                if stop_event.is_set():
                    break
                wake_revision = self._wake_revision()
                result = self.run_automatic(
                    enforce_image_free_space=True,
                    stop_event=stop_event,
                )
                if stop_event.is_set():
                    break
                logs = result.get("logs") or {}
                if int(logs.get("removed") or 0) > 0:
                    logger.info({"event": "log_auto_cleanup_done", **logs})
                image_space = result.get("image_space")
                if image_space:
                    logger.info({
                        "event": "image_auto_cleanup",
                        "free_mb": image_space["free_mb"],
                        "min_free_mb": image_space["min_free_mb"],
                    })
                    logger.info({"event": "image_auto_cleanup_done", **image_space["cleanup"]})
                errors = result.get("errors") or {}
                if errors.get("logs"):
                    logger.error({"event": "log_auto_cleanup_failed", "error": errors["logs"]})
                if errors.get("images"):
                    logger.error({"event": "image_auto_cleanup_failed", "error": errors["images"]})
                next_epoch = self._schedule_after_cleanup(wake_revision)
                deadline = time.monotonic() + max(0.0, next_epoch - time.time())
        finally:
            with self._status_lock:
                if self._scheduler_status_owner is status_owner:
                    self._scheduler_active = False
                    self._scheduler_status_owner = None
                    if self._repository is None:
                        self._next_run_at = None

    def scheduler_worker(self, stop_event: threading.Event) -> None:
        error_backoff = RETENTION_ERROR_BACKOFF_INITIAL_SECS
        while not stop_event.is_set():
            try:
                if self._repository is None:
                    self._scheduler_leader_loop(stop_event)
                    return
                with self._repository.scheduler_leader_lock(timeout_seconds=0):
                    self._scheduler_leader_loop(stop_event)
                    return
            except TimeoutError:
                if stop_event.wait(RETENTION_STOP_POLL_SECS):
                    return
            except Exception as exc:
                if stop_event.is_set():
                    return
                delay = min(error_backoff, RETENTION_ERROR_BACKOFF_MAX_SECS)
                logger.error({
                    "event": "retention_cleanup_scheduler_failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "retry_in_seconds": delay,
                })
                if stop_event.wait(delay):
                    return
                error_backoff = min(
                    RETENTION_ERROR_BACKOFF_MAX_SECS,
                    max(RETENTION_ERROR_BACKOFF_INITIAL_SECS, error_backoff * 2),
                )

    def start_scheduler(self, stop_event: threading.Event) -> threading.Thread:
        with self._scheduler_lock:
            if self._scheduler_stop_event is stop_event and self._scheduler_thread is not None:
                if self._scheduler_thread.is_alive() or stop_event.is_set():
                    return self._scheduler_thread
            thread = threading.Thread(
                target=self.scheduler_worker,
                args=(stop_event,),
                daemon=True,
                name="retention-cleanup",
            )
            self._scheduler_stop_event = stop_event
            self._scheduler_thread = thread
            if self._repository is None:
                self._set_next_run(time.time() + self.interval_seconds)
            else:
                self._shared_schedule_epoch(initialize=True)
            thread.start()
            return thread


retention_cleanup_coordinator = RetentionCleanupCoordinator(
    repository=RetentionCleanupRepository(),
)


def start_retention_cleanup_scheduler(stop_event: threading.Event) -> threading.Thread:
    return retention_cleanup_coordinator.start_scheduler(stop_event)
