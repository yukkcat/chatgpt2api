from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from api import system
from api.call_contract import AttemptSummary, CallDetail, CallSummaryPage
from services.call_view import build_attempt_summary, build_call_detail, build_call_summary
from services.log_service import LogService


def _call_log(*, call_id: str = "call-1", status: str = "success") -> dict:
    return {
        "id": call_id,
        "time": "2026-07-25 01:00:00",
        "type": "call",
        "summary": "图片调用完成",
        "detail": {
            "call_id": call_id,
            "endpoint": "/v1/images/generations",
            "model": "gpt-image-2",
            "started_at": "2026-07-25 01:00:00",
            "ended_at": "2026-07-25 01:00:04",
            "duration_ms": 4130,
            "status": status,
            "status_code": 200 if status == "success" else 502,
            "request_text": "short prompt",
            "request_text_full": "complete prompt for detail only",
            "request_meta": {"n": 2},
            "urls": ["/images/one.png"],
            "public_error": "" if status == "success" else "Image generation failed.",
            "upstream_error": "" if status == "success" else "upstream diagnostic",
            "upstream_text": "" if status == "success" else "upstream text",
            "image_attempts": [
                {
                    "slot": 1,
                    "attempt": 1,
                    "status": "failed",
                    "error_code": "image_tool_error",
                    "switched_account": True,
                },
                {
                    "slot": 1,
                    "attempt": 2,
                    "status": "success",
                    "account_email": "second@example.com",
                },
            ],
        },
    }


