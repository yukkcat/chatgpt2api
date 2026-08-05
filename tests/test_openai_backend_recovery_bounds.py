from __future__ import annotations

import unittest
from unittest import mock

from services.openai_backend_api import OpenAIBackendAPI


class ConversationRecoveryBoundsTests(unittest.TestCase):
    def _backend_with_items(self, items: list[dict[str, object]]) -> OpenAIBackendAPI:
        backend = object.__new__(OpenAIBackendAPI)
        backend._list_recent_conversations = mock.Mock(return_value=items)
        return backend

    def test_prompt_match_after_recovery_window_is_rejected(self) -> None:
        backend = self._backend_with_items([{
            "id": "late-request",
            "title": "draw a red lighthouse",
            "update_time": 1_601.0,
        }])

        recovered = backend.find_conversation_by_prompt(
            "draw a red lighthouse",
            started_at=1_000.0,
        )

        self.assertEqual(recovered, "")

    def test_prompt_match_inside_recovery_window_is_accepted(self) -> None:
        backend = self._backend_with_items([{
            "id": "current-request",
            "title": "draw a red lighthouse",
            "update_time": 1_005.0,
        }])

        recovered = backend.find_conversation_by_prompt(
            "draw a red lighthouse",
            started_at=1_000.0,
        )

        self.assertEqual(recovered, "current-request")


if __name__ == "__main__":
    unittest.main()
