from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.request_detail_view import request_proxy_source_label, request_status_presentation


MONITOR_SCHEMA_VERSION = 1

ENTRY_QUEUE_METRIC_KEYS = ("handler_queue_ms", "stream_first_queue_ms")

DIGEST_METRIC_PAIRS = (
    ("等待入口", "handler_queue_ms"),
    ("首包", "stream_first_queue_ms"),
    ("等待账号", "account_wait_ms"),
    ("等待出口", "egress_wait_ms"),
    ("出口租约", "egress_acquire_ms"),
    ("上传", "upload_ms"),
    ("初始化", "bootstrap_ms"),
    ("令牌", "requirements_ms"),
    ("准备", "prepare_conversation_ms"),
    ("启动", "generation_start_ms"),
    ("HTTP首包", "http_ttfb_ms"),
    ("HTTP等待", "http_wait_ms"),
    ("SSE首事件", "sse_first_event_ms"),
    ("SSE空窗", "sse_max_gap_ms"),
    ("上游生成", "conversation_stream_ms"),
    ("上游断流", "stream_error_ms"),
    ("等待结果", "poll_wait_ms"),
    ("查询结果", "poll_request_ms"),
    ("结果处理", "resolve_ms"),
    ("下载", "download_ms"),
)

SLOW_METRIC_PAIRS = (
    ("handler_queue_ms", "等待入口"),
    ("stream_first_queue_ms", "首包"),
    ("account_wait_ms", "等待账号"),
    ("egress_wait_ms", "等待出口"),
    ("egress_acquire_ms", "出口租约"),
    ("upload_ms", "上传"),
    ("bootstrap_ms", "初始化"),
    ("requirements_ms", "令牌"),
    ("prepare_conversation_ms", "准备"),
    ("generation_start_ms", "启动"),
    ("http_dns_ms", "HTTP DNS"),
    ("http_tcp_ms", "HTTP TCP"),
    ("http_tls_ms", "HTTP TLS"),
    ("http_wait_ms", "HTTP 等待"),
    ("http_ttfb_ms", "HTTP 首包"),
    ("sse_first_event_ms", "SSE 首事件"),
    ("sse_max_gap_ms", "SSE 最大空窗"),
    ("sse_last_gap_ms", "SSE 收尾空窗"),
    ("conversation_stream_ms", "上游生成"),
    ("stream_error_ms", "上游断流"),
    ("poll_wait_ms", "等待结果"),
    ("poll_request_ms", "查询结果"),
    ("resolve_ms", "结果处理"),
    ("download_ms", "下载"),
    ("response_ms", "响应整理"),
)

EVENT_METRIC_PAIRS = (
    ("等待入口", "handler_queue_ms"),
    ("首包", "stream_first_queue_ms"),
    ("等待账号", "account_wait_ms"),
    ("等待出口", "egress_wait_ms"),
    ("上传", "upload_ms"),
    ("初始化", "bootstrap_ms"),
    ("令牌", "requirements_ms"),
    ("准备", "prepare_conversation_ms"),
    ("启动", "generation_start_ms"),
    ("HTTP首包", "http_ttfb_ms"),
    ("HTTP等待", "http_wait_ms"),
    ("SSE首事件", "sse_first_event_ms"),
    ("SSE空窗", "sse_max_gap_ms"),
    ("上游生成", "conversation_stream_ms"),
    ("上游断流", "stream_error_ms"),
    ("等待结果", "poll_wait_ms"),
    ("查询结果", "poll_request_ms"),
    ("结果处理", "resolve_ms"),
    ("下载", "download_ms"),
    ("响应整理", "response_ms"),
)

LINEAR_STAGE_KEYS = (
    "account_wait_ms",
    "egress_wait_ms",
    "upload_ms",
    "bootstrap_ms",
    "requirements_ms",
    "prepare_conversation_ms",
    "generation_start_ms",
    "conversation_stream_ms",
    "stream_error_ms",
    "poll_wait_ms",
    "poll_request_ms",
    "resolve_ms",
    "download_ms",
    "response_ms",
)

