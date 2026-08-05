from __future__ import annotations

import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from services.account_service import ImageAccountSelectionError
from services.image_failure import (
    ImageDownloadError,
    ImageGenerationError,
    classify_conversation_failure,
    image_failure,
)
from services.log_service import (
    LoggedCall,
    _exception_log_fields,
    _strip_internal_response_fields,
    collect_image_attempts,
)
from services.protocol import conversation
from services.realtime_monitor_service import RealtimeMonitorService
from utils.helper import UpstreamHTTPError


def _message_node(
    node_id: str,
    parent: str | None,
    *,
    role: str,
    content_type: str,
    parts: list[object],
    create_time: float = 1.0,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": node_id,
        "parent": parent,
        "children": [],
        "message": {
            "id": node_id,
            "author": {"role": role},
            "content": {"content_type": content_type, "parts": parts},
            "metadata": metadata or {},
            "create_time": create_time,
            "status": "finished_successfully",
            "end_turn": True,
        },
    }


class ConversationBoundaryTests(unittest.TestCase):
    def test_partial_image_argument_json_still_triggers_result_polling(self) -> None:
        self.assertTrue(conversation.is_image_generation_arguments(
            '{"size":"auto","n":1}',
            role="assistant",
            content_type="code",
        ))
        self.assertTrue(conversation.is_image_generation_arguments(
            '{"size":null,"n":1,"prompt":null,"instructions":"draw a lighthouse"}',
            role="assistant",
            content_type="code",
        ))
        self.assertFalse(conversation.is_image_generation_arguments(
            '{"size":"auto","n":1}',
            role="assistant",
            content_type="text",
        ))
        self.assertFalse(conversation.is_image_generation_arguments(
            '{"size":"auto","n":1}',
            role="user",
            content_type="code",
        ))
        for text in (
            '{"n":1}',
            '{"size":"auto"}',
            '{"status":"failed","n":1}',
            '{"message":"ordinary json","size":"auto"}',
        ):
            with self.subTest(text=text):
                self.assertFalse(conversation.is_image_generation_arguments(
                    text,
                    role="assistant",
                    content_type="code",
                ))

    def test_historical_image_does_not_hide_current_turn_failure(self) -> None:
        data = {
            "current_node": "current-tool",
            "mapping": {
                "old-user": _message_node(
                    "old-user", None, role="user", content_type="text", parts=["old"]
                ),
                "old-tool": _message_node(
                    "old-tool",
                    "old-user",
                    role="tool",
                    content_type="multimodal_text",
                    parts=[{"asset_pointer": "file-service://file_old"}],
                    metadata={"async_task_type": "image_gen"},
                ),
                "current-user": _message_node(
                    "current-user", "old-tool", role="user", content_type="text", parts=["new"]
                ),
                "current-tool": _message_node(
                    "current-tool",
                    "current-user",
                    role="tool",
                    content_type="system_error",
                    parts=[],
                    metadata={"is_error": True, "error_code": "image_generation_user_error"},
                ),
            },
        }

        failure = classify_conversation_failure(data)

        self.assertIsNotNone(failure)
        self.assertEqual(failure.code, "image_tool_error")

    def test_current_node_lineage_wins_when_timestamps_are_equal(self) -> None:
        data = {
            "current_node": "assistant",
            "mapping": {
                "assistant": _message_node(
                    "assistant", "user", role="assistant", content_type="text", parts=["opaque"]
                ),
                "user": _message_node(
                    "user", None, role="user", content_type="text", parts=["prompt"]
                ),
            },
        }

        failure = classify_conversation_failure(data)

        self.assertIsNotNone(failure)
        self.assertEqual(failure.code, "upstream_text_reply")

    def test_assistant_reference_is_not_an_image_result_after_tool_metadata(self) -> None:
        state = conversation.ConversationState(tool_invoked=True)
        event = {
            "message": {
                "author": {"role": "assistant"},
                "content": {"content_type": "text", "parts": ["done"]},
                "metadata": {"referenced_image_ids": ["file_00000000aaaaaaaaaaaaaaaaaaaaaaaa"]},
                "status": "finished_successfully",
                "end_turn": True,
            }
        }

        conversation.update_conversation_state(state, json.dumps(event), event)

        self.assertEqual(state.file_ids, [])

    def test_explicit_image_tool_output_is_still_accepted(self) -> None:
        state = conversation.ConversationState()
        event = {
            "message": {
                "author": {"role": "tool"},
                "content": {
                    "content_type": "multimodal_text",
                    "parts": [{"asset_pointer": "file-service://file_result"}],
                },
                "metadata": {"async_task_type": "image_gen"},
            }
        }

        conversation.update_conversation_state(state, json.dumps(event), event)

        self.assertEqual(state.file_ids, ["file_result"])

    def test_generic_tool_error_does_not_override_terminal_assistant_text(self) -> None:
        assistant_text = "Upstream returned a request-specific explanation."
        tool_event = {
            "message": {
                "id": "tool",
                "author": {"role": "tool"},
                "content": {"content_type": "text", "parts": ["processing failed"]},
                "metadata": {"async_task_type": "image_gen", "is_error": True},
                "status": "finished_successfully",
            }
        }
        assistant_event = {
            "message": {
                "id": "assistant",
                "author": {"role": "assistant"},
                "content": {"content_type": "text", "parts": [assistant_text]},
                "status": "finished_successfully",
                "end_turn": True,
            }
        }
        data = {
            "current_node": "assistant",
            "mapping": {
                "user": _message_node(
                    "user", None, role="user", content_type="text", parts=["draw"]
                ),
                "tool": {
                    **_message_node(
                        "tool",
                        "user",
                        role="tool",
                        content_type="text",
                        parts=["processing failed"],
                        metadata={"async_task_type": "image_gen", "is_error": True},
                    ),
                },
                "assistant": _message_node(
                    "assistant",
                    "tool",
                    role="assistant",
                    content_type="text",
                    parts=[assistant_text],
                    create_time=2.0,
                ),
            },
        }

        conversation_failure = classify_conversation_failure(data)
        events = list(conversation.iter_conversation_payloads(iter([
            json.dumps(tool_event),
            json.dumps(assistant_event),
            "[DONE]",
        ])))
        stream_failure = events[-1]["_image_failure"]

        for failure in (conversation_failure, stream_failure):
            self.assertIsNotNone(failure)
            self.assertEqual(failure.code, "upstream_text_reply")
            self.assertEqual(failure.status_code, 400)
            self.assertFalse(failure.account_failure)
            self.assertEqual(failure.public_detail, assistant_text)


