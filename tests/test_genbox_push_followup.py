from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
import tempfile

import pytest
from fastapi import HTTPException
from PIL import Image

_test_db = Path(tempfile.gettempdir()) / "chatgpt2api-genbox-push-tests.db"
_test_db.unlink(missing_ok=True)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_test_db.as_posix()}")
os.environ.setdefault("CHATGPT2API_AUTH_KEY", "unit-test-auth-key")

import services.genbox_push_service as push
import services.image_storage_service as storage_module
import services.config as config_module
import services.image_task_service as image_tasks


class FakeResponse:
    def __init__(self, status_code: int, payload: object):
        self.status_code = status_code
        self.content = json.dumps(payload).encode("utf-8")


class FakeSession:
    def __init__(self, responses: list[FakeResponse], calls: list[tuple]):
        self.responses = iter(responses)
        self.calls = calls

    def get(self, *args, **kwargs):
        self.calls.append(("get", args, kwargs))
        return next(self.responses)

    def post(self, *args, **kwargs):
        self.calls.append(("post", args, kwargs))
        return next(self.responses)

    def close(self):
        self.calls.append(("close",))


class TimeoutSession:
    def __init__(self, calls: list[tuple]):
        self.calls = calls

    def get(self, *args, **kwargs):
        self.calls.append(("get", args, kwargs))
        raise TimeoutError("test timeout")

    def close(self):
        self.calls.append(("close",))


def png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, format="PNG")
    return output.getvalue()


def registered_storage(monkeypatch, tmp_path: Path, rel: str = "registered.png"):
    index_file = tmp_path / "image_index.json"
    index_file.write_text(json.dumps({"items": {rel: {"local": True}}}), encoding="utf-8")
    image_root = tmp_path / "images"
    image_root.mkdir()
    image_path = image_root / rel
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(png_bytes())
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage_module, "DATA_DIR", tmp_path)
    return storage_module.ImageStorageService(index_file=index_file), image_path


def configure(monkeypatch, *, enabled: bool = True):
    settings = {
        "enabled": enabled,
        "base_url": "https://genbox.invalid",
        "source_id": "test-source",
        "push_key": "test-secret",
        "timeout_secs": 5,
        "auto_push_after_studio": True,
    }
    monkeypatch.setattr(push.config, "get_genbox_push_settings", lambda: settings)
    monkeypatch.setenv("CHATGPT2API_BASE_URL", "http://app.invalid")
    monkeypatch.setattr(
        push.config,
        "get_image_storage_settings",
        lambda: {"public_base_url": "http://app.invalid"},
    )
    return settings


def test_unconfigured_push_makes_zero_network_requests(monkeypatch):
    configure(monkeypatch, enabled=False)
    calls: list[tuple] = []
    monkeypatch.setattr(push.requests, "Session", lambda **kwargs: calls.append(("session",)) or None)
    with pytest.raises(HTTPException) as exc:
        push.push_gallery_image("generated.png")
    assert exc.value.status_code == 409
    assert calls == []


def test_registered_gallery_push_carries_metadata_and_retains_source(monkeypatch, tmp_path: Path):
    configure(monkeypatch)
    service, image_path = registered_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(push, "image_storage_service", service)
    payload = image_path.read_bytes()
    monkeypatch.setattr(
        push.image_storage_service,
        "record_genbox_push",
        lambda rel, **kwargs: {"status": "imported", "sha256": kwargs["sha256"], "updated_at": kwargs["updated_at"]},
    )
    import hashlib

    sha = hashlib.sha256(payload).hexdigest()
    calls: list[tuple] = []
    session = FakeSession(
        [
            FakeResponse(200, {"ok": True, "contract_version": "v1", "source_id": "test-source", "max_image_bytes": len(payload)}),
            FakeResponse(200, {"ok": True, "contract_version": "v1", "source_id": "test-source", "sha256": sha, "status": "imported"}),
        ],
        calls,
    )
    monkeypatch.setattr(push.requests, "Session", lambda **kwargs: session)
    result = push.push_gallery_image(
        "registered.png",
        metadata={"prompt": "a red square", "date": "2026-08-05", "created_at": "2026-08-05T10:00:00Z", "model": "gpt-image-2"},
    )
    post = next(call for call in calls if call[0] == "post")
    assert post[2]["data"] == {
        "remote_path": "registered.png",
        "source_sha256": sha,
        "prompt": "a red square",
        "created_at": "2026-08-05T10:00:00Z",
        "date": "2026-08-05",
        "model": "gpt-image-2",
    }
    assert post[2]["headers"]["X-GenBox-Key"] == "test-secret"
    assert "test-secret" not in json.dumps(result)
    assert result["source_retained"] is True
    assert image_path.is_file()
    assert image_path.read_bytes() == payload


