from __future__ import annotations

import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from fastapi import FastAPI

from api import system
from services.dashboard_metrics_service import (
    DASHBOARD_METRICS_SCHEMA_VERSION,
    DashboardMetricsService,
)
from services.log_service import LogService
from services.storage.dashboard_metrics_repository import DashboardMetricsRepository
from utils.timezone import beijing_now


def _database_url(root: Path) -> str:
    return f"sqlite:///{(root / 'app.db').as_posix()}"


class _ExplodingIterable:
    def __iter__(self):
        raise AssertionError("current dashboard metrics schema must not consume call logs")


def _call(
    *,
    started_at: str,
    status: str,
    call_id: str = "",
    model: str = "gpt-image-2",
    duration_ms: int | None = None,
    error_code: str = "",
    image_attempts: list[dict] | None = None,
) -> dict:
    detail = {
        "started_at": started_at,
        "status": status,
        "endpoint": "/v1/images/generations",
        "model": model,
    }
    if duration_ms is not None:
        detail["duration_ms"] = duration_ms
    if error_code:
        detail["error_code"] = error_code
        detail["error"] = f"upstream failure: {error_code}"
    if image_attempts is not None:
        detail["image_attempts"] = image_attempts
    item = {"time": started_at, "detail": detail}
    if call_id:
        item.update({"id": call_id, "type": "call"})
    return item


