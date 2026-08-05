from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
import re
from typing import Any

from utils.diagnostics import sanitize_diagnostic_text


ACCOUNT_OPERATION_EVENT_LIMIT = 500

_VALID_STATUSES = frozenset({"info", "success", "failed", "skipped"})
_STATUS_TONES = {
    "info": "info",
    "success": "success",
    "failed": "danger",
    "skipped": "warning",
}
_ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_action(value: object) -> str:
    action = str(value or "").strip().lower()
    return action if _ACTION_PATTERN.fullmatch(action) else "account_operation"


def normalize_account_operation_event(
    raw: object,
    *,
    fallback_sequence: int,
    sensitive_values: Iterable[object] = (),
    proxy_values: Iterable[object] = (),
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    sensitive_values = tuple(sensitive_values)
    proxy_values = tuple(proxy_values)
    status = str(raw.get("status") or "info").strip().lower()
    if status not in _VALID_STATUSES:
        status = "info"
    try:
        sequence = max(1, int(raw.get("sequence") or fallback_sequence))
    except (TypeError, ValueError):
        sequence = max(1, int(fallback_sequence))

    def clean(value: object, *, limit: int) -> str:
        return sanitize_diagnostic_text(
            value,
            sensitive_values=sensitive_values,
            proxy_values=proxy_values,
            limit=limit,
        )

    return {
        "sequence": sequence,
        "timestamp": clean(raw.get("timestamp") or _now_iso(), limit=80),
        "account_id": clean(raw.get("account_id"), limit=160),
        "account_label": clean(raw.get("account_label"), limit=240),
        "action": _clean_action(raw.get("action")),
        "status": status,
        "tone": _STATUS_TONES[status],
        "message": clean(raw.get("message"), limit=500),
    }


def _count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _summary_item(
    key: str,
    label: str,
    value: int,
    *,
    tone: str = "",
) -> dict[str, Any]:
    item: dict[str, Any] = {"key": key, "label": label, "value": value}
    if tone:
        item["tone"] = tone
    return item


def project_account_operation_presentation(
    progress: dict[str, Any],
    *,
    legacy_sync_alias: bool = False,
) -> dict[str, Any]:
    result = progress.get("result") if isinstance(progress.get("result"), dict) else None
    imported = (
        progress.get("import_result")
        if isinstance(progress.get("import_result"), dict)
        else None
    )
    processed = _count(progress.get("processed"))
    total = _count(progress.get("total"))

    if imported is not None:
        failed = _count(imported.get("failed"))
        summary_items = [
            _summary_item("added", "新增", _count(imported.get("added"))),
            _summary_item("skipped", "更新 / 跳过", _count(imported.get("skipped"))),
            _summary_item("synced", "同步", _count(imported.get("synced"))),
            _summary_item("failed", "失败", failed, tone="danger" if failed else ""),
        ]
    elif result is not None:
        failed = len(result.get("errors") or []) if isinstance(result.get("errors"), list) else 0
        summary_items = []
        if "synced" in result:
            summary_items.append(_summary_item("synced", "同步", _count(result.get("synced"))))
        elif "refreshed" in result:
            summary_items.append(_summary_item(
                "refreshed",
                "同步" if legacy_sync_alias else "刷新",
                _count(result.get("refreshed")),
            ))
        elif "added" in result:
            summary_items.append(_summary_item("added", "新增", _count(result.get("added"))))
        elif "updated" in result:
            summary_items.append(_summary_item("updated", "更新", _count(result.get("updated"))))
        summary_items.extend([
            _summary_item("failed", "失败", failed, tone="danger" if failed else ""),
            _summary_item("skipped", "跳过", _count(result.get("skipped"))),
            _summary_item(
                "removed",
                "移除",
                len(result.get("removed_ids") or [])
                if isinstance(result.get("removed_ids"), list)
                else _count(result.get("removed")),
                tone="warning" if result.get("removed_ids") or _count(result.get("removed")) else "",
            ),
        ])
    else:
        failed = sum(
            1
            for event in progress.get("events") or []
            if isinstance(event, dict) and event.get("status") == "failed"
        )
        summary_items = [
            _summary_item("processed", "已处理", processed),
            _summary_item("remaining", "待处理", max(0, total - processed)),
            _summary_item("total", "总数", total),
        ]

    has_error = bool(progress.get("error"))
    done = bool(progress.get("done"))
    if has_error:
        status_label = "失败"
        tone = "danger"
    elif not done:
        status_label = str(progress.get("stage_label") or "处理中").strip() or "处理中"
        tone = "info"
    elif failed:
        status_label = "部分完成"
        tone = "warning"
    else:
        status_label = "已完成"
        tone = "success"

    if has_error:
        message = str(progress.get("error") or "账号操作失败").strip() or "账号操作失败"
    elif not done:
        message = str(progress.get("stage_label") or "").strip()
        if not message:
            message = f"已处理 {processed} / {total}"
    else:
        parts = [
            f"{item['label']} {item['value']}"
            for item in summary_items
            if _count(item.get("value")) > 0
        ]
        prefix = "任务部分完成" if failed else "任务完成"
        message = f"{prefix} · {' · '.join(parts)}" if parts else prefix

    return {
        "status_label": status_label,
        "tone": tone,
        "message": message,
        "summary_items": summary_items,
    }


def normalize_account_operation_events(
    raw_events: object,
    *,
    sensitive_values: Iterable[object] = (),
    proxy_values: Iterable[object] = (),
    limit: int = ACCOUNT_OPERATION_EVENT_LIMIT,
) -> list[dict[str, Any]]:
    if not isinstance(raw_events, (list, tuple)):
        return []
    sensitive_values = tuple(sensitive_values)
    proxy_values = tuple(proxy_values)
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_events, start=1):
        event = normalize_account_operation_event(
            raw,
            fallback_sequence=index,
            sensitive_values=sensitive_values,
            proxy_values=proxy_values,
        )
        if event is not None:
            normalized.append(event)
    bounded_limit = max(1, int(limit or ACCOUNT_OPERATION_EVENT_LIMIT))
    return normalized[-bounded_limit:]


