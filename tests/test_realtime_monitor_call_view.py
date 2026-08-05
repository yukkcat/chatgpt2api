from __future__ import annotations

import unittest

from services.call_view import build_call_summary
from services.realtime_monitor_service import RealtimeMonitorService


class RealtimeMonitorCallViewTests(unittest.TestCase):
    @staticmethod
    def _base_detail(call_id: str, **overrides: object) -> dict[str, object]:
        detail: dict[str, object] = {
            "call_id": call_id,
            "endpoint": "/v1/images/generations",
            "model": "gpt-image-2",
            "started_at": "2026-07-25 01:00:00",
            "ended_at": "2026-07-25 01:00:02",
            "duration_ms": 2000,
            "status": "success",
        }
        detail.update(overrides)
        return detail

    @staticmethod
    def _start(service: RealtimeMonitorService, call_id: str) -> None:
        service.start(
            call_id,
            endpoint="/v1/images/generations",
            model="gpt-image-2",
            summary="文生图",
            role="admin",
            key_name="管理员",
        )

    def test_completed_record_reuses_shared_call_summary(self) -> None:
        service = RealtimeMonitorService()
        self._start(service, "call-success")
        detail = self._base_detail(
            "call-success",
            request_meta={"n": 2},
            result_data_count=2,
            image_attempts=[
                {
                    "slot": 1,
                    "attempt": 1,
                    "status": "failed",
                    "switched_account": True,
                    "public_error": "first account failed",
                },
                {
                    "slot": 1,
                    "attempt": 2,
                    "status": "success",
                    "switched_account": False,
                },
                {
                    "slot": 2,
                    "attempt": 1,
                    "status": "success",
                    "switched_account": False,
                },
            ],
        )

        service.finish(detail)
        snapshot = service.snapshot()
        row = snapshot["recent"][0]
        expected = build_call_summary(
            {
                "id": "call-success",
                "time": detail["started_at"],
                "type": "call",
                "summary": "文生图",
                "detail": detail,
            }
        )

        for key in (
            "outcome",
            "attempt_count",
            "switch_count",
            "recovered_after_switch",
            "image_requested_count",
            "image_succeeded_count",
            "image_failed_count",
            "image_result_status",
            "public_error",
        ):
            self.assertEqual(row[key], expected[key])
        self.assertEqual(row["outcome"], "success")
        self.assertEqual(row["attempt_count"], 3)
        self.assertEqual(row["switch_count"], 1)
        self.assertTrue(row["recovered_after_switch"])
        self.assertEqual(snapshot["summary"]["account_switch_requests"], 1)
        self.assertEqual(snapshot["summary"]["account_switches"], 1)
        self.assertEqual(snapshot["summary"]["account_switch_success"], 1)

    def test_success_after_account_switch_clears_only_call_level_diagnostics(self) -> None:
        service = RealtimeMonitorService()
        self._start(service, "call-recovered")
        service.stage(
            "call-recovered",
            "image_attempt_failed",
            index=1,
            total=1,
            attempt=1,
            status="failed",
            failure_code="image_quota_exhausted",
            public_error="first account failed",
            raw_error="first raw error",
            upstream_error="first upstream error",
            upstream_message="first upstream message",
            account_failure=True,
        )
        service.stage(
            "call-recovered",
            "image_cross_account_retry",
            index=1,
            total=1,
            attempt=2,
            account_switch_count=1,
        )
        detail = self._base_detail(
            "call-recovered",
            request_meta={"n": 1},
            result_data_count=1,
            image_attempts=[
                {
                    "slot": 1,
                    "attempt": 1,
                    "status": "failed",
                    "failure_code": "image_quota_exhausted",
                    "public_error": "first account failed",
                    "upstream_error": "first upstream error",
                    "switched_account": True,
                },
                {
                    "slot": 1,
                    "attempt": 2,
                    "status": "success",
                    "switched_account": False,
                },
            ],
        )

        service.finish(detail)

        monitor = detail["monitor"]
        for key in ("error", "raw_error", "upstream_error", "upstream_message"):
            self.assertNotIn(key, monitor)
        self.assertEqual(
            detail["image_attempts"][0]["upstream_error"],
            "first upstream error",
        )
        self.assertTrue(
            any(
                event.get("upstream_error") == "first upstream error"
                for event in monitor["events"]
            )
        )
        self.assertEqual(service.snapshot()["recent"][0]["outcome"], "success")

    def test_completed_aggregate_keeps_outcomes_mutually_exclusive(self) -> None:
        service = RealtimeMonitorService()
        cases = (
            ("rate", {"status": "failed", "status_code": 429, "error_code": "image_quota_exhausted"}),
            ("text", {"status": "failed", "status_code": 400, "error_code": "upstream_text_reply"}),
            ("failed", {"status": "failed", "status_code": 502, "error_code": "image_tool_error"}),
        )
        for call_id, values in cases:
            self._start(service, call_id)
            service.finish(self._base_detail(call_id, **values))

        snapshot = service.snapshot()
        outcomes = {row["call_id"]: row["outcome"] for row in snapshot["recent"]}
        self.assertEqual(outcomes, {"failed": "failed", "text": "text_review", "rate": "rate_limited"})
        self.assertEqual(snapshot["summary"]["success"], 0)
        self.assertEqual(snapshot["summary"]["failed"], 1)
        self.assertEqual(snapshot["summary"]["rate_limited"], 1)
        self.assertEqual(snapshot["summary"]["text_review"], 1)
        self.assertEqual(snapshot["summary"]["success_rate"], 0)

    def test_completed_rate_limit_uses_one_terminal_state_everywhere(self) -> None:
        service = RealtimeMonitorService()
        self._start(service, "call-rate-limited")
        payload = self._base_detail(
            "call-rate-limited",
            status="failed",
            status_code=429,
            error_code="image_quota_exhausted",
        )
        service.finish(payload)

        snapshot = service.snapshot()
        row = snapshot["recent"][0]
        final_event = snapshot["events"][0]

        self.assertEqual(row["outcome"], "rate_limited")
        self.assertEqual(row["status"], "rate_limited")
        self.assertEqual(row["stage"], "rate_limited")
        self.assertEqual(row["stage_label"], "限流")
        self.assertEqual(final_event["event"], "rate_limited")
        self.assertEqual(final_event["label"], "限流")
        self.assertEqual(payload["monitor"]["stage"], "rate_limited")
        self.assertEqual(payload["monitor"]["stage_label"], "限流")

    def test_partial_success_uses_shared_image_counts(self) -> None:
        service = RealtimeMonitorService()
        self._start(service, "call-partial")
        service.finish(
            self._base_detail(
                "call-partial",
                request_meta={"n": 2},
                result_data_count=1,
                image_attempts=[
                    {"slot": 1, "attempt": 1, "status": "failed", "switched_account": True},
                    {"slot": 2, "attempt": 1, "status": "success", "switched_account": False},
                ],
            )
        )

        snapshot = service.snapshot()
        row = snapshot["recent"][0]
        self.assertEqual(row["outcome"], "partial_success")
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["image_requested_count"], 2)
        self.assertEqual(row["image_succeeded_count"], 1)
        self.assertEqual(row["image_failed_count"], 1)
        self.assertEqual(snapshot["summary"]["success"], 1)
        self.assertEqual(snapshot["summary"]["partial_success"], 1)

    def test_active_stage_contract_is_unchanged(self) -> None:
        service = RealtimeMonitorService()
        self._start(service, "call-active")
        service.stage(
            "call-active",
            "image_cross_account_retry",
            index=1,
            total=1,
            attempt=2,
            max_account_attempts=4,
            account_switch_count=1,
            account_email="next@example.com",
        )

        row = service.snapshot()["active"][0]
        self.assertEqual(row["status"], "running")
        self.assertEqual(row["stage"], "image_cross_account_retry")
        self.assertEqual(row["image_account_attempt"], 2)
        self.assertEqual(row["image_account_max_attempts"], 4)
        self.assertEqual(row["image_account_switch_count"], 1)
        self.assertNotIn("outcome", row)

    def test_call_detail_returns_active_events_in_chronological_order(self) -> None:
        service = RealtimeMonitorService()
        self._start(service, "call-detail-active")
        service.stage("call-detail-active", "image_getting_account")
        service.stage("call-detail-active", "image_generating", conversation_stream_ms=800)

        detail = service.call_detail("call-detail-active")

        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["status"], "running")
        self.assertEqual(
            [event["event"] for event in detail["events"]],
            ["handler_submitted", "image_getting_account", "image_generating"],
        )
        self.assertNotIn("started_ts", detail)
        self.assertNotIn("stage_started_ts", detail)

    def test_call_detail_returns_completed_record_with_terminal_event(self) -> None:
        service = RealtimeMonitorService()
        self._start(service, "call-detail-completed")
        service.stage("call-detail-completed", "image_generating")
        service.finish(self._base_detail("call-detail-completed"))

        detail = service.call_detail("call-detail-completed")

        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["status"], "success")
        self.assertEqual(detail["events"][-1]["event"], "completed")

    def test_call_detail_returns_none_for_unknown_or_empty_call_id(self) -> None:
        service = RealtimeMonitorService()

        self.assertIsNone(service.call_detail("missing"))
        self.assertIsNone(service.call_detail("  "))


if __name__ == "__main__":
    unittest.main()
