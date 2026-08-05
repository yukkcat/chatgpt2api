from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from curl_cffi import requests
from fastapi import HTTPException

from services.config import config
from services.image_storage_service import image_storage_service, normalize_image_relative_path


_ALLOWED_STATUSES = {"imported", "already-imported", "duplicate-local"}


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": code})


def _json_object(response: Any) -> dict[str, Any]:
    content = bytes(response.content or b"")
    if len(content) > 1024 * 1024:
        raise _error(502, "genbox_invalid_receipt")
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
        raise _error(502, "genbox_invalid_receipt") from exc
    if not isinstance(value, dict):
        raise _error(502, "genbox_invalid_receipt")
    return value


def _settings() -> dict[str, object]:
    settings = config.get_genbox_push_settings()
    required = ("base_url", "source_id", "push_key")
    if not settings.get("enabled") or any(not str(settings.get(key) or "").strip() for key in required):
        raise _error(409, "genbox_not_configured")
    return settings


def _validate_probe(value: Mapping[str, Any], source_id: str, size: int) -> None:
    if (
        value.get("ok") is not True
        or value.get("contract_version") != "v1"
        or value.get("source_id") != source_id
        or not isinstance(value.get("max_image_bytes"), int)
        or value["max_image_bytes"] < size
    ):
        raise _error(502, "genbox_probe_rejected")


def _validate_receipt(value: Mapping[str, Any], source_id: str, sha256: str) -> str:
    status = value.get("status")
    if (
        value.get("ok") is not True
        or value.get("contract_version") != "v1"
        or value.get("source_id") != source_id
        or value.get("sha256") != sha256
        or status not in _ALLOWED_STATUSES
    ):
        raise _error(502, "genbox_invalid_receipt")
    return str(status)


def push_gallery_image(relative_path: str) -> dict[str, object]:
    settings = _settings()
    rel = normalize_image_relative_path(relative_path)
    payload = image_storage_service.get_bytes(rel)
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
                raise _error(502, "genbox_unavailable")
            _validate_probe(_json_object(probe), str(settings["source_id"]), len(payload))
            response = session.post(
                f"{str(settings['base_url']).rstrip('/')}/api/sync/push",
                headers=headers,
                files={"image": (Path(rel).name, payload, "application/octet-stream")},
                data={"remote_path": rel, "source_sha256": sha256},
                timeout=timeout,
                allow_redirects=False,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise _error(504, "genbox_request_failed") from exc
        if not 200 <= int(response.status_code) < 300:
            raise _error(502, "genbox_rejected")
        status = _validate_receipt(_json_object(response), str(settings["source_id"]), sha256)
    finally:
        session.close()
    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    state = image_storage_service.record_genbox_push(rel, status=status, sha256=sha256, updated_at=updated_at)
    return {"path": rel, **state, "source_retained": True}
