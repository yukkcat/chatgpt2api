from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from typing import Any

from services.image_failure import image_failure


TERMINAL_STATUSES = frozenset({"success", "partial_success", "failed", "text_review"})

_STAGE_LABELS = {
    "queued": "排队中",
    "running": "生成中",
    "getting_account": "等待账号",
    "image_egress_waiting": "等待出口",
    "image_egress_ready": "出口就绪",
    "uploading": "上传图片",
    "bootstrapping": "初始化上游",
    "getting_token": "获取令牌",
    "preparing_conversation": "准备会话",
    "starting_generation": "等待上游首包",
    "generating": "上游生成中",
    "image_stream_resolve_start": "等待图片结果",
    "receiving_image": "接收图片",
}

_TERMINAL_STAGE_LABELS = {
    "success": "成功",
    "partial_success": "部分成功",
    "failed": "失败",
    "text_review": "文本",
}

_ASSET_TEXT_FIELDS = ("url", "path", "b64_json", "revised_prompt")
_ASSET_DIMENSION_FIELDS = ("width", "height")
_ASSET_PAYLOAD_FIELDS = ("url", "b64_json")


def _text(value: object, default: str = "") -> str:
    return str(value or default).strip()


def _image_count(value: object, default: int = 1) -> int:
    try:
        return min(4, max(1, int(value)))
    except (TypeError, ValueError):
        return default


def _non_negative_int_or_none(value: object) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return None


def _timestamp(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        return timestamp if timestamp > 0 else None
    return None


def _asset_dimension(value: object) -> int | None:
    parsed = _non_negative_int_or_none(value)
    return parsed if parsed and parsed > 0 else None


def _asset(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    result: dict[str, Any] = {
        field: _text(raw.get(field)) if isinstance(raw.get(field), str) else ""
        for field in _ASSET_TEXT_FIELDS
    }
    if not any(result[field] for field in _ASSET_PAYLOAD_FIELDS):
        return None
    for field in _ASSET_DIMENSION_FIELDS:
        result[field] = _asset_dimension(raw.get(field))
    return result


def _results(raw: Mapping[str, object]) -> list[dict[str, Any]]:
    source = raw.get("results")
    if not isinstance(source, list):
        source = raw.get("data")
    if not isinstance(source, list):
        return []
    return [asset for item in source if (asset := _asset(item)) is not None]


def _status(raw: Mapping[str, object], result_count: int, requested_count: int) -> str:
    raw_status = _text(raw.get("status")).lower()
    if raw_status in {"queued", "running"}:
        return raw_status
    if raw_status == "success":
        if result_count >= requested_count:
            return "success"
        if result_count > 0:
            return "partial_success"
        return "failed"
    if raw_status == "error":
        status_code = _non_negative_int_or_none(raw.get("status_code"))
        failure = image_failure(_text(raw.get("error_code")))
        if status_code == 400 or failure.outcome == "text":
            return "text_review"
    return "failed"


def _stage(raw: Mapping[str, object], status: str) -> tuple[str, str]:
    if status in TERMINAL_STATUSES:
        return status, _TERMINAL_STAGE_LABELS[status]
    progress = _text(raw.get("progress")).lower()
    if progress:
        return progress, _STAGE_LABELS.get(progress, _STAGE_LABELS[status])
    return status, _STAGE_LABELS[status]


def _elapsed_ms(
    raw: Mapping[str, object],
    *,
    status: str,
    duration_ms: int | None,
    now_ts: float,
) -> int | None:
    if status in TERMINAL_STATUSES:
        return duration_ms
    if status == "queued":
        base_ts = _timestamp(raw.get("created_ts"))
    else:
        base_ts = _timestamp(raw.get("started_ts"))
    if base_ts is None:
        return None
    return max(0, int((now_ts - base_ts) * 1000))


def image_task_row(
    raw: Mapping[str, object],
    *,
    now_ts: float | None = None,
) -> dict[str, Any]:
    requested_count = _image_count(raw.get("requested_count", raw.get("n")))
    results = _results(raw)[:requested_count]
    succeeded_count = len(results)
    status = _status(raw, len(results), requested_count)
    terminal = status in TERMINAL_STATUSES
    if terminal and status != "text_review":
        failed_count = requested_count - succeeded_count
    else:
        failed_count = 0
    pending_count = 0 if terminal else requested_count - succeeded_count
    duration_ms = _non_negative_int_or_none(raw.get("duration_ms"))
    stage_code, stage_label = _stage(raw, status)
    error_code = _text(raw.get("error_code"))
    public_error = _text(raw.get("public_error") or raw.get("error"))

    return {
        "id": _text(raw.get("id")),
        "status": status,
        "terminal": terminal,
        "mode": "edit" if _text(raw.get("mode")).lower() == "edit" else "generate",
        "model": _text(raw.get("model"), "gpt-image-2"),
        "size": _text(raw.get("size")),
        "quality": _text(raw.get("quality"), "auto"),
        "stage_code": stage_code,
        "stage_label": stage_label,
        "created_at": _text(raw.get("created_at")),
        "updated_at": _text(raw.get("updated_at")),
        "requested_count": requested_count,
        "succeeded_count": succeeded_count,
        "failed_count": failed_count,
        "pending_count": pending_count,
        "duration_ms": duration_ms,
        "elapsed_ms": _elapsed_ms(
            raw,
            status=status,
            duration_ms=duration_ms,
            now_ts=time.time() if now_ts is None else now_ts,
        ),
        "error_code": error_code,
        "public_error": public_error,
        "results": results,
        "actions": {
            "resume_poll": status == "failed" and raw.get("can_resume_poll") is True,
        },
    }


def image_task_page(
    raw_items: Iterable[Mapping[str, object]],
    *,
    missing_ids: Iterable[object] = (),
    now_ts: float | None = None,
) -> dict[str, Any]:
    projection_ts = time.time() if now_ts is None else now_ts
    return {
        "items": [image_task_row(item, now_ts=projection_ts) for item in raw_items],
        "missing_ids": list(dict.fromkeys(
            task_id for value in missing_ids if (task_id := _text(value))
        )),
    }
