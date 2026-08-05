from __future__ import annotations

import unittest
from unittest import mock

import services.image_service as image_service


class ImageServiceTests(unittest.TestCase):
    def test_list_images_returns_requested_window_and_total_after_tag_filter(self) -> None:
        storage_items = [
            {
                "path": f"2026/05/29/item-{index}.png",
                "date": "2026-05-29",
                "created_at": f"2026-05-29 10:0{index}:00",
                "name": f"item-{index}.png",
                "size": 100 + index,
            }
            for index in range(5)
        ]
        tags = {
            "2026/05/29/item-0.png": ["keep"],
            "2026/05/29/item-1.png": ["skip"],
            "2026/05/29/item-2.png": ["keep"],
            "2026/05/29/item-3.png": ["keep"],
            "2026/05/29/item-4.png": ["skip"],
        }

        with (
            mock.patch.object(image_service, "load_tags", return_value=tags),
            mock.patch.object(image_service.image_storage_service, "list_items", return_value=storage_items),
        ):
            result = image_service.list_images("http://server", tag="keep", limit=2, offset=2)

        self.assertEqual(result["total"], 3)
        self.assertEqual(result["page_size"], 2)
        self.assertEqual(result["page"], 2)
        self.assertEqual(result["page_count"], 2)
        self.assertFalse(result["has_more"])
        self.assertEqual(
            [item["path"] for item in result["items"]],
            ["2026/05/29/item-3.png"],
        )


if __name__ == "__main__":
    unittest.main()