class CallViewContractTests(unittest.TestCase):
    def test_attempt_result_status_comes_from_delivery_scope(self) -> None:
        attempt = build_attempt_summary({
            "slot": 1,
            "attempt": 1,
            "status": "failed",
            "failure_code": "signed_asset_delivery_failed",
            "failure_scope": "delivery",
            "status_code": 502,
        })

        self.assertEqual(attempt["outcome"], "failed")
        self.assertEqual(attempt["result_status"], "generated_but_delivery_failed")
        self.assertEqual(attempt["presentation"]["status"], {"label": "生成成功", "tone": "warning"})
        self.assertEqual(attempt["presentation"]["failure_label"], "结果交付失败")

    def test_image_download_failure_code_is_delivery_fallback(self) -> None:
        attempt = build_attempt_summary({
            "slot": 1,
            "attempt": 1,
            "status": "failed",
            "failure_code": "image_download_failed",
            "status_code": 502,
        })

        self.assertEqual(attempt["result_status"], "generated_but_delivery_failed")

    def test_generic_error_code_does_not_turn_success_into_delivery_failure(self) -> None:
        attempt = build_attempt_summary({
            "slot": 1,
            "attempt": 1,
            "status": "success",
            "failure_code": "diagnostic_warning",
        })

        self.assertEqual(attempt["outcome"], "success")
        self.assertEqual(attempt["result_status"], "success")

    def test_non_delivery_attempt_failure_remains_failed(self) -> None:
        attempt = build_attempt_summary({
            "slot": 1,
            "attempt": 1,
            "status": "failed",
            "failure_code": "image_poll_timeout",
            "failure_scope": "transient",
            "status_code": 502,
        })

        self.assertEqual(attempt["outcome"], "failed")
        self.assertEqual(attempt["result_status"], "failed")
        self.assertEqual(attempt["error_label"], "等待图片结果超时")
        self.assertEqual(attempt["presentation"]["failure_label"], "等待图片结果超时")
        self.assertEqual(attempt["presentation"]["marker_tone"], "danger")

    def test_retry_duration_breakdown_uses_monitor_metrics(self) -> None:
        item = _call_log()
        attempts = item["detail"]["image_attempts"]
        attempts[0]["monitor"] = {"metrics": {"total_ms": 1_200}}
        attempts[1]["monitor"] = {"metrics": {"total_ms": 3_400}}

        summary = build_call_summary(item)
        detail = build_call_detail(item)

        self.assertEqual(summary["presentation"]["duration"]["breakdown"], "(1.2s + 3.4s)")
        self.assertEqual([attempt["duration_ms"] for attempt in detail["attempts"]], [1_200, 3_400])

    def test_summary_is_lightweight_and_uses_canonical_result_fields(self) -> None:
        summary = build_call_summary(_call_log())

        self.assertEqual(summary["outcome"], "partial_success")
        self.assertEqual(summary["attempt_count"], 2)
        self.assertEqual(summary["switch_count"], 1)
        self.assertTrue(summary["recovered_after_switch"])
        self.assertEqual(summary["image_requested_count"], 2)
        self.assertEqual(summary["image_succeeded_count"], 1)
        self.assertEqual(summary["image_failed_count"], 1)
        self.assertNotIn("request_text_full", summary)
        self.assertNotIn("raw_detail", summary)

    def test_detail_preserves_diagnostics_without_changing_summary(self) -> None:
        item = _call_log(status="failed")
        detail = build_call_detail(item)

        self.assertEqual(
            {key: detail[key] for key in build_call_summary(item)},
            build_call_summary(item),
        )
        self.assertEqual(detail["request_text_full"], "complete prompt for detail only")
        self.assertEqual(detail["upstream_error"], "upstream diagnostic")
        self.assertEqual(detail["upstream_text"], "upstream text")
        self.assertEqual(len(detail["attempts"]), 2)
        self.assertTrue(detail["detail_presentation"]["has_attempt_breakdown"])
        self.assertEqual(
            detail["detail_presentation"]["attempt_groups"],
            [
                {
                    "slot": 1,
                    "slot_label": "图片 1",
                    "attempt_count": 2,
                    "attempt_text": "2 次尝试",
                    "switch_count": 1,
                    "switch_text": "切换 1 次",
                    "status": {"label": "成功", "tone": "success"},
                },
                {
                    "slot": 2,
                    "slot_label": "图片 2",
                    "attempt_count": 0,
                    "attempt_text": "0 次尝试",
                    "switch_count": 0,
                    "switch_text": "",
                    "status": {"label": "未记录", "tone": "muted"},
                },
            ],
        )
        CallDetail.model_validate(detail)

    def test_detail_fields_and_diagnostics_are_projected_by_backend(self) -> None:
        item = _call_log(status="failed")
        item["detail"].update(
            key_id="sk-example-secret-token",
            key_name="管理员",
            proxy_source="account_group",
            proxy_group_id="primary",
            proxy_node_name="node-a",
            reason="upstream rejected",
            upstream_error_type="token_revoked",
            upstream_request_id="req-1",
            tool_invoked=True,
            blocked=False,
            request_shape={"remote_image_urls": 1},
        )

        presentation = build_call_detail(item)["detail_presentation"]
        primary = {field["label"]: field["value"] for field in presentation["primary_fields"]}
        diagnostics = {field["label"]: field["value"] for field in presentation["diagnostic_fields"]}

        self.assertEqual(primary["出口"], "账号组 primary/node-a")
        self.assertEqual(primary["密钥"], "管理员 / sk-ex***oken")
        self.assertNotIn("账号", primary)
        self.assertNotIn("会话 ID", primary)
        self.assertEqual(diagnostics["状态码"], "502")
        self.assertEqual(diagnostics["原因"], "upstream rejected")
        self.assertEqual(diagnostics["上游错误"], "token_revoked")
        self.assertEqual(diagnostics["工具调用"], "true")
        self.assertEqual(diagnostics["阻断"], "false")

    def test_single_attempt_keeps_identity_fields_and_has_no_group_summary(self) -> None:
        item = _call_log()
        item["detail"].update(
            request_meta={"n": 1},
            urls=["/images/one.png"],
            account_email="one@example.com",
            conversation_id="conversation-1",
            image_attempts=[{
                "slot": 1,
                "attempt": 1,
                "status": "success",
                "account_email": "one@example.com",
            }],
        )

        presentation = build_call_detail(item)["detail_presentation"]
        primary = {field["label"]: field["value"] for field in presentation["primary_fields"]}

        self.assertFalse(presentation["has_attempt_breakdown"])
        self.assertEqual(presentation["attempt_groups"], [])
        self.assertEqual(primary["账号"], "one@example.com")
        self.assertEqual(primary["会话 ID"], "conversation-1")

    def test_clean_success_has_no_diagnostics_and_zero_status_is_hidden(self) -> None:
        item = _call_log()
        item["detail"].update(
            status="success",
            status_code=0,
            stage="completed",
            request_meta={"n": 1},
            urls=["/images/one.png"],
            image_attempts=[],
        )

        presentation = build_call_detail(item)["detail_presentation"]

        self.assertEqual(presentation["diagnostic_fields"], [])

    def test_timeline_auto_expand_is_a_backend_decision(self) -> None:
        item = _call_log()
        item["detail"].update(
            request_meta={},
            urls=[],
            image_attempts=[],
            endpoint="/v1/chat/completions",
            model="gpt-4.1",
            duration_ms=179_999,
        )
        self.assertFalse(build_call_detail(item)["detail_presentation"]["auto_expand_timeline"])

        item["detail"]["duration_ms"] = 180_000
        self.assertTrue(build_call_detail(item)["detail_presentation"]["auto_expand_timeline"])

        item["detail"].update(duration_ms=1_000, status="failed", status_code=502)
        self.assertTrue(build_call_detail(item)["detail_presentation"]["auto_expand_timeline"])

        item["detail"].update(status="success", status_code=200, metrics={"stream_error_ms": 1})
        self.assertTrue(build_call_detail(item)["detail_presentation"]["auto_expand_timeline"])

    def test_timeline_presentation_is_projected_by_backend(self) -> None:
        item = _call_log()
        item["detail"].update(
            request_meta={"n": 1},
            request_shape={"input_image_parts": 1, "remote_image_urls": 2},
            image_attempts=[],
            metrics={
                "handler_queue_ms": 1_000,
                "upload_ms": 70,
                "bootstrap_ms": 2_000,
                "generation_start_ms": 100,
                "sse_stream_ms": 200,
                "conversation_stream_ms": 5_070,
                "resolve_ms": 50,
                "download_ms": 60,
            },
            monitor={
                "events": [
                    {
                        "time": "2026-07-25 01:00:01",
                        "handler_queue_ms": 1_000,
                    },
                ],
            },
        )

        timeline = build_call_detail(item)["detail_presentation"]["timeline"]
        segments = {segment["key"]: segment for segment in timeline["segments"]}
        groups = {group["key"]: group for group in timeline["groups"]}
        steps = {
            step["key"]: step
            for group in timeline["groups"]
            for step in group["steps"]
        }

        self.assertEqual(segments["entry_queue"]["label"], "入口排队")
        self.assertEqual(segments["entry_queue"]["category"], "entry")
        self.assertEqual(segments["entry_queue"]["tone"], "warning")
        self.assertEqual(segments["entry_queue"]["value_text"], "1s")
        self.assertEqual(segments["upstream"]["value_ms"], 3_000)
        self.assertEqual(groups["prepare"]["label"], "上游准备")
        self.assertEqual(steps["handler_queue_ms"]["status_label"], "慢")
        self.assertEqual(steps["handler_queue_ms"]["time"], "2026-07-25 01:00:01")
        self.assertEqual(
            steps["upload_ms"]["description"],
            "参考图上传 · 输入图 1 · 远程图 2",
        )
        self.assertEqual(
            steps["resolve_ms"]["description"],
            "file ID / 下载地址 · 结果图 1",
        )
        self.assertEqual(
            steps["download_ms"]["description"],
            "图片文件下载 · 下载 1 张",
        )
        self.assertIn(
            {
                "key": "warning",
                "label": "超过阈值",
                "category": "state",
                "tone": "warning",
            },
            timeline["legend_items"],
        )

    def test_timeline_thresholds_and_stream_error_tone_are_backend_decisions(self) -> None:
        item = _call_log()
        item["detail"].update(
            request_meta={"n": 1},
            urls=[],
            image_attempts=[],
            metrics={"account_wait_ms": 9_999, "stream_error_ms": 1},
        )

        timeline = build_call_detail(item)["detail_presentation"]["timeline"]
        steps = {
            step["key"]: step
            for group in timeline["groups"]
            for step in group["steps"]
        }

        self.assertEqual(steps["account_wait_ms"]["tone"], "info")
        self.assertEqual(steps["stream_error_ms"]["tone"], "danger")
        self.assertEqual(steps["stream_error_ms"]["status_label"], "异常")
        self.assertEqual(
            next(segment for segment in timeline["segments"] if segment["key"] == "upstream")["tone"],
            "danger",
        )

        item["detail"]["metrics"]["account_wait_ms"] = 10_000
        timeline = build_call_detail(item)["detail_presentation"]["timeline"]
        account_step = next(
            step
            for group in timeline["groups"]
            for step in group["steps"]
            if step["key"] == "account_wait_ms"
        )
        self.assertEqual(account_step["tone"], "warning")

    def test_attempt_timeline_is_projected_and_top_level_timeline_is_suppressed(self) -> None:
        item = _call_log()
        item["detail"]["metrics"] = {"handler_queue_ms": 500}
        item["detail"]["image_attempts"][0]["monitor"] = {
            "metrics": {"account_wait_ms": 10_000},
            "events": [{"time": "2026-07-25 01:00:02", "account_wait_ms": 10_000}],
        }

        detail = build_call_detail(item)

        self.assertEqual(
            detail["detail_presentation"]["timeline"],
            {"segments": [], "legend_items": [], "groups": []},
        )
        attempt_timeline = detail["attempts"][0]["presentation"]["timeline"]
        account_step = next(
            step
            for group in attempt_timeline["groups"]
            for step in group["steps"]
            if step["key"] == "account_wait_ms"
        )
        self.assertEqual(account_step["tone"], "warning")
        self.assertEqual(account_step["time"], "2026-07-25 01:00:02")

    def test_string_booleans_and_attempt_indexes_are_normalized(self) -> None:
        switched = build_attempt_summary({
            "slot": 0,
            "attempt": "0",
            "status": "failed",
            "switched_account": "true",
        })
        not_switched = build_attempt_summary({
            "slot": None,
            "attempt": None,
            "status": "failed",
            "switched_account": "false",
        })

        self.assertEqual((switched["slot"], switched["attempt"]), (1, 1))
        self.assertTrue(switched["switched_account"])
        self.assertFalse(not_switched["switched_account"])
        AttemptSummary.model_validate(switched)
        AttemptSummary.model_validate(not_switched)

        item = _call_log()
        item["detail"]["image_attempts"] = [
            {"slot": 0, "attempt": 0, "status": "failed", "switched_account": "TRUE"},
            {"slot": 1, "attempt": 2, "status": "success", "switched_account": "false"},
        ]
        detail = build_call_detail(item)
        self.assertEqual(detail["switch_count"], 1)
        self.assertEqual(
            [(attempt["slot"], attempt["attempt"]) for attempt in detail["attempts"]],
            [(1, 1), (1, 2)],
        )

    def test_positive_string_boolean_diagnostics_are_visible(self) -> None:
        item = _call_log()
        item["detail"].update(
            request_meta={"n": 1},
            image_attempts=[],
            tool_invoked="false",
            blocked="true",
        )

        fields = {
            field["label"]: field["value"]
            for field in build_call_detail(item)["detail_presentation"]["diagnostic_fields"]
        }

        self.assertEqual(fields["工具调用"], "false")
        self.assertEqual(fields["阻断"], "true")

    def test_non_anomalous_boolean_diagnostics_are_hidden_on_success(self) -> None:
        item = _call_log()
        item["detail"].update(
            request_meta={"n": 1},
            image_attempts=[],
            tool_invoked="true",
            blocked="false",
        )

        fields = build_call_detail(item)["detail_presentation"]["diagnostic_fields"]

        self.assertEqual(fields, [])

    def test_account_status_aliases_are_normalized(self) -> None:
        cases = {
            "ready": ("正常", "success", "success"),
            "rate_limited": ("限流", "rate_limited", "warning"),
            "invalid": ("异常", "failed", "danger"),
            "disabled": ("禁用", "unknown", "muted"),
        }
        for raw_status, expected in cases.items():
            with self.subTest(raw_status=raw_status):
                summary = build_call_summary({
                    "type": "account",
                    "detail": {"status": raw_status},
                })
                display_status, outcome, tone = expected
                self.assertEqual(summary["display_status"], display_status)
                self.assertEqual(summary["outcome"], outcome)
                self.assertEqual(summary["presentation"]["status"], {
                    "label": display_status,
                    "tone": tone,
                })

    def test_single_delivery_failure_gets_an_attempt_breakdown(self) -> None:
        item = _call_log(status="failed")
        item["detail"].update(
            request_meta={"n": 1},
            urls=[],
            account_email="delivery@example.com",
            conversation_id="delivery-conversation",
            image_attempts=[{
                "slot": 1,
                "attempt": 1,
                "status": "failed",
                "failure_scope": "delivery",
                "failure_code": "signed_asset_delivery_failed",
                "monitor": {"metrics": {"download_ms": 500}},
            }],
        )

        detail = build_call_detail(item)
        presentation = detail["detail_presentation"]

        self.assertTrue(presentation["has_attempt_breakdown"])
        self.assertEqual(presentation["attempt_groups"][0]["status"], {
            "label": "生成成功",
            "tone": "warning",
        })
        self.assertEqual(
            detail["attempts"][0]["result_status"],
            "generated_but_delivery_failed",
        )
        self.assertTrue(detail["attempts"][0]["presentation"]["timeline"]["groups"])
        primary = {field["label"]: field["value"] for field in presentation["primary_fields"]}
        self.assertEqual(primary["账号"], "delivery@example.com")
        self.assertEqual(primary["会话 ID"], "delivery-conversation")
        attempt_steps = {
            step["key"]: step
            for group in detail["attempts"][0]["presentation"]["timeline"]["groups"]
            for step in group["steps"]
        }
        self.assertEqual(
            attempt_steps["download_ms"]["description"],
            "图片文件下载 · 下载 1 张",
        )

    def test_requested_slots_without_attempts_do_not_show_empty_attempt_panel(self) -> None:
        item = _call_log(status="failed")
        item["detail"].update(
            request_meta={"n": 3},
            urls=[],
            image_attempts=[],
            metrics={"handler_queue_ms": 250},
        )

        presentation = build_call_detail(item)["detail_presentation"]

        self.assertFalse(presentation["has_attempt_breakdown"])
        self.assertEqual(presentation["attempt_groups"], [])
        self.assertTrue(presentation["timeline"]["groups"])

    def test_detail_timings_are_canonical_across_raw_metric_sources(self) -> None:
        item = _call_log()
        item["detail"].update(
            perf={"handler_queue_ms": 100, "upload_ms": 50},
            metrics={"handler_queue_ms": 200, "resolve_ms": 30},
            monitor={
                "metrics": {"handler_queue_ms": 150, "poll_wait_ms": 400},
                "images": {
                    "1": {"metrics": {"poll_wait_ms": 500, "download_ms": 60}},
                },
            },
        )

        timings = build_call_detail(item)["timings_ms"]

        self.assertEqual(timings["handler_queue_ms"], 200)
        self.assertEqual(timings["poll_wait_ms"], 500)
        self.assertEqual(timings["upload_ms"], 50)
        self.assertEqual(timings["resolve_ms"], 30)
        self.assertEqual(timings["download_ms"], 60)

    def test_detail_preserves_preview_only_upstream_text(self) -> None:
        item = _call_log(status="failed")
        item["detail"].pop("upstream_text")
        item["detail"]["upstream_message_preview"] = "preview diagnostic"
        item["detail"]["image_attempts"][0]["upstream_message_preview"] = "attempt preview"

        detail = build_call_detail(item)

        self.assertEqual(detail["upstream_text"], "preview diagnostic")
        self.assertEqual(detail["attempts"][0]["upstream_text"], "attempt preview")

    def test_result_urls_fill_gaps_in_captured_success_attempts(self) -> None:
        item = _call_log()
        item["detail"]["urls"] = ["/images/one.png", "/images/two.png"]
        item["detail"]["image_attempts"] = [
            {"slot": 1, "attempt": 1, "status": "success"},
        ]

        summary = build_call_summary(item)

        self.assertEqual(summary["outcome"], "success")
        self.assertEqual(summary["image_requested_count"], 2)
        self.assertEqual(summary["image_succeeded_count"], 2)
        self.assertEqual(summary["image_failed_count"], 0)

    def test_stored_partial_success_status_survives_without_image_counts(self) -> None:
        item = _call_log(status="partial_success")
        item["detail"].pop("request_meta")
        item["detail"].pop("urls")
        item["detail"].pop("image_attempts")

        summary = build_call_summary(item)

        self.assertEqual(summary["outcome"], "partial_success")

    def test_explicit_image_request_marker_classifies_remapped_responses_model(self) -> None:
        item = _call_log()
        item["detail"].update(
            endpoint="/v1/responses",
            model="custom-image-alias",
            image_request=True,
        )

        summary = build_call_summary(item)

        self.assertEqual(summary["business"], "image_chat")

    def test_switch_count_keeps_explicit_total_when_attempt_capture_is_incomplete(self) -> None:
        item = _call_log()
        item["detail"]["switch_count"] = 3

        summary = build_call_summary(item)

        self.assertEqual(summary["switch_count"], 3)

    def test_presentation_is_derived_from_canonical_summary(self) -> None:
        item = _call_log()
        item["detail"]["image_attempts"][0]["duration_ms"] = 1200
        item["detail"]["image_attempts"][1]["duration_ms"] = 3400

        summary = build_call_summary(item)
        presentation = summary["presentation"]

        self.assertEqual(
            presentation["request"],
            {
                "kind": "文生图",
                "primary": "gpt-image-2",
                "secondary": "/v1/images/generations",
            },
        )
        self.assertEqual(
            presentation["execution"],
            {
                "primary": "2 个任务 · 2 次尝试",
                "secondary": "",
            },
        )
        self.assertEqual(presentation["status"], {"label": "部分成功", "tone": "warning"})
        self.assertEqual(presentation["result"]["text"], "生成 1/2 张图片")
        self.assertEqual(presentation["result"]["diagnostics"], "")
        self.assertEqual(
            presentation["duration"],
            {"text": "4.13s", "breakdown": "(1.2s + 3.4s)", "tone": "success"},
        )
        self.assertFalse(presentation["is_failure"])

    def test_public_error_wins_over_generic_failure_label(self) -> None:
        item = _call_log(status="failed")
        item["summary"] = ""
        item["detail"]["request_meta"] = {"n": 1}
        item["detail"]["urls"] = []
        item["detail"]["error_code"] = "image_tool_error"
        item["detail"]["image_attempts"] = [{
            "slot": 1,
            "attempt": 1,
            "status": "failed",
            "status_code": 502,
            "error_code": "image_tool_error",
        }]

        presentation = build_call_summary(item)["presentation"]

        self.assertEqual(presentation["result"]["text"], "Image generation failed.")
        self.assertEqual(
            presentation["result"]["diagnostics"],
            "HTTP 502 · image_tool_error",
        )
        self.assertEqual(presentation["status"], {"label": "失败", "tone": "danger"})
        self.assertEqual(presentation["duration"]["tone"], "danger")
        self.assertTrue(presentation["is_failure"])

    def test_failure_label_is_used_when_public_error_is_empty(self) -> None:
        item = _call_log(status="failed")
        item["summary"] = ""
        item["detail"].update(
            request_meta={"n": 1},
            urls=[],
            public_error="",
            error_code="image_poll_timeout",
            image_attempts=[],
        )

        presentation = build_call_summary(item)["presentation"]

        self.assertEqual(presentation["result"]["text"], "等待图片结果超时")

    def test_text_review_presentation_keeps_existing_wording(self) -> None:
        item = _call_log(status="failed")
        item["summary"] = "流式调用失败"
        item["detail"].update(
            status_code=400,
            request_meta={"n": 1},
            urls=[],
            image_attempts=[],
        )

        presentation = build_call_summary(item)["presentation"]

        self.assertEqual(presentation["status"], {"label": "文本", "tone": "warning"})
        self.assertEqual(presentation["result"]["text"], "上游返回文本")
        self.assertEqual(presentation["summary_text"], "文本")

    def test_success_at_one_minute_uses_warning_duration_tone(self) -> None:
        item = _call_log()
        item["detail"].update(
            endpoint="/v1/chat/completions",
            model="gpt-4.1",
            duration_ms=60000,
            request_meta={},
            urls=[],
            image_attempts=[],
        )

        presentation = build_call_summary(item)["presentation"]

        self.assertEqual(presentation["result"]["text"], "文本响应完成")
        self.assertEqual(presentation["duration"], {"text": "1m", "breakdown": "", "tone": "warning"})