class DashboardMetricsContractTests(unittest.TestCase):
    def test_outcomes_are_mutually_exclusive_and_text_is_excluded_from_success_rate(self) -> None:
        now = beijing_now().isoformat()
        calls = [
            _call(started_at=now, status="success", duration_ms=1200),
            _call(started_at=now, status="failed", error_code="image_tool_error"),
            _call(started_at=now, status="failed", error_code="image_quota_exhausted"),
            _call(started_at=now, status="failed", error_code="content_policy_violation"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            service = DashboardMetricsService(database_url=_database_url(Path(temp_dir)))
            self.assertTrue(service.rebuild_if_needed(iter(calls)))
            summary = service.summary("24h")

        self.assertEqual(
            summary["totals"],
            {
                "total": 4,
                "success": 1,
                "failed": 1,
                "rate_limited": 1,
                "final_failed": 2,
                "text_review": 1,
                "measured": 3,
                "success_rate": 33.33,
            },
        )
        self.assertEqual(
            sum(summary["totals"][key] for key in ("success", "failed", "rate_limited", "text_review")),
            summary["totals"]["total"],
        )
        self.assertEqual(
            summary["totals"]["measured"],
            summary["totals"]["success"] + summary["totals"]["final_failed"],
        )
        self.assertEqual(sum(summary["trend"]["final_failed_requests"]), 2)
        model = next(item for item in summary["models"] if item["name"] == "gpt-image-2")
        self.assertEqual(model["final_failed_calls"], 2)
        self.assertEqual(sum(model["final_failed_series"]), 2)

    def test_model_average_duration_uses_only_successes_with_a_duration(self) -> None:
        now = beijing_now().isoformat()
        calls = [
            _call(started_at=now, status="success", duration_ms=100),
            _call(started_at=now, status="success", duration_ms=300),
            _call(started_at=now, status="success"),
            _call(started_at=now, status="failed", duration_ms=9000, error_code="image_tool_error"),
            _call(
                started_at=now,
                status="failed",
                duration_ms=8000,
                error_code="content_policy_violation",
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            service = DashboardMetricsService(database_url=_database_url(Path(temp_dir)))
            service.rebuild_if_needed(calls)
            summary = service.summary("24h")

        model = next(item for item in summary["models"] if item["name"] == "gpt-image-2")
        self.assertEqual(model["total_calls"], 5)
        self.assertEqual(model["success_calls"], 3)
        self.assertEqual(model["failed_calls"], 1)
        self.assertEqual(model["text_review_calls"], 1)
        self.assertEqual(model["avg_success_duration_ms"], 200.0)
        measured_buckets = [value for value in model["avg_success_duration_series_ms"] if value]
        self.assertEqual(measured_buckets, [200.0])

    def test_trend_success_rate_uses_none_for_buckets_without_measured_calls(self) -> None:
        now = beijing_now().isoformat()
        calls = [
            _call(started_at=now, status="success"),
            _call(started_at=now, status="failed", error_code="image_tool_error"),
            _call(started_at=now, status="failed", error_code="content_policy_violation"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            service = DashboardMetricsService(database_url=_database_url(Path(temp_dir)))
            service.rebuild_if_needed(calls)
            summary = service.summary("24h")

        success_rate = summary["trend"]["success_rate"]
        self.assertEqual([value for value in success_rate if value is not None], [50.0])
        self.assertEqual(sum(value is None for value in success_rate), 23)

    def test_model_duration_series_uses_none_for_buckets_without_measurement(self) -> None:
        now = beijing_now().isoformat()
        calls = [_call(started_at=now, status="success", duration_ms=200)]

        with tempfile.TemporaryDirectory() as temp_dir:
            service = DashboardMetricsService(database_url=_database_url(Path(temp_dir)))
            service.rebuild_if_needed(calls)
            summary = service.summary("24h")

        model = next(item for item in summary["models"] if item["name"] == "gpt-image-2")
        duration_series = model["avg_success_duration_series_ms"]
        self.assertEqual([value for value in duration_series if value is not None], [200.0])
        self.assertEqual(sum(value is None for value in duration_series), 23)

    def test_model_p95_uses_none_when_percentile_is_in_overflow_bucket(self) -> None:
        now = beijing_now().isoformat()
        calls = [_call(started_at=now, status="success", duration_ms=3_600_001)]

        with tempfile.TemporaryDirectory() as temp_dir:
            service = DashboardMetricsService(database_url=_database_url(Path(temp_dir)))
            service.rebuild_if_needed(calls)
            summary = service.summary("24h")

        model = next(item for item in summary["models"] if item["name"] == "gpt-image-2")
        self.assertIsNone(model["p95_success_duration_ms"])

    def test_switching_counts_requests_attempts_and_successful_recovery_separately(self) -> None:
        now = beijing_now().isoformat()
        calls = [
            _call(
                started_at=now,
                status="success",
                image_attempts=[
                    {"switched_account": True},
                    {"switched_account": True},
                    {"switched_account": False},
                ],
            ),
            _call(
                started_at=now,
                status="failed",
                error_code="image_tool_error",
                image_attempts=[{"switched_account": True}],
            ),
            _call(started_at=now, status="success", image_attempts=[]),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            service = DashboardMetricsService(database_url=_database_url(Path(temp_dir)))
            service.rebuild_if_needed(calls)
            summary = service.summary("24h")

        self.assertEqual(
            summary["switching"],
            {"requests": 2, "count": 3, "recovered": 1, "recovery_rate": 50.0},
        )
        self.assertEqual(sum(summary["trend"]["switch_requests"]), 2)
        self.assertEqual(sum(summary["trend"]["switch_count"]), 3)
        self.assertEqual(sum(summary["trend"]["switch_recovered"]), 1)

    def test_summary_many_builds_24_hour_7_day_and_30_day_views_from_one_snapshot(self) -> None:
        now = beijing_now()
        calls = [
            _call(started_at=now.isoformat(), status="success"),
            _call(started_at=(now - timedelta(days=2)).isoformat(), status="success"),
            _call(started_at=(now - timedelta(days=10)).isoformat(), status="success"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            service = DashboardMetricsService(database_url=_database_url(Path(temp_dir)))
            service.rebuild_if_needed(calls)
            with patch.object(service, "_snapshot_data", wraps=service._snapshot_data) as snapshot:
                summaries = service.summary_many()

        self.assertEqual(list(summaries), ["24h", "7d", "30d"])
        self.assertEqual(snapshot.call_count, 1)
        self.assertEqual(summaries["24h"]["totals"]["total"], 1)
        self.assertEqual(summaries["7d"]["totals"]["total"], 2)
        self.assertEqual(summaries["30d"]["totals"]["total"], 3)
        self.assertEqual(len(summaries["24h"]["trend"]["labels"]), 24)
        self.assertEqual(len(summaries["7d"]["trend"]["labels"]), 7)
        self.assertEqual(len(summaries["30d"]["trend"]["labels"]), 30)

    def test_missing_and_legacy_metrics_are_stream_rebuilt_to_current_schema(self) -> None:
        now = beijing_now().isoformat()
        for existing_payload in (None, {"version": 1, "days": {}}):
            with self.subTest(existing_payload=existing_payload):
                with tempfile.TemporaryDirectory() as temp_dir:
                    path = _database_url(Path(temp_dir))
                    if existing_payload is not None:
                        DashboardMetricsRepository(path).replace(existing_payload)
                    consumed = 0

                    def stream():
                        nonlocal consumed
                        consumed += 1
                        yield _call(started_at=now, status="success")

                    service = DashboardMetricsService(database_url=path)
                    self.assertTrue(service.rebuild_if_needed(stream()))
                    persisted = service.repository.load().data

                    self.assertEqual(consumed, 1)
                    self.assertEqual(persisted["version"], DASHBOARD_METRICS_SCHEMA_VERSION)
                    self.assertEqual(service.summary("24h")["totals"]["success"], 1)

    def test_current_schema_does_not_consume_the_rebuild_stream(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = _database_url(Path(temp_dir))
            DashboardMetricsRepository(path).replace({
                "version": DASHBOARD_METRICS_SCHEMA_VERSION,
                "days": {},
                "ingest": {"initialized": True},
            })
            service = DashboardMetricsService(database_url=path)


            rebuilt = service.rebuild_if_needed(_ExplodingIterable())

        self.assertFalse(rebuilt)

    def test_startup_sync_recovers_calls_after_checkpoint_without_double_counting(self) -> None:
        now = beijing_now().isoformat()
        checkpointed = _call(started_at=now, status="success", call_id="call-a", duration_ms=100)
        appended = _call(started_at=now, status="success", call_id="call-b", duration_ms=200)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs = LogService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
            metrics_path = _database_url(root)
            logs.append_item(checkpointed)

            service = DashboardMetricsService(database_url=metrics_path)
            self.assertTrue(service.sync_from_log_service(logs))
            persisted_before_sync = service.repository.load().data
            self.assertEqual(persisted_before_sync["version"], DASHBOARD_METRICS_SCHEMA_VERSION)

            logs.append_item(appended)
            restarted = DashboardMetricsService(database_url=metrics_path)
            self.assertFalse(restarted.sync_from_log_service(logs))
            first_sync = restarted.summary("24h")
            self.assertEqual(first_sync["totals"]["total"], 2)
            self.assertEqual(first_sync["totals"]["success"], 2)

            second_restart = DashboardMetricsService(database_url=metrics_path)
            self.assertFalse(second_restart.sync_from_log_service(logs))
            second_sync = second_restart.summary("24h")
            persisted_after_sync = second_restart.repository.load().data

        self.assertEqual(second_sync["totals"]["total"], 2)
        self.assertEqual(second_sync["totals"]["success"], 2)
        self.assertEqual(persisted_after_sync["ingest"]["last_event_id"], "call-b")
        self.assertGreater(persisted_after_sync["ingest"]["log_cursor"]["sequence"], 0)

    def test_ingest_failure_keeps_cache_dirty_until_successful_resync(self) -> None:
        now = beijing_now().isoformat()
        first = _call(started_at=now, status="success", call_id="call-a")
        second = _call(started_at=now, status="success", call_id="call-b")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs = LogService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
            metrics_path = _database_url(root)
            logs.append_item(first)
            service = DashboardMetricsService(database_url=metrics_path)
            service.sync_from_log_service(logs)

            logs.append_item(second)
            service.mark_ingest_failed("append_callback_failed")
            degraded = service.snapshot_many()

            self.assertTrue(service.sync_from_log_service(logs))
            ready = service.snapshot_many()

        self.assertEqual(degraded["ranges"]["24h"]["totals"]["total"], 1)
        self.assertEqual(degraded["metrics"]["status"], "degraded")
        self.assertTrue(degraded["metrics"]["stale"])
        self.assertEqual(degraded["metrics"]["source"], "call_record_sequence")
        self.assertEqual(degraded["metrics"]["source_revision"], "call-a")
        self.assertIsNotNone(degraded["metrics"]["last_ingested_at"])
        self.assertIsNotNone(degraded["metrics"]["checkpoint_at"])
        self.assertFalse(degraded["metrics"]["ready"])
        self.assertEqual(degraded["metrics"]["failure_reason"], "append_callback_failed")
        self.assertTrue(ready["metrics"]["ready"])
        self.assertEqual(ready["ranges"]["24h"]["totals"]["total"], 2)

    def test_startup_does_not_upgrade_legacy_schema_before_sync(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = _database_url(Path(temp_dir))
            DashboardMetricsRepository(path).replace({"version": 1, "days": {}})
            service = DashboardMetricsService(database_url=path)

            self.assertTrue(service.begin_startup())
            persisted = service.repository.load().data
            self.assertEqual(persisted["version"], 1)

    def test_concurrent_instances_sync_without_losing_or_double_counting_calls(self) -> None:
        now = beijing_now().isoformat()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs = LogService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
            metrics_path = _database_url(root)
            initializer = DashboardMetricsService(database_url=metrics_path)
            initializer.sync_from_log_service(logs)
            logs.append_item(_call(started_at=now, status="success", call_id="call-a"))
            logs.append_item(_call(started_at=now, status="success", call_id="call-b"))
            first = DashboardMetricsService(database_url=metrics_path)
            second = DashboardMetricsService(database_url=metrics_path)
            barrier = threading.Barrier(2)

            def sync(service: DashboardMetricsService) -> None:
                barrier.wait(timeout=2)
                service.sync_from_log_service(logs)

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(sync, service) for service in (first, second)]
                for future in futures:
                    future.result(timeout=5)

            summary = DashboardMetricsService(database_url=metrics_path).summary("24h")

        self.assertEqual(summary["totals"]["total"], 2)
        self.assertEqual(summary["totals"]["success"], 2)

    def test_log_cursor_recovers_appends_exactly_once_across_restarts(self) -> None:
        now = beijing_now().isoformat()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs = LogService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
            metrics_path = _database_url(root)
            logs.append_item(
                _call(started_at=now, status="success", call_id="call-a")
            )

            first = DashboardMetricsService(database_url=metrics_path)
            first.sync_from_log_service(logs)
            self.assertEqual(first.summary("24h")["totals"]["total"], 1)

            logs.append_item(
                _call(started_at=now, status="failed", call_id="call-b")
            )
            self.assertEqual(first.summary("24h")["totals"]["total"], 1)

            second = DashboardMetricsService(database_url=metrics_path)
            second.sync_from_log_service(logs)
            self.assertEqual(second.summary("24h")["totals"]["total"], 2)

            third = DashboardMetricsService(database_url=metrics_path)
            third.sync_from_log_service(logs)
            persisted = third.repository.load().data
            final_total = third.summary("24h")["totals"]["total"]

        self.assertEqual(final_total, 2)
        self.assertGreater(persisted["ingest"]["log_cursor"]["sequence"], 0)

    def test_unchanged_log_cursor_does_not_rewrite_metrics(self) -> None:
        now = beijing_now().isoformat()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs = LogService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
            metrics_path = _database_url(root)
            logs.append_item(_call(started_at=now, status="success", call_id="call-a"))
            service = DashboardMetricsService(database_url=metrics_path)
            service.sync_from_log_service(logs)

            revision_before = service.repository.load().revision
            rebuilt = service.sync_from_log_service(logs)
            revision_after = service.repository.load().revision

        self.assertFalse(rebuilt)
        self.assertEqual(revision_after, revision_before)

    def test_dashboard_sync_coalesces_requests_within_the_short_ttl(self) -> None:
        now = beijing_now().isoformat()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs = LogService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
            service = DashboardMetricsService(database_url=_database_url(root))
            logs.append_item(_call(started_at=now, status="success", call_id="call-a"))

            with patch(
                "services.dashboard_metrics_service.time.monotonic",
                side_effect=[100.0, 100.0, 100.5, 102.0, 102.0],
            ):
                self.assertTrue(service.sync_for_dashboard(logs))
                logs.append_item(_call(started_at=now, status="success", call_id="call-b"))
                self.assertFalse(service.sync_for_dashboard(logs))
                self.assertEqual(service.summary("24h")["totals"]["total"], 1)
                self.assertFalse(service.sync_for_dashboard(logs))

            summary = service.summary("24h")

        self.assertEqual(summary["totals"]["total"], 2)

    def test_degraded_checkpoint_is_rebuilt_before_it_can_be_ready_again(self) -> None:
        now = beijing_now().isoformat()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs = LogService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
            metrics_path = _database_url(root)
            service = DashboardMetricsService(database_url=metrics_path)
            logs.append_item(
                _call(started_at=now, status="success", call_id="call-a")
            )
            service.sync_from_log_service(logs)

            logs.append_item(
                _call(started_at=now, status="failed", call_id="call-b")
            )
            service.mark_ingest_failed("append_callback_failed")
            degraded_restart = DashboardMetricsService(database_url=metrics_path)
            self.assertTrue(degraded_restart.begin_startup())

            logs.append_item(
                _call(started_at=now, status="success", call_id="call-c")
            )
            degraded_restart.sync_from_log_service(logs)
            self.assertEqual(degraded_restart.summary("24h")["totals"]["total"], 3)
            self.assertTrue(degraded_restart.snapshot_many()["metrics"]["ready"])

            final_restart = DashboardMetricsService(database_url=metrics_path)
            final_restart.sync_from_log_service(logs)
            final_total = final_restart.summary("24h")["totals"]["total"]

        self.assertEqual(final_total, 3)

    def test_concurrent_log_cursor_syncs_do_not_double_count(self) -> None:
        now = beijing_now().isoformat()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs = LogService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
            metrics_path = _database_url(root)
            for call_id in ("call-a", "call-b"):
                logs.append_item(
                    _call(started_at=now, status="success", call_id=call_id)
                )

            first = DashboardMetricsService(database_url=metrics_path)
            second = DashboardMetricsService(database_url=metrics_path)
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(service.sync_from_log_service, logs)
                    for service in (first, second)
                ]
                for future in futures:
                    future.result(timeout=5)

            logs.append_item(
                _call(started_at=now, status="success", call_id="call-c")
            )
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(service.sync_from_log_service, logs)
                    for service in (second, first)
                ]
                for future in futures:
                    future.result(timeout=5)

            summary = DashboardMetricsService(database_url=metrics_path).summary("24h")

        self.assertEqual(summary["totals"]["total"], 3)

    def test_destructive_log_change_rotates_generation_and_rebuilds_metrics(self) -> None:
        now = beijing_now().isoformat()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logs = LogService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
            metrics = DashboardMetricsService(database_url=_database_url(root))
            logs.append_item(_call(started_at=now, status="success", call_id="call-a"))
            logs.append_item(_call(started_at=now, status="success", call_id="call-b"))

            self.assertTrue(metrics.sync_from_log_service(logs))
            self.assertEqual(logs.delete(["call-a"]), {"removed": 1})
            self.assertTrue(metrics.sync_from_log_service(logs))
            summary = metrics.summary("24h")

        self.assertEqual(summary["totals"]["total"], 1)
        self.assertEqual(summary["totals"]["success"], 1)

    def test_filtered_log_stats_total_counts_all_filter_matches(self) -> None:
        now = beijing_now().isoformat()
        with tempfile.TemporaryDirectory() as temp_dir:
            logs = LogService(database_url=f"sqlite:///{(Path(temp_dir) / 'app.db').as_posix()}")
            for index in range(3):
                logs.append_item(
                    _call(started_at=now, status="success", call_id=f"success-{index}")
                )
            logs.append_item(_call(started_at=now, status="failed", call_id="failed"))

            page = logs.list_page(type="call", status="success", limit=1)

        self.assertEqual(page["stats_scope"], "filtered")
        self.assertEqual(page["total"], 3)
        self.assertEqual(page["stats"]["total"], 3)
        self.assertEqual(len(page["items"]), 1)

class DashboardHttpContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_returns_three_ranges_and_does_not_run_expensive_scans(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            metrics = DashboardMetricsService(database_url=_database_url(Path(temp_dir)))
            metrics.sync_from_logs([])
            snapshot = metrics.snapshot_many()

        backend = Mock()
        backend.get_backend_info.return_value = {
            "type": "database",
            "db_type": "sqlite",
            "description": "Application Database (sqlite)",
        }
        backend.health_check.side_effect = AssertionError("dashboard must not run storage health checks")

        app = FastAPI()
        app.include_router(system.create_router("9.9.9-test"))
        transport = httpx.ASGITransport(app=app)
        with (
            patch("api.system.require_admin"),
            patch(
                "services.dashboard_view.account_service.get_stats",
                return_value={"total": 1, "active": 1},
            ),
            patch("services.dashboard_view.dashboard_metrics_service.snapshot_many", return_value=snapshot),
            patch("services.dashboard_view.dashboard_metrics_service.sync_for_dashboard") as sync_metrics,
            patch("services.dashboard_view.config.get_storage_backend", return_value=backend),
            patch(
                "services.dashboard_view.config.get_image_storage_settings",
                return_value={"enabled": False, "mode": "local"},
            ),
            patch("api.system.log_service.list", side_effect=AssertionError("dashboard must not scan logs")) as list_logs,
            patch("api.system.storage_stats", side_effect=AssertionError("dashboard must not scan images")) as image_stats,
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/dashboard?time_range=7d")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["meta"]["selected_range"], "7d")
        self.assertEqual(body["meta"]["available_ranges"], ["24h", "7d", "30d"])
        self.assertEqual(list(body["ranges"]), ["24h", "7d", "30d"])
        self.assertEqual(body["logs"], body["ranges"]["7d"])
        self.assertTrue(body["metrics"]["ready"])
        self.assertIsNone(body["ranges"]["24h"]["totals"]["success_rate"])
        self.assertEqual(body["ranges"]["24h"]["totals"]["final_failed"], 0)
        self.assertIsNone(body["ranges"]["24h"]["switching"]["recovery_rate"])
        self.assertEqual(
            body["storage"],
            {
                "application_database": {
                    "type": "database",
                    "db_type": "sqlite",
                    "description": "Application Database (sqlite)",
                },
                "image_storage": {
                    "enabled": False,
                    "mode": "local",
                    "status": "not_checked",
                    "available": None,
                    "image_count": None,
                    "image_size_bytes": None,
                },
            },
        )
        list_logs.assert_not_called()
        image_stats.assert_not_called()
        backend.health_check.assert_not_called()
        sync_metrics.assert_called_once()


if __name__ == "__main__":
    unittest.main()
