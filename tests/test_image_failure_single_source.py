from __future__ import annotations

import unittest
from unittest import mock

from services.config import config
from services.image_failure import (
    IMAGE_TIMEOUT_PUBLIC_MESSAGE,
    ImageGenerationError,
    terminal_assistant_text,
)
from services.log_service import _exception_log_fields
from services.openai_backend_api import OpenAIBackendAPI, requests
from services.protocol.conversation import (
    ConversationRequest,
    _recover_after_image_stream_timeout,
    stream_codex_image_outputs,
)
from services.realtime_monitor_service import RealtimeMonitorService
from utils.helper import UpstreamHTTPError


class PollFailureSelectionTests(unittest.TestCase):
    class FakeBackend(OpenAIBackendAPI):
        def __init__(self) -> None:
            self.clock = 0.0
            self.task_result: object = []
            self.conversation_result: object = {}
            self.assistant_text = ""

        def _reset_image_result_timing(self) -> None:
            return None

        def _add_image_result_timing(self, _key: str, _milliseconds: float) -> None:
            return None

        def _sleep_for_image_poll(self, seconds: float) -> None:
            self.clock += seconds

        def _query_backend_tasks(self, **_kwargs: object):
            if isinstance(self.task_result, BaseException):
                raise self.task_result
            return self.task_result

        def _get_conversation(self, _conversation_id: str, **_kwargs: object):
            if isinstance(self.conversation_result, BaseException):
                raise self.conversation_result
            return self.conversation_result

        def _conversation_poll_snapshot(self, _conversation: object):
            return {}, self.assistant_text

        def _extract_image_tool_records(self, _conversation: object):
            return []

    def _poll(self, backend: FakeBackend) -> None:
        with (
            mock.patch.dict(
                config.data,
                {
                    "image_poll_initial_wait_secs": 0,
                    "image_poll_interval_secs": 1,
                    "image_settle_enabled": False,
                    "image_check_before_hit_enabled": False,
                },
            ),
            mock.patch(
                "services.openai_backend_api.time.monotonic",
                side_effect=lambda: backend.clock,
            ),
        ):
            backend._poll_image_results("conversation-1", timeout_secs=1)

    def test_task_probe_http_failure_is_not_rewritten_as_poll_timeout(self) -> None:
        backend = self.FakeBackend()
        backend.task_result = UpstreamHTTPError(
            "/backend-api/tasks",
            429,
            {"error": {"type": "rate_limit_error"}},
        )

        with self.assertRaises(Exception) as raised:
            self._poll(backend)

        self.assertEqual(raised.exception.failure.code, "upstream_rate_limited")
        self.assertEqual(raised.exception.failure.status_code, 429)

    def test_later_transport_failure_beats_earlier_generic_task_failure(self) -> None:
        backend = self.FakeBackend()
        backend.task_result = [{
            "image_gen_message": {
                "status": "failed",
                "metadata": {"is_error": True},
                "content": {"content_type": "text", "parts": []},
            },
        }]
        backend.conversation_result = requests.exceptions.ConnectionError(
            "connection dropped"
        )

        with self.assertRaises(Exception) as raised:
            self._poll(backend)

        self.assertEqual(raised.exception.failure.code, "upstream_connection_failed")

    def test_poll_timeout_keeps_upstream_text_separate_from_diagnostic(self) -> None:
        backend = self.FakeBackend()
        backend.assistant_text = '{"size":"auto","n":1}'

        with self.assertRaises(Exception) as raised:
            self._poll(backend)

        fields = _exception_log_fields(raised.exception, image=True)
        self.assertEqual(fields["error_code"], "image_poll_timeout")
        self.assertEqual(fields["public_error"], IMAGE_TIMEOUT_PUBLIC_MESSAGE)
        self.assertEqual(fields["raw_upstream_message"], '{"size":"auto","n":1}')
        self.assertNotIn("raw_error", fields)
        self.assertNotIn("upstream_error", fields)

    def test_poll_timeout_without_upstream_text_omits_message_field(self) -> None:
        backend = self.FakeBackend()

        with self.assertRaises(Exception) as raised:
            self._poll(backend)

        fields = _exception_log_fields(raised.exception, image=True)
        self.assertEqual(fields["public_error"], IMAGE_TIMEOUT_PUBLIC_MESSAGE)
        self.assertNotIn("raw_error", fields)
        self.assertNotIn("upstream_error", fields)
        self.assertNotIn("raw_upstream_message", fields)

    def test_current_turn_image_arguments_are_kept_as_upstream_text(self) -> None:
        data = {
            "current_node": "current-code",
            "mapping": {
                "old-user": {
                    "parent": None,
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["old"]},
                    },
                },
                "old-code": {
                    "parent": "old-user",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"content_type": "code", "text": '{"prompt":"old"}'},
                        "status": "finished_successfully",
                    },
                },
                "current-user": {
                    "parent": "old-code",
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["cat"]},
                    },
                },
                "current-code": {
                    "parent": "current-user",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {
                            "content_type": "code",
                            "text": '{"size":"1024x1024","n":1,"prompt":"cat"}',
                        },
                        "status": "finished_successfully",
                    },
                },
            },
        }

        self.assertEqual(
            terminal_assistant_text(data),
            '{"size":"1024x1024","n":1,"prompt":"cat"}',
        )


