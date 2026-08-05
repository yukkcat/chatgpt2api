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


def test_registered_gallery_push_carries_metadata_and_retains_source(monkeypatch):
    configure(monkeypatch)
    payload = png_bytes()
    monkeypatch.setattr(push.image_storage_service, "get_bytes", lambda rel: payload)
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
        "generated.png",
        metadata={"prompt": "a red square", "created_at": "2026-08-05T10:00:00Z", "model": "gpt-image-2"},
    )
    post = next(call for call in calls if call[0] == "post")
    assert post[2]["data"] == {
        "remote_path": "generated.png",
        "source_sha256": sha,
        "prompt": "a red square",
        "created_at": "2026-08-05T10:00:00Z",
        "model": "gpt-image-2",
    }
    assert post[2]["headers"]["X-GenBox-Key"] == "test-secret"
    assert "test-secret" not in json.dumps(result)
    assert result["source_retained"] is True


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


@pytest.mark.parametrize(
    "response, expected_code",
    [
        (FakeResponse(200, {"ok": True, "contract_version": "v1", "source_id": "test-source", "max_image_bytes": 999}), "genbox_invalid_receipt"),
        (FakeResponse(500, {"error": "bad"}), "genbox_rejected"),
    ],
)
def test_receipt_and_http_errors_keep_source(monkeypatch, response: FakeResponse, expected_code: str):
    configure(monkeypatch)
    payload = png_bytes()
    monkeypatch.setattr(push.image_storage_service, "get_bytes", lambda rel: payload)
    probe = FakeResponse(200, {"ok": True, "contract_version": "v1", "source_id": "test-source", "max_image_bytes": len(payload)})
    if response.status_code == 200:
        import hashlib

        response = FakeResponse(200, {"ok": True, "contract_version": "v1", "source_id": "test-source", "sha256": "0" * 64, "status": "imported"})
    calls: list[tuple] = []
    monkeypatch.setattr(push.requests, "Session", lambda **kwargs: FakeSession([probe, response], calls))
    with pytest.raises(HTTPException) as exc:
        push.push_gallery_image("generated.png")
    assert exc.value.detail["error"] == expected_code
    assert calls[0][0] == "get"


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
            "created": 1722852000,
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
            {"prompt": "current generation prompt", "created_at": 1722852000, "model": "gpt-image-2"},
        )
    ]