class LogServiceCallContractTests(unittest.TestCase):
    def test_list_and_detail_use_the_same_summary_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = LogService(database_url=f"sqlite:///{(Path(temp_dir) / 'app.db').as_posix()}")
            service.append_item(_call_log())

            page = service.list_page(type="call", limit=20)
            detail = service.get_detail("call-1")

        self.assertIsNotNone(detail)
        CallSummaryPage.model_validate(page)
        CallDetail.model_validate(detail)
        row = page["items"][0]
        assert detail is not None
        self.assertEqual(
            {key: detail[key] for key in row},
            row,
        )
        self.assertNotIn("raw_detail", row)
        self.assertEqual(detail["request_text_full"], "complete prompt for detail only")

    def test_detail_keeps_truncated_public_error_identical_to_list_summary(self) -> None:
        item = _call_log(status="failed")
        item["detail"]["public_error"] = "x" * 1200

        summary = build_call_summary(item)
        detail = build_call_detail(item)

        self.assertEqual(len(summary["public_error"]), 1003)
        self.assertEqual(detail["public_error"], summary["public_error"])
        self.assertEqual(detail["raw_detail"]["public_error"], "x" * 1200)


class LogHttpContractTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _app() -> FastAPI:
        app = FastAPI()
        app.include_router(system.create_router("test"))
        return app

    async def test_list_response_does_not_expose_detail_fields(self) -> None:
        summary = build_call_summary(_call_log())
        page = {
            "items": [summary],
            "total": 1,
            "limit": 20,
            "offset": 0,
            "has_more": False,
            "facets_scope": "page",
            "stats_scope": "page",
            "total_scope": "type",
            "facets": {"statuses": {}, "endpoints": {}, "models": {}, "accounts": {}},
            "stats": {"total": 1, "success": 1, "text_review": 0, "failed": 0, "limited": 0, "image": 1},
        }
        transport = httpx.ASGITransport(app=self._app())
        with (
            patch("api.system.require_admin"),
            patch("api.system.log_service.list_page", return_value=page),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/logs?type=call&limit=20")

        self.assertEqual(response.status_code, 200, response.text)
        row = response.json()["items"][0]
        self.assertNotIn("request_text_full", row)
        self.assertNotIn("attempts", row)
        self.assertNotIn("monitor", row)
        self.assertNotIn("raw_detail", row)

    async def test_missing_detail_returns_404(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        with (
            patch("api.system.require_admin"),
            patch("api.system.log_service.get_detail", return_value=None),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/logs/missing")

        self.assertEqual(response.status_code, 404, response.text)

    async def test_delete_runs_in_threadpool(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        run_in_threadpool = AsyncMock(return_value={"removed": 1})
        with (
            patch("api.system.require_admin"),
            patch("api.system.run_in_threadpool", run_in_threadpool),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/logs/delete", json={"ids": ["call-1"]})

        self.assertEqual(response.status_code, 200, response.text)
        run_in_threadpool.assert_awaited_once_with(system.log_service.delete, ["call-1"])


if __name__ == "__main__":
    unittest.main()