class RealtimeMonitorBoundaryTests(unittest.TestCase):
    def test_success_clears_call_failure_but_preserves_failed_attempt(self) -> None:
        monitor = RealtimeMonitorService()
        call_id = "failed-account-then-success"
        attempts = [
            {
                "slot": 1,
                "attempt": 1,
                "status": "failed",
                "failure_code": "image_poll_timeout",
                "status_code": 502,
                "public_error": "Image generation timed out. Please try again.",
                "account_failure": True,
                "raw_error": "opaque timeout diagnostic",
            },
            {"slot": 1, "attempt": 2, "status": "success"},
        ]
        monitor.start(call_id, endpoint="/v1/images/generations", model="gpt-image-2")
        monitor.stage(
            call_id,
            "image_attempt_failed",
            index=1,
            attempt=1,
            failure_code="image_poll_timeout",
            status_code=502,
            public_error="Image generation timed out. Please try again.",
            account_failure=True,
            raw_error="opaque timeout diagnostic",
        )
        detail = {
            "call_id": call_id,
            "status": "success",
            "duration_ms": 1000,
            "image_attempts": attempts,
        }

        monitor.finish(detail)

        record = next(
            item
            for item in monitor.snapshot()["recent"]
            if item["call_id"] == call_id
        )
        self.assertEqual(record["status"], "success")
        for key in (
            "failure_code",
            "status_code",
            "account_failure",
            "error",
            "raw_error",
            "upstream_error",
            "upstream_message",
        ):
            self.assertNotIn(key, record)
        self.assertEqual(record["public_error"], "")
        self.assertEqual(detail["image_attempts"][0]["failure_code"], "image_poll_timeout")
        self.assertEqual(detail["image_attempts"][0]["raw_error"], "opaque timeout diagnostic")


