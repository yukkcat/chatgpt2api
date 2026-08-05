from __future__ import annotations

import hashlib
import unittest
from unittest import mock

from fastapi import HTTPException

import services.genbox_push_service as genbox_push_module


REL = "2026/07/24/hero-alpha.png"
PUBLIC_REL = "2026/07/24/hero-beta.png"
BASE_URL = "https://push.example.test"
SOURCE_ID = "source-a"
PUSH_KEY = "push-secret"
STORED_URL = f"https://console.example.test/images/{REL}"
PUBLIC_STORED_URL = f"https://assets.example.test/{PUBLIC_REL}"
SHA256 = hashlib.sha256(b"genbox-image-payload").hexdigest()


def _settings(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "enabled": True,
        "base_url": BASE_URL,
        "source_id": SOURCE_ID,
        "push_key": PUSH_KEY,
        "timeout_secs": 20,
        "auto_push_after_studio": True,
    }
    value.update(overrides)
    return value


def _image_storage_settings(public_base_url: str = "") -> dict[str, object]:
    return {
        "enabled": True,
        "mode": "local",
        "public_base_url": public_base_url,
    }


class _FakeConfig:
    def __init__(
        self,
        genbox: dict[str, object] | None = None,
        image_storage: dict[str, object] | None = None,
        base_url: str = "",
    ) -> None:
        self._genbox = genbox if genbox is not None else _settings()
        self._image_storage = image_storage if image_storage is not None else _image_storage_settings()
        self._base_url = base_url

    def get_genbox_push_settings(self) -> dict[str, object]:
        return dict(self._genbox)

    def get_image_storage_settings(self) -> dict[str, object]:
        return dict(self._image_storage)

    @property
    def base_url(self) -> str:
        return self._base_url


class _FakeStorage:
    def __init__(self, states: dict[str, dict[str, str]] | None = None) -> None:
        self.states = dict(states or {})
        self.state_lookups: list[str] = []
        self.deleted: list[str] = []

    def get_genbox_push_state(self, rel: str) -> dict[str, str] | None:
        self.state_lookups.append(rel)
        return self.states.get(rel)

    def delete(self, rel: str) -> bool:
        self.deleted.append(rel)
        return True


class GenBoxAutoPushTests(unittest.TestCase):
    def _run_inline(self, target, name):
        target()
        return None

    def test_disabled_or_unconfigured_never_dispatches_or_reads(self) -> None:
        cases = [
            _settings(enabled=False, auto_push_after_studio=True),
            _settings(enabled=True, auto_push_after_studio=False),
            _settings(enabled=True, auto_push_after_studio=True, push_key=""),
            _settings(enabled=True, auto_push_after_studio=True, base_url=""),
        ]
        for settings in cases:
            with self.subTest(settings=settings):
                storage = _FakeStorage()
                with (
                    mock.patch.object(genbox_push_module, "config", _FakeConfig(genbox=settings)),
                    mock.patch.object(genbox_push_module, "image_storage_service", storage),
                    mock.patch.object(
                        genbox_push_module,
                        "_spawn_thread",
                        side_effect=AssertionError("auto push thread must not be spawned"),
                    ),
                ):
                    genbox_push_module.auto_push_gallery_urls([STORED_URL])
                self.assertEqual(storage.state_lookups, [])

    def test_auto_push_dispatches_each_stored_url_once(self) -> None:
        pushed: list[str] = []
        config = _FakeConfig(
            base_url="https://console.example.test",
            image_storage=_image_storage_settings("https://assets.example.test"),
        )
        with (
            mock.patch.object(genbox_push_module, "config", config),
            mock.patch.object(genbox_push_module, "image_storage_service", _FakeStorage()),
            mock.patch.object(genbox_push_module, "_spawn_thread", self._run_inline),
            mock.patch.object(
                genbox_push_module,
                "push_gallery_image",
                side_effect=lambda rel: pushed.append(rel),
            ),
        ):
            genbox_push_module.auto_push_gallery_urls([STORED_URL, STORED_URL, PUBLIC_STORED_URL])
        self.assertEqual(pushed, [REL, PUBLIC_REL])

    def test_auto_push_skips_images_with_existing_terminal_state(self) -> None:
        pushed: list[str] = []
        state = {"status": "imported", "sha256": SHA256, "updated_at": "2026-07-24T00:00:00Z"}
        with (
            mock.patch.object(genbox_push_module, "config", _FakeConfig()),
            mock.patch.object(genbox_push_module, "image_storage_service", _FakeStorage({REL: state})),
            mock.patch.object(genbox_push_module, "_spawn_thread", self._run_inline),
            mock.patch.object(
                genbox_push_module,
                "push_gallery_image",
                side_effect=lambda rel: pushed.append(rel),
            ),
        ):
            genbox_push_module.auto_push_gallery_urls([STORED_URL])
        self.assertEqual(pushed, [])

    def test_auto_push_failure_never_raises_out_of_the_hook(self) -> None:
        with (
            mock.patch.object(genbox_push_module, "config", _FakeConfig()),
            mock.patch.object(genbox_push_module, "image_storage_service", _FakeStorage()),
            mock.patch.object(genbox_push_module, "_spawn_thread", self._run_inline),
            mock.patch.object(
                genbox_push_module,
                "push_gallery_image",
                side_effect=HTTPException(status_code=504, detail={"error": "genbox_request_failed"}),
            ),
        ):
            genbox_push_module.auto_push_gallery_urls([STORED_URL])

    def test_unparseable_urls_are_skipped_without_reading_state(self) -> None:
        storage = _FakeStorage()
        with (
            mock.patch.object(genbox_push_module, "config", _FakeConfig()),
            mock.patch.object(genbox_push_module, "image_storage_service", storage),
            mock.patch.object(genbox_push_module, "_spawn_thread", self._run_inline),
            mock.patch.object(
                genbox_push_module,
                "push_gallery_image",
                side_effect=AssertionError("must not push"),
            ),
        ):
            genbox_push_module.auto_push_gallery_urls([
                "not-a-url",
                "ftp://assets.example.test/2026/07/24/beta.png",
                "https://other.example.test/raw/2026/07/24/gamma.png",
            ])
        self.assertEqual(storage.state_lookups, [])

    def test_rel_from_stored_url_handles_default_and_public_base_urls(self) -> None:
        config = _FakeConfig(
            base_url="https://console.example.test",
            image_storage=_image_storage_settings("https://assets.example.test"),
        )
        with mock.patch.object(genbox_push_module, "config", config):
            self.assertEqual(genbox_push_module._rel_from_stored_url(STORED_URL), REL)
            self.assertEqual(genbox_push_module._rel_from_stored_url(PUBLIC_STORED_URL), PUBLIC_REL)
            self.assertIsNone(genbox_push_module._rel_from_stored_url("https://other.example.test/no-images/a.png"))
            self.assertIsNone(genbox_push_module._rel_from_stored_url("not-a-url"))