@pytest.mark.parametrize("bad_path", ["missing.png", "../outside.png", "/absolute.png", "folder", "note.txt"])
def test_invalid_or_unregistered_gallery_paths_are_rejected(monkeypatch, tmp_path: Path, bad_path: str):
    index_file = tmp_path / "image_index.json"
    index_file.write_text(json.dumps({"items": {"registered.png": {"local": True}}}), encoding="utf-8")
    image_root = tmp_path / "images"
    image_root.mkdir()
    (image_root / "registered.png").write_bytes(png_bytes())
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage_module, "DATA_DIR", tmp_path)
    service = storage_module.ImageStorageService(index_file=index_file)
    with pytest.raises(HTTPException) as exc:
        service.get_bytes(bad_path)
    assert exc.value.status_code == 404


def test_non_image_content_is_rejected_before_network(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(push.image_storage_service, "get_bytes", lambda rel: b"not-an-image")
    calls: list[tuple] = []
    monkeypatch.setattr(push.requests, "Session", lambda **kwargs: calls.append(("session",)) or None)
    with pytest.raises(HTTPException) as exc:
        push.push_gallery_image("fake.png")
    assert exc.value.status_code == 404
    assert calls == []


def test_push_timeout_returns_error_without_delete(monkeypatch):
    configure(monkeypatch)
    payload = png_bytes()
    monkeypatch.setattr(push.image_storage_service, "get_bytes", lambda rel: payload)
    calls: list[tuple] = []
    monkeypatch.setattr(push.requests, "Session", lambda **kwargs: TimeoutSession(calls))
    with pytest.raises(HTTPException) as exc:
        push.push_gallery_image("generated.png")
    assert exc.value.detail["error"] == "genbox_request_failed"
    assert calls[0][0] == "get"
    assert all(call[0] != "delete" for call in calls)


def test_auto_push_logs_do_not_expose_push_key(monkeypatch, tmp_path: Path):
    configure(monkeypatch)
    service, image_path = registered_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(push, "image_storage_service", service)
    monkeypatch.setattr(push, "_spawn_thread", lambda target, name: target())

    records: list[object] = []

    class RecordingLogger:
        def info(self, message: object) -> None:
            records.append(message)

        def warning(self, message: object) -> None:
            records.append(message)

        def error(self, message: object) -> None:
            records.append(message)

    monkeypatch.setattr(push, "logger", RecordingLogger())
    payload = image_path.read_bytes()
    import hashlib

    sha = hashlib.sha256(payload).hexdigest()
    success_session = FakeSession(
        [
            FakeResponse(200, {"ok": True, "contract_version": "v1", "source_id": "test-source", "max_image_bytes": len(payload)}),
            FakeResponse(200, {"ok": True, "contract_version": "v1", "source_id": "test-source", "sha256": sha, "status": "imported"}),
        ],
        [],
    )
    monkeypatch.setattr(push.requests, "Session", lambda **kwargs: success_session)
    push._run_auto_push("registered.png", metadata={"prompt": "a red square"})
    assert any("genbox_auto_push_succeeded" in str(record) for record in records)

    timeout_calls: list[tuple] = []
    monkeypatch.setattr(push.requests, "Session", lambda **kwargs: TimeoutSession(timeout_calls))
    push._run_auto_push("registered.png")
    assert any("genbox_auto_push_failed" in str(record) for record in records)
    assert "test-secret" not in str(records)


def test_push_uses_gallery_registration_before_network(monkeypatch, tmp_path: Path):
    configure(monkeypatch)
    service, _ = registered_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(push, "image_storage_service", service)
    calls: list[tuple] = []
    monkeypatch.setattr(push.requests, "Session", lambda **kwargs: calls.append(("session",)) or None)
    with pytest.raises(HTTPException) as exc:
        push.push_gallery_image("unregistered.png")
    assert exc.value.status_code == 404
    assert calls == []


def test_timeout_keeps_registered_source_bytes_on_disk(monkeypatch, tmp_path: Path):
    configure(monkeypatch)
    service, image_path = registered_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(push, "image_storage_service", service)
    original = image_path.read_bytes()
    calls: list[tuple] = []
    monkeypatch.setattr(push.requests, "Session", lambda **kwargs: TimeoutSession(calls))
    with pytest.raises(HTTPException) as exc:
        push.push_gallery_image("registered.png")
    assert exc.value.detail["error"] == "genbox_request_failed"
    assert image_path.is_file()
    assert image_path.read_bytes() == original


@pytest.mark.parametrize(
    "post_payload, post_status, expected_code",
    [
        ({"ok": True, "contract_version": "v1", "source_id": "test-source", "sha256": "0" * 64, "status": "imported"}, 200, "genbox_invalid_receipt"),
        ({"error": "bad"}, 500, "genbox_rejected"),
    ],
)
def test_receipt_and_http_errors_keep_source(monkeypatch, tmp_path: Path, post_payload: dict[str, object], post_status: int, expected_code: str):
    configure(monkeypatch)
    service, image_path = registered_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(push, "image_storage_service", service)
    original = image_path.read_bytes()
    probe = FakeResponse(200, {"ok": True, "contract_version": "v1", "source_id": "test-source", "max_image_bytes": len(original)})
    calls: list[tuple] = []
    monkeypatch.setattr(push.requests, "Session", lambda **kwargs: FakeSession([probe, FakeResponse(post_status, post_payload)], calls))
    with pytest.raises(HTTPException) as exc:
        push.push_gallery_image("registered.png")
    assert exc.value.detail["error"] == expected_code
    assert calls[0][0] == "get"
    assert image_path.is_file()
    assert image_path.read_bytes() == original


def test_external_url_is_not_eligible_for_studio_auto_push(monkeypatch):
    configure(monkeypatch)
    assert push._rel_from_stored_url("https://evil.invalid/images/old.png") is None


def test_studio_task_passes_only_result_urls_and_real_metadata(monkeypatch, tmp_path: Path):
    captured: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        image_tasks,
        "auto_push_gallery_urls",
        lambda urls, *, metadata=None: captured.append((urls, dict(metadata or {}))),
    )
    monkeypatch.setattr(image_tasks.realtime_monitor_service, "start", lambda *args, **kwargs: None)
    monkeypatch.setattr(image_tasks.realtime_monitor_service, "stage", lambda *args, **kwargs: None)
    service = image_tasks.ImageTaskService(
        tmp_path / "tasks.json",
        generation_handler=lambda payload: {
            "date": "2026-08-05",
            "data": [{"url": "http://app.invalid/images/current.png"}],
            "_image_urls": ["http://app.invalid/images/current.png"],
        },
    )
    key = "owner:task"
    service._tasks[key] = {"id": "task", "owner_id": "owner", "status": "queued"}
    monkeypatch.setattr(service, "_log_call", lambda *args, **kwargs: None)
    import time

    service._run_task(
        key,
        "generate",
        {"prompt": "current generation prompt"},
        {"id": "owner", "name": "unit", "role": "admin"},
        "gpt-image-2",
        time.time(),
        time.perf_counter(),
    )
    assert captured == [
        (
            ["http://app.invalid/images/current.png"],
            {"prompt": "current generation prompt", "date": "2026-08-05", "model": "gpt-image-2"},
        )
    ]

