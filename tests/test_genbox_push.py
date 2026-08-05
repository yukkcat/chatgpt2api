from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

import services.genbox_push_service as genbox_push_module
from services.image_storage_service import ImageStorageService
from services.json_file import read_json_object, write_json_file


PAYLOAD = b"genbox-image-payload"
SHA256 = hashlib.sha256(PAYLOAD).hexdigest()
REL = "2026/07/24/hero-alpha.png"
BASE_URL = "https://push.example.test"
SOURCE_ID = "source-a"
PUSH_KEY = "push-secret"


def _settings(**overrides: object) -> dict[str, object]:
    value = {
        "enabled": True,
        "base_url": BASE_URL,
        "source_id": SOURCE_ID,
        "push_key": PUSH_KEY,
        "timeout_secs": 20,
    }
    value.update(overrides)
    return value


def _valid_probe() -> bytes:
    return json.dumps({
        "ok": True,
        "contract_version": "v1",
        "source_id": SOURCE_ID,
        "max_image_bytes": len(PAYLOAD) + 1,
    }).encode()


def _valid_receipt(status: str = "imported", sha256: str = SHA256) -> bytes:
    return json.dumps({
        "ok": True,
        "contract_version": "v1",
        "source_id": SOURCE_ID,
        "sha256": sha256,
        "status": status,
    }).encode()


class FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"{}") -> None:
        self.status_code = status_code
        self.content = content


class FakeSession:
    def __init__(self, probe: FakeResponse | None = None, push: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.probe = probe
        self.push = push
        self.error = error
        self.get_calls: list[tuple[str, dict[str, object]]] = []
        self.post_calls: list[tuple[str, dict[str, object]]] = []
        self.closed = False

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.get_calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.probe

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.post_calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.push

    def close(self) -> None:
        self.closed = True


class FakeImageStorage:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = dict(payloads)
        self.get_calls: list[str] = []
        self.recorded: list[tuple[str, str, str, str]] = []
        self.deleted: list[str] = []

    def get_bytes(self, relative_path: str) -> bytes:
        self.get_calls.append(relative_path)
        try:
            return self.payloads[relative_path]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="image not found") from exc

    def record_genbox_push(self, relative_path: str, *, status: str, sha256: str, updated_at: str) -> dict[str, str]:
        self.recorded.append((relative_path, status, sha256, updated_at))
        return {"status": status, "sha256": sha256, "updated_at": updated_at}

    def delete(self, relative_path: str) -> bool:
        self.deleted.append(relative_path)
        return True