class CodexFailureTests(unittest.TestCase):
    class FakeBackend:
        def iter_codex_image_response_events(self, **_kwargs: object):
            yield {
                "type": "response.failed",
                "response": {
                    "status": "failed",
                    "error": {
                        "type": "insufficient_quota",
                        "code": "insufficient_quota",
                        "message": "opaque quota detail",
                    },
                },
            }

    def test_codex_json_error_uses_structured_failure(self) -> None:
        request = ConversationRequest(
            model="gpt-image-2-codex",
            prompt="draw a lighthouse",
            message_as_error=True,
        )

        with self.assertRaises(ImageGenerationError) as raised:
            list(stream_codex_image_outputs(self.FakeBackend(), request))

        self.assertEqual(raised.exception.failure.code, "image_quota_exhausted")
        self.assertEqual(raised.exception.failure.status_code, 429)


class StreamTimeoutFallbackTests(unittest.TestCase):
    class FakeBackend:
        def _query_backend_tasks(self, **_kwargs: object):
            return []

        def _get_conversation(self, *_args: object, **_kwargs: object):
            raise RuntimeError("conversation probe failed")

    def test_code_arguments_survive_failed_conversation_probe(self) -> None:
        upstream_text = '{"size":"1024x1024","n":1,"prompt":"cat"}'
        last = {
            "conversation_id": "conversation-1",
            "text": upstream_text,
            "message_role": "assistant",
            "content_type": "code",
        }

        with self.assertRaises(ImageGenerationError) as raised:
            _recover_after_image_stream_timeout(
                self.FakeBackend(),
                ConversationRequest(model="gpt-image-2", prompt="cat"),
                last,
                TimeoutError("SSE stream exceeded 180s"),
                1,
                1,
                0.0,
            )

        self.assertEqual(raised.exception.failure.code, "image_stream_timeout")
        self.assertEqual(raised.exception.raw_upstream_message, upstream_text)
        self.assertEqual(raised.exception.upstream_error, "")


class RealtimeFailureFieldTests(unittest.TestCase):
    def test_attempt_event_keeps_canonical_failure_fields(self) -> None:
        monitor = RealtimeMonitorService()
        call_id = "canonical-failure-fields"
        failure_fields = {
            "failure_code": "image_quota_exhausted",
            "status_code": 429,
            "error_type": "insufficient_quota",
            "public_error": "No image generation quota is currently available.",
            "account_failure": True,
            "switched_account": True,
        }
        monitor.start(call_id, endpoint="/v1/images/generations", model="gpt-image-2")
        monitor.stage(
            call_id,
            "image_attempt_failed",
            index=1,
            attempt=1,
            status="failed",
            **failure_fields,
        )
        detail = {
            "call_id": call_id,
            "status": "failed",
            "duration_ms": 1000,
            "image_attempts": [{"slot": 1, "attempt": 1, "status": "failed", **failure_fields}],
            **failure_fields,
        }

        monitor.finish(detail)

        snapshot = monitor.snapshot()
        record = next(
            item
            for item in snapshot["recent"]
            if item["call_id"] == call_id
        )
        event = next(
            item
            for item in snapshot["events"]
            if item["call_id"] == call_id
            and item["event"] == "image_attempt_failed"
        )
        attempt_event = detail["image_attempts"][0]["monitor"]["events"][-1]
        for key, value in failure_fields.items():
            self.assertEqual(record[key], value)
            self.assertEqual(event[key], value)
            self.assertEqual(attempt_event[key], value)


if __name__ == "__main__":
    unittest.main()
