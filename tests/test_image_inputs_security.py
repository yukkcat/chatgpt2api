from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from curl_cffi import CurlOpt
from fastapi import HTTPException

from api import image_inputs


class _Response:
    def __init__(self, status_code: int = 200, *, headers: dict[str, str] | None = None, chunks: list[bytes] | None = None):
        self.status_code = status_code
        self.headers = headers or {"content-type": "image/png"}
        self._chunks = chunks or []
        self.closed = False

    def iter_content(self, chunk_size: int | None = None):
        del chunk_size
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


class ImageInputSecurityTests(unittest.TestCase):
    def test_private_and_loopback_hosts_are_rejected(self) -> None:
        for url in ("http://127.0.0.1/image.png", "http://10.0.0.5/image.png", "http://localhost/image.png"):
            with self.subTest(url=url):
                with self.assertRaises(HTTPException) as raised:
                    image_inputs._validate_public_image_url(url)
                self.assertIn("not publicly reachable", str(raised.exception.detail))

    @mock.patch("api.image_inputs.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))])
    @mock.patch("api.image_inputs.requests.get")
    def test_validated_address_is_pinned_for_the_actual_connection(
        self,
        get: mock.Mock,
        _getaddrinfo: mock.Mock,
    ) -> None:
        get.return_value = _Response(chunks=[b"image"])

        image_inputs._download_image_url("https://public.example/image.png")

        options = get.call_args.kwargs["curl_options"]
        self.assertEqual(options[CurlOpt.NOPROXY], "*")
        self.assertEqual(options[CurlOpt.RESOLVE], ["public.example:443:93.184.216.34"])
        self.assertNotIn("proxies", get.call_args.kwargs)

    @mock.patch("api.image_inputs.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))])
    @mock.patch("api.image_inputs.requests.get")
    def test_redirect_target_is_revalidated(self, get: mock.Mock, _getaddrinfo: mock.Mock) -> None:
        get.return_value = _Response(302, headers={"location": "http://127.0.0.1/secret"})
        with self.assertRaises(HTTPException) as raised:
            image_inputs._download_image_url("https://public.example/image.png")
        self.assertIn("not publicly reachable", str(raised.exception.detail))
        get.assert_called_once()

    @mock.patch("api.image_inputs.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))])
    @mock.patch("api.image_inputs.requests.get")
    def test_remote_response_is_read_with_per_source_limit(self, get: mock.Mock, _getaddrinfo: mock.Mock) -> None:
        get.return_value = _Response(chunks=[b"1234"])
        with mock.patch.object(image_inputs, "MAX_IMAGE_REFERENCE_BYTES", 3):
            with self.assertRaises(HTTPException) as raised:
                image_inputs._download_image_url("https://public.example/image.png")
        self.assertIn("exceeds 50MB limit", str(raised.exception.detail))
        self.assertTrue(get.return_value.closed)

    def test_combined_sources_have_a_total_limit(self) -> None:
        sources = [(b"123", "one.png", "image/png"), (b"456", "two.png", "image/png")]
        with mock.patch.object(image_inputs, "MAX_IMAGE_REFERENCE_BYTES", 4), mock.patch.object(
            image_inputs, "MAX_IMAGE_INPUT_BYTES", 5
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(image_inputs.read_image_sources(sources))
        self.assertIn("combined image inputs exceed 100MB limit", str(raised.exception.detail))


if __name__ == "__main__":
    unittest.main()
