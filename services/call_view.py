from __future__ import annotations

from typing import Any, Iterable, Mapping

from services.image_failure import (
    is_rate_limit_failure_code,
    is_structured_failure,
    is_text_review_failure_code,
)
from services.request_detail_view import (
    build_request_detail_core,
    build_request_timeline_presentation,
    format_request_duration,
    request_status_presentation,
)


_SUMMARY_ERROR_LIMIT = 1000

_IMAGE_FAILURE_LABELS = {
    "upstream_error": "上游请求失败",
    "internal_error": "内部处理异常",
    "upstream_unavailable": "上游服务暂不可用",
    "upstream_connection_failed": "无法连接上游",
    "upstream_connection_timeout": "上游连接超时",
    "upstream_rate_limited": "上游服务限流",
    "image_poll_timeout": "等待图片结果超时",
    "image_stream_timeout": "上游图片流超时",
    "image_stream_interrupted": "上游图片流中断",
    "image_tool_error": "图片工具异常",
    "image_quota_exhausted": "图片额度已用尽",
    "file_upload_throttled": "参考图上传受限",
    "auth_invalid": "账号登录态失效",
    "content_policy_violation": "内容安全策略拒绝",
    "invalid_image_input": "图片输入无效",
    "upstream_text_reply": "上游仅返回文本",
    "no_image_generated": "未生成图片",
    "unsupported_model": "模型不支持生图",
    "image_download_failed": "图片下载失败",
    "task_interrupted": "图片任务被中断",
    "no_available_account": "暂无可用账号",
    "insufficient_quota": "图片额度不足",
}

_BUSINESS_LABELS = {
    "account": "账号操作",
    "image_generation": "文生图",
    "image_edit": "图生图",
    "image_chat": "对话生图",
    "chat": "对话",
    "responses": "响应",
    "messages": "消息",
    "search": "搜索",
    "file": "文件",
}

