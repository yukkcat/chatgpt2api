from __future__ import annotations

import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from services.dashboard_metrics_service import DashboardMetricsService
from services.image_failure import ImageGenerationError, image_failure
from services.log_service import LogService, LoggedCall


class LogServiceTests(unittest.TestCase):
    def test_list_page_returns_requested_window_and_total(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = LogService(database_url=f"sqlite:///{(Path(tmp_dir) / 'app.db').as_posix()}")
            for index in range(5):
                service.add("call", f"item-{index}", {"index": index})

            result = service.list_page(type="call", limit=2, offset=2)

            self.assertEqual(result["total"], 5)
            self.assertEqual(result["limit"], 2)
            self.assertEqual(result["offset"], 2)
            self.assertEqual([item["summary"] for item in result["items"]], ["item-2", "item-1"])
            self.assertEqual(result["stats_scope"], "filtered")
            self.assertEqual(result["facets_scope"], "filtered")
            self.assertEqual(result["total_scope"], "type")
            self.assertEqual(result["stats"]["total"], 5)

    def test_query_filters_logs_on_server_side(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = LogService(database_url=f"sqlite:///{(Path(tmp_dir) / 'app.db').as_posix()}")
            service.add(
                "call",
                "text success",
                {
                    "status": "success",
                    "endpoint": "/v1/chat/completions",
                    "model": "gpt-4o",
                    "account_email": "chat@example.test",
                    "request_text": "hello",
                },
            )
            service.add(
                "call",
                "image failed",
                {
                    "status": "failed",
                    "endpoint": "/v1/images/edits",
                    "model": "gpt-image-2",
                    "account_email": "image@example.test",
                    "conversation_id": "conv-1",
                    "error_code": "image_tool_error",
                    "raw_upstream_message": "upstream returned text",
                },
            )

            result = service.list_page(
                type="call",
                status="failed",
                endpoint="/v1/images/edits",
                account="image@example.test",
                conversation_id="conv-1",
                search="image_tool_error",
                limit=10,
            )

            self.assertEqual(result["total"], 1)
            self.assertEqual(result["stats"]["failed"], 1)
            self.assertEqual(result["stats"]["image"], 1)
            self.assertEqual(result["items"][0]["summary"], "image failed")
            self.assertIn("/v1/images/edits", result["facets"]["endpoints"])
            self.assertIn("gpt-image-2", result["facets"]["models"])

    def test_limited_stats_use_only_structured_status_and_failure_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = LogService(database_url=f"sqlite:///{(Path(tmp_dir) / 'app.db').as_posix()}")
            service.add(
                "call",
                "structured quota",
                {"status": "failed", "error_code": "image_quota_exhausted", "error": "opaque"},
            )
            service.add(
                "call",
                "legacy structured code",
                {"status": "failed", "failure_code": "upstream_rate_limited", "error": "opaque"},
            )
            service.add(
                "call",
                "text must not classify",
                {
                    "status": "failed",
                    "error_code": "upstream_error",
                    "error": "quota exhausted and rate limited",
                },
            )

            result = service.list_page(type="call", limit=10)

            self.assertEqual(result["stats"]["failed"], 1)
            self.assertEqual(result["stats"]["limited"], 2)

    def test_failure_code_alone_is_failed_in_logs_and_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            logs = LogService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
            metrics = DashboardMetricsService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
            logs.add("call", "failed", {"failure_code": "image_tool_error"})

            page = logs.list_page(type="call", limit=10)
            metrics.sync_from_logs(logs.list(type="call", limit=10))
            summary = metrics.summary("24h")

        self.assertEqual(page["stats"]["failed"], 1)
        self.assertEqual(page["stats"]["success"], 0)
        self.assertEqual(summary["totals"]["failed"], 1)
        self.assertEqual(summary["totals"]["success"], 0)

    def test_rate_limit_status_is_separate_from_failed_in_logs_and_dashboard(self) -> None:
        for status in ("limited", "rate_limited", "限流"):
            with self.subTest(status=status):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    root = Path(tmp_dir)
                    logs = LogService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
                    metrics = DashboardMetricsService(database_url=f"sqlite:///{(root / 'app.db').as_posix()}")
                    logs.add("call", "limited", {"status": status})

                    page = logs.list_page(type="call", limit=10)
                    metrics.sync_from_logs(logs.list(type="call", limit=10))
                    summary = metrics.summary("24h")

                self.assertEqual(page["stats"]["failed"], 0)
                self.assertEqual(page["stats"]["limited"], 1)
                self.assertEqual(summary["totals"]["failed"], 0)
                self.assertEqual(summary["totals"]["success"], 0)
                self.assertEqual(summary["totals"]["rate_limited"], 1)
                self.assertEqual(sum(summary["trend"]["rate_limited_requests"]), 1)

    def test_delete_with_empty_ids_does_not_clear_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = LogService(database_url=f"sqlite:///{(Path(tmp_dir) / 'app.db').as_posix()}")
            service.add("call", "keep-1", {"status": "success"})
            service.add("call", "keep-2", {"status": "failed"})

            result = service.delete([])
            remaining = service.list_page(type="call", limit=10)

            self.assertEqual(result["removed"], 0)
            self.assertEqual(remaining["total"], 2)
            self.assertEqual(
                {item["summary"] for item in remaining["items"]},
                {"keep-1", "keep-2"},
            )

    def test_delete_removes_only_matching_log_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = LogService(database_url=f"sqlite:///{(Path(tmp_dir) / 'app.db').as_posix()}")
            service.add("call", "keep-old", {"status": "success"})
            service.add("call", "delete-me", {"status": "failed"})
            service.add("call", "keep-new", {"status": "success"})
            item_ids = {
                item["summary"]: item["id"]
                for item in service.list_page(type="call", limit=10)["items"]
            }

            result = service.delete([item_ids["delete-me"], item_ids["delete-me"], "", "missing-id"])
            remaining = service.list_page(type="call", limit=10)

            self.assertEqual(result["removed"], 1)
            self.assertEqual(remaining["total"], 2)
            self.assertEqual(
                [item["summary"] for item in remaining["items"]],
                ["keep-new", "keep-old"],
            )


class LoggedImageErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_projected_failure_controls_log_and_hides_internal_fields(self) -> None:
        call = LoggedCall(
            {"id": "admin", "name": "管理员", "role": "admin"},
            "/api/accounts/{account_id}/test",
            "gpt-image-2",
            "账号画图测试",
            image_request=True,
        )

        def handler(payload: dict[str, object]) -> dict[str, object]:
            self.assertTrue(payload.get("_call_id"))
            self.assertTrue(payload.get("_trace_image_perf"))
            return {
                "status": "failed",
                "error_code": "AccountTestError",
                "error_message": "测试失败",
                "_call_status": "failed",
                "_call_error": "测试失败",
                "_account_email": "test@example.test",
            }

        with (
            mock.patch("services.log_service.log_service.add") as add_log,
            mock.patch("services.log_service.realtime_monitor_service.start") as monitor_start,
            mock.patch("services.log_service.realtime_monitor_service.finish") as monitor_finish,
        ):
            result = await call.run(handler, {})

        self.assertEqual(
            result,
            {
                "status": "failed",
                "error_code": "AccountTestError",
                "error_message": "测试失败",
            },
        )
        detail = add_log.call_args.args[2]
        self.assertEqual(detail["status"], "failed")
        self.assertEqual(detail["error"], "测试失败")
        self.assertEqual(detail["error_code"], "AccountTestError")
        self.assertEqual(detail["account_email"], "test@example.test")
        monitor_start.assert_called_once()
        monitor_finish.assert_called_once()

    async def test_generic_image_exception_uses_same_failure_in_api_and_log(self) -> None:
        raw_error = "private synchronous image diagnostic"

        def direct_handler():
            raise RuntimeError(raw_error)

        def pre_first_item_handler():
            def items():
                raise RuntimeError(raw_error)
                yield {}

            return items()

        for name, handler in (
            ("direct", direct_handler),
            ("pre_first_item", pre_first_item_handler),
        ):
            with self.subTest(path=name):
                call = LoggedCall(
                    {"id": "key-1", "name": "Key", "role": "admin"},
                    "/v1/images/generations",
                    "gpt-image-2",
                    "文生图",
                )
                with mock.patch("services.log_service.log_service.add") as add_log:
                    response = await call.run(handler)

                add_log.assert_called_once()
                payload = json.loads(response.body)
                detail = add_log.call_args.args[2]
                self.assertEqual(response.status_code, 500)
                self.assertEqual(payload["error"]["code"], "internal_error")
                self.assertEqual(payload["error"]["type"], "server_error")
                self.assertEqual(detail["error_code"], payload["error"]["code"])
                self.assertEqual(detail["failure_code"], payload["error"]["code"])
                self.assertEqual(detail["status_code"], response.status_code)
                self.assertEqual(detail["error_type"], payload["error"]["type"])
                self.assertEqual(detail["public_error"], payload["error"]["message"])
                self.assertEqual(detail["error"], payload["error"]["message"])
                self.assertEqual(detail["raw_error"], raw_error)
                self.assertEqual(detail["failure_scope"], "internal")
                self.assertFalse(detail["failure_account_failure"])
                self.assertFalse(detail["failure_retryable"])
                self.assertNotIn(raw_error, response.body.decode("utf-8"))

    async def test_terminal_text_uses_same_failure_in_api_log_and_attempt(self) -> None:
        public_text = "opaque terminal assistant reply"
        failure = image_failure(
            "upstream_text_reply",
            raw_detail=public_text,
        ).with_public_detail(public_text)

        def handler():
            error = ImageGenerationError(
                public_text,
                failure=failure,
                raw_error=public_text,
                raw_upstream_message=public_text,
            )
            error.image_attempts = [{
                "slot": 1,
                "attempt": 1,
                "status": "failed",
                "failure_code": failure.code,
                "status_code": failure.status_code,
                "error_type": failure.error_type,
                "public_error": public_text,
                "raw_error": public_text,
                "account_failure": failure.account_failure,
                "switched_account": False,
            }]
            raise error

        call = LoggedCall(
            {"id": "key-1", "name": "Key", "role": "admin"},
            "/v1/images/generations",
            "gpt-image-2",
            "文生图",
        )
        with mock.patch("services.log_service.log_service.add") as add_log:
            response = await call.run(handler)

        payload = json.loads(response.body)
        detail = add_log.call_args.args[2]
        attempt = detail["image_attempts"][0]
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"]["code"], failure.code)
        self.assertEqual(payload["error"]["message"], public_text)
        self.assertEqual(detail["error_code"], payload["error"]["code"])
        self.assertEqual(detail["public_error"], payload["error"]["message"])
        self.assertEqual(detail["error"], payload["error"]["message"])
        self.assertEqual(attempt["failure_code"], payload["error"]["code"])
        self.assertEqual(attempt["status_code"], response.status_code)
        self.assertEqual(attempt["public_error"], payload["error"]["message"])
        self.assertFalse(attempt["account_failure"])
        self.assertFalse(attempt["switched_account"])

    async def test_structured_rate_limit_returns_429_not_500(self) -> None:
        def handler():
            raise ImageGenerationError(
                "opaque upstream diagnostic",
                failure=image_failure("upstream_rate_limited"),
            )

        call = LoggedCall({"id": "key-1", "name": "Key", "role": "admin"}, "/v1/images/generations", "gpt-image-2", "文生图")
        with mock.patch("services.log_service.log_service.add") as add_log:
            response = await call.run(handler)

        self.assertEqual(response.status_code, 429)
        self.assertIn("upstream_rate_limited", response.body.decode("utf-8"))
        detail = add_log.call_args.args[2]
        self.assertEqual(detail["error_code"], "upstream_rate_limited")
        self.assertEqual(detail["failure_capability"], "image_generation")

    async def test_poll_timeout_returns_canonical_502(self) -> None:
        def handler():
            error = ImageGenerationError(
                "",
                failure=image_failure("image_poll_timeout"),
                raw_error="",
                upstream_error='{"error":{"code":"generation_pending"}}',
                raw_upstream_message='{"size":"auto","n":1}',
            )
            error.poll_timeout_secs = 120
            raise error

        call = LoggedCall({"id": "key-1", "name": "Key", "role": "admin"}, "/v1/images/generations", "gpt-image-2", "文生图")
        with mock.patch("services.log_service.log_service.add") as add_log:
            response = await call.run(handler)

        self.assertEqual(response.status_code, 502)
        self.assertIn("image_poll_timeout", response.body.decode("utf-8"))
        detail = add_log.call_args.args[2]
        self.assertEqual(detail["error_code"], "image_poll_timeout")
        self.assertEqual(detail["poll_timeout_secs"], 120)
        self.assertNotIn("raw_error", detail)
        self.assertEqual(detail["upstream_error"], '{"error":{"code":"generation_pending"}}')
        self.assertEqual(detail["raw_upstream_message"], '{"size":"auto","n":1}')

    async def test_stream_structured_rate_limit_returns_429_before_stream_starts(self) -> None:
        def handler():
            def items():
                raise ImageGenerationError(
                    "opaque upstream diagnostic",
                    failure=image_failure("upstream_rate_limited"),
                )
                yield {}

            return items()

        call = LoggedCall({"id": "key-1", "name": "Key", "role": "admin"}, "/v1/images/generations", "gpt-image-2", "文生图")
        with mock.patch("services.log_service.log_service.add") as add_log:
            response = await call.run(handler)

        self.assertEqual(response.status_code, 429)
        self.assertIn("upstream_rate_limited", response.body.decode("utf-8"))
        detail = add_log.call_args.args[2]
        self.assertEqual(detail["error_code"], "upstream_rate_limited")
        self.assertEqual(detail["failure_capability"], "image_generation")


if __name__ == "__main__":
    unittest.main()
