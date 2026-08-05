from __future__ import annotations

import copy
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Iterable

from services.call_view import call_outcome, call_switch_count
from services.storage.dashboard_metrics_repository import (
    DashboardMetricsRepository,
)
from utils.log import logger
from utils.timezone import beijing_now, parse_to_beijing_naive


DASHBOARD_METRICS_RETENTION_DAYS = 60
DASHBOARD_METRICS_SCHEMA_VERSION = 4
DASHBOARD_TIME_RANGES = ("24h", "7d", "30d")
DASHBOARD_DURATION_BUCKETS_MS = (
    250,
    500,
    1_000,
    2_000,
    3_000,
    5_000,
    10_000,
    20_000,
    30_000,
    60_000,
    120_000,
    180_000,
    300_000,
    600_000,
    900_000,
    1_800_000,
    3_600_000,
)

_NON_MODEL_KEYS = {
    "",
    "-",
    "auto",
    "default",
    "unknown",
    "null",
    "none",
    "low",
    "medium",
    "high",
    "standard",
    "hd",
    "portrait",
    "landscape",
    "square",
    "vertical",
    "horizontal",
    "image",
    "images",
    "text",
    "chat",
    "generation",
    "generations",
    "edit",
    "edits",
}


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _detail_value(item: dict[str, Any], key: str, default: object = "") -> object:
    detail = item.get("detail")
    if isinstance(detail, dict):
        value = detail.get(key)
        if value not in (None, ""):
            return value
    value = item.get(key)
    return default if value in (None, "") else value


def _parse_log_time(value: object) -> datetime | None:
    return parse_to_beijing_naive(value)


def _beijing_now_naive() -> datetime:
    return beijing_now().replace(tzinfo=None)


def _call_started_at(item: dict[str, Any]) -> object:
    return _detail_value(item, "started_at", item.get("time"))


def _call_event_at(item: dict[str, Any]) -> object:
    return item.get("time")


def _looks_like_model_label(value: object) -> bool:
    label = _clean_text(value)
    key = label.lower().replace("\u00d7", "x")
    if key in _NON_MODEL_KEYS or key.startswith("/"):
        return False
    if re.fullmatch(r"\d+\s*x\s*\d+", key) or re.fullmatch(r"\d+\s*:\s*\d+", key):
        return False
    return bool(label)


def _increment(counter: dict[str, int], key: object, default: str = "unknown") -> None:
    label = _clean_text(key) or default
    counter[label] = int(counter.get(label, 0) or 0) + 1


def _dashboard_outcome(item: dict[str, Any]) -> str:
    outcome = call_outcome(item)
    if outcome == "partial_success":
        return "success"
    return "failed" if outcome == "unknown" else outcome


def _image_switch_count(item: dict[str, Any]) -> int:
    return call_switch_count(item)


def _duration_histogram_index(duration_ms: float) -> int:
    for index, upper_bound in enumerate(DASHBOARD_DURATION_BUCKETS_MS):
        if duration_ms <= upper_bound:
            return index
    return len(DASHBOARD_DURATION_BUCKETS_MS)


def _histogram_percentile(histogram: list[int], percentile: float) -> float | None:
    total = sum(max(0, int(value or 0)) for value in histogram)
    if total <= 0:
        return None
    target = max(1, int(total * percentile + 0.999999))
    cumulative = 0
    for index, value in enumerate(histogram):
        cumulative += max(0, int(value or 0))
        if cumulative < target:
            continue
        if index < len(DASHBOARD_DURATION_BUCKETS_MS):
            return float(DASHBOARD_DURATION_BUCKETS_MS[index])
        return None
    return None

def _empty_bucket() -> dict[str, Any]:
    return {
        "total": 0,
        "success": 0,
        "failed": 0,
        "text_review": 0,
        "rate_limited": 0,
        "switch_requests": 0,
        "switch_count": 0,
        "switch_recovered": 0,
        "success_duration_total_ms": 0.0,
        "success_duration_count": 0,
        "success_duration_histogram": [],
        "by_model": {},
        "model_success": {},
        "model_failed": {},
        "model_rate_limited": {},
        "model_text_review": {},
        "model_success_total_times": {},
        "model_success_time_counts": {},
        "model_success_duration_histograms": {},
    }


