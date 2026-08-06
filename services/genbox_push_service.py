from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from curl_cffi import requests
from fastapi import HTTPException
from PIL import Image

from services.bounded_task_runner import BoundedTaskRunner, env_int
from services.config import config
from services.genbox_push_view import (
    GENBOX_PUSH_TERMINAL_STATUSES,
    genbox_push_state,
)
from services.image_storage_service import image_storage_service, normalize_image_relative_path
from utils.log import logger


class GenBoxPushError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


_ERROR_SPECS = {
    "genbox_not_configured": (409, "GenBox 尚未配置，请先在设置的外部服务中填写并启用"),
    "genbox_invalid_receipt": (502, "GenBox 返回的数据无效"),
    "genbox_probe_rejected": (502, "GenBox 连接验证未通过"),
    "genbox_unavailable": (502, "GenBox 服务当前不可用"),
    "genbox_rejected": (502, "GenBox 未接受该图片"),
    "genbox_request_failed": (504, "GenBox 请求失败或超时"),
}


def _error(code: str) -> GenBoxPushError:
    status_code, message = _ERROR_SPECS[code]
    return GenBoxPushError(status_code, code, message)


_auto_push_runner = BoundedTaskRunner(
    name="genbox-auto-push",
    max_workers=env_int("CHATGPT2API_GENBOX_PUSH_CONCURRENCY", 8),
    queue_size=env_int("CHATGPT2API_GENBOX_PUSH_QUEUE_SIZE", 64),
)


def _json_object(response: Any) -> dict[str, Any]:
    content = bytes(response.content or b"")
    if len(content) > 1024 * 1024:
        raise _error("genbox_invalid_receipt")

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate receipt key")
            value[key] = item
        return value

    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=object_pairs)
    except (UnicodeDecodeError, ValueError) as exc:
        raise _error("genbox_invalid_receipt") from exc
    if not isinstance(value, dict):
        raise _error("genbox_invalid_receipt")
    return value


def _rel_from_stored_url(url: str) -> str | None:
    raw = str(url or "").strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    configured_origins: set[tuple[str, str]] = set()
    for base in (
        config.base_url,
        config.get_image_storage_settings().get("public_base_url"),
    ):
        try:
            origin = urlsplit(str(base or "").strip().rstrip("/"))
        except ValueError:
            continue
        if origin.scheme in {"http", "https"} and origin.netloc:
            configured_origins.add((origin.scheme, origin.netloc.lower()))
    if (parsed.scheme, parsed.netloc.lower()) not in configured_origins:
        return None
    path = parsed.path or ""
    if "/images/" in path:
        rel = path.split("/images/", 1)[1]
    else:
        rel = ""
        public_base_url = str(config.get_image_storage_settings().get("public_base_url") or "").strip().rstrip("/")
        for prefix in (public_base_url, str(config.base_url or "").strip().rstrip("/")):
            if prefix and raw.startswith(f"{prefix}/"):
                rel = raw[len(prefix) + 1 :]
                break
        if not rel:
            return None
    try:
        return normalize_image_relative_path(rel)
    except HTTPException:
        return None


def _auto_push_settings() -> dict[str, object] | None:
    settings = config.get_genbox_push_settings()
    if not settings.get("enabled") or not settings.get("auto_push_after_studio"):
        return None
    required = ("base_url", "source_id", "push_key")
    if any(not str(settings.get(key) or "").strip() for key in required):
        return None
    return settings


def start_genbox_push_service() -> None:
    _auto_push_runner.start()


def shutdown_genbox_push_service() -> None:
    _auto_push_runner.shutdown_cancel_pending_and_wait()


def _run_auto_push(rel: str, *, metadata: Mapping[str, Any] | None = None) -> None:
    try:
        push_gallery_image(rel, metadata=metadata)
        logger.info({"event": "genbox_auto_push_succeeded", "path": rel})
    except GenBoxPushError as exc:
        logger.warning({"event": "genbox_auto_push_failed", "path": rel, "code": exc.code})
    except Exception as exc:
        logger.warning({
            "event": "genbox_auto_push_failed",
            "path": rel,
            "error": type(exc).__name__,
        })


def _auto_push_cancelled(rel: str, _: BaseException) -> None:
    logger.info({"event": "genbox_auto_push_cancelled", "path": rel})