RECORD_FIELDS = {
    "call_id",
    "endpoint",
    "model",
    "summary",
    "role",
    "key_name",
    "status",
    "outcome",
    "stage",
    "stage_label",
    "started_at",
    "ended_at",
    "updated_at",
    "elapsed_ms",
    "stage_elapsed_ms",
    "duration_ms",
    "account_email",
    "previous_account_email",
    "image_account_attempt",
    "image_account_max_attempts",
    "image_account_switch_count",
    "attempt_count",
    "switch_count",
    "image_requested_count",
    "image_succeeded_count",
    "image_failed_count",
    "image_result_status",
    "recovered_after_switch",
    "public_error",
    "conversation_id",
    "error",
    "raw_error",
    "upstream_error",
    "upstream_message",
    "url_count",
    "proxy_source",
    "proxy_hash",
    "egress_key",
    "egress_label",
    "proxy_group_id",
    "proxy_node_id",
    "proxy_node_name",
    "image_egress_limit",
    "has_proxy",
    "egress_mode",
    "local_reason",
    "failure_code",
    "failure_scope",
    "failure_capability",
    "failure_retryable",
    "failure_account_failure",
    "failure_retry_after",
    "status_code",
    "error_type",
    "account_failure",
    "switched_account",
}

IMAGE_FIELDS = {
    "index",
    "total",
    "account_email",
    "previous_account_email",
    "account_attempt",
    "max_account_attempts",
    "account_switch_count",
    "stage",
    "stage_label",
    "updated_at",
    "status",
    "returned_result",
    "returned_message",
    "proxy_source",
    "proxy_hash",
    "egress_key",
    "egress_label",
    "proxy_group_id",
    "proxy_node_id",
    "proxy_node_name",
    "image_egress_limit",
    "has_proxy",
    "egress_mode",
    "local_reason",
    "failure_code",
    "failure_scope",
    "failure_capability",
    "failure_retryable",
    "failure_account_failure",
    "failure_retry_after",
    "status_code",
    "error_type",
    "public_error",
    "account_failure",
    "switched_account",
    "error",
    "raw_error",
    "upstream_error",
    "upstream_message",
}

EVENT_FIELDS = {
    "time",
    "call_id",
    "event",
    "label",
    "model",
    "index",
    "total",
    "attempt",
    "account_email",
    "previous_account_email",
    "account_switch_count",
    "max_account_attempts",
    "status",
    "sse_event_count",
    "proxy_source",
    "proxy_hash",
    "egress_key",
    "egress_label",
    "proxy_group_id",
    "proxy_node_id",
    "proxy_node_name",
    "image_egress_limit",
    "egress_mode",
    "has_proxy",
    "local_reason",
    "failure_code",
    "failure_scope",
    "failure_capability",
    "failure_retryable",
    "failure_account_failure",
    "failure_retry_after",
    "status_code",
    "error_type",
    "public_error",
    "account_failure",
    "switched_account",
    "error",
    "raw_error",
    "upstream_error",
    "upstream_message",
    *(key for _, key in EVENT_METRIC_PAIRS),
    "http_dns_ms",
    "http_tcp_ms",
    "http_tls_ms",
    "http_total_ms",
    "sse_last_gap_ms",
    "sse_stream_ms",
    "stream_ms",
    "total_ms",
}

INTEGER_FIELDS = {
    "elapsed_ms",
    "stage_elapsed_ms",
    "duration_ms",
    "image_account_attempt",
    "image_account_max_attempts",
    "image_account_switch_count",
    "attempt_count",
    "switch_count",
    "image_requested_count",
    "image_succeeded_count",
    "image_failed_count",
    "url_count",
    "image_egress_limit",
    "failure_retry_after",
    "status_code",
    "index",
    "total",
    "account_attempt",
    "max_account_attempts",
    "account_switch_count",
    "attempt",
    "sse_event_count",
}

BOOLEAN_FIELDS = {
    "recovered_after_switch",
    "has_proxy",
    "failure_retryable",
    "failure_account_failure",
    "account_failure",
    "switched_account",
    "returned_result",
    "returned_message",
}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int(value: object) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _text(value: object) -> str:
    return str(value or "").strip()


def _format_ms(value: object) -> str:
    ms = _int(value)
    if ms <= 0:
        return "-"
    if ms >= 60_000:
        return f"{ms / 60_000:.1f}m"
    if ms >= 1_000:
        return f"{ms / 1_000:.1f}s"
    return f"{ms}ms"


def _metric_map(value: object) -> dict[str, int]:
    return {
        str(key): _int(metric)
        for key, metric in _mapping(value).items()
        if str(key).endswith("_ms")
    }


