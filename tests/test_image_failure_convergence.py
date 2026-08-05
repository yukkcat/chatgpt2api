from __future__ import annotations

import unittest

from services.image_failure import (
    classify_conversation_failure,
    classify_task_failure,
    image_failure,
    merge_message_failure,
    public_image_error_message,
)


def _node(message_id: str, parent: str | None, message: dict) -> dict:
    return {
        "id": message_id,
        "parent": parent,
        "message": {"id": message_id, **message},
    }


class ImageFailureConvergenceTests(unittest.TestCase):
    def test_plain_terminal_text_is_bad_request(self) -> None:
        failure = image_failure("upstream_text_reply")

        self.assertEqual(failure.status_code, 400)
        self.assertEqual(failure.error_type, "invalid_request_error")
        self.assertFalse(failure.account_failure)

    def test_generic_task_error_does_not_override_terminal_text(self) -> None:
        text = image_failure("upstream_text_reply", raw_detail="opaque reply")
        generic = classify_task_failure({
            "image_gen_message": {
                "status": "failed",
                "is_error": True,
            },
        })

        self.assertIsNotNone(generic)
        self.assertEqual(merge_message_failure(text, generic).code, "upstream_text_reply")
        self.assertEqual(merge_message_failure(generic, text).code, "upstream_text_reply")

    def test_explicit_quota_code_overrides_terminal_text(self) -> None:
        text = image_failure("upstream_text_reply", raw_detail="opaque reply")
        quota = image_failure("image_quota_exhausted", raw_detail={"code": "insufficient_quota"})

        self.assertEqual(merge_message_failure(text, quota).code, "image_quota_exhausted")
        self.assertEqual(merge_message_failure(quota, text).code, "image_quota_exhausted")

    def test_direct_tool_system_error_is_not_plain_assistant_text(self) -> None:
        assistant_text = "You've hit the Free plan limit for image generations requests."
        conversation = {
            "current_node": "assistant",
            "mapping": {
                "user": _node("user", None, {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["draw"]},
                    "status": "finished_successfully",
                    "create_time": 1,
                }),
                "tool": _node("tool", "user", {
                    "author": {"role": "tool"},
                    "content": {"content_type": "system_error", "parts": ["opaque tool failure"]},
                    "metadata": {"async_task_type": "image_gen"},
                    "status": "finished_successfully",
                    "create_time": 2,
                }),
                "assistant": _node("assistant", "tool", {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": [assistant_text]},
                    "status": "finished_successfully",
                    "end_turn": True,
                    "create_time": 3,
                }),
            },
        }

        failure = classify_conversation_failure(conversation)

        self.assertIsNotNone(failure)
        self.assertEqual(failure.code, "image_tool_error")
        self.assertEqual(failure.status_code, 502)
        self.assertTrue(failure.account_failure)
        self.assertEqual(public_image_error_message(failure), assistant_text)

    def test_processing_tool_text_then_terminal_text_is_plain_text_reply(self) -> None:
        conversation = {
            "current_node": "assistant",
            "mapping": {
                "user": _node("user", None, {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["draw"]},
                    "status": "finished_successfully",
                    "create_time": 1,
                }),
                "tool": _node("tool", "user", {
                    "author": {"role": "tool"},
                    "content": {"content_type": "text", "parts": ["processing"]},
                    "metadata": {"async_task_type": "image_gen"},
                    "status": "finished_successfully",
                    "create_time": 2,
                }),
                "assistant": _node("assistant", "tool", {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["opaque policy reply"]},
                    "status": "finished_successfully",
                    "end_turn": True,
                    "create_time": 3,
                }),
            },
        }

        failure = classify_conversation_failure(conversation)

        self.assertIsNotNone(failure)
        self.assertEqual(failure.code, "upstream_text_reply")
        self.assertFalse(failure.account_failure)


if __name__ == "__main__":
    unittest.main()
