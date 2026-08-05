from __future__ import annotations

import json
import time
import unittest
from unittest import mock

from curl_cffi.requests.exceptions import RequestException

from services.image_failure import ImageGenerationError
from services.protocol import conversation


class ConversationStreamRecoveryRegressionTests(unittest.TestCase):
    def test_timeout_followup_classifies_terminal_image_arguments_as_tool_error(self) -> None:
        arguments = json.dumps({
            "size": "1024x1024",
            "n": 1,
            "prompt": "draw a lighthouse",
        })
        upstream_conversation = {
            "current_node": "assistant-1",
            "mapping": {
                "user-1": {
                    "parent": "",
                    "message": {
                        "id": "user-1",
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["draw a lighthouse"]},
                    },
                },
                "assistant-1": {
                    "parent": "user-1",
                    "message": {
                        "id": "assistant-1",
                        "author": {"role": "assistant"},
                        "content": {"content_type": "code", "text": arguments},
                        "status": "finished_successfully",
                        "end_turn": True,
                    },
                },
            },
        }
        backend = mock.Mock()
        backend._get_conversation.return_value = upstream_conversation
        backend._conversation_poll_snapshot.return_value = ({
            "messages": [{
                "role": "assistant",
                "content_type": "code",
                "status": "finished_successfully",
                "text_preview": arguments,
            }],
        }, arguments)
        backend._extract_image_tool_records.return_value = []
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )

        with mock.patch.object(
            conversation,
            "_image_stream_timeout_task_diagnostics",
            return_value=(None, "", [], ""),
        ):
            with self.assertRaises(ImageGenerationError) as raised:
                conversation._recover_after_image_stream_timeout(
                    backend,
                    request,
                    {"conversation_id": "conversation-1"},
                    TimeoutError("SSE stream exceeded 180s"),
                    1,
                    1,
                    time.time() - 180,
                )

        self.assertEqual(raised.exception.failure.code, "image_tool_error")
        self.assertEqual(raised.exception.raw_upstream_message, arguments)

    def test_request_exception_with_file_id_recovers_result(self) -> None:
        def interrupted_events():
            yield {
                "type": "conversation.event",
                "conversation_id": "conversation-1",
                "file_ids": ["file_00000000abcdefabcdefabcdef"],
                "sediment_ids": [],
                "text": "",
            }
            raise RequestException("transport closed")

        expected = conversation.ImageOutput(
            kind="result",
            model="gpt-image-2",
            index=1,
            total=1,
            data=[{"url": "https://example.test/image.png"}],
            conversation_id="conversation-1",
        )
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )

        with (
            mock.patch.object(conversation, "conversation_events", return_value=interrupted_events()),
            mock.patch.object(
                conversation,
                "_resolve_image_urls_with_monitor",
                return_value=["https://example.test/image.png"],
            ),
            mock.patch.object(
                conversation,
                "_image_result_output_from_urls",
                return_value=expected,
            ),
        ):
            outputs = list(conversation.stream_image_outputs(mock.Mock(), request))

        self.assertEqual(outputs[-1], expected)

    def test_request_exception_without_stream_state_is_not_reclassified(self) -> None:
        def interrupted_events():
            raise RequestException("transport closed")
            yield  # pragma: no cover

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )

        with mock.patch.object(
            conversation,
            "conversation_events",
            return_value=interrupted_events(),
        ):
            with self.assertRaises(RequestException) as raised:
                list(conversation.stream_image_outputs(mock.Mock(), request))

        self.assertEqual(str(raised.exception), "transport closed")

    def test_normal_conversation_recovery_uses_request_start_time(self) -> None:
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )
        events = iter([{
            "type": "conversation.done",
            "conversation_id": "",
            "file_ids": [],
            "sediment_ids": [],
            "text": "",
            "turn_use_case": "image gen",
        }])
        recovered_started_at: list[float | None] = []

        def recover(*_args: object, **kwargs: object) -> str:
            recovered_started_at.append(kwargs.get("started_at"))
            return ""

        before = time.time()
        with (
            mock.patch.object(conversation, "conversation_events", return_value=events),
            mock.patch.object(conversation, "_recover_image_conversation_id", side_effect=recover),
            mock.patch.object(conversation, "_backend_http_timing_data", return_value={}),
            mock.patch.object(conversation, "_resolve_image_urls_with_monitor", return_value=[]),
        ):
            list(conversation.stream_image_outputs(mock.Mock(), request))
        after = time.time()

        self.assertEqual(len(recovered_started_at), 1)
        self.assertIsNotNone(recovered_started_at[0])
        self.assertGreaterEqual(recovered_started_at[0], before)
        self.assertLessEqual(recovered_started_at[0], after)


if __name__ == "__main__":
    unittest.main()