def _canonical_timings(record: Mapping[str, Any]) -> dict[str, int]:
    metrics = _metric_map(record.get("metrics"))
    perf = _metric_map(record.get("perf"))
    return {
        key: max(metrics.get(key, 0), perf.get(key, 0))
        for key in sorted(metrics.keys() | perf.keys())
    }


def _copy_fields(source: Mapping[str, Any], fields: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in fields:
        if key not in source or source[key] is None:
            continue
        value = source[key]
        if key in INTEGER_FIELDS:
            result[key] = _int(value)
        elif key in BOOLEAN_FIELDS:
            result[key] = bool(value)
        else:
            result[key] = str(value)
    return result


def _build_egress(record: Mapping[str, Any]) -> dict[str, Any]:
    source = str(record.get("proxy_source") or "direct").strip() or "direct"
    source_label = request_proxy_source_label(source)
    group_id = str(record.get("proxy_group_id") or "").strip()
    node_name = str(record.get("proxy_node_name") or "").strip()
    node_id = str(record.get("proxy_node_id") or "").strip()
    node_label = "/".join(value for value in (group_id, node_name or node_id) if value)
    raw_label = str(record.get("egress_label") or "").strip()
    label = node_label
    if not label and raw_label not in {"", "direct", source, f"{source}_profile"} and not raw_label.startswith("proxy:"):
        label = raw_label
    proxy_hash = str(record.get("proxy_hash") or "").strip()
    display = f"{source_label} {label}" if label else source_label
    if not label and proxy_hash and proxy_hash != "direct":
        display = f"{source_label} {proxy_hash}"
    return {
        "source": source,
        "source_label": source_label,
        "label": label,
        "hash": proxy_hash,
        "display": display,
        "key": str(record.get("egress_key") or ""),
        "mode": str(record.get("egress_mode") or ""),
        "group_id": group_id,
        "node_id": node_id,
        "node_name": node_name,
        "has_proxy": bool(record.get("has_proxy")) if "has_proxy" in record else None,
    }


def _build_account_attempt(record: Mapping[str, Any]) -> dict[str, Any]:
    attempt = _int(record.get("image_account_attempt"))
    max_attempts = max(attempt, _int(record.get("image_account_max_attempts")))
    switch_count = _int(record.get("image_account_switch_count"))
    images = _mapping(record.get("images"))
    image_count = max((_int(_mapping(item).get("total")) for item in images.values()), default=0)
    parts: list[str] = []
    if attempt and max_attempts:
        prefix = "最高第 " if image_count > 1 else "第 "
        parts.append(f"{prefix}{attempt}/{max_attempts} 次")
    if attempt or max_attempts or switch_count:
        parts.append(f"已切换 {switch_count} 次" if switch_count else "未切换")
    return {
        "attempt": attempt,
        "max_attempts": max_attempts,
        "switch_count": switch_count,
        "image_count": image_count,
        "display": " · ".join(parts),
    }


def _row_duration(record: Mapping[str, Any]) -> int:
    return max(_int(record.get("duration_ms")), _int(record.get("elapsed_ms")))


def _tracked_duration(timings: Mapping[str, int]) -> int:
    queue = sum(_int(timings.get(key)) for key in ENTRY_QUEUE_METRIC_KEYS)
    linear = sum(_int(timings.get(key)) for key in LINEAR_STAGE_KEYS)
    wrapped = max(_int(timings.get("total_ms")), _int(timings.get("stream_ms")), linear)
    return queue + wrapped


def _slow_metrics(record: Mapping[str, Any], timings: Mapping[str, int]) -> tuple[list[dict[str, Any]], int, int]:
    duration = _row_duration(record)
    tracked = _tracked_duration(timings)
    untracked = max(0, duration - tracked)
    items = [
        {
            "key": key,
            "label": label,
            "value_ms": value,
            "value_text": _format_ms(value),
            "important": value >= 10_000,
        }
        for key, label in SLOW_METRIC_PAIRS
        if (value := _int(timings.get(key))) > 0
    ]
    if untracked >= 1_000:
        items.append(
            {
                "key": "untracked_ms",
                "label": "未标记",
                "value_ms": untracked,
                "value_text": _format_ms(untracked),
                "important": untracked >= 10_000,
            }
        )
    if not items and duration > 0:
        items.append(
            {
                "key": "duration_ms",
                "label": "总耗时",
                "value_ms": duration,
                "value_text": _format_ms(duration),
                "important": duration >= 10_000,
            }
        )
    return items, tracked, untracked


def _slow_reason(items: list[dict[str, Any]]) -> tuple[str, str]:
    candidates = sorted(
        (item for item in items if item["key"] not in {"stream_ms", "total_ms", "duration_ms"}),
        key=lambda item: item["value_ms"],
        reverse=True,
    )
    if not candidates or candidates[0]["value_ms"] < 1_000:
        return "", ""
    top = candidates[0]
    key = str(top["key"])
    label = str(top["label"])
    value = str(top["value_text"])
    if key == "untracked_ms":
        return "instrumentation_gap", f"仍有 {value} 没有落到具体阶段，说明这段链路还缺埋点。"
    if key == "poll_wait_ms":
        return "image_poll_wait", "主要卡在等待图片结果，通常是 ChatGPT 图片任务尚未完成或轮询退避。"
    if key == "poll_request_ms":
        return "image_poll_request", "主要卡在查询图片结果，通常是任务或会话查询接口响应较慢。"
    if key == "resolve_ms":
        return "image_result_resolve", "主要卡在结果处理，通常是图片文件 ID 转换下载地址较慢。"
    if key == "conversation_stream_ms":
        return "upstream_generation", "主要卡在上游生成中，通常是 ChatGPT 生成阶段耗时。"
    if key == "stream_error_ms":
        return "upstream_stream_error", "主要卡在上游断流，通常是 HTTP2/SSE、代理或上游边缘节点中断。"
    if key in {"http_ttfb_ms", "http_wait_ms"}:
        return "http_first_byte", "主要卡在 HTTP 首包，通常是代理出口、上游边缘节点或请求排队变慢。"
    if key in {"http_dns_ms", "http_tcp_ms", "http_tls_ms"}:
        return "http_connect", f"主要卡在 HTTP 建连阶段：{label} {value}。"
    if key == "sse_first_event_ms":
        return "sse_first_event", "主要卡在 SSE 首事件，说明连接已建立但上游长时间没有返回首个事件。"
    if key in {"sse_max_gap_ms", "sse_last_gap_ms"}:
        return "sse_gap", "主要卡在 SSE 空窗，说明上游流中间长时间没有新事件。"
    if key == "egress_wait_ms":
        return "egress_wait", "主要卡在等待出口，通常是代理组、默认出口、资源代理或出站会话准备变慢。"
    if key in {"upload_ms", "bootstrap_ms", "requirements_ms", "prepare_conversation_ms", "generation_start_ms"}:
        return "upstream_prepare", f"主要卡在上游准备阶段：{label} {value}。"
    if key == "account_wait_ms":
        return "account_wait", "主要卡在等待账号，通常是可用账号不足或账号并发被占满。"
    if key in set(ENTRY_QUEUE_METRIC_KEYS):
        return "entry_queue", "主要卡在等待入口，通常是后端同步线程容量不足；可通过环境变量 CHATGPT2API_THREAD_TOKENS 调整。"
    return "primary_metric", f"主要耗时：{label} {value}。"


def _status_presentation(record: Mapping[str, Any]) -> tuple[str, str]:
    value = str(record.get("outcome") or record.get("status") or "").lower()
    presentation = request_status_presentation(value, fallback=value or "-")
    return presentation["label"], presentation["tone"]


def _metric_digest(record: Mapping[str, Any], timings: Mapping[str, int]) -> str:
    parts = sorted(
        (
            (value, f"{label} {_format_ms(value)}")
            for label, key in DIGEST_METRIC_PAIRS
            if (value := _int(timings.get(key))) > 0
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    texts = [text for _, text in parts]
    if str(record.get("status") or "").lower() == "running" and _int(record.get("stage_elapsed_ms")) > 0:
        texts.insert(0, f"当前阶段 {_format_ms(record.get('stage_elapsed_ms'))}")
    return " / ".join(texts[:4]) or "-"


def _project_image(value: object) -> dict[str, Any]:
    image = _mapping(value)
    result = _copy_fields(image, IMAGE_FIELDS)
    result["metrics"] = _metric_map(image.get("metrics"))
    return result


def _project_event(value: object) -> dict[str, Any]:
    event = _mapping(value)
    result = _copy_fields(event, EVENT_FIELDS)
    result.setdefault("time", "")
    result.setdefault("call_id", "")
    result.setdefault("event", "")
    result["label"] = _text(result.get("label")) or _text(result.get("event"))
    parts = [
        f"{label} {_format_ms(event.get(key))}"
        for label, key in EVENT_METRIC_PAIRS
        if _int(event.get(key)) > 0
    ]
    result["timing_text"] = " / ".join(parts[:3]) or "-"
    account_email = _text(event.get("account_email"))
    previous_account_email = _text(event.get("previous_account_email"))
    account_text = (
        f"{previous_account_email} → {account_email}"
        if previous_account_email and account_email
        else account_email
    )
    result["detail_text"] = " · ".join(
        part
        for part in (
            "已切换账号" if bool(event.get("switched_account")) else "",
            account_text,
            _text(event.get("public_error")) or _text(event.get("error")),
        )
        if part
    )
    return result


def _project_record(value: object, *, include_detail: bool = False) -> dict[str, Any]:
    record = _mapping(value)
    result = _copy_fields(record, RECORD_FIELDS)
    result.setdefault("call_id", "")
    metrics = _metric_map(record.get("metrics"))
    perf = _metric_map(record.get("perf"))
    timings = _canonical_timings(record)
    result["metrics"] = metrics
    result["perf"] = perf
    result["timings_ms"] = timings
    result["images"] = {
        str(key): _project_image(image)
        for key, image in _mapping(record.get("images")).items()
        if isinstance(image, Mapping)
    }
    egress = _build_egress(record)
    account_attempt = _build_account_attempt(record)
    slow_metrics, tracked, untracked = _slow_metrics(record, timings)
    reason_code, reason = _slow_reason(slow_metrics)
    status_label, status_tone = _status_presentation(record)
    stage_text = _text(record.get("stage_label")) or _text(record.get("stage"))
    if not stage_text:
        stage_text = "运行中" if _text(record.get("status")).lower() == "running" else status_label
    result["egress"] = egress
    result["account_attempt"] = account_attempt
    result["presentation"] = {
        "status_label": status_label,
        "status_tone": status_tone,
        "stage_text": stage_text,
        "error_text": _text(record.get("public_error")) or _text(record.get("error")),
        "duration_text": _format_ms(_row_duration(record)),
        "metric_digest": _metric_digest(record, timings),
        "egress_text": egress["display"],
        "account_attempt_text": account_attempt["display"],
        "account_egress_text": (
            f"账号 {_format_ms(timings.get('account_wait_ms'))} / "
            f"出口 {_format_ms(timings.get('egress_wait_ms'))}"
        ),
        "tracked_duration_ms": tracked,
        "untracked_duration_ms": untracked,
        "slow_metrics": slow_metrics,
        "slow_reason_code": reason_code,
        "slow_reason": reason,
    }
    if include_detail:
        raw_events = record.get("events") if isinstance(record.get("events"), list) else []
        result["events"] = [_project_event(event) for event in raw_events]
    return result


def _count_map(value: object) -> dict[str, int]:
    return {str(key): _int(count) for key, count in _mapping(value).items()}


def _project_summary(value: object) -> dict[str, Any]:
    summary = _mapping(value)
    success = _int(summary.get("success"))
    failed = _int(summary.get("failed"))
    rate_limited = _int(summary.get("rate_limited"))
    measured = success + failed + rate_limited
    switch_requests = _int(summary.get("account_switch_requests"))
    switches = _int(summary.get("account_switches"))
    switch_success = _int(summary.get("account_switch_success"))
    metric_p95 = _metric_map(summary.get("metric_p95"))
    active_by_egress = _count_map(summary.get("active_by_egress"))
    slow = _mapping(summary.get("slow_counts"))
    success_rate = _float(summary.get("success_rate"))
    if "success_rate" not in summary:
        success_rate = round(success * 100 / measured, 1) if measured else 0.0
    recovery_rate = _float(summary.get("account_switch_recovery_rate"))
    if "account_switch_recovery_rate" not in summary:
        recovery_rate = round(switch_success * 100 / switch_requests, 1) if switch_requests else 0.0
    return {
        "active": _int(summary.get("active")),
        "completed": _int(summary.get("completed")),
        "success": success,
        "partial_success": _int(summary.get("partial_success")),
        "failed": failed,
        "rate_limited": rate_limited,
        "text_review": _int(summary.get("text_review")),
        "measured": measured,
        "success_rate": success_rate,
        "account_switch_requests": switch_requests,
        "account_switches": switches,
        "account_switch_success": switch_success,
        "account_switch_recovery_rate": recovery_rate,
        "switch_unrecovered": max(0, switch_requests - switch_success),
        "switch_average": round(switches / switch_requests, 1) if switch_requests else 0.0,
        "stream_error_requests": _int(summary.get("stream_error_requests")),
        "avg_duration_ms": _int(summary.get("avg_duration_ms")),
        "p95_duration_ms": _int(summary.get("p95_duration_ms")),
        "entry_queue_p95_ms": max((_int(metric_p95.get(key)) for key in ENTRY_QUEUE_METRIC_KEYS), default=0),
        "active_egress_count": len(active_by_egress),
        "metric_p95": metric_p95,
        "slow_counts": {
            "handler_queue": _int(slow.get("handler_queue")),
            "stream_first_queue": _int(slow.get("stream_first_queue")),
            "account_wait": _int(slow.get("account_wait")),
            "egress_wait": _int(slow.get("egress_wait")),
            "total_over_120s": _int(slow.get("total_over_120s")),
            "local_reject_or_busy": _int(slow.get("local_reject_or_busy")),
        },
        "by_model": _count_map(summary.get("by_model")),
        "active_by_model": _count_map(summary.get("active_by_model")),
        "active_by_egress": active_by_egress,
        "active_by_stage": _count_map(summary.get("active_by_stage")),
    }


def _active_egress_meta(summary: Mapping[str, Any]) -> str:
    items = list(_mapping(summary.get("active_by_egress")).items())
    if not items:
        return "暂无活跃出口"
    parts = []
    for key, count in items[:2]:
        source, separator, detail = str(key).partition(":")
        label = request_proxy_source_label(source)
        parts.append(f"{label}{f' {detail}' if separator else ''} {_int(count)}")
    return " / ".join(parts)


def _diagnostic_item(key: str, label: str, value: int | float | str, meta: str, tone: str = "muted") -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "meta": meta, "tone": tone}


def _build_diagnostic_groups(
    summary: Mapping[str, Any],
    thread_tokens: int,
    completed_window_text: str,
) -> list[dict[str, Any]]:
    p95 = _mapping(summary.get("metric_p95"))
    slow = _mapping(summary.get("slow_counts"))
    local_busy = _int(slow.get("local_reject_or_busy"))
    switch_requests = _int(summary.get("account_switch_requests"))
    switch_count = _int(summary.get("account_switches"))
    switch_success = _int(summary.get("account_switch_success"))
    switch_unrecovered = _int(summary.get("switch_unrecovered"))
    active_egress_meta = _active_egress_meta(summary)
    return [
        {
            "key": "overview",
            "title": "实时概览",
            "meta": "窗口与结果",
            "items": [
                _diagnostic_item("active", "当前并发", _int(summary.get("active")), f"线程容量 {thread_tokens}"),
                _diagnostic_item("completed", "完成窗口", _int(summary.get("completed")), completed_window_text),
                _diagnostic_item("success", "成功数", _int(summary.get("success")), "窗口内成功", "success"),
                _diagnostic_item("failed", "失败数", _int(summary.get("failed")), "窗口内失败", "danger" if _int(summary.get("failed")) else "muted"),
                _diagnostic_item("text_review", "文本数", _int(summary.get("text_review")), "返回文本，不计失败", "warning"),
                _diagnostic_item("success_rate", "成功率", f"{summary.get('success_rate', 0)}%", "不含文本", "success"),
                _diagnostic_item("slow_total", "慢请求", _int(slow.get("total_over_120s")), "总耗时超过 120 秒", "warning" if _int(slow.get("total_over_120s")) else "muted"),
                _diagnostic_item("rate_limited", "限流数", _int(summary.get("rate_limited")), "窗口内限流", "warning"),
            ],
        },
        {
            "key": "entry_egress",
            "title": "入口与出口",
            "meta": "本地线程、请求入口、代理出口",
            "items": [
                _diagnostic_item("thread_capacity", "线程容量", thread_tokens, "入口执行上限"),
                _diagnostic_item("handler_queue_ms", "入口排队 P95", _format_ms(p95.get("handler_queue_ms")), f"线程容量 {thread_tokens} · 慢 {_int(slow.get('handler_queue'))}", "info"),
                _diagnostic_item("stream_first_queue_ms", "首包排队 P95", _format_ms(p95.get("stream_first_queue_ms")), f"慢 {_int(slow.get('stream_first_queue'))}", "info"),
                _diagnostic_item("egress_wait_ms", "出口等待 P95", _format_ms(p95.get("egress_wait_ms")), active_egress_meta, "info"),
                _diagnostic_item("egress_acquire_ms", "出口租约 P95", _format_ms(p95.get("egress_acquire_ms")), "获取图片出口", "info"),
                _diagnostic_item("active_egress", "活跃出口", _int(summary.get("active_egress_count")), active_egress_meta, "info"),
                _diagnostic_item("egress_wait_slow", "出口等待慢请求", _int(slow.get("egress_wait")), "等待超过 1 秒", "warning" if _int(slow.get("egress_wait")) else "muted"),
                _diagnostic_item("local_busy", "本地拒绝/繁忙", local_busy, "无号 / 并发 / 策略", "danger" if local_busy else "muted"),
            ],
        },
        {
            "key": "account_switch",
            "title": "账号与切换",
            "meta": "账号等待、切换动作、恢复结果",
            "items": [
                _diagnostic_item("account_wait_ms", "账号等待 P95", _format_ms(p95.get("account_wait_ms")), "账号池筛选", "info"),
                _diagnostic_item("account_wait_slow", "账号等待慢请求", _int(slow.get("account_wait")), "等待超过 5 秒", "warning" if _int(slow.get("account_wait")) else "muted"),
                _diagnostic_item("account_switch_requests", "切号请求", switch_requests, "发生过账号切换", "warning" if switch_requests else "muted"),
                _diagnostic_item("account_switches", "切换次数", switch_count, "窗口内实际切换", "warning" if switch_count else "muted"),
                _diagnostic_item("account_switch_success", "切号后成功", switch_success, "已恢复请求" if switch_requests else "暂无切号请求", "success" if switch_success else "muted"),
                _diagnostic_item("account_switch_recovery_rate", "切号恢复率", f"{summary.get('account_switch_recovery_rate', 0)}%", "切号后成功 / 切号请求", "success" if switch_success else "muted"),
                _diagnostic_item("account_switch_unrecovered", "切号未恢复", switch_unrecovered, "切号后仍失败", "danger" if switch_unrecovered else "muted"),
                _diagnostic_item("account_switch_average", "平均切换", summary.get("switch_average", 0), "每个切号请求", "warning" if switch_count else "muted"),
            ],
        },
        {
            "key": "upstream_prepare",
            "title": "上游准备",
            "meta": "上传、令牌、会话、建连",
            "items": [
                _diagnostic_item("upload_ms", "图片上传", _format_ms(p95.get("upload_ms")), "参考图上传"),
                _diagnostic_item("bootstrap_ms", "上游初始化", _format_ms(p95.get("bootstrap_ms")), "ChatGPT 会话"),
                _diagnostic_item("requirements_ms", "令牌获取", _format_ms(p95.get("requirements_ms")), "requirements / token"),
                _diagnostic_item("prepare_conversation_ms", "会话准备", _format_ms(p95.get("prepare_conversation_ms")), "准备图片会话"),
                _diagnostic_item("generation_start_ms", "启动生成", _format_ms(p95.get("generation_start_ms")), "提交上游请求"),
                _diagnostic_item("http_dns_ms", "DNS 解析", _format_ms(p95.get("http_dns_ms")), "HTTP DNS P95", "info"),
                _diagnostic_item("http_tcp_ms", "TCP 连接", _format_ms(p95.get("http_tcp_ms")), "HTTP TCP P95", "info"),
                _diagnostic_item("http_tls_ms", "TLS 握手", _format_ms(p95.get("http_tls_ms")), "HTTP TLS P95", "info"),
            ],
        },
        {
            "key": "generation_transport",
            "title": "生成与传输",
            "meta": "HTTP、SSE、上游生成、断流",
            "items": [
                _diagnostic_item("http_wait_ms", "HTTP 等待", _format_ms(p95.get("http_wait_ms")), "发出请求到首包", "info"),
                _diagnostic_item("http_ttfb_ms", "HTTP 首包", _format_ms(p95.get("http_ttfb_ms")), "请求开始到首包", "info"),
                _diagnostic_item("sse_first_event_ms", "SSE 首事件", _format_ms(p95.get("sse_first_event_ms")), "连接后首个事件", "info"),
                _diagnostic_item("sse_max_gap_ms", "SSE 最大空窗", _format_ms(p95.get("sse_max_gap_ms")), "两次事件最大间隔", "info"),
                _diagnostic_item("sse_last_gap_ms", "SSE 收尾空窗", _format_ms(p95.get("sse_last_gap_ms")), "最后事件到结束", "info"),
                _diagnostic_item("conversation_stream_ms", "上游生成", _format_ms(p95.get("conversation_stream_ms")), "会话流响应", "success"),
                _diagnostic_item("stream_error_requests", "断流请求", _int(summary.get("stream_error_requests")), "窗口内发生断流", "danger" if _int(summary.get("stream_error_requests")) else "muted"),
                _diagnostic_item("stream_error_ms", "断流耗时 P95", _format_ms(p95.get("stream_error_ms")), "HTTP2 / SSE"),
            ],
        },
        {
            "key": "result_delivery",
            "title": "结果与交付",
            "meta": "总耗时、轮询、解析、下载",
            "items": [
                _diagnostic_item("average", "平均总耗时", _format_ms(summary.get("avg_duration_ms")), "窗口均值", "info"),
                _diagnostic_item("p95", "P95 总耗时", _format_ms(summary.get("p95_duration_ms")), "慢请求参考", "info"),
                _diagnostic_item("poll_wait_ms", "等待结果", _format_ms(p95.get("poll_wait_ms")), "间隔 / 退避", "warning"),
                _diagnostic_item("poll_request_ms", "查询结果", _format_ms(p95.get("poll_request_ms")), "task / conversation", "info"),
                _diagnostic_item("resolve_ms", "结果处理", _format_ms(p95.get("resolve_ms")), "file ID / 下载地址", "warning"),
                _diagnostic_item("download_ms", "图片下载", _format_ms(p95.get("download_ms")), "下载并返回"),
                _diagnostic_item("response_ms", "响应整理", _format_ms(p95.get("response_ms")), "整理 API 响应"),
                _diagnostic_item("stream_ms", "协议处理 P95", _format_ms(p95.get("stream_ms")), "图片协议完整处理", "info"),
            ],
        },
    ]


def build_monitor_view(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    threadpool_source = _mapping(snapshot.get("threadpool"))
    window_source = _mapping(snapshot.get("window"))
    threadpool = {
        "tokens": _int(threadpool_source.get("tokens")),
        "previous_tokens": _int(threadpool_source.get("previous_tokens")),
    }
    window = {
        "completed": _int(window_source.get("completed")),
        "completed_capacity": _int(window_source.get("completed_capacity")),
        "events": _int(window_source.get("events")),
        "event_capacity": _int(window_source.get("event_capacity")),
    }
    summary = _project_summary(snapshot.get("summary"))
    completed_window_text = f"窗口 {window['completed']} / {window['completed_capacity']}"
    return {
        "schema_version": MONITOR_SCHEMA_VERSION,
        "updated_at": str(snapshot.get("updated_at") or ""),
        "threadpool": threadpool,
        "window": window,
        "summary": summary,
        "active": [_project_record(item) for item in snapshot.get("active", []) if isinstance(item, Mapping)],
        "recent": [_project_record(item) for item in snapshot.get("recent", []) if isinstance(item, Mapping)],
        "slow": [_project_record(item) for item in snapshot.get("slow", []) if isinstance(item, Mapping)],
        "metric_labels": {str(key): str(label) for key, label in _mapping(snapshot.get("metric_labels")).items()},
        "completed_window_text": completed_window_text,
        "entry_queue_text": _format_ms(summary["entry_queue_p95_ms"]),
        "active_stage_items": [
            {"label": str(label), "count": _int(count)}
            for label, count in list(summary["active_by_stage"].items())[:8]
            if _int(count) > 0
        ],
        "diagnostic_groups": _build_diagnostic_groups(summary, threadpool["tokens"], completed_window_text),
    }


def build_monitor_record_view(record: Mapping[str, Any]) -> dict[str, Any]:
    return _project_record(record, include_detail=True)