def _merge_bucket(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        "total",
        "success",
        "failed",
        "text_review",
        "rate_limited",
        "switch_requests",
        "switch_count",
        "switch_recovered",
    ):
        target[key] = int(target.get(key, 0) or 0) + int(source.get(key, 0) or 0)
    target["success_duration_total_ms"] = (
        float(target.get("success_duration_total_ms", 0.0) or 0.0)
        + float(source.get("success_duration_total_ms", 0.0) or 0.0)
    )
    target["success_duration_count"] = (
        int(target.get("success_duration_count", 0) or 0)
        + int(source.get("success_duration_count", 0) or 0)
    )
    for key in (
        "by_model",
        "model_success",
        "model_failed",
        "model_rate_limited",
        "model_text_review",
        "model_success_total_times",
        "model_success_time_counts",
    ):
        target_map = target.setdefault(key, {})
        source_map = source.get(key) if isinstance(source.get(key), dict) else {}
        for name, value in source_map.items():
            try:
                numeric = float(value) if key == "model_success_total_times" else int(value)
            except (TypeError, ValueError):
                numeric = 0.0 if key == "model_success_total_times" else 0
            target_map[str(name)] = target_map.get(str(name), 0) + numeric

    target_histograms = target.setdefault("model_success_duration_histograms", {})
    source_histograms = (
        source.get("model_success_duration_histograms")
        if isinstance(source.get("model_success_duration_histograms"), dict)
        else {}
    )
    histogram_size = len(DASHBOARD_DURATION_BUCKETS_MS) + 1
    for model, raw_histogram in source_histograms.items():
        if not isinstance(raw_histogram, list):
            continue
        target_histogram = target_histograms.setdefault(str(model), [0] * histogram_size)
        if not isinstance(target_histogram, list) or len(target_histogram) != histogram_size:
            target_histogram = [0] * histogram_size
            target_histograms[str(model)] = target_histogram
        for index in range(histogram_size):
            value = raw_histogram[index] if index < len(raw_histogram) else 0
            target_histogram[index] += int(value or 0)

    source_histogram = source.get("success_duration_histogram")
    if isinstance(source_histogram, list):
        target_histogram = target.get("success_duration_histogram")
        if not isinstance(target_histogram, list) or len(target_histogram) != histogram_size:
            target_histogram = [0] * histogram_size
            target["success_duration_histogram"] = target_histogram
        for index in range(histogram_size):
            value = source_histogram[index] if index < len(source_histogram) else 0
            target_histogram[index] += int(value or 0)


def _percentage(numerator: int, denominator: int) -> float | None:
    return round(numerator * 100 / denominator, 2) if denominator > 0 else None


def _bucket_metrics(bucket: dict[str, Any]) -> dict[str, Any]:
    success = int(bucket.get("success", 0) or 0)
    failed = int(bucket.get("failed", 0) or 0)
    rate_limited = int(bucket.get("rate_limited", 0) or 0)
    final_failed = failed + rate_limited
    measured = success + final_failed
    duration_total = float(bucket.get("success_duration_total_ms", 0.0) or 0.0)
    duration_count = int(bucket.get("success_duration_count", 0) or 0)
    switch_requests = int(bucket.get("switch_requests", 0) or 0)
    switch_recovered = int(bucket.get("switch_recovered", 0) or 0)
    histogram = bucket.get("success_duration_histogram")
    return {
        "total_calls": int(bucket.get("total", 0) or 0),
        "success_calls": success,
        "final_failed_calls": final_failed,
        "success_rate": _percentage(success, measured),
        "avg_success_duration_ms": (
            round(duration_total / duration_count, 2)
            if duration_count > 0
            else None
        ),
        "p95_success_duration_ms": _histogram_percentile(
            histogram if isinstance(histogram, list) else [],
            0.95,
        ),
        "switch_requests": switch_requests,
        "switch_count": int(bucket.get("switch_count", 0) or 0),
        "switch_recovered": switch_recovered,
        "switch_recovery_rate": _percentage(switch_recovered, switch_requests),
    }

def _empty_metrics_data() -> dict[str, Any]:
    return {
        "version": DASHBOARD_METRICS_SCHEMA_VERSION,
        "days": {},
        "ingest": {
            "initialized": False,
            "status": "uninitialized",
            "stale": True,
            "last_event_id": None,
            "last_event_at": None,
            "checkpoint_at": None,
            "failure_reason": None,
        },
    }


def _merge_metrics_data(target: dict[str, Any], source: dict[str, Any]) -> None:
    target_days = target.setdefault("days", {})
    source_days = source.get("days") if isinstance(source.get("days"), dict) else {}
    for day_key, source_day in source_days.items():
        if not isinstance(source_day, dict):
            continue
        target_day = target_days.setdefault(str(day_key), _empty_bucket())
        if not isinstance(target_day, dict):
            target_day = _empty_bucket()
            target_days[str(day_key)] = target_day
        _merge_bucket(target_day, source_day)

        target_hours = target_day.get("hours")
        if not isinstance(target_hours, dict):
            target_hours = {}
            target_day["hours"] = target_hours
        source_hours = source_day.get("hours") if isinstance(source_day.get("hours"), dict) else {}
        for hour_key, source_hour in source_hours.items():
            if not isinstance(source_hour, dict):
                continue
            target_hour = target_hours.setdefault(str(hour_key), _empty_bucket())
            if not isinstance(target_hour, dict):
                target_hour = _empty_bucket()
                target_hours[str(hour_key)] = target_hour
            _merge_bucket(target_hour, source_hour)