class GenBoxPushServiceTests(unittest.TestCase):
    def test_unconfigured_push_never_builds_a_session_or_reads_image(self) -> None:
        storage = FakeImageStorage({REL: PAYLOAD})
        settings = _settings(enabled=False, base_url="", source_id="", push_key="")
        session_built = False

        def build_session(*_args: object, **_kwargs: object) -> object:
            nonlocal session_built
            session_built = True
            raise AssertionError("session must not be created")

        with (
            mock.patch.object(genbox_push_module, "config", SimpleNamespace(get_genbox_push_settings=lambda: settings)),
            mock.patch.object(genbox_push_module, "image_storage_service", storage),
            mock.patch.object(genbox_push_module.requests, "Session", side_effect=build_session),
        ):
            with self.assertRaises(HTTPException) as caught:
                genbox_push_module.push_gallery_image(REL)

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail, {"error": "genbox_not_configured"})
        self.assertEqual(storage.get_calls, [])
        self.assertFalse(session_built)

    def test_success_records_nonsensitive_state_and_ignores_safe_to_delete_source(self) -> None:
        receipt = json.loads(_valid_receipt())
        receipt["safe_to_delete_source"] = True
        receipt["remote_path"] = "/tmp/do-not-trust"
        session = FakeSession(
            FakeResponse(200, _valid_probe()),
            FakeResponse(200, json.dumps(receipt).encode()),
        )
        storage = FakeImageStorage({REL: PAYLOAD})

        with (
            mock.patch.object(genbox_push_module, "config", SimpleNamespace(get_genbox_push_settings=_settings)),
            mock.patch.object(genbox_push_module, "image_storage_service", storage),
            mock.patch.object(genbox_push_module.requests, "Session", return_value=session),
        ):
            result = genbox_push_module.push_gallery_image(REL)

        self.assertEqual(len(storage.recorded), 1)
        recorded_path, status, sha256, updated_at = storage.recorded[0]
        self.assertEqual(recorded_path, REL)
        self.assertEqual(status, "imported")
        self.assertEqual(sha256, SHA256)
        self.assertTrue(updated_at.endswith("Z"))
        self.assertEqual(result, {
            "path": REL,
            "status": "imported",
            "sha256": SHA256,
            "updated_at": updated_at,
            "source_retained": True,
        })
        self.assertEqual(storage.deleted, [])
        self.assertEqual(storage.payloads[REL], PAYLOAD)
        self.assertEqual(session.get_calls[0][0], f"{BASE_URL}/api/sync/push/status")
        self.assertEqual(session.post_calls[0][0], f"{BASE_URL}/api/sync/push")
        post_kwargs = session.post_calls[0][1]
        self.assertEqual(post_kwargs["headers"], {
            "X-GenBox-Source": SOURCE_ID,
            "X-GenBox-Key": PUSH_KEY,
        })
        self.assertEqual(post_kwargs["files"], {
            "image": ("hero-alpha.png", PAYLOAD, "application/octet-stream"),
        })
        self.assertEqual(post_kwargs["data"], {
            "remote_path": REL,
            "source_sha256": SHA256,
        })

    def test_failure_modes_do_not_record_or_delete_source(self) -> None:
        cases = [
            ("probe-auth", FakeSession(FakeResponse(401, b"{}"), None)),
            ("push-auth", FakeSession(FakeResponse(200, _valid_probe()), FakeResponse(401, b"{}"))),
            (
                "probe-rejected",
                FakeSession(
                    FakeResponse(200, json.dumps({
                        "ok": True,
                        "contract_version": "v1",
                        "source_id": "wrong-source",
                        "max_image_bytes": len(PAYLOAD) + 1,
                    }).encode()),
                    None,
                ),
            ),
            (
                "receipt-hash-mismatch",
                FakeSession(FakeResponse(200, _valid_probe()), FakeResponse(200, _valid_receipt(sha256="0" * 64))),
            ),
            (
                "receipt-invalid-status",
                FakeSession(FakeResponse(200, _valid_probe()), FakeResponse(200, _valid_receipt(status="pending"))),
            ),
            ("timeout", FakeSession(error=TimeoutError("timed out"))),
            ("network", FakeSession(error=ConnectionError("connection failed"))),
        ]

        for name, session in cases:
            with self.subTest(name=name):
                storage = FakeImageStorage({REL: PAYLOAD})
                with (
                    mock.patch.object(genbox_push_module, "config", SimpleNamespace(get_genbox_push_settings=_settings)),
                    mock.patch.object(genbox_push_module, "image_storage_service", storage),
                    mock.patch.object(genbox_push_module.requests, "Session", return_value=session),
                ):
                    with self.assertRaises(HTTPException) as caught:
                        genbox_push_module.push_gallery_image(REL)

                self.assertIn(caught.exception.status_code, {502, 504})
                self.assertEqual(storage.recorded, [])
                self.assertEqual(storage.deleted, [])
                self.assertEqual(storage.payloads[REL], PAYLOAD)

    def test_receipt_parser_rejects_duplicate_keys_oversized_and_non_objects(self) -> None:
        cases = [
            b'{"ok": true, "ok": false}',
            b"[1, 2, 3]",
            b"not-json",
        ]
        for content in cases:
            with self.subTest(content=content[:24]):
                with self.assertRaises(HTTPException) as caught:
                    genbox_push_module._json_object(FakeResponse(200, content))
                self.assertEqual(caught.exception.status_code, 502)
                self.assertEqual(caught.exception.detail, {"error": "genbox_invalid_receipt"})

        with self.assertRaises(HTTPException) as caught:
            genbox_push_module._json_object(FakeResponse(200, b"x" * (1024 * 1024 + 1)))
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(caught.exception.detail, {"error": "genbox_invalid_receipt"})

    def test_record_genbox_push_saves_only_nonsensitive_state_and_keeps_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index_path = root / "image-index.json"
            source_path = root / "images" / REL
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(PAYLOAD)
            write_json_file(index_path, {
                "items": {
                    REL: {
                        "path": REL,
                        "local": True,
                        "webdav": False,
                        "storage": "local",
                    }
                }
            })
            storage = ImageStorageService(index_path)

            with mock.patch("services.config.DATA_DIR", root):
                state = storage.record_genbox_push(
                    REL,
                    status="imported",
                    sha256=SHA256,
                    updated_at="2026-07-25T12:00:00Z",
                )

            self.assertEqual(state, {
                "status": "imported",
                "sha256": SHA256,
                "updated_at": "2026-07-25T12:00:00Z",
            })
            indexed = read_json_object(index_path)["items"][REL]
            self.assertEqual(indexed["genbox_push"], state)
            self.assertTrue(source_path.is_file())
            self.assertEqual(source_path.read_bytes(), PAYLOAD)


if __name__ == "__main__":
    unittest.main()

