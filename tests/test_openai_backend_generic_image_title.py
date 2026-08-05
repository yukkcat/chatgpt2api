from __future__ import annotations

import unittest
from unittest import mock

from services.openai_backend_api import OpenAIBackendAPI


class GenericImageTitleTests(unittest.TestCase):
    def test_generic_image_title_is_ignored_when_prompt_contains_image_word(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._list_recent_conversations = mock.Mock(return_value=[{
            "id": "other-request",
            "title": "Image",
            "update_time": 1_005.0,
        }])

        recovered = backend.find_conversation_by_prompt(
            "generate an image of a red lighthouse",
            started_at=1_000.0,
        )

        self.assertEqual(recovered, "")


if __name__ == "__main__":
    unittest.main()