def test_auto_push_ignores_external_urls_without_spawning_network(monkeypatch):
    configure(monkeypatch)
    spawned: list[tuple] = []
    monkeypatch.setattr(push, "_spawn_thread", lambda target, name: spawned.append((target, name)) or None)
    push.auto_push_gallery_urls([
        "https://evil.invalid/images/old.png",
        "file:///etc/passwd",
        "https://app.invalid/images/unregistered.png",
    ])
    assert spawned == []

def test_legacy_registered_local_item_without_flags_is_readable(monkeypatch, tmp_path: Path):
    index_file = tmp_path / "image_index.json"
    index_file.write_text(json.dumps({"items": {"legacy.png": {"storage": "local"}}}), encoding="utf-8")
    image_root = tmp_path / "images"
    image_root.mkdir()
    payload = png_bytes()
    (image_root / "legacy.png").write_bytes(payload)
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage_module, "DATA_DIR", tmp_path)
    service = storage_module.ImageStorageService(index_file=index_file)
    assert service.get_bytes("legacy.png") == payload


def test_has_local_rejects_unregistered_path(monkeypatch, tmp_path: Path):
    service, _ = registered_storage(monkeypatch, tmp_path)
    assert service.has_local("registered.png") is True
    assert service.has_local("unregistered.png") is False