def append_account_operation_events(
    raw_events: object,
    additions: Iterable[object],
    *,
    sensitive_values: Iterable[object] = (),
    proxy_values: Iterable[object] = (),
    limit: int = ACCOUNT_OPERATION_EVENT_LIMIT,
    existing_events_normalized: bool = False,
) -> list[dict[str, Any]]:
    sensitive_values = tuple(sensitive_values)
    proxy_values = tuple(proxy_values)
    bounded_limit = max(1, int(limit or ACCOUNT_OPERATION_EVENT_LIMIT))
    if existing_events_normalized and isinstance(raw_events, (list, tuple)):
        events = [
            dict(event)
            for event in raw_events[-bounded_limit:]
            if isinstance(event, dict)
        ]
    else:
        events = normalize_account_operation_events(
            raw_events,
            sensitive_values=sensitive_values,
            proxy_values=proxy_values,
            limit=bounded_limit,
        )

    next_sequence = 1
    for existing in events:
        try:
            next_sequence = max(next_sequence, int(existing.get("sequence") or 0) + 1)
        except (TypeError, ValueError):
            continue

    for raw in additions:
        if not isinstance(raw, dict):
            continue
        event = normalize_account_operation_event(
            {
                "sequence": next_sequence,
                "timestamp": raw.get("timestamp") or _now_iso(),
                "account_id": raw.get("account_id"),
                "account_label": raw.get("account_label"),
                "action": raw.get("action"),
                "status": raw.get("status"),
                "message": raw.get("message"),
            },
            fallback_sequence=next_sequence,
            sensitive_values=sensitive_values,
            proxy_values=proxy_values,
        )
        if event is None:
            continue
        events.append(event)
        next_sequence += 1
        if len(events) > bounded_limit:
            del events[:-bounded_limit]
    return events


def append_account_operation_event(
    raw_events: object,
    *,
    account_id: object = "",
    account_label: object = "",
    action: object,
    status: object,
    message: object,
    sensitive_values: Iterable[object] = (),
    proxy_values: Iterable[object] = (),
    timestamp: object = "",
    limit: int = ACCOUNT_OPERATION_EVENT_LIMIT,
    existing_events_normalized: bool = False,
) -> list[dict[str, Any]]:
    return append_account_operation_events(
        raw_events,
        [{
            "timestamp": timestamp,
            "account_id": account_id,
            "account_label": account_label,
            "action": action,
            "status": status,
            "message": message,
        }],
        sensitive_values=sensitive_values,
        proxy_values=proxy_values,
        limit=limit,
        existing_events_normalized=existing_events_normalized,
    )
