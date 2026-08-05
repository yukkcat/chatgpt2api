from __future__ import annotations

import unittest

from fastapi.routing import APIRoute
from pydantic import ValidationError

from api.monitor_contract import MonitorRecordDetailView, RealtimeMonitorView
from api.system import create_router
from services.monitor_view import build_monitor_record_view, build_monitor_view
from services.realtime_monitor_service import RealtimeMonitorService


class MonitorContractTests(unittest.TestCase):
    @staticmethod
    def _summary() -> dict[str, object]:
        return {
            "active": 1,
            "completed": 5,
            "success": 2,
            "partial_success": 1,
            "failed": 1,
            "rate_limited": 1,
            "text_review": 1,
            "success_rate": 50.0,
            "account_switch_requests": 2,
            "account_switches": 3,
            "account_switch_success": 1,
            "account_switch_recovery_rate": 50.0,
            "stream_error_requests": 1,
            "avg_duration_ms": 12_000,
            "p95_duration_ms": 24_000,
            "metric_p95": {
                "handler_queue_ms": 1_200,
                "stream_first_queue_ms": 800,
                "account_wait_ms": 5_500,
                "egress_wait_ms": 900,
                "poll_wait_ms": 8_000,
            },
            "slow_counts": {
                "handler_queue": 1,
                "stream_first_queue": 0,
                "account_wait": 1,
                "egress_wait": 0,
                "total_over_120s": 0,
                "local_reject_or_busy": 0,
            },
            "by_model": {"gpt-image-2": 5},
            "active_by_model": {"gpt-image-2": 1},
            "active_by_egress": {"account_group:primary/node-a": 1},
            "active_by_stage": {"上游生成中": 1, "等待账号": 0},
        }

    @staticmethod
    def _record(**overrides: object) -> dict[str, object]:
        record: dict[str, object] = {
            "call_id": "call-1",
            "endpoint": "/v1/images/generations",
            "model": "gpt-image-2",
            "status": "running",
            "stage": "image_generating",
            "stage_label": "上游生成中",
            "started_at": "2026-07-27 10:00:00",
            "updated_at": "2026-07-27 10:00:08",
            "elapsed_ms": 8_200,
            "stage_elapsed_ms": 3_000,
            "started_ts": 123.0,
            "stage_started_ts": 125.0,
            "metrics": {
                "handler_queue_ms": 120,
                "poll_wait_ms": 5_000,
            },
            "perf": {
                "handler_queue_ms": 200,
                "poll_wait_ms": 1_000,
                "conversation_stream_ms": 3_000,
            },
            "images": {
                "1": {
                    "index": 1,
                    "total": 2,
                    "account_attempt": 3,
                    "max_account_attempts": 4,
                    "account_switch_count": 2,
                    "metrics": {"poll_wait_ms": 5_000},
                }
            },
            "image_account_attempt": 3,
            "image_account_max_attempts": 4,
            "image_account_switch_count": 2,
            "proxy_source": "account_group",
            "proxy_group_id": "primary",
            "proxy_node_name": "node-a",
            "has_proxy": True,
        }
        record.update(overrides)
        return record

    def _snapshot(self) -> dict[str, object]:
        outcomes = (
            ("success", "success"),
            ("partial", "partial_success"),
            ("failed", "failed"),
            ("rate", "rate_limited"),
            ("text", "text_review"),
        )
        recent = [
            self._record(
                call_id=call_id,
                status="success" if outcome == "partial_success" else outcome,
                outcome=outcome,
                elapsed_ms=None,
                stage_elapsed_ms=None,
                duration_ms=8_200,
            )
            for call_id, outcome in outcomes
        ]
        return {
            "updated_at": "2026-07-27 10:00:09",
            "threadpool": {"tokens": 80, "previous_tokens": 40},
            "window": {
                "completed": 5,
                "completed_capacity": 500,
                "events": 2,
                "event_capacity": 1_000,
            },
            "summary": self._summary(),
            "active": [self._record()],
            "recent": recent,
            "slow": [recent[2]],
            "events": [
                {
                    "time": "2026-07-27 10:00:08",
                    "call_id": "call-1",
                    "event": "image_generating",
                    "label": "上游生成中",
                    "model": "gpt-image-2",
                    "conversation_stream_ms": 3_000,
                    "poll_wait_ms": 5_000,
                }
            ],
            "metric_labels": {"poll_wait_ms": "等待图片结果"},
        }

    def test_snapshot_projects_one_validated_backend_view(self) -> None:
        payload = build_monitor_view(self._snapshot())
        validated = RealtimeMonitorView.model_validate(payload)

        self.assertEqual(validated.schema_version, 1)
        self.assertEqual(validated.completed_window_text, "窗口 5 / 500")
        self.assertEqual(validated.entry_queue_text, "1.2s")
        self.assertEqual(validated.active_stage_items[0].label, "上游生成中")
        self.assertEqual(len(validated.diagnostic_groups), 6)
        self.assertTrue(all(item.tone in {"success", "danger", "warning", "info", "muted"} for group in validated.diagnostic_groups for item in group.items))
        self.assertNotIn("events", payload)

    def test_canonical_timings_and_record_presentations_match_frontend_rules(self) -> None:
        row = build_monitor_view(self._snapshot())["active"][0]

        self.assertEqual(row["metrics"]["handler_queue_ms"], 120)
        self.assertEqual(row["perf"]["handler_queue_ms"], 200)
        self.assertEqual(row["timings_ms"]["handler_queue_ms"], 200)
        self.assertEqual(row["timings_ms"]["poll_wait_ms"], 5_000)
        self.assertEqual(row["egress"]["display"], "账号组 primary/node-a")
        self.assertEqual(row["account_attempt"]["display"], "最高第 3/4 次 · 已切换 2 次")
        self.assertEqual(row["presentation"]["metric_digest"], "当前阶段 3.0s / 等待结果 5.0s / 上游生成 3.0s / 等待入口 200ms")
        self.assertEqual(row["presentation"]["stage_text"], "上游生成中")
        self.assertEqual(row["presentation"]["error_text"], "")
        self.assertEqual(row["presentation"]["account_egress_text"], "账号 - / 出口 -")
        self.assertEqual(row["presentation"]["slow_reason_code"], "image_poll_wait")
        self.assertEqual(row["presentation"]["tracked_duration_ms"], 8_200)
        self.assertEqual(row["presentation"]["untracked_duration_ms"], 0)
        self.assertNotIn("started_ts", row)
        self.assertNotIn("stage_started_ts", row)

    def test_outcome_status_and_partial_success_remain_distinct(self) -> None:
        rows = {row["call_id"]: row for row in build_monitor_view(self._snapshot())["recent"]}

        self.assertEqual(rows["success"]["presentation"]["status_label"], "成功")
        self.assertEqual(rows["partial"]["status"], "success")
        self.assertEqual(rows["partial"]["outcome"], "partial_success")
        self.assertEqual(rows["partial"]["presentation"]["status_label"], "部分成功")
        self.assertEqual(rows["failed"]["presentation"]["status_tone"], "danger")
        self.assertEqual(rows["rate"]["presentation"]["status_label"], "限流")
        self.assertEqual(rows["text"]["presentation"]["status_label"], "文本")

    def test_summary_derives_measured_switch_and_egress_fields(self) -> None:
        summary = build_monitor_view(self._snapshot())["summary"]

        self.assertEqual(summary["measured"], 4)
        self.assertEqual(summary["entry_queue_p95_ms"], 1_200)
        self.assertEqual(summary["switch_unrecovered"], 1)
        self.assertEqual(summary["switch_average"], 1.5)
        self.assertEqual(summary["active_egress_count"], 1)

    def test_egress_projection_covers_direct_default_group_and_runtime(self) -> None:
        snapshot = self._snapshot()
        snapshot["active"] = [
            self._record(call_id="direct", proxy_source="direct", proxy_group_id="", proxy_node_name="", has_proxy=False),
            self._record(call_id="default", proxy_source="default", proxy_group_id="", proxy_node_name="", proxy_hash="abc123"),
            self._record(call_id="group", proxy_source="account_group", proxy_group_id="g1", proxy_node_name="n1"),
            self._record(call_id="runtime", proxy_source="runtime_resource", proxy_group_id="", proxy_node_name="", egress_label="asset-proxy"),
        ]
        rows = {row["call_id"]: row["egress"]["display"] for row in build_monitor_view(snapshot)["active"]}

        self.assertEqual(rows["direct"], "直连")
        self.assertEqual(rows["default"], "默认 abc123")
        self.assertEqual(rows["group"], "账号组 g1/n1")
        self.assertEqual(rows["runtime"], "资源代理 asset-proxy")

    def test_untracked_duration_gets_a_stable_reason_code(self) -> None:
        snapshot = self._snapshot()
        snapshot["slow"] = [self._record(duration_ms=20_000, elapsed_ms=None, stage_elapsed_ms=None)]
        presentation = build_monitor_view(snapshot)["slow"][0]["presentation"]

        self.assertEqual(presentation["tracked_duration_ms"], 8_200)
        self.assertEqual(presentation["untracked_duration_ms"], 11_800)
        self.assertEqual(presentation["slow_reason_code"], "instrumentation_gap")

    def test_record_detail_projects_and_validates_its_stage_timeline(self) -> None:
        record = self._record(
            events=[
                {
                    "time": "2026-07-27 10:00:08",
                    "call_id": "call-1",
                    "event": "image_generating",
                    "label": "上游生成中",
                    "conversation_stream_ms": 3_000,
                    "switched_account": True,
                    "previous_account_email": "first@example.com",
                    "account_email": "second@example.com",
                    "public_error": "上游账号不可用",
                }
            ]
        )

        payload = build_monitor_record_view(record)
        detail = MonitorRecordDetailView.model_validate(payload)

        self.assertNotIn("detail_presentation", payload)
        self.assertEqual(detail.events[0].label, "上游生成中")
        self.assertEqual(detail.events[0].timing_text, "上游生成 3.0s")
        self.assertEqual(
            detail.events[0].detail_text,
            "已切换账号 · first@example.com → second@example.com · 上游账号不可用",
        )

    def test_record_text_fallbacks_are_resolved_by_backend(self) -> None:
        snapshot = self._snapshot()
        snapshot["active"] = [
            self._record(call_id="label", stage_label="  可读阶段  ", stage="raw-stage"),
            self._record(call_id="stage", stage_label="", stage="raw-stage"),
            self._record(call_id="running", stage_label="", stage=""),
            self._record(
                call_id="error",
                public_error="  public error  ",
                error="internal error",
            ),
        ]
        rows = {
            row["call_id"]: row["presentation"]
            for row in build_monitor_view(snapshot)["active"]
        }

        self.assertEqual(rows["label"]["stage_text"], "可读阶段")
        self.assertEqual(rows["stage"]["stage_text"], "raw-stage")
        self.assertEqual(rows["running"]["stage_text"], "运行中")
        self.assertEqual(rows["error"]["error_text"], "public error")

    def test_empty_event_label_falls_back_to_event_name(self) -> None:
        record = self._record(events=[{
            "time": "2026-07-27 10:00:08",
            "call_id": "call-1",
            "event": "image_generating",
            "label": "",
        }])

        event = build_monitor_record_view(record)["events"][0]

        self.assertEqual(event["label"], "image_generating")

    def test_strict_contract_rejects_unknown_response_fields(self) -> None:
        payload = build_monitor_view(self._snapshot())
        payload["unexpected"] = True
        with self.assertRaises(ValidationError):
            RealtimeMonitorView.model_validate(payload)

    def test_route_publishes_strict_snapshot_model(self) -> None:
        routes = {
            route.path: route
            for route in create_router("test").routes
            if isinstance(route, APIRoute)
        }

        self.assertIs(routes["/api/monitor/realtime"].response_model, RealtimeMonitorView)
        self.assertIs(routes["/api/monitor/realtime/{call_id}"].response_model, MonitorRecordDetailView)

    def test_live_service_snapshot_validates_without_changing_collection(self) -> None:
        service = RealtimeMonitorService()
        service.start("live", endpoint="/v1/images/generations", model="gpt-image-2")
        service.stage(
            "live",
            "image_generating",
            index=1,
            total=1,
            attempt=1,
            max_account_attempts=4,
            conversation_stream_ms=2_000,
        )

        RealtimeMonitorView.model_validate(build_monitor_view(service.snapshot()))


if __name__ == "__main__":
    unittest.main()