def _record(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _detail(item: Mapping[str, Any]) -> dict[str, Any]:
    detail = item.get("detail")
    return _record(detail) if isinstance(detail, Mapping) else dict(item)


def _value(item: Mapping[str, Any], key: str, default: object = "") -> object:
    detail = item.get("detail")
    if isinstance(detail, Mapping):
        value = detail.get(key)
        if value not in (None, ""):
            return value
    value = item.get(key)
    return default if value in (None, "") else value


def _clean(value: object) -> str:
    return str(value or "").strip()


def _image_failure_label(value: object) -> str:
    return _IMAGE_FAILURE_LABELS.get(_clean(value).lower(), "")


def _normalize_account_status(value: object) -> str:
    status = _clean(value)
    aliases = {
        "正常": "正常",
        "normal": "正常",
        "ready": "正常",
        "success": "正常",
        "completed": "正常",
        "complete": "正常",
        "done": "正常",
        "限流": "限流",
        "limited": "限流",
        "rate_limited": "限流",
        "cooling": "限流",
        "backoff": "限流",
        "异常": "异常",
        "abnormal": "异常",
        "invalid": "异常",
        "error": "异常",
        "failed": "异常",
        "fail": "异常",
        "incomplete": "异常",
        "禁用": "禁用",
        "disabled": "禁用",
    }
    return aliases.get(status.lower(), status)


def _int(value: object) -> int:
    try:
        parsed = int(float(value or 0))
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on", "是"}:
        return True
    if normalized in {"0", "false", "no", "off", "否"}:
        return False
    return None


def _bool(value: object) -> bool:
    return _optional_bool(value) is True


def _first_text(item: Mapping[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = _value(item, key)
        if text := _clean(value):
            return text
    return ""


def _known_url(value: object) -> str:
    text = _clean(value)
    if text.startswith(("http://", "https://", "/images/", "/image-thumbnails/")):
        return text
    return ""


def _urls_from(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    urls: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            url = _known_url(item.get("url"))
        else:
            url = _known_url(item)
        if url and url not in urls:
            urls.append(url)
    return urls


def call_image_urls(item: Mapping[str, Any]) -> list[str]:
    detail = _detail(item)
    urls: list[str] = []
    for key in ("image_urls", "urls", "result_urls", "_image_urls", "data"):
        for url in _urls_from(detail.get(key)):
            if url not in urls:
                urls.append(url)
    return urls


def call_business_kind(item: Mapping[str, Any]) -> str:
    log_type = _clean(item.get("type") or _value(item, "type")).lower()
    endpoint = _clean(_value(item, "endpoint")).lower().rstrip("/")
    model = _clean(_value(item, "model")).lower()
    image_request = _bool(_value(item, "image_request"))

    if log_type == "account":
        return "account"
    if endpoint.endswith("/images/generations"):
        return "image_generation"
    if endpoint.endswith("/images/edits"):
        return "image_edit"
    if image_request:
        return "image_chat"
    if endpoint.endswith("/chat/completions"):
        return "image_chat" if "image" in model else "chat"
    if endpoint.endswith("/responses"):
        return "responses"
    if endpoint.endswith("/messages"):
        return "messages"
    if "search" in endpoint:
        return "search"
    if "file" in endpoint:
        return "file"
    return "other"


def _attempt_items(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    attempts = _value(item, "image_attempts", [])
    if not isinstance(attempts, list):
        return []
    normalized: list[dict[str, Any]] = []
    for value in attempts:
        if not isinstance(value, Mapping):
            continue
        attempt = dict(value)
        attempt["slot"] = max(1, _int(attempt.get("slot")))
        attempt["attempt"] = max(1, _int(attempt.get("attempt")))
        if "switched_account" in attempt:
            attempt["switched_account"] = _optional_bool(attempt.get("switched_account"))
        normalized.append(attempt)
    return normalized


def call_switch_count(item: Mapping[str, Any]) -> int:
    attempts = _attempt_items(item)
    attempt_count = sum(1 for attempt in attempts if attempt.get("switched_account") is True)
    explicit_count = max(
        _int(_value(item, "switch_count")),
        _int(_value(item, "image_account_switch_count")),
    )
    return max(attempt_count, explicit_count)


def _explicit_int(item: Mapping[str, Any], key: str) -> int | None:
    detail = item.get("detail")
    if isinstance(detail, Mapping) and key in detail and detail.get(key) not in (None, ""):
        return _int(detail.get(key))
    if key in item and item.get(key) not in (None, ""):
        return _int(item.get(key))
    return None


def call_image_counts(item: Mapping[str, Any]) -> tuple[int, int, int, str]:
    business = call_business_kind(item)
    explicit_requested = _explicit_int(item, "image_requested_count")
    explicit_succeeded = _explicit_int(item, "image_succeeded_count")
    explicit_failed = _explicit_int(item, "image_failed_count")
    attempts = _attempt_items(item)

    request_meta = _value(item, "request_meta", {})
    request_meta = request_meta if isinstance(request_meta, Mapping) else {}
    monitor = _value(item, "monitor", {})
    monitor = monitor if isinstance(monitor, Mapping) else {}
    images = monitor.get("images") if isinstance(monitor.get("images"), Mapping) else {}

    requested = max(
        explicit_requested or 0,
        _int(request_meta.get("n")),
        max((_int(attempt.get("slot")) for attempt in attempts), default=0),
        max(
            (
                _int(image.get("total"))
                for image in images.values()
                if isinstance(image, Mapping)
            ),
            default=0,
        ),
    )
    succeeded_slots = {
        _int(attempt.get("slot"))
        for attempt in attempts
        if _clean(attempt.get("status")).lower() == "success" and _int(attempt.get("slot")) > 0
    }
    result_count = max(
        _int(_value(item, "result_data_count")),
        _int(_value(item, "result_url_count")),
        len(call_image_urls(item)),
    )
    if explicit_succeeded is not None:
        succeeded = explicit_succeeded
    elif succeeded_slots:
        succeeded = max(len(succeeded_slots), result_count)
    else:
        succeeded = result_count
    requested = max(requested, succeeded)

    if explicit_failed is not None:
        failed = explicit_failed
    else:
        failed = max(0, requested - succeeded)
    requested = max(requested, succeeded + failed)

    explicit_status = _clean(_value(item, "image_result_status")).lower()
    if explicit_status in {"success", "failed", "partial_success"}:
        result_status = explicit_status
    elif succeeded > 0 and failed > 0:
        result_status = "partial_success"
    elif succeeded > 0:
        result_status = "success"
    elif requested > 0:
        result_status = "failed"
    else:
        result_status = ""

    if business not in {"image_generation", "image_edit", "image_chat"} and not any(
        (explicit_requested, explicit_succeeded, explicit_failed, attempts, result_count)
    ):
        return 0, 0, 0, ""
    return requested, succeeded, failed, result_status


def call_outcome(item: Mapping[str, Any]) -> str:
    status = _clean(_value(item, "status")).lower()
    error_code = _clean(_value(item, "error_code", _value(item, "failure_code"))).lower()
    status_code = _int(_value(item, "status_code"))
    requested, succeeded, failed, result_status = call_image_counts(item)

    if call_business_kind(item) == "account":
        account_status = _normalize_account_status(status)
        if status_code == 429 or account_status == "限流":
            return "rate_limited"
        if status_code >= 400 or account_status == "异常":
            return "failed"
        if account_status == "正常":
            return "success"
        if account_status == "禁用":
            return "unknown"

    if status == "partial_success" or result_status == "partial_success" or (
        requested > 0 and succeeded > 0 and failed > 0
    ):
        return "partial_success"
    if status == "text_review" or status_code == 400 or is_text_review_failure_code(error_code):
        return "text_review"
    if status in {"success", "completed", "complete", "done"}:
        return "success"
    if status_code == 429 or is_rate_limit_failure_code(status) or is_rate_limit_failure_code(error_code):
        return "rate_limited"
    if status_code >= 400 or is_structured_failure(
        status=status,
        error=_value(item, "error"),
        error_code=_value(item, "error_code"),
        failure_code=_value(item, "failure_code"),
    ):
        return "failed"
    return "unknown"


def call_timings_ms(item: Mapping[str, Any]) -> dict[str, int]:
    detail = _detail(item)
    monitor = detail.get("monitor") if isinstance(detail.get("monitor"), Mapping) else {}
    sources: list[Mapping[str, Any]] = []
    for value in (detail.get("perf"), detail.get("metrics"), monitor.get("metrics")):
        if isinstance(value, Mapping):
            sources.append(value)
    images = monitor.get("images")
    if isinstance(images, Mapping):
        for image in images.values():
            if isinstance(image, Mapping) and isinstance(image.get("metrics"), Mapping):
                sources.append(image["metrics"])

    timings: dict[str, int] = {}
    for source in sources:
        for key, value in source.items():
            name = _clean(key)
            if not name.endswith("_ms"):
                continue
            milliseconds = _int(value)
            if milliseconds > 0:
                timings[name] = max(timings.get(name, 0), milliseconds)
    return timings


def _duration_ms(item: Mapping[str, Any]) -> int:
    explicit = _int(_value(item, "duration_ms"))
    if explicit:
        return explicit
    timings = call_timings_ms(item)
    return max(
        timings.get("total_ms", 0),
        timings.get("handler_exec_ms", 0),
        timings.get("stream_ms", 0),
    )


def _attempt_result_status(attempt: Mapping[str, Any], outcome: str | None = None) -> str:
    failure_scope = _clean(attempt.get("failure_scope")).lower()
    error_code = _clean(attempt.get("error_code") or attempt.get("failure_code")).lower()
    if failure_scope == "delivery" or (not failure_scope and error_code == "image_download_failed"):
        return "generated_but_delivery_failed"
    if (outcome or call_outcome(attempt)) == "success":
        return "success"
    return "failed"


def _attempt_timings_ms(attempt: Mapping[str, Any]) -> dict[str, int]:
    monitor = _record(attempt.get("monitor"))
    return {
        _clean(key): _int(metric)
        for key, metric in _record(monitor.get("metrics")).items()
        if _clean(key).endswith("_ms") and _int(metric) > 0
    }


def _attempt_duration_ms(
    attempt: Mapping[str, Any],
    timings: Mapping[str, int] | None = None,
) -> int:
    resolved_timings = timings if timings is not None else _attempt_timings_ms(attempt)
    return _int(attempt.get("duration_ms")) or max(
        _int(resolved_timings.get("total_ms")),
        _int(resolved_timings.get("stream_ms")),
        _int(resolved_timings.get("handler_exec_ms")),
    )


def build_attempt_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    attempt = dict(value)
    outcome = call_outcome(attempt)
    error_code = _clean(attempt.get("error_code") or attempt.get("failure_code"))
    monitor = _record(attempt.get("monitor"))
    timings = _attempt_timings_ms(attempt)
    duration_ms = _attempt_duration_ms(attempt, timings)
    result_status = _attempt_result_status(attempt, outcome)
    error_label = _image_failure_label(error_code)
    if result_status == "generated_but_delivery_failed":
        status_presentation = {"label": "生成成功", "tone": "warning"}
    else:
        status_presentation = _status_presentation({"outcome": outcome})
    summary = {
        "slot": max(1, _int(attempt.get("slot"))),
        "attempt": max(1, _int(attempt.get("attempt"))),
        "account_email": _clean(attempt.get("account_email")),
        "conversation_id": _clean(attempt.get("conversation_id")),
        "status": _clean(attempt.get("status")),
        "outcome": outcome,
        "result_status": result_status,
        "duration_ms": duration_ms,
        "status_code": _int(attempt.get("status_code")),
        "error_code": error_code,
        "error_label": error_label,
        "public_error": _clean(attempt.get("public_error") or attempt.get("error")),
        "upstream_error": _clean(attempt.get("upstream_error") or attempt.get("raw_upstream_error")),
        "upstream_text": _clean(
            attempt.get("upstream_text")
            or attempt.get("raw_upstream_message")
            or attempt.get("upstream_message")
            or attempt.get("upstream_message_preview")
        ),
        "switched_account": _optional_bool(attempt.get("switched_account")),
        "timings_ms": timings,
        "monitor": monitor,
    }
    summary["presentation"] = {
        "status": status_presentation,
        "failure_label": error_label or (
            "结果交付失败"
            if result_status == "generated_but_delivery_failed"
            else "生成失败"
        ),
        "marker_tone": "success" if result_status == "success" else "danger",
        "switch_label": "切换账号" if summary["switched_account"] is True else "",
        "error_code_text": error_code,
        "status_code_text": f"HTTP {summary['status_code']}" if summary["status_code"] else "",
        "show_failure": result_status != "success",
        "show_error_details": bool(
            summary["public_error"]
            or summary["upstream_error"]
            or summary["upstream_text"]
        ),
        "timeline": build_request_timeline_presentation(
            timings,
            monitor.get("events"),
            image_count=1,
        ),
    }
    return summary


def _type_label(log_type: object) -> str:
    value = _clean(log_type)
    if value == "call":
        return "调用日志"
    if value == "account":
        return "账号日志"
    return value or "日志"


def _business_label(business: object, log_type: object) -> str:
    return _BUSINESS_LABELS.get(_clean(business), _type_label(log_type))


_format_duration = format_request_duration


def _duration_breakdown(attempts: list[dict[str, Any]]) -> str:
    ordered_attempts = sorted(
        attempts,
        key=lambda attempt: (_int(attempt.get("slot")), _int(attempt.get("attempt"))),
    )
    attempts_by_slot: dict[int, list[int]] = {}
    for attempt in ordered_attempts:
        duration_ms = _attempt_duration_ms(attempt)
        if duration_ms <= 0:
            continue
        slot = _int(attempt.get("slot"))
        attempts_by_slot.setdefault(slot, []).append(duration_ms)

    retry_groups = [
        (slot, durations)
        for slot, durations in sorted(attempts_by_slot.items())
        if len(durations) > 1
    ]
    if not retry_groups:
        return ""

    has_multiple_slots = len({_int(attempt.get("slot")) for attempt in attempts}) > 1
    expressions: list[str] = []
    for slot, durations in retry_groups:
        expression = " + ".join(_format_duration(duration) for duration in durations)
        expressions.append(f"图 {slot}：{expression}" if has_multiple_slots else expression)
    return f"({'；'.join(expressions)})"


def _status_presentation(summary: Mapping[str, Any]) -> dict[str, str]:
    outcome = _clean(summary.get("outcome"))
    display_status = _clean(summary.get("display_status"))
    if _clean(summary.get("business")) == "account" and display_status:
        tones = {"正常": "success", "异常": "danger", "限流": "warning", "禁用": "muted"}
        return {"label": display_status, "tone": tones.get(display_status, "muted")}
    return request_status_presentation(outcome, fallback=display_status or "记录")


def _result_text(summary: Mapping[str, Any]) -> str:
    outcome = _clean(summary.get("outcome"))
    requested = _int(summary.get("image_requested_count"))
    succeeded = _int(summary.get("image_succeeded_count"))
    public_error = _clean(summary.get("public_error"))
    error_label = _image_failure_label(summary.get("error_code"))
    summary_text = _clean(summary.get("summary"))

    if outcome == "partial_success":
        return f"生成 {succeeded}/{requested} 张图片"
    if outcome == "text_review":
        return "上游返回文本"
    if outcome in {"failed", "rate_limited"}:
        return public_error or error_label or summary_text or "调用失败"
    if succeeded > 0:
        return (
            f"生成 {succeeded}/{requested} 张图片"
            if requested > 1
            else f"生成 {succeeded} 张图片"
        )
    if outcome == "success":
        business = _clean(summary.get("business"))
        if business in {"image_generation", "image_edit", "image_chat"}:
            return "图片生成完成"
        if business == "search":
            return "搜索完成"
        if business in {"chat", "responses", "messages"}:
            return "文本响应完成"
        if business == "account":
            return summary_text or "账号操作完成"
        return "调用完成"
    return summary_text or public_error or "调用完成"


def _build_presentation(
    summary: Mapping[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    outcome = _clean(summary.get("outcome"))
    log_type = _clean(summary.get("type"))
    business = _clean(summary.get("business"))
    task_count = _int(summary.get("image_requested_count"))
    attempt_count = _int(summary.get("attempt_count"))
    caller = _clean(summary.get("key_name") or summary.get("key_id"))
    execution_parts = [
        f"{task_count} 个任务" if task_count > 0 else "",
        f"{attempt_count} 次尝试" if attempt_count > 0 else "",
    ]
    execution_primary = " · ".join(part for part in execution_parts if part) or caller or "-"
    show_failure_details = outcome in {"failed", "rate_limited"}
    diagnostics = " · ".join(
        part
        for part in (
            f"HTTP {_int(summary.get('status_code'))}"
            if show_failure_details and _int(summary.get("status_code")) > 0
            else "",
            _clean(summary.get("error_code")) if show_failure_details else "",
        )
        if part
    )
    summary_text = _clean(summary.get("summary"))
    if outcome == "text_review" and summary_text:
        summary_text = summary_text.replace("流式调用失败", "文本").replace("调用失败", "文本")
    if not summary_text:
        summary_text = _clean(summary.get("public_error"))

    duration_ms = _int(summary.get("duration_ms"))
    return {
        "request": {
            "kind": "" if log_type == "account" else _business_label(business, log_type),
            "primary": _clean(summary.get("model")) or _type_label(log_type),
            "secondary": _clean(summary.get("endpoint")),
        },
        "execution": {
            "primary": execution_primary,
            "secondary": caller if task_count > 0 else "",
        },
        "status": _status_presentation(summary),
        "result": {
            "text": _result_text(summary),
            "diagnostics": diagnostics,
        },
        "summary_text": summary_text,
        "duration": {
            "text": _format_duration(duration_ms),
            "breakdown": _duration_breakdown(attempts),
            "tone": (
                "danger"
                if outcome == "failed"
                else "warning"
                if duration_ms >= 60000
                else "success"
            ),
        },
        "is_failure": outcome == "failed",
    }


def _attempt_group_presentations(
    attempts: list[dict[str, Any]],
    requested_count: int,
) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for attempt in attempts:
        slot = max(1, _int(attempt.get("slot")))
        grouped.setdefault(slot, []).append(attempt)

    result: list[dict[str, Any]] = []
    slot_count = max(requested_count, max(grouped, default=0))
    for slot in range(1, slot_count + 1):
        slot_attempts = grouped.get(slot, [])
        attempt_count = len(slot_attempts)
        switch_count = sum(1 for attempt in slot_attempts if attempt.get("switched_account") is True)
        succeeded = any(_clean(attempt.get("result_status")) == "success" for attempt in slot_attempts)
        delivery_failed = any(
            _clean(attempt.get("result_status")) == "generated_but_delivery_failed"
            for attempt in slot_attempts
        )
        if succeeded:
            status = {"label": "成功", "tone": "success"}
        elif delivery_failed:
            status = {"label": "生成成功", "tone": "warning"}
        elif slot_attempts:
            status = {"label": "失败", "tone": "danger"}
        else:
            status = {"label": "未记录", "tone": "muted"}
        result.append(
            {
                "slot": slot,
                "slot_label": f"图片 {slot}",
                "attempt_count": attempt_count,
                "attempt_text": f"{attempt_count} 次尝试",
                "switch_count": switch_count,
                "switch_text": f"切换 {switch_count} 次" if switch_count else "",
                "status": status,
            }
        )
    return result


def _build_detail_presentation(
    summary: Mapping[str, Any],
    detail: Mapping[str, Any],
    monitor: Mapping[str, Any],
    attempts: list[dict[str, Any]],
    timings: Mapping[str, int],
    image_count: int,
) -> dict[str, Any]:
    requested_count = _int(summary.get("image_requested_count"))
    has_delivery_failure = any(
        _clean(attempt.get("result_status")) == "generated_but_delivery_failed"
        for attempt in attempts
    )
    has_attempt_breakdown = (
        bool(attempts)
        and (
            len(attempts) > 1
            or requested_count > 1
            or has_delivery_failure
        )
    )
    identity_lives_in_attempts = len(attempts) > 1 or requested_count > 1
    core = build_request_detail_core(
        summary,
        detail,
        monitor,
        timings,
        events=monitor.get("events"),
        image_count=image_count,
        request_shape=detail.get("request_shape"),
        hide_account_identity=identity_lives_in_attempts,
        suppress_timeline=has_attempt_breakdown,
    )
    return {
        **core,
        "has_attempt_breakdown": has_attempt_breakdown,
        "attempt_groups": (
            _attempt_group_presentations(attempts, requested_count)
            if has_attempt_breakdown
            else []
        ),
    }


def build_call_summary(item: Mapping[str, Any], *, error_limit: int = _SUMMARY_ERROR_LIMIT) -> dict[str, Any]:
    requested, succeeded, failed, result_status = call_image_counts(item)
    attempts = _attempt_items(item)
    switch_count = call_switch_count(item)
    outcome = call_outcome(item)
    business = call_business_kind(item)
    display_status = _clean(_value(item, "status"))
    if business == "account":
        display_status = _normalize_account_status(display_status)
    public_error = _first_text(item, ("public_error", "error"))
    if error_limit > 0 and len(public_error) > error_limit:
        public_error = f"{public_error[:error_limit]}..."
    image_urls = call_image_urls(item)
    summary = {
        "id": _clean(item.get("id") or _value(item, "call_id")),
        "time": _clean(item.get("time") or _value(item, "started_at")),
        "type": _clean(item.get("type") or "call"),
        "summary": _clean(item.get("summary")),
        "business": business,
        "outcome": outcome,
        "display_status": display_status,
        "endpoint": _clean(_value(item, "endpoint")),
        "model": _clean(_value(item, "model")),
        "started_at": _clean(_value(item, "started_at")),
        "ended_at": _clean(_value(item, "ended_at")),
        "duration_ms": _duration_ms(item),
        "key_id": _clean(_value(item, "key_id")),
        "key_name": _clean(_value(item, "key_name")),
        "role": _clean(_value(item, "role")),
        "account_email": _clean(_value(item, "account_email")),
        "conversation_id": _clean(_value(item, "conversation_id")),
        "status_code": _int(_value(item, "status_code")),
        "error_code": _clean(_value(item, "error_code", _value(item, "failure_code"))),
        "public_error": public_error,
        "image_requested_count": requested,
        "image_succeeded_count": succeeded,
        "image_failed_count": failed,
        "image_result_status": result_status,
        "preview_image_url": image_urls[0] if image_urls else "",
        "attempt_count": len(attempts),
        "switch_count": switch_count,
        "recovered_after_switch": switch_count > 0 and outcome in {"success", "partial_success"},
    }
    summary["presentation"] = _build_presentation(summary, attempts)
    return summary


def build_call_detail(item: Mapping[str, Any]) -> dict[str, Any]:
    detail = _detail(item)
    monitor = _record(detail.get("monitor"))
    summary = build_call_summary(item)
    attempts = [build_attempt_summary(value) for value in _attempt_items(item)]
    timings = call_timings_ms(item)
    image_urls = call_image_urls(item)
    return {
        **summary,
        "request_text": _clean(detail.get("request_text")),
        "request_text_full": _clean(detail.get("request_text_full")),
        "request_text_truncated": _bool(detail.get("request_text_truncated")),
        "request_shape": _record(detail.get("request_shape")),
        "request_meta": _record(detail.get("request_meta")),
        "upstream_error": _clean(
            detail.get("upstream_error")
            or detail.get("raw_upstream_error")
            or monitor.get("upstream_error")
            or monitor.get("raw_upstream_error")
        ),
        "upstream_text": _clean(
            detail.get("upstream_text")
            or detail.get("raw_upstream_message")
            or detail.get("upstream_message")
            or detail.get("upstream_message_preview")
            or detail.get("upstream_preview")
            or monitor.get("upstream_text")
            or monitor.get("raw_upstream_message")
            or monitor.get("upstream_message")
            or monitor.get("upstream_message_preview")
            or monitor.get("upstream_preview")
        ),
        "image_urls": image_urls,
        "attempts": attempts,
        "timings_ms": timings,
        "perf": _record(detail.get("perf")),
        "metrics": _record(detail.get("metrics")),
        "monitor": monitor,
        "detail_presentation": _build_detail_presentation(
            summary,
            detail,
            monitor,
            attempts,
            timings,
            len(image_urls),
        ),
        "raw_detail": detail,
    }
