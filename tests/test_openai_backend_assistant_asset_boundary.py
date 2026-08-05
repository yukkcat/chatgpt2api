from __future__ import annotations

import unittest

from services.openai_backend_api import OpenAIBackendAPI


class AssistantImageAssetBoundaryTests(unittest.TestCase):
    def test_assistant_asset_keeps_output_pointer_but_not_input_reference(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        conversation = {
            "mapping": {
                "result": {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {
                            "content_type": "multimodal_text",
                            "parts": [{
                                "content_type": "image_asset_pointer",
                                "asset_pointer": "file-service://file_result",
                            }],
                        },
                        "metadata": {
                            "async_task_type": "image_gen",
                            "referenced_image_ids": [
                                "file_00000000aaaaaaaaaaaaaaaaaaaaaaaa",
                            ],
                        },
                        "create_time": 1.0,
                    },
                },
            },
        }

        records = backend._extract_image_tool_records(conversation)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["file_ids"], ["file_result"])
        self.assertEqual(records[0]["sediment_ids"], [])


if __name__ == "__main__":
    unittest.main()
