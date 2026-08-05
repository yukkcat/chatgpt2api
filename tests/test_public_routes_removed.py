from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from api.app import create_app


class PublicRoutesRemovedTests(unittest.IsolatedAsyncioTestCase):
    async def test_removed_public_routes_are_not_served_by_the_web_fallback(self) -> None:
        app = create_app()
        transport = httpx.ASGITransport(app=app)

        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "index.html"
            index_path.write_text("<html></html>", encoding="utf-8")

            def resolve_asset(requested_path: str) -> Path | None:
                return index_path if requested_path == "" else None

            with patch("api.app.resolve_web_asset", side_effect=resolve_asset):
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://test",
                ) as client:
                    for path in (
                        "/public/log",
                        "/public/stats",
                        "/public/display",
                        "/public/uptime",
                    ):
                        response = await client.get(path)
                        self.assertEqual(response.status_code, 404, path)


if __name__ == "__main__":
    unittest.main()