class DashboardMetricsService:
    """Rebuildable rolling aggregates derived from the canonical call log."""

    def __init__(
        self,
        repository: DashboardMetricsRepository | None = None,
        *,
        database_url: str | None = None,
    ) -> None:
        if repository is not None and database_url is not None:
            raise ValueError("provide repository or database_url, not both")
        self.repository = repository or DashboardMetricsRepository(database_url)
        self._lock = threading.RLock()
        self._ingest_failed = False
        self._stale_reason: str | None = None
        self._dashboard_sync_not_before = 0.0

    @staticmethod
    def _normalize_persisted(value: object) -> dict[str, Any]:
        data = copy.deepcopy(value) if isinstance(value, dict) else {}
        if not isinstance(data.get("days"), dict):
            data["days"] = {}
        if not isinstance(data.get("ingest"), dict):
            data["ingest"] = {}
        try:
            data["version"] = int(data.get("version") or 0)
        except (TypeError, ValueError):
            data["version"] = 0
        return data

    def _load_persisted(self) -> dict[str, Any]:
        return self._normalize_persisted(self.repository.load().data)

    @staticmethod
    def _prepare_save(
        data: dict[str, Any],
        *,
        normalize_schema: bool = True,
    ) -> dict[str, Any]:
        if normalize_schema:
            data["version"] = DASHBOARD_METRICS_SCHEMA_VERSION
        data["retention_days"] = DASHBOARD_METRICS_RETENTION_DAYS
        data["updated_at"] = beijing_now().isoformat(timespec="seconds")
        return data

    def _save(self, data: dict[str, Any], *, normalize_schema: bool = True) -> None:
        self.repository.replace(
            self._prepare_save(data, normalize_schema=normalize_schema)
        )

    @staticmethod
    def _ingest_state(data: dict[str, Any]) -> dict[str, Any]:
        ingest = data.get("ingest")
        if not isinstance(ingest, dict):
            ingest = {}
            data["ingest"] = ingest
        return ingest

    @classmethod
    def _set_ingest_state(
        cls,
        data: dict[str, Any],
        *,
        status: str,
        stale: bool,
        reason: str | None,
        checkpoint_at: str | None = None,
    ) -> dict[str, Any]:
        ingest = cls._ingest_state(data)
        ingest["mode"] = "call_record_sequence"
        ingest["status"] = status
        ingest["stale"] = bool(stale)
        ingest["failure_reason"] = reason
        if checkpoint_at is not None:
            ingest["checkpoint_at"] = checkpoint_at
        return ingest

    @staticmethod
    def _prune(data: dict[str, Any], now: datetime | None = None) -> bool:
        current = (now or _beijing_now_naive()).date()
        cutoff = current - timedelta(days=DASHBOARD_METRICS_RETENTION_DAYS - 1)
        days = data.get("days") if isinstance(data.get("days"), dict) else {}
        changed = False
        for day in list(days.keys()):
            try:
                parsed = datetime.strptime(str(day), "%Y-%m-%d").date()
            except ValueError:
                days.pop(day, None)
                changed = True
                continue
            if parsed < cutoff or parsed > current:
                days.pop(day, None)
                changed = True
        return changed

    def begin_startup(self) -> bool:
        """Report whether startup must rebuild instead of applying a cursor tail."""
        with self._lock:
            data = self._load_persisted()
            ingest = self._ingest_state(data)
            cursor_valid = self._normalize_log_cursor(ingest.get("log_cursor")) is not None
            needs_rebuild = not (
                data.get("version") == DASHBOARD_METRICS_SCHEMA_VERSION
                and ingest.get("initialized") is True
                and ingest.get("status") == "ready"
                and ingest.get("stale") is not True
                and not _clean_text(ingest.get("failure_reason"))
                and cursor_valid
            )
            self._ingest_failed = needs_rebuild
            self._stale_reason = "startup_rebuild_pending" if needs_rebuild else None
            return needs_rebuild
    @staticmethod
    def _normalize_log_cursor(value: object) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        generation = _clean_text(value.get("generation"))
        try:
            sequence = int(value.get("sequence"))
        except (TypeError, ValueError):
            return None
        if not generation or sequence < 0:
            return None
        return {
            "generation": generation,
            "sequence": sequence,
        }

    def _reset_runtime_ingest_locked(self) -> None:
        self._ingest_failed = False
        self._stale_reason = None
    def _build_log_window_locked(
        self,
        items: Iterable[dict[str, Any]],
        end_cursor: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], int]:
        rebuilt = _empty_metrics_data()
        current_date = _beijing_now_naive().date()
        cutoff = current_date - timedelta(days=DASHBOARD_METRICS_RETENTION_DAYS - 1)
        last_event_id: str | None = None
        last_event_at: str | None = None
        record_count = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            call_id = _clean_text(item.get("id"))
            if call_id:
                last_event_id = call_id
            event_dt = _parse_log_time(_call_event_at(item))
            if event_dt is not None:
                last_event_at = event_dt.isoformat(timespec="seconds")
            bucket_dt = _parse_log_time(_call_started_at(item))
            if (
                bucket_dt is None
                or bucket_dt.date() < cutoff
                or bucket_dt.date() > current_date
            ):
                continue
            self._apply_call_to_data(rebuilt, item, bucket_dt)
            record_count += 1

        self._prune(rebuilt)
        now = beijing_now().isoformat(timespec="seconds")
        ingest = self._set_ingest_state(
            rebuilt,
            status="ready",
            stale=False,
            reason=None,
            checkpoint_at=now,
        )
        ingest["initialized"] = True
        ingest["records"] = record_count
        ingest["last_event_id"] = last_event_id
        ingest["last_event_at"] = last_event_at
        ingest["last_sync_at"] = now
        ingest["last_sync_records"] = record_count
        ingest["log_cursor"] = self._normalize_log_cursor(end_cursor)
        return rebuilt, record_count

    def _apply_log_window_locked(
        self,
        data: dict[str, Any],
        items: Iterable[dict[str, Any]],
        end_cursor: dict[str, Any] | None,
    ) -> int:
        delta = _empty_metrics_data()
        current_date = _beijing_now_naive().date()
        cutoff = current_date - timedelta(days=DASHBOARD_METRICS_RETENTION_DAYS - 1)
        last_event_id: str | None = None
        last_event_at: str | None = None
        record_count = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            call_id = _clean_text(item.get("id"))
            if call_id:
                last_event_id = call_id
            event_dt = _parse_log_time(_call_event_at(item))
            if event_dt is not None:
                last_event_at = event_dt.isoformat(timespec="seconds")
            bucket_dt = _parse_log_time(_call_started_at(item))
            if (
                bucket_dt is None
                or bucket_dt.date() < cutoff
                or bucket_dt.date() > current_date
            ):
                continue
            self._apply_call_to_data(delta, item, bucket_dt)
            record_count += 1

        _merge_metrics_data(data, delta)
        self._prune(data)
        now = beijing_now().isoformat(timespec="seconds")
        ingest = self._set_ingest_state(
            data,
            status="ready",
            stale=False,
            reason=None,
            checkpoint_at=now,
        )
        ingest["initialized"] = True
        if last_event_id is not None:
            ingest["last_event_id"] = last_event_id
        if last_event_at is not None:
            ingest["last_event_at"] = last_event_at
        ingest["records"] = int(ingest.get("records", 0) or 0) + record_count
        ingest["last_sync_at"] = now
        ingest["last_sync_records"] = record_count
        ingest["log_cursor"] = self._normalize_log_cursor(end_cursor)
        return record_count

    def sync_from_log_service(self, log_source: Any) -> bool:
        """Synchronize one stable Call Record sequence window exactly once.

        A missing, stale, or mismatched cursor triggers a full rebuild. The
        aggregate and its end cursor are committed only while that captured log
        boundary still holds, so destructive rewrites cannot publish a mixed
        snapshot as ready.
        """
        from services.log_service import LogCursorMismatch

        with self._lock:
            try:
                for attempt in range(3):
                    rebuilt = False
                    record_count = 0
                    unchanged = False
                    try:
                        def synchronize(current: dict[str, Any] | None) -> dict[str, Any]:
                            nonlocal rebuilt, record_count, unchanged
                            data = self._normalize_persisted(current)
                            ingest = self._ingest_state(data)
                            cursor = self._normalize_log_cursor(ingest.get("log_cursor"))
                            checkpoint_ready = (
                                data.get("version") == DASHBOARD_METRICS_SCHEMA_VERSION
                                and ingest.get("initialized") is True
                                and ingest.get("status") == "ready"
                                and ingest.get("stale") is not True
                                and not _clean_text(ingest.get("failure_reason"))
                                and cursor is not None
                                and not self._ingest_failed
                            )

                            if checkpoint_ready:
                                try:
                                    with log_source.open_call_window(cursor) as (items, end_cursor):
                                        if self._normalize_log_cursor(end_cursor) == cursor:
                                            with log_source.hold_call_cursor(end_cursor):
                                                unchanged = True
                                                return data
                                        record_count = self._apply_log_window_locked(
                                            data,
                                            items,
                                            end_cursor,
                                        )
                                except LogCursorMismatch:
                                    checkpoint_ready = False

                            if not checkpoint_ready:
                                rebuilt = True
                                with log_source.open_call_window(None) as (items, end_cursor):
                                    data, record_count = self._build_log_window_locked(
                                        items,
                                        end_cursor,
                                    )

                            with log_source.hold_call_cursor(end_cursor):
                                return self._prepare_save(data)

                        self.repository.update(synchronize)
                        if unchanged:
                            self._reset_runtime_ingest_locked()
                            return False
                        break
                    except LogCursorMismatch:
                        if attempt >= 2:
                            raise
            except Exception:
                self._ingest_failed = True
                self._stale_reason = "log_cursor_sync_failed"
                try:
                    self.mark_ingest_failed(self._stale_reason)
                except Exception:
                    pass
                raise

            self._reset_runtime_ingest_locked()
            logger.info({
                "event": "dashboard_metrics_log_cursor_synced",
                "mode": "rebuild" if rebuilt else "incremental",
                "records": record_count,
            })
            return rebuilt

    def sync_for_dashboard(
        self,
        log_source: Any,
        *,
        min_interval_seconds: float = 1.0,
    ) -> bool:
        """Refresh metrics while coalescing concurrent dashboard requests."""
        with self._lock:
            now = time.monotonic()
            if now < self._dashboard_sync_not_before:
                return False
            try:
                return self.sync_from_log_service(log_source)
            finally:
                self._dashboard_sync_not_before = time.monotonic() + max(
                    0.0,
                    float(min_interval_seconds),
                )

    def sync_from_logs(self, items: Iterable[dict[str, Any]]) -> bool:
        """Full rebuild helper for migrations and deterministic tests."""
        with self._lock:
            rebuilt, record_count = self._build_log_window_locked(items, None)
            self._save(rebuilt)
            self._reset_runtime_ingest_locked()
            logger.info({
                "event": "dashboard_metrics_synced",
                "schema_version": DASHBOARD_METRICS_SCHEMA_VERSION,
                "records": record_count,
            })
            return True
    def mark_ingest_failed(self, reason: str = "ingest_failed") -> None:
        """Persist a stale marker so the next sync must rebuild from canonical logs."""
        with self._lock:
            self._ingest_failed = True
            self._stale_reason = _clean_text(reason) or "ingest_failed"
            try:
                def mark_failed(current: dict[str, Any] | None) -> dict[str, Any]:
                    data = self._normalize_persisted(current)
                    ingest = self._set_ingest_state(
                        data,
                        status="degraded",
                        stale=True,
                        reason=self._stale_reason,
                    )
                    ingest["ingest_failed_at"] = beijing_now().isoformat(timespec="seconds")
                    return self._prepare_save(
                        data,
                        normalize_schema=data.get("version") == DASHBOARD_METRICS_SCHEMA_VERSION,
                    )

                self.repository.update(mark_failed)
            except Exception as exc:
                logger.error({"event": "dashboard_metrics_ingest_marker_failed", "error": str(exc)})
    @staticmethod
    def _apply_call(bucket: dict[str, Any], item: dict[str, Any]) -> None:
        model = _clean_text(_detail_value(item, "model"))
        outcome = _dashboard_outcome(item)
        duration_ms: float | None = None
        duration_raw = _detail_value(item, "duration_ms", None)
        if outcome == "success" and duration_raw not in (None, ""):
            try:
                duration_ms = max(0.0, float(duration_raw))
            except (TypeError, ValueError):
                duration_ms = None

        bucket["total"] = int(bucket.get("total", 0) or 0) + 1
        bucket[outcome] = int(bucket.get(outcome, 0) or 0) + 1

        switch_count = _image_switch_count(item)
        if switch_count > 0:
            bucket["switch_requests"] = int(bucket.get("switch_requests", 0) or 0) + 1
            bucket["switch_count"] = int(bucket.get("switch_count", 0) or 0) + switch_count
            if outcome == "success":
                bucket["switch_recovered"] = int(bucket.get("switch_recovered", 0) or 0) + 1

        if duration_ms is not None:
            bucket["success_duration_total_ms"] = (
                float(bucket.get("success_duration_total_ms", 0.0) or 0.0)
                + duration_ms
            )
            bucket["success_duration_count"] = (
                int(bucket.get("success_duration_count", 0) or 0) + 1
            )
            histogram = bucket.setdefault(
                "success_duration_histogram",
                [0] * (len(DASHBOARD_DURATION_BUCKETS_MS) + 1),
            )
            if not isinstance(histogram, list) or len(histogram) != len(DASHBOARD_DURATION_BUCKETS_MS) + 1:
                histogram = [0] * (len(DASHBOARD_DURATION_BUCKETS_MS) + 1)
                bucket["success_duration_histogram"] = histogram
            histogram[_duration_histogram_index(duration_ms)] += 1

        if _looks_like_model_label(model):
            _increment(bucket.setdefault("by_model", {}), model)
            _increment(bucket.setdefault(f"model_{outcome}", {}), model)
            if duration_ms is not None:
                totals = bucket.setdefault("model_success_total_times", {})
                counts = bucket.setdefault("model_success_time_counts", {})
                histograms = bucket.setdefault("model_success_duration_histograms", {})
                totals[model] = float(totals.get(model, 0.0) or 0.0) + duration_ms
                counts[model] = int(counts.get(model, 0) or 0) + 1
                histogram = histograms.setdefault(
                    model,
                    [0] * (len(DASHBOARD_DURATION_BUCKETS_MS) + 1),
                )
                if not isinstance(histogram, list) or len(histogram) != len(DASHBOARD_DURATION_BUCKETS_MS) + 1:
                    histogram = [0] * (len(DASHBOARD_DURATION_BUCKETS_MS) + 1)
                    histograms[model] = histogram
                histogram[_duration_histogram_index(duration_ms)] += 1

    @classmethod
    def _apply_call_to_data(cls, data: dict[str, Any], item: dict[str, Any], dt: datetime) -> None:
        days = data.setdefault("days", {})
        day_key = dt.strftime("%Y-%m-%d")
        hour_key = dt.strftime("%H")
        day = days.setdefault(day_key, _empty_bucket())
        hours = day.setdefault("hours", {})
        hour = hours.setdefault(hour_key, _empty_bucket())
        cls._apply_call(day, item)
        cls._apply_call(hour, item)

    def rebuild_if_needed(self, items: Iterable[dict[str, Any]]) -> bool:
        """Rebuild derived metrics once when the persisted schema changes."""
        with self._lock:
            persisted = self._load_persisted()
            if persisted.get("version") == DASHBOARD_METRICS_SCHEMA_VERSION:
                if self._prune(persisted):
                    self._save(persisted)
                return False
        self.sync_from_logs(items)
        logger.info({
            "event": "dashboard_metrics_rebuilt",
            "schema_version": DASHBOARD_METRICS_SCHEMA_VERSION,
        })
        return True

    def _snapshot_data(self) -> dict[str, Any]:
        with self._lock:
            data = self._load_persisted()
            self._prune(data)
            if self._ingest_failed:
                self._set_ingest_state(
                    data,
                    status="degraded",
                    stale=True,
                    reason=self._stale_reason or "ingest_failed",
                )
            return copy.deepcopy(data)
    def _snapshot_days(self) -> dict[str, Any]:
        data = self._snapshot_data()
        days = data.get("days") if isinstance(data.get("days"), dict) else {}
        return days

    @staticmethod
    def _metrics_view(data: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        ingest = data.get("ingest") if isinstance(data.get("ingest"), dict) else {}
        schema_ready = data.get("version") == DASHBOARD_METRICS_SCHEMA_VERSION
        ready = (
            schema_ready
            and ingest.get("initialized") is True
            and ingest.get("status") == "ready"
            and ingest.get("stale") is not True
        )
        last_ingested_at = _clean_text(ingest.get("last_event_at")) or None
        last_ingested_dt = _parse_log_time(last_ingested_at)
        freshness_ms = (
            max(0, int((now - last_ingested_dt).total_seconds() * 1000))
            if last_ingested_dt is not None
            else None
        )
        return {
            "status": "ready" if ready else "degraded",
            "ready": ready,
            "stale": not ready,
        "source": "call_record_sequence",
            "source_revision": _clean_text(ingest.get("last_event_id")) or None,
            "last_ingested_at": last_ingested_at,
            "freshness_ms": freshness_ms,
            "checkpoint_at": _clean_text(ingest.get("checkpoint_at")) or None,
            "failure_reason": _clean_text(ingest.get("failure_reason")) or None,
            "retention_days": DASHBOARD_METRICS_RETENTION_DAYS,
        }

    @staticmethod
    def _range_view(
        days: dict[str, Any],
        time_range: str,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        bucket_count = {"24h": 24, "7d": 7, "30d": 30}.get(time_range)
        if bucket_count is None:
            raise ValueError(f"Unsupported dashboard time range: {time_range}")
        bucket_delta = timedelta(hours=1) if time_range == "24h" else timedelta(days=1)
        bucket_format = "%H:00" if time_range == "24h" else "%m-%d"
        current_bucket_start = (
            now.replace(minute=0, second=0, microsecond=0)
            if time_range == "24h"
            else now.replace(hour=0, minute=0, second=0, microsecond=0)
        )
        starts = [
            current_bucket_start - bucket_delta * (bucket_count - 1 - index)
            for index in range(bucket_count)
        ]
        labels = [start.strftime(bucket_format) for start in starts]
        window = {
            "requested": time_range,
            "start_at": starts[0].isoformat(timespec="seconds"),
            "end_at": now.isoformat(timespec="seconds"),
            "bucket_unit": "hour" if time_range == "24h" else "day",
            "bucket_count": bucket_count,
        }

        def bucket_for(start: datetime) -> dict[str, Any]:
            day = days.get(start.strftime("%Y-%m-%d"), {})
            hours = (
                day.get("hours")
                if isinstance(day, dict) and isinstance(day.get("hours"), dict)
                else {}
            )
            if time_range == "24h":
                bucket = hours.get(start.strftime("%H"), {}) if isinstance(hours, dict) else {}
                return bucket if isinstance(bucket, dict) else {}
            bucket = _empty_bucket()
            for hour in hours.values() if isinstance(hours, dict) else ():
                if isinstance(hour, dict):
                    _merge_bucket(bucket, hour)
            return bucket

        series_buckets = [bucket_for(start) for start in starts]
        total_bucket = _empty_bucket()
        for bucket in series_buckets:
            _merge_bucket(total_bucket, bucket)

        def integer_series(key: str) -> list[int]:
            return [int(bucket.get(key, 0) or 0) for bucket in series_buckets]

        total_requests = integer_series("total")
        success_requests = integer_series("success")
        failed_requests = integer_series("failed")
        rate_limited_requests = integer_series("rate_limited")
        final_failed_requests = [
            failed_requests[index] + rate_limited_requests[index]
            for index in range(bucket_count)
        ]
        text_review_requests = integer_series("text_review")
        measured_requests = [
            success_requests[index] + final_failed_requests[index]
            for index in range(bucket_count)
        ]
        success_rate = [
            round(success_requests[index] * 100 / measured, 2) if measured > 0 else None
            for index, measured in enumerate(measured_requests)
        ]

        model_keys = (
            "by_model",
            "model_success",
            "model_failed",
            "model_rate_limited",
            "model_text_review",
        )
        model_series: dict[str, dict[str, list[int]]] = {}
        model_duration_totals: dict[str, list[float]] = {}
        model_duration_counts: dict[str, list[int]] = {}
        for index, bucket in enumerate(series_buckets):
            for key in model_keys:
                values = bucket.get(key) if isinstance(bucket.get(key), dict) else {}
                for model, count in values.items():
                    series = model_series.setdefault(
                        str(model),
                        {name: [0] * bucket_count for name in model_keys},
                    )
                    series[key][index] += int(count or 0)
            totals = (
                bucket.get("model_success_total_times")
                if isinstance(bucket.get("model_success_total_times"), dict)
                else {}
            )
            counts = (
                bucket.get("model_success_time_counts")
                if isinstance(bucket.get("model_success_time_counts"), dict)
                else {}
            )
            for model, total in totals.items():
                model_duration_totals.setdefault(str(model), [0.0] * bucket_count)[index] += float(total or 0.0)
            for model, count in counts.items():
                model_duration_counts.setdefault(str(model), [0] * bucket_count)[index] += int(count or 0)

        model_names = sorted(
            set(model_series) | set(model_duration_totals) | set(model_duration_counts),
            key=lambda model: (-sum(model_series.get(model, {}).get("by_model", [])), model.lower()),
        )
        models: list[dict[str, Any]] = []
        model_requests: dict[str, list[int]] = {}
        model_success_requests: dict[str, list[int]] = {}
        model_failed_requests: dict[str, list[int]] = {}
        model_rate_limited_requests: dict[str, list[int]] = {}
        model_text_review_requests: dict[str, list[int]] = {}
        model_avg_success_duration_ms: dict[str, list[float | None]] = {}
        all_histograms = (
            total_bucket.get("model_success_duration_histograms")
            if isinstance(total_bucket.get("model_success_duration_histograms"), dict)
            else {}
        )
        for model in model_names:
            series = model_series.get(model, {name: [0] * bucket_count for name in model_keys})
            duration_totals = model_duration_totals.get(model, [0.0] * bucket_count)
            duration_counts = model_duration_counts.get(model, [0] * bucket_count)
            avg_duration_series = [
                round(duration_totals[index] / duration_counts[index], 2)
                if duration_counts[index] > 0
                else None
                for index in range(bucket_count)
            ]
            model_requests[model] = series["by_model"]
            model_success_requests[model] = series["model_success"]
            model_failed_requests[model] = series["model_failed"]
            model_rate_limited_requests[model] = series["model_rate_limited"]
            model_text_review_requests[model] = series["model_text_review"]
            model_avg_success_duration_ms[model] = avg_duration_series
            total_duration = sum(duration_totals)
            duration_count = sum(duration_counts)
            success_calls = sum(series["model_success"])
            failed_calls = sum(series["model_failed"])
            rate_limited_calls = sum(series["model_rate_limited"])
            final_failed_series = [
                series["model_failed"][index] + series["model_rate_limited"][index]
                for index in range(bucket_count)
            ]
            final_failed_calls = failed_calls + rate_limited_calls
            measured_calls = success_calls + final_failed_calls
            raw_histogram = all_histograms.get(model)
            histogram = raw_histogram if isinstance(raw_histogram, list) else []
            models.append({
                "name": model,
                "total_calls": sum(series["by_model"]),
                "success_calls": success_calls,
                "failed_calls": failed_calls,
                "rate_limited_calls": rate_limited_calls,
                "final_failed_calls": final_failed_calls,
                "text_review_calls": sum(series["model_text_review"]),
                "measured_calls": measured_calls,
                "success_rate": (
                    round(success_calls * 100 / measured_calls, 2)
                    if measured_calls > 0
                    else None
                ),
                "avg_success_duration_ms": round(total_duration / duration_count, 2) if duration_count > 0 else None,
                "p95_success_duration_ms": _histogram_percentile(histogram, 0.95),
                "call_series": series["by_model"],
                "success_series": series["model_success"],
                "failed_series": series["model_failed"],
                "rate_limited_series": series["model_rate_limited"],
                "final_failed_series": final_failed_series,
                "text_review_series": series["model_text_review"],
                "avg_success_duration_series_ms": avg_duration_series,
            })

        current_metrics = _bucket_metrics(total_bucket)
        success_total = current_metrics["success_calls"]
        failed_total = int(total_bucket.get("failed", 0) or 0)
        rate_limited_total = int(total_bucket.get("rate_limited", 0) or 0)
        final_failed_total = current_metrics["final_failed_calls"]
        measured_total = success_total + final_failed_total
        totals = {
            "total": current_metrics["total_calls"],
            "success": success_total,
            "failed": failed_total,
            "rate_limited": rate_limited_total,
            "final_failed": final_failed_total,
            "text_review": int(total_bucket.get("text_review", 0) or 0),
            "measured": measured_total,
            "success_rate": current_metrics["success_rate"],
            "avg_success_duration_ms": current_metrics["avg_success_duration_ms"],
            "p95_success_duration_ms": current_metrics["p95_success_duration_ms"],
        }
        switching = {
            "requests": current_metrics["switch_requests"],
            "count": current_metrics["switch_count"],
            "recovered": current_metrics["switch_recovered"],
            "recovery_rate": current_metrics["switch_recovery_rate"],
        }
        buckets = [
            {
                "label": start.strftime(bucket_format),
                "start_at": start.isoformat(timespec="seconds"),
                "end_at": (start + bucket_delta).isoformat(timespec="seconds"),
                **_bucket_metrics(current_bucket),
            }
            for start, current_bucket in zip(starts, series_buckets)
        ]
        trend = {
            "labels": labels,
            "total_requests": total_requests,
            "success_requests": success_requests,
            "failed_requests": failed_requests,
            "rate_limited_requests": rate_limited_requests,
            "final_failed_requests": final_failed_requests,
            "text_review_requests": text_review_requests,
            "measured_requests": measured_requests,
            "success_rate": success_rate,
            "switch_requests": integer_series("switch_requests"),
            "switch_count": integer_series("switch_count"),
            "switch_recovered": integer_series("switch_recovered"),
            "model_requests": model_requests,
            "model_success_requests": model_success_requests,
            "model_failed_requests": model_failed_requests,
            "model_rate_limited_requests": model_rate_limited_requests,
            "model_text_review_requests": model_text_review_requests,
            "model_avg_success_duration_ms": model_avg_success_duration_ms,
        }
        return {
            "time_range": time_range,
            "bucket_unit": "hour" if time_range == "24h" else "day",
            "window": window,
            "totals": totals,
            "switching": switching,
            "buckets": buckets,
            "models": models,
            "trend": trend,
        }

    def snapshot_many(
        self,
        time_ranges: Iterable[str] = DASHBOARD_TIME_RANGES,
    ) -> dict[str, Any]:
        requested = tuple(dict.fromkeys(str(item or "").strip() for item in time_ranges))
        invalid = [item for item in requested if item not in DASHBOARD_TIME_RANGES]
        if invalid:
            raise ValueError(f"Unsupported dashboard time ranges: {', '.join(invalid)}")
        data = self._snapshot_data()
        days = data.get("days") if isinstance(data.get("days"), dict) else {}
        now = _beijing_now_naive()
        return {
            "metrics": self._metrics_view(data, now=now),
            "ranges": {
                time_range: self._range_view(days, time_range, now=now)
                for time_range in requested
            },
        }

    def summary_many(
        self,
        time_ranges: Iterable[str] = DASHBOARD_TIME_RANGES,
    ) -> dict[str, dict[str, Any]]:
        return self.snapshot_many(time_ranges)["ranges"]

    def summary(self, time_range: str = "24h") -> dict[str, Any]:
        return self.snapshot_many((time_range,))["ranges"][time_range]


dashboard_metrics_service = DashboardMetricsService()
