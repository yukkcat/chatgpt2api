from __future__ import annotations

import unittest

from services.openai_backend_api import OpenAIBackendAPI


class ConversationImageRecordBoundaryTests(unittest.TestCase):
    def test_assistant_code_reference_ids_are_not_generated_results(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        reference_id = "file_00000000aaaaaaaaaaaaaaaaaaaaaaaa"
        conversation = {
            "mapping": {
                "arguments": {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {
                            "content_type": "code",
                            "text": (
                                '{"size":"auto","n":1,"prompt":"draw",'
                                f'"referenced_image_ids":["{reference_id}"]}}'
                            ),
                        },
                        "metadata": {"async_task_type": "image_gen"},
                        "create_time": 1.0,
                    },
                },
            },
        }

        records = backend._extract_image_tool_records(conversation)

        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