class AttemptTraceTests(unittest.TestCase):
    class FakeBackend:
        def __init__(self, access_token: str, **_kwargs: object) -> None:
            self.access_token = access_token
            self.proxy_profile = SimpleNamespace(image_concurrency_limit=0)
            self.cancel_checker = None
            self.progress_callback = None

        def close(self) -> None:
            return None

    def test_account_result_persistence_failure_does_not_replace_success(self) -> None:
        result = conversation.ImageOutput(
            kind="result",
            model="gpt-image-2",
            index=1,
            total=1,
            data=[{"b64_json": "aW1hZ2U="}],
        )
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
            message_as_error=True,
        )

        with (
            mock.patch.object(
                conversation.account_service,
                "get_available_access_token",
                return_value="token-a",
            ),
            mock.patch.object(
                conversation.account_service,
                "get_account",
                return_value={"email": "a@example.test", "refresh_token": "refresh-a"},
            ),
            mock.patch.object(
                conversation.account_service,
                "mark_image_result",
                side_effect=OSError("accounts persistence failed"),
            ),
            mock.patch.object(
                conversation.account_service,
                "release_image_slot",
            ) as release_slot,
            mock.patch.object(conversation, "OpenAIBackendAPI", self.FakeBackend),
            mock.patch.object(conversation, "is_codex_image_model", return_value=False),
            mock.patch.object(
                conversation,
                "stream_image_outputs",
                return_value=iter([result]),
            ),
            mock.patch.object(conversation, "_cleanup_image_conversations_after_success"),
            mock.patch.object(conversation.proxy_settings, "acquire_image_egress", return_value=0),
        ):
            outputs = conversation._generate_single_image(request, 1, 1)

        self.assertEqual(outputs, [result])
        self.assertEqual(outputs[0].image_attempts[0]["status"], "success")
        release_slot.assert_called_once_with("token-a")

    def test_account_result_persistence_failure_does_not_replace_image_failure(self) -> None:
        original = ImageGenerationError(
            "opaque timeout",
            failure=image_failure("image_poll_timeout"),
            raw_upstream_message='{"size":"auto","n":1}',
        )
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
            message_as_error=True,
        )

        with (
            mock.patch.dict(
                conversation.config.data,
                {"image_account_retry_enabled": False},
            ),
            mock.patch.object(
                conversation.account_service,
                "get_available_access_token",
                return_value="token-a",
            ),
            mock.patch.object(
                conversation.account_service,
                "get_account",
                return_value={"email": "a@example.test", "refresh_token": "refresh-a"},
            ),
            mock.patch.object(
                conversation.account_service,
                "mark_image_result",
                side_effect=OSError("accounts persistence failed"),
            ),
            mock.patch.object(conversation.account_service, "release_image_slot"),
            mock.patch.object(conversation, "OpenAIBackendAPI", self.FakeBackend),
            mock.patch.object(conversation, "is_codex_image_model", return_value=False),
            mock.patch.object(conversation, "stream_image_outputs", side_effect=original),
            mock.patch.object(conversation.proxy_settings, "acquire_image_egress", return_value=0),
        ):
            with self.assertRaises(ImageGenerationError) as raised:
                conversation._generate_single_image(request, 1, 1)

        self.assertIs(raised.exception, original)
        self.assertEqual(raised.exception.failure.code, "image_poll_timeout")
        self.assertEqual(
            raised.exception.image_attempts[0]["raw_upstream_message"],
            '{"size":"auto","n":1}',
        )

    def test_retry_pool_exhaustion_preserves_original_failure(self) -> None:
        selections = ["token-a", ImageAccountSelectionError("unavailable", "no fallback")]

        def stream(*_args: object, **_kwargs: object):
            raise ImageGenerationError(
                "opaque delivery failure",
                failure=image_failure("image_download_failed"),
                account_email="a@example.test",
                conversation_id="conv-a",
                raw_error="signed download failed",
                raw_upstream_message='{"size":"auto","n":1}',
            )
            yield

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
            message_as_error=True,
        )
        with (
            mock.patch.object(
                conversation.account_service,
                "get_available_access_token",
                side_effect=selections,
            ),
            mock.patch.object(
                conversation.account_service,
                "get_account",
                return_value={"email": "a@example.test"},
            ),
            mock.patch.object(
                conversation.account_service,
                "mark_image_result",
                return_value={
                    "capability_failure_counts": {"image_generation": 1},
                },
            ),
            mock.patch.object(conversation, "OpenAIBackendAPI", self.FakeBackend),
            mock.patch.object(conversation, "is_codex_image_model", return_value=False),
            mock.patch.object(conversation, "stream_image_outputs", side_effect=stream),
            mock.patch.object(conversation.proxy_settings, "acquire_image_egress", return_value=0),
        ):
            with self.assertRaises(ImageGenerationError) as raised:
                conversation._generate_single_image(request, 1, 1)

        self.assertEqual(raised.exception.failure.code, "image_download_failed")
        self.assertEqual(raised.exception.conversation_id, "conv-a")
        self.assertEqual(len(raised.exception.image_attempts), 1)
        self.assertEqual(raised.exception.image_attempts[0]["account_email"], "a@example.test")
        self.assertEqual(
            raised.exception.image_attempts[0]["raw_upstream_message"],
            '{"size":"auto","n":1}',
        )
        self.assertEqual(
            raised.exception.image_attempts[0]["raw_error"],
            "signed download failed",
        )

    def test_upstream_http_failure_is_stored_as_upstream_error(self) -> None:
        def stream(*_args: object, **_kwargs: object):
            raise UpstreamHTTPError(
                "/backend-api/f/conversation/prepare",
                520,
                "<html>upstream unavailable</html>",
            )
            yield

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="cat",
            message_as_error=True,
        )
        with (
            mock.patch.dict(
                conversation.config.data,
                {"image_account_retry_enabled": False},
            ),
            mock.patch.object(
                conversation.account_service,
                "get_available_access_token",
                return_value="token-a",
            ),
            mock.patch.object(
                conversation.account_service,
                "get_account",
                return_value={"email": "a@example.test"},
            ),
            mock.patch.object(conversation.account_service, "mark_image_result"),
            mock.patch.object(conversation, "OpenAIBackendAPI", self.FakeBackend),
            mock.patch.object(conversation, "is_codex_image_model", return_value=False),
            mock.patch.object(conversation, "stream_image_outputs", side_effect=stream),
            mock.patch.object(conversation.proxy_settings, "acquire_image_egress", return_value=0),
        ):
            with self.assertRaises(ImageGenerationError) as raised:
                conversation._generate_single_image(request, 1, 1)

        self.assertEqual(raised.exception.failure.code, "upstream_unavailable")
        self.assertEqual(raised.exception.raw_error, "")
        self.assertIn("status=520", raised.exception.upstream_error)
        attempt = raised.exception.image_attempts[0]
        self.assertNotIn("raw_error", attempt)
        self.assertIn("status=520", attempt["upstream_error"])

    def test_text_outcomes_do_not_switch_accounts(self) -> None:
        for failure_code in (
            "content_policy_violation",
            "invalid_image_input",
            "upstream_text_reply",
        ):
            with self.subTest(failure_code=failure_code):
                selected: list[set[str]] = []

                def select_account(**kwargs: object) -> str:
                    selected.append(set(kwargs.get("excluded_tokens") or set()))
                    return "token-a"

                def stream(*_args: object, **_kwargs: object):
                    raise ImageGenerationError(
                        "opaque request rejection",
                        failure=image_failure(failure_code),
                    )
                    yield

                request = conversation.ConversationRequest(
                    model="gpt-image-2",
                    prompt="draw a lighthouse",
                    message_as_error=True,
                )
                with (
                    mock.patch.object(
                        conversation.account_service,
                        "get_available_access_token",
                        side_effect=select_account,
                    ),
                    mock.patch.object(
                        conversation.account_service,
                        "get_account",
                        return_value={"email": "a@example.test"},
                    ),
                    mock.patch.object(
                        conversation.account_service,
                        "mark_image_result",
                        return_value={},
                    ) as mark_result,
                    mock.patch.object(conversation, "OpenAIBackendAPI", self.FakeBackend),
                    mock.patch.object(conversation, "is_codex_image_model", return_value=False),
                    mock.patch.object(conversation, "stream_image_outputs", side_effect=stream),
                    mock.patch.object(conversation.proxy_settings, "acquire_image_egress", return_value=0),
                ):
                    with self.assertRaises(ImageGenerationError) as raised:
                        conversation._generate_single_image(request, 1, 1)

                self.assertEqual(raised.exception.failure.code, failure_code)
                self.assertEqual(selected, [set()])
                self.assertEqual(mark_result.call_count, 1)
                self.assertIs(
                    mark_result.call_args.kwargs["failure"],
                    raised.exception.failure,
                )
                self.assertEqual(
                    raised.exception.image_attempts[0]["failure_code"],
                    failure_code,
                )
                self.assertEqual(
                    raised.exception.image_attempts[0]["status"],
                    "text_review",
                )
                self.assertFalse(
                    raised.exception.image_attempts[0]["switched_account"],
                )

    def test_retry_setting_can_disable_cross_account_switch(self) -> None:
        selected: list[set[str]] = []

        def select_account(**kwargs: object) -> str:
            selected.append(set(kwargs.get("excluded_tokens") or set()))
            return "token-a"

        def stream(*_args: object, **_kwargs: object):
            raise ImageGenerationError(
                "opaque delivery failure",
                failure=image_failure("image_download_failed"),
            )
            yield

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
            message_as_error=True,
        )
        with (
            mock.patch.dict(
                conversation.config.data,
                {"image_account_retry_enabled": False},
            ),
            mock.patch.object(
                conversation.account_service,
                "get_available_access_token",
                side_effect=select_account,
            ),
            mock.patch.object(
                conversation.account_service,
                "get_account",
                return_value={"email": "a@example.test"},
            ),
            mock.patch.object(conversation.account_service, "mark_image_result"),
            mock.patch.object(conversation, "OpenAIBackendAPI", self.FakeBackend),
            mock.patch.object(conversation, "is_codex_image_model", return_value=False),
            mock.patch.object(conversation, "stream_image_outputs", side_effect=stream),
            mock.patch.object(conversation.proxy_settings, "acquire_image_egress", return_value=0),
        ):
            with self.assertRaises(ImageGenerationError) as raised:
                conversation._generate_single_image(request, 1, 1)

        self.assertEqual(selected, [set()])
        self.assertEqual(len(raised.exception.image_attempts), 1)
        self.assertFalse(raised.exception.image_attempts[0]["switched_account"])

    def test_download_failure_switches_account_and_preserves_consumed_quota(self) -> None:
        selected: list[set[str]] = []

        def select_account(**kwargs: object) -> str:
            excluded = set(kwargs.get("excluded_tokens") or set())
            selected.append(excluded)
            return "token-b" if "token-a" in excluded else "token-a"

        def stream(backend: object, _request: object, index: int, total: int):
            if getattr(backend, "access_token", "") == "token-a":
                raise ImageDownloadError("opaque download failure")
            yield conversation.ImageOutput(
                kind="result",
                model="gpt-image-2",
                index=index,
                total=total,
                data=[{"b64_json": "aW1hZ2U="}],
            )

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
            message_as_error=True,
        )
        with (
            mock.patch.object(
                conversation.account_service,
                "get_available_access_token",
                side_effect=select_account,
            ),
            mock.patch.object(
                conversation.account_service,
                "get_account",
                return_value={"email": "a@example.test"},
            ),
            mock.patch.object(
                conversation.account_service,
                "mark_image_result",
            ) as mark_result,
            mock.patch.object(conversation, "OpenAIBackendAPI", self.FakeBackend),
            mock.patch.object(conversation, "is_codex_image_model", return_value=False),
            mock.patch.object(conversation, "stream_image_outputs", side_effect=stream),
            mock.patch.object(conversation.proxy_settings, "acquire_image_egress", return_value=0),
            mock.patch.object(conversation, "_cleanup_image_conversations_after_success"),
        ):
            outputs = conversation._generate_single_image(request, 1, 1)

        self.assertEqual(selected, [set(), {"token-a"}])
        self.assertEqual(mark_result.call_count, 2)
        self.assertFalse(mark_result.call_args_list[0].args[1])
        self.assertTrue(mark_result.call_args_list[0].kwargs["quota_consumed"])
        self.assertTrue(mark_result.call_args_list[1].args[1])
        attempt = outputs[0].image_attempts[0]
        self.assertEqual(attempt["status"], "failed")
        self.assertEqual(attempt["failure_code"], "image_download_failed")
        self.assertFalse(attempt["account_failure"])
        self.assertTrue(attempt["switched_account"])

    def test_retry_attempts_keep_separate_monitor_metrics(self) -> None:
        call_id = "attempt-monitor-regression"

        def select_account(**kwargs: object) -> str:
            excluded = set(kwargs.get("excluded_tokens") or set())
            return "token-b" if "token-a" in excluded else "token-a"

        def stream(backend: AttemptTraceTests.FakeBackend, request: object, index: int, total: int):
            metric = 222 if backend.access_token == "token-b" else 111
            conversation._monitor_image_stage(
                request,
                "image_preparing_conversation",
                prepare_conversation_ms=metric,
                index=index,
                total=total,
            )
            if backend.access_token == "token-a":
                error = conversation.ImagePollTimeoutError("opaque timeout")
                error.last_assistant_text = '{"size":"auto","n":1}'
                raise error
            yield conversation.ImageOutput(
                kind="result",
                model="gpt-image-2",
                index=index,
                total=total,
                data=[{"b64_json": "aW1hZ2U="}],
            )

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
            message_as_error=True,
            call_id=call_id,
            trace_image_perf=True,
        )
        conversation.realtime_monitor_service.start(
            call_id,
            endpoint="/v1/images/generations",
            model=request.model,
        )
        with (
            mock.patch.object(
                conversation.account_service,
                "get_available_access_token",
                side_effect=select_account,
            ),
            mock.patch.object(
                conversation.account_service,
                "get_account",
                side_effect=lambda token: {"email": f"{token}@example.test"},
            ),
            mock.patch.object(
                conversation.account_service,
                "mark_image_result",
                return_value={"capability_failure_counts": {"image_generation": 1}},
            ),
            mock.patch.object(conversation, "OpenAIBackendAPI", self.FakeBackend),
            mock.patch.object(conversation, "is_codex_image_model", return_value=False),
            mock.patch.object(conversation, "stream_image_outputs", side_effect=stream),
            mock.patch.object(conversation.proxy_settings, "acquire_image_egress", return_value=0),
            mock.patch.object(conversation, "_cleanup_image_conversations_after_success"),
        ):
            outputs = conversation._generate_single_image(request, 1, 1)

        detail = {
            "call_id": call_id,
            "status": "success",
            "duration_ms": 333,
            "image_attempts": outputs[0].image_attempts,
        }
        conversation.realtime_monitor_service.finish(detail)

        attempts = detail["image_attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["failure_code"], "image_poll_timeout")
        self.assertEqual(attempts[0]["raw_upstream_message"], '{"size":"auto","n":1}')
        self.assertEqual(attempts[1]["status"], "success")
        self.assertEqual(attempts[0]["monitor"]["metrics"]["prepare_conversation_ms"], 111)
        self.assertEqual(attempts[1]["monitor"]["metrics"]["prepare_conversation_ms"], 222)
        self.assertTrue(attempts[0]["monitor"]["events"])
        self.assertTrue(attempts[1]["monitor"]["events"])

    def test_collector_keeps_conversation_and_attempt_metadata(self) -> None:
        output = conversation.ImageOutput(
            kind="result",
            model="gpt-image-2",
            index=1,
            total=1,
            data=[{"b64_json": "aW1hZ2U="}],
            account_email="b@example.test",
            conversation_id="conv-b",
            image_attempts=[{
                "slot": 1,
                "attempt": 1,
                "account_email": "b@example.test",
                "status": "success",
                "duration_ms": 1000,
            }],
        )

        result = conversation.collect_image_outputs([output])

        self.assertEqual(result["_conversation_id"], "conv-b")
        self.assertEqual(result["_image_attempts"], output.image_attempts)

    def test_multi_image_request_returns_successful_slots_when_others_fail(self) -> None:
        def generate(
            request: conversation.ConversationRequest,
            index: int,
            total: int,
        ) -> list[conversation.ImageOutput]:
            attempt = {
                "slot": index,
                "attempt": 1,
                "account_email": f"slot-{index}@example.test",
                "status": "success" if index == 1 else "failed",
                "duration_ms": 1000,
            }
            if index == 1:
                return [conversation.ImageOutput(
                    kind="result",
                    model=request.model,
                    index=index,
                    total=total,
                    data=[{"b64_json": "aW1hZ2U="}],
                    image_attempts=[attempt],
                )]
            attempt["failure_code"] = "image_poll_timeout"
            raise ImageGenerationError(
                "opaque timeout",
                failure=image_failure("image_poll_timeout"),
                image_attempts=[attempt],
            )

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw four lighthouses",
            n=4,
            message_as_error=True,
        )
        for parallel in (False, True):
            with self.subTest(parallel=parallel):
                with (
                    mock.patch.object(
                        type(conversation.config),
                        "image_parallel_generation",
                        new_callable=mock.PropertyMock,
                        return_value=parallel,
                    ),
                    mock.patch.object(
                        conversation,
                        "_generate_single_image",
                        side_effect=generate,
                    ) as generate_mock,
                ):
                    result = conversation.collect_image_outputs(
                        conversation.stream_image_outputs_with_pool(request)
                    )
                self.assertEqual(result["data"], [{"b64_json": "aW1hZ2U="}])
                self.assertEqual(generate_mock.call_count, 4)

    def test_multi_image_request_still_fails_when_every_slot_fails(self) -> None:
        def generate(
            request: conversation.ConversationRequest,
            index: int,
            total: int,
        ) -> list[conversation.ImageOutput]:
            raise ImageGenerationError(
                f"slot {index} timed out",
                failure=image_failure("image_poll_timeout"),
            )

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw four lighthouses",
            n=4,
            message_as_error=True,
        )
        for parallel in (False, True):
            with self.subTest(parallel=parallel):
                with (
                    mock.patch.object(
                        type(conversation.config),
                        "image_parallel_generation",
                        new_callable=mock.PropertyMock,
                        return_value=parallel,
                    ),
                    mock.patch.object(
                        conversation,
                        "_generate_single_image",
                        side_effect=generate,
                    ) as generate_mock,
                ):
                    with self.assertRaises(ImageGenerationError) as raised:
                        conversation.collect_image_outputs(
                            conversation.stream_image_outputs_with_pool(request)
                        )
                self.assertEqual(raised.exception.failure.code, "image_poll_timeout")
                self.assertEqual(generate_mock.call_count, 4)

    def test_multi_image_failure_selection_is_deterministic(self) -> None:
        def error(code: str, slot: int) -> ImageGenerationError:
            return ImageGenerationError(
                f"{code} from slot {slot}",
                failure=image_failure(code),
                raw_error=f"raw {slot}",
                image_attempts=[{
                    "slot": slot,
                    "attempt": 1,
                    "status": "failed",
                    "failure_code": code,
                }],
            )

        cases = (
            ("task_interrupted", "image_poll_timeout", "task_interrupted"),
            ("image_poll_timeout", "image_quota_exhausted", "image_quota_exhausted"),
            ("auth_invalid", "image_quota_exhausted", "auth_invalid"),
            ("image_quota_exhausted", "invalid_image_input", "image_quota_exhausted"),
        )
        for first_code, second_code, expected in cases:
            with self.subTest(first=first_code, second=second_code):
                first = error(first_code, 1)
                second = error(second_code, 2)
                for errors in ({1: first, 2: second}, {2: second, 1: first}):
                    selected = conversation._select_image_pool_error(errors)
                    self.assertIsNotNone(selected)
                    self.assertEqual(selected.failure.code, expected)
                    self.assertEqual(
                        [(item["slot"], item["attempt"]) for item in selected.image_attempts],
                        [(1, 1), (2, 1)],
                    )

    def test_multi_image_failure_tie_uses_lowest_slot(self) -> None:
        first = ImageGenerationError(
            "first timeout",
            failure=image_failure("image_poll_timeout"),
            raw_error="slot one",
        )
        second = ImageGenerationError(
            "second timeout",
            failure=image_failure("image_poll_timeout"),
            raw_error="slot two",
        )

        selected = conversation._select_image_pool_error({2: second, 1: first})

        self.assertIs(selected, first)
        self.assertEqual(selected.raw_error, "slot one")

    def test_parallel_pool_does_not_swallow_consumer_exception(self) -> None:
        def generate(
            request: conversation.ConversationRequest,
            index: int,
            total: int,
        ) -> list[conversation.ImageOutput]:
            return [conversation.ImageOutput(
                kind="result",
                model=request.model,
                index=index,
                total=total,
                data=[{"b64_json": "aW1hZ2U="}],
            )]

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw two lighthouses",
            n=2,
            message_as_error=True,
        )
        with (
            mock.patch.object(
                type(conversation.config),
                "image_parallel_generation",
                new_callable=mock.PropertyMock,
                return_value=True,
            ),
            mock.patch.object(conversation, "_generate_single_image", side_effect=generate),
        ):
            outputs = conversation.stream_image_outputs_with_pool(request)
            next(outputs)
            with self.assertRaisesRegex(RuntimeError, "consumer stopped"):
                outputs.throw(RuntimeError("consumer stopped"))

    def test_parallel_pool_deadline_returns_completed_slots_without_waiting(self) -> None:
        def generate(
            request: conversation.ConversationRequest,
            index: int,
            total: int,
        ) -> list[conversation.ImageOutput]:
            if index == 1:
                return [conversation.ImageOutput(
                    kind="result",
                    model=request.model,
                    index=index,
                    total=total,
                    data=[{"b64_json": "aW1hZ2U="}],
                )]
            while time.monotonic() < request.deadline_monotonic:
                time.sleep(0.002)
            raise ImageGenerationError(
                f"slot {index} interrupted",
                failure=image_failure("task_interrupted"),
            )

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw four lighthouses",
            n=4,
            message_as_error=True,
        )
        started = time.monotonic()
        with (
            mock.patch.object(
                type(conversation.config),
                "image_parallel_generation",
                new_callable=mock.PropertyMock,
                return_value=True,
            ),
            mock.patch.object(
                type(conversation.config),
                "image_request_timeout_secs",
                new_callable=mock.PropertyMock,
                create=True,
                return_value=0.05,
            ),
            mock.patch.object(conversation, "_generate_single_image", side_effect=generate),
        ):
            result = conversation.collect_image_outputs(
                conversation.stream_image_outputs_with_pool(request)
            )

        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(result["data"], [{"b64_json": "aW1hZ2U="}])

    def test_single_image_deadline_does_not_wait_for_stuck_worker(self) -> None:
        def generate(
            request: conversation.ConversationRequest,
            _index: int,
            _total: int,
        ) -> list[conversation.ImageOutput]:
            while time.monotonic() < request.deadline_monotonic:
                time.sleep(0.002)
            raise ImageGenerationError(
                "slot interrupted at request deadline",
                failure=image_failure("task_interrupted"),
            )

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw one lighthouse",
            n=1,
            message_as_error=True,
        )
        started = time.monotonic()
        with (
            mock.patch.object(
                type(conversation.config),
                "image_request_timeout_secs",
                new_callable=mock.PropertyMock,
                create=True,
                return_value=0.05,
            ),
            mock.patch.object(conversation, "_generate_single_image", side_effect=generate),
        ):
            with self.assertRaises(ImageGenerationError) as raised:
                conversation.collect_image_outputs(
                    conversation.stream_image_outputs_with_pool(request)
                )

        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(raised.exception.failure.code, "task_interrupted")

    def test_serial_pool_deadline_does_not_wait_for_stuck_slot(self) -> None:
        def generate(
            request: conversation.ConversationRequest,
            _index: int,
            _total: int,
        ) -> list[conversation.ImageOutput]:
            while time.monotonic() < request.deadline_monotonic:
                time.sleep(0.002)
            raise ImageGenerationError(
                "slot interrupted at request deadline",
                failure=image_failure("task_interrupted"),
            )

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw two lighthouses",
            n=2,
            message_as_error=True,
        )
        started = time.monotonic()
        with (
            mock.patch.object(
                type(conversation.config),
                "image_parallel_generation",
                new_callable=mock.PropertyMock,
                return_value=False,
            ),
            mock.patch.object(
                type(conversation.config),
                "image_request_timeout_secs",
                new_callable=mock.PropertyMock,
                create=True,
                return_value=0.05,
            ),
            mock.patch.object(conversation, "_generate_single_image", side_effect=generate),
        ):
            with self.assertRaises(ImageGenerationError) as raised:
                conversation.collect_image_outputs(
                    conversation.stream_image_outputs_with_pool(request)
                )

        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(raised.exception.failure.code, "task_interrupted")

    def test_parallel_pool_deadline_preserves_completed_timeout_failure(self) -> None:
        def generate(
            request: conversation.ConversationRequest,
            index: int,
            _total: int,
        ) -> list[conversation.ImageOutput]:
            while time.monotonic() < request.deadline_monotonic:
                time.sleep(0.002)
            raise ImageGenerationError(
                f"slot {index} interrupted",
                failure=image_failure("image_poll_timeout"),
            )

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw four lighthouses",
            n=4,
            message_as_error=True,
        )
        started = time.monotonic()
        with (
            mock.patch.object(
                type(conversation.config),
                "image_parallel_generation",
                new_callable=mock.PropertyMock,
                return_value=True,
            ),
            mock.patch.object(
                type(conversation.config),
                "image_request_timeout_secs",
                new_callable=mock.PropertyMock,
                create=True,
                return_value=0.05,
            ),
            mock.patch.object(conversation, "_generate_single_image", side_effect=generate),
        ):
            with self.assertRaises(ImageGenerationError) as raised:
                conversation.collect_image_outputs(
                    conversation.stream_image_outputs_with_pool(request)
                )

        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(raised.exception.failure.code, "image_poll_timeout")

    def test_monitor_merges_failed_slots_into_partial_success_log(self) -> None:
        monitor = RealtimeMonitorService()
        call_id = "partial-success-attempts"
        monitor.start(call_id, endpoint="/v1/images/generations", model="gpt-image-2")
        monitor.capture_image_attempts(call_id, [{
            "slot": 2,
            "attempt": 1,
            "account_email": "failed@example.test",
            "status": "failed",
            "duration_ms": 120_000,
            "failure_code": "image_poll_timeout",
            "status_code": 502,
            "public_error": "Image generation timed out. Please try again.",
            "account_failure": True,
            "switched_account": False,
        }])
        detail = {
            "call_id": call_id,
            "status": "success",
            "duration_ms": 120_500,
            "request_meta": {"n": 2},
            "image_attempts": [{
                "slot": 1,
                "attempt": 1,
                "account_email": "success@example.test",
                "status": "success",
                "duration_ms": 60_000,
            }],
        }

        monitor.finish(detail)

        self.assertEqual(
            [(item["slot"], item["attempt"], item["status"]) for item in detail["image_attempts"]],
            [(1, 1, "success"), (2, 1, "failed")],
        )
        record = next(
            item
            for item in monitor.snapshot()["recent"]
            if item["call_id"] == call_id
        )
        self.assertEqual(record["image_requested_count"], 2)
        self.assertEqual(record["image_succeeded_count"], 1)
        self.assertEqual(record["image_failed_count"], 1)
        self.assertEqual(record["image_result_status"], "partial_success")

    def test_attempt_diagnostics_survive_log_normalization(self) -> None:
        attempts = collect_image_attempts([{
            "slot": 2,
            "attempt": 1,
            "account_email": "failed@example.test",
            "status": "failed",
            "failure_code": "image_poll_timeout",
            "public_error": "Image generation timed out. Please try again.",
            "upstream_error": '{"error":{"code":"generation_pending"}}',
            "raw_upstream_message": '{"size":"auto","n":4}',
        }])

        self.assertEqual(attempts[0]["upstream_error"], '{"error":{"code":"generation_pending"}}')
        self.assertEqual(attempts[0]["raw_upstream_message"], '{"size":"auto","n":4}')

    def test_partial_multi_image_result_is_not_reported_as_success(self) -> None:
        outputs = [
            conversation.ImageOutput(
                kind="result",
                model="gpt-image-2",
                index=1,
                total=2,
                data=[{"b64_json": "aW1hZ2U="}],
            ),
            conversation.ImageOutput(
                kind="message",
                model="gpt-image-2",
                index=2,
                total=2,
                text="opaque failure",
                failure=image_failure("image_poll_timeout"),
            ),
        ]

        with self.assertRaises(ImageGenerationError) as raised:
            conversation.collect_image_outputs(outputs)

        self.assertEqual(raised.exception.failure.code, "image_poll_timeout")

    def test_attempt_metadata_is_logged_and_removed_from_public_response(self) -> None:
        attempts = [{
            "slot": 1,
            "attempt": 1,
            "account_email": "a@example.test",
            "status": "failed",
            "failure_code": "image_poll_timeout",
            "conversation_id": "conv-a",
            "duration_ms": 120000,
            "monitor": {
                "metrics": {"account_wait_ms": 1200},
                "events": [{
                    "time": "2026-07-11 12:00:00",
                    "event": "image_account_lookup",
                    "label": "等待账号",
                    "account_wait_ms": 1200,
                }],
            },
        }]
        error = ImageGenerationError(
            "opaque timeout",
            failure=image_failure("image_poll_timeout"),
        )
        error.image_attempts = attempts

        fields = _exception_log_fields(error, image=True)
        public = _strip_internal_response_fields({"data": [], "_image_attempts": attempts})

        self.assertEqual(fields["image_attempts"], attempts)
        self.assertNotIn("_image_attempts", public)

        call = LoggedCall(
            {"id": "key-1", "name": "Key", "role": "admin"},
            "/v1/images/generations",
            "gpt-image-2",
            "image",
        )
        with mock.patch("services.log_service.log_service.add") as add_log:
            call.log("调用完成", result={"data": [], "_image_attempts": attempts})

        self.assertEqual(add_log.call_args.args[2]["image_attempts"], attempts)


if __name__ == "__main__":
    unittest.main()