def _submit_auto_push(rel: str, *, metadata: Mapping[str, Any] | None = None) -> bool:
    reservation = _auto_push_runner.reserve()
    if reservation is None:
        return False
    return reservation.commit(
        _run_auto_push,
        rel,
        metadata=metadata,
        on_cancel=lambda exc: _auto_push_cancelled(rel, exc),
    )


def auto_push_gallery_urls(urls: list[str], *, metadata: Mapping[str, Any] | None = None) -> None:
    try:
        if _auto_push_settings() is None:
            return
        rels: list[str] = []
        seen: set[str] = set()
        for url in urls:
            rel = _rel_from_stored_url(url)
            if not rel or rel in seen:
                continue
            seen.add(rel)
            state = image_storage_service.get_genbox_push_state(rel)
            if state is not None and str(state.get("status")) in GENBOX_PUSH_TERMINAL_STATUSES:
                continue
            rels.append(rel)
        for rel in rels:
            if not _submit_auto_push(rel, metadata=metadata):
                logger.warning({"event": "genbox_auto_push_queue_full", "path": rel})
    except Exception as exc:
        logger.warning({
            "event": "genbox_auto_push_dispatch_failed",
            "error": type(exc).__name__,
        })


def _settings() -> dict[str, object]:
    settings = config.get_genbox_push_settings()
    required = ("base_url", "source_id", "push_key")
    if not settings.get("enabled") or any(not str(settings.get(key) or "").strip() for key in required):
        raise _error("genbox_not_configured")
    return settings


def _validate_probe(value: Mapping[str, Any], source_id: str, size: int) -> None:
    if (
        value.get("ok") is not True
        or value.get("contract_version") != "v1"
        or value.get("source_id") != source_id
        or not isinstance(value.get("max_image_bytes"), int)
        or value["max_image_bytes"] < size
    ):
        raise _error("genbox_probe_rejected")


def _validate_receipt(value: Mapping[str, Any], source_id: str, sha256: str) -> str:
    status = value.get("status")
    if (
        value.get("ok") is not True
        or value.get("contract_version") != "v1"
        or value.get("source_id") != source_id
        or value.get("sha256") != sha256
        or status not in GENBOX_PUSH_TERMINAL_STATUSES
    ):
        raise _error("genbox_invalid_receipt")
    return str(status)


def push_gallery_image(relative_path: str, *, metadata: Mapping[str, Any] | None = None) -> dict[str, object]:
    settings = _settings()
    rel = normalize_image_relative_path(relative_path)
    payload = image_storage_service.get_bytes(rel)
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
    except Exception as exc:
        raise GenBoxPushError(404, "genbox_source_not_found", "Gallery image not registered or not a valid image") from exc
    sha256 = hashlib.sha256(payload).hexdigest()
    headers = {
        "X-GenBox-Source": str(settings["source_id"]),
        "X-GenBox-Key": str(settings["push_key"]),
    }
    timeout = int(settings["timeout_secs"])
    session = requests.Session(verify=True)
    try:
        try:
            probe = session.get(
                f"{str(settings['base_url']).rstrip('/')}/api/sync/push/status",
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
            )
            if not 200 <= int(probe.status_code) < 300:
                raise _error("genbox_unavailable")
            _validate_probe(_json_object(probe), str(settings["source_id"]), len(payload))
            data: dict[str, str] = {"remote_path": rel, "source_sha256": sha256}
            for key in ("prompt", "created_at", "date", "model"):
                value = metadata.get(key) if isinstance(metadata, Mapping) else None
                if value is not None and str(value).strip():
                    data[key] = str(value)
            response = session.post(
                f"{str(settings['base_url']).rstrip('/')}/api/sync/push",
                headers=headers,
                files={"image": (Path(rel).name, payload, "application/octet-stream")},
                data=data,
                timeout=timeout,
                allow_redirects=False,
            )
        except GenBoxPushError:
            raise
        except Exception as exc:
            raise _error("genbox_request_failed") from exc
        if not 200 <= int(response.status_code) < 300:
            raise _error("genbox_rejected")
        status = _validate_receipt(_json_object(response), str(settings["source_id"]), sha256)
    finally:
        session.close()
    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    state = image_storage_service.record_genbox_push(rel, status=status, sha256=sha256, updated_at=updated_at)
    projected = genbox_push_state(state)
    if projected is None:
        raise RuntimeError("stored GenBox push state is invalid")
    return {"path": rel, **projected, "source_retained": True}
