from __future__ import annotations

import json
import re
from typing import Any, Mapping


_TIMELINE_CATEGORIES = (
    ("entry", "入口与账号"),
    ("prepare", "上游准备"),
    ("upstream", "上游生成"),
    ("resolve", "结果处理"),
    ("download", "图片下载"),
)

_TIMELINE_STEPS = (
    ("handler_queue_ms", "等待入口", "entry", "run_in_threadpool"),
    ("stream_first_queue_ms", "读取首包", "entry", "首个响应事件"),
    ("account_wait_ms", "等待账号", "entry", "账号池筛选"),
    ("egress_wait_ms", "等待出口", "entry", "代理出口准备"),
    ("egress_acquire_ms", "出口租约", "entry", "代理节点并发"),
    ("upload_ms", "上传输入图", "prepare", "参考图上传"),
    ("bootstrap_ms", "预热页面", "prepare", "ChatGPT 页面"),
    ("requirements_ms", "获取请求令牌", "prepare", "requirements / token"),
    ("prepare_conversation_ms", "准备会话", "prepare", "图片会话上下文"),
    ("http_dns_ms", "HTTP DNS", "prepare", "域名解析"),
    ("http_tcp_ms", "HTTP TCP", "prepare", "代理 / TCP 建连"),
    ("http_tls_ms", "HTTP TLS", "prepare", "TLS 握手"),
    ("http_wait_ms", "HTTP 等待", "prepare", "请求发出到首包"),
    ("http_ttfb_ms", "HTTP 首包", "prepare", "请求开始到首包"),
    ("generation_start_ms", "启动生成", "upstream", "提交上游请求"),
    ("sse_stream_ms", "SSE 流耗时", "upstream", "data 事件持续时间"),
    ("sse_first_event_ms", "SSE 首事件", "upstream", "首个 data 事件"),
    ("sse_max_gap_ms", "SSE 最大空窗", "upstream", "两次事件最大间隔"),
    ("sse_last_gap_ms", "SSE 收尾空窗", "upstream", "最后事件到关闭"),
    ("conversation_stream_ms", "上游生成", "upstream", "ChatGPT 会话流"),
    ("stream_error_ms", "上游断流", "upstream", "HTTP2 / SSE"),
    ("poll_wait_ms", "等待结果", "resolve", "首次等待 / 轮询间隔 / 退避"),
    ("poll_request_ms", "查询结果", "resolve", "task / conversation"),
    ("resolve_ms", "解析结果", "resolve", "file ID / 下载地址"),
    ("response_ms", "响应整理", "resolve", "Codex 响应"),
    ("download_ms", "下载图片", "download", "图片文件下载"),
)

_TIMELINE_SEGMENTS = (
    ("entry_queue", "入口排队", "entry", ("handler_queue_ms", "stream_first_queue_ms")),
    ("account_egress", "账号与出口", "entry", ("account_wait_ms", "egress_wait_ms")),
    (
        "prepare",
        "上游准备",
        "prepare",
        ("upload_ms", "bootstrap_ms", "requirements_ms", "prepare_conversation_ms"),
    ),
    ("upstream", "上游生成", "upstream", ("generation_start_ms", "sse_stream_ms")),
    ("poll_wait", "等待结果", "resolve", ("poll_wait_ms",)),
    (
        "query_resolve",
        "查询与解析",
        "resolve",
        ("poll_request_ms", "resolve_ms", "response_ms"),
    ),
    ("download", "图片下载", "download", ("download_ms",)),
)

_DEFAULT_TIMELINE_WARNING_THRESHOLD_MS = 60_000
_TIMELINE_WARNING_THRESHOLDS_MS = {
    "handler_queue_ms": 1_000,
    "stream_first_queue_ms": 1_000,
    "account_wait_ms": 10_000,
    "egress_wait_ms": 10_000,
    "egress_acquire_ms": 10_000,
    "upload_ms": 60_000,
    "bootstrap_ms": 60_000,
    "requirements_ms": 60_000,
    "prepare_conversation_ms": 60_000,
    "generation_start_ms": 60_000,
    "http_dns_ms": 1_000,
    "http_tcp_ms": 3_000,
    "http_tls_ms": 5_000,
    "http_wait_ms": 30_000,
    "http_ttfb_ms": 30_000,
    "sse_first_event_ms": 30_000,
    "sse_max_gap_ms": 60_000,
    "sse_last_gap_ms": 30_000,
    "poll_wait_ms": 60_000,
    "poll_request_ms": 30_000,
    "download_ms": 60_000,
    "response_ms": 30_000,
}


def _record(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _int(value: object) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _clean(value: object) -> str:
    return str(value or "").strip()


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = _clean(value).lower()
    if normalized in {"1", "true", "yes", "on", "是"}:
        return True
    if normalized in {"0", "false", "no", "off", "否"}:
        return False
    return None


def _inline_value(value: object) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (list, tuple)):
        return " · ".join(filter(None, (_inline_value(item) for item in value)))
    if isinstance(value, Mapping):
        entries = [(str(key), item) for key, item in value.items() if item not in (None, "")]
        if not entries:
            return ""
        if len(entries) <= 8 and all(not isinstance(item, (Mapping, list, tuple)) for _, item in entries):
            return " · ".join(f"{key}: {_inline_value(item)}" for key, item in entries)
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return _clean(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return _clean(value)


def _compact_duration_number(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def format_request_duration(milliseconds: object) -> str:
    value = _int(milliseconds)
    if value < 1000:
        return f"{value}ms"
    if value < 10000:
        return f"{_compact_duration_number(value / 1000, 2)}s"
    if value < 60000:
        return f"{_compact_duration_number(value / 1000, 1)}s"
    return f"{_compact_duration_number(value / 60000, 1)}m"


def request_status_presentation(outcome: object, *, fallback: object = "记录") -> dict[str, str]:
    normalized = _clean(outcome).lower()
    presentations = {
        "success": {"label": "成功", "tone": "success"},
        "partial_success": {"label": "部分成功", "tone": "warning"},
        "rate_limited": {"label": "限流", "tone": "warning"},
        "text_review": {"label": "文本", "tone": "warning"},
        "failed": {"label": "失败", "tone": "danger"},
        "error": {"label": "失败", "tone": "danger"},
        "fail": {"label": "失败", "tone": "danger"},
        "running": {"label": "运行中", "tone": "info"},
    }
    return presentations.get(
        normalized,
        {"label": _clean(fallback) or normalized or "记录", "tone": "muted"},
    )


def request_proxy_source_label(value: object) -> str:
    source = _clean(value) or "direct"
    if "account_group" in source:
        return "账号组"
    if "account" in source:
        return "账号"
    if "default" in source or "global" in source:
        return "默认"
    if "runtime_resource" in source:
        return "资源代理"
    if "runtime" in source:
        return "代理会话"
    if "explicit" in source:
        return "指定"
    if "direct" in source:
        return "直连"
    return source


def request_egress_text(detail: Mapping[str, Any], monitor: Mapping[str, Any]) -> str:
    def value(key: str) -> str:
        return _diagnostic_text(detail, key) or _inline_value(monitor.get(key))

    source = value("proxy_source")
    if not source:
        return ""
    source_label = request_proxy_source_label(source)
    group_id = value("proxy_group_id")
    node_name = value("proxy_node_name")
    node_id = value("proxy_node_id")
    node_label = "/".join(part for part in (group_id, node_name or node_id) if part)
    if node_label:
        return f"{source_label} {node_label}"
    egress_label = value("egress_label")
    if egress_label and egress_label != "direct" and not egress_label.startswith("proxy:"):
        return f"{source_label} {egress_label}"
    proxy_hash = value("proxy_hash")
    if proxy_hash and proxy_hash != "direct":
        return f"{source_label} {proxy_hash}"
    return source_label


def request_detail_field(
    label: str,
    value: object,
    *,
    copyable: bool = False,
    wide: bool = False,
) -> dict[str, Any] | None:
    text = _inline_value(value)
    if not text or text == "-" or text.lower() in {"null", "undefined"}:
        return None
    return {"label": label, "value": text, "copyable": copyable, "wide": wide}


def _diagnostic_raw(detail: Mapping[str, Any], key: str) -> object:
    if key in detail and detail.get(key) not in (None, ""):
        return detail.get(key)
    diagnosis = detail.get("diagnosis")
    if isinstance(diagnosis, Mapping):
        return diagnosis.get(key)
    return None


def _diagnostic_text(detail: Mapping[str, Any], key: str) -> str:
    return _inline_value(_diagnostic_raw(detail, key))


def _masked_key_label(value: object) -> str:
    return re.sub(
        r"sk-[A-Za-z0-9_-]{6,}",
        lambda match: f"{match.group(0)[:5]}***{match.group(0)[-4:]}",
        _clean(value),
    )


def _time_range_text(summary: Mapping[str, Any]) -> str:
    started = _clean(summary.get("started_at") or summary.get("time"))
    ended = _clean(summary.get("ended_at") or summary.get("updated_at"))
    if not started:
        return ended
    if not ended or ended == started:
        return started
    return f"{started} → {ended}"


def _timeline_metric_tone(key: str, value_ms: int) -> str:
    if key == "stream_error_ms":
        return "danger"
    threshold = _TIMELINE_WARNING_THRESHOLDS_MS.get(key, _DEFAULT_TIMELINE_WARNING_THRESHOLD_MS)
    return "warning" if value_ms >= threshold else "info"


def _timeline_status_label(tone: str) -> str:
    return "异常" if tone == "danger" else "慢" if tone == "warning" else "记录"


def _timeline_event_time(events: object, metric_key: str) -> str:
    if not isinstance(events, (list, tuple)):
        return ""
    for event in events:
        if isinstance(event, Mapping) and _int(event.get(metric_key)) > 0:
            return _inline_value(event.get("time"))
    return ""


def _timeline_segment_value(
    timings: Mapping[str, int],
    segment_key: str,
    aggregate_keys: tuple[str, ...],
) -> int:
    primary_value = sum(_int(timings.get(key)) for key in aggregate_keys)
    if segment_key != "upstream":
        return primary_value
    envelope_value = _int(timings.get("conversation_stream_ms")) or _int(timings.get("stream_error_ms"))
    if envelope_value <= 0:
        return primary_value
    prepare_keys = next((keys for key, _, _, keys in _TIMELINE_SEGMENTS if key == "prepare"), ())
    prepare_value = sum(_int(timings.get(key)) for key in prepare_keys)
    return max(primary_value, max(0, envelope_value - prepare_value))


def _request_shape_image_summary(value: object) -> str:
    shape = _record(value)
    labels = (
        ("input_image_parts", "输入图"),
        ("image_url_parts", "图链"),
        ("image_parts", "图片块"),
        ("data_url_images", "base64"),
        ("remote_image_urls", "远程图"),
        ("literal_image_placeholders", "占位图"),
    )
    return " · ".join(
        f"{label} {count}" for key, label in labels if (count := _int(shape.get(key))) > 0
    )


def build_request_timeline_presentation(
    timings: Mapping[str, int],
    events: object,
    *,
    image_count: int = 0,
    request_shape: object = None,
) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    for segment_key, label, category, aggregate_keys in _TIMELINE_SEGMENTS:
        value_ms = _timeline_segment_value(timings, segment_key, aggregate_keys)
        if value_ms <= 0:
            continue
        tone_keys = (*aggregate_keys, "stream_error_ms") if segment_key == "upstream" else aggregate_keys
        tones = [
            _timeline_metric_tone(key, metric_value)
            for key in tone_keys
            if (metric_value := _int(timings.get(key))) > 0
        ]
        tone = "danger" if "danger" in tones else "warning" if "warning" in tones else "info"
        segments.append({
            "key": segment_key,
            "label": label,
            "category": category,
            "value_ms": value_ms,
            "value_text": format_request_duration(value_ms),
            "tone": tone,
        })

    steps_by_category: dict[str, list[dict[str, Any]]] = {}
    for key, label, category, description in _TIMELINE_STEPS:
        value_ms = _int(timings.get(key))
        if value_ms <= 0:
            continue
        description_parts = [description]
        if key == "upload_ms":
            description_parts.append(_request_shape_image_summary(request_shape))
        if key == "resolve_ms" and image_count > 0:
            description_parts.append(f"结果图 {image_count}")
        if key == "download_ms" and image_count > 0:
            description_parts.append(f"下载 {image_count} 张")
        tone = _timeline_metric_tone(key, value_ms)
        steps_by_category.setdefault(category, []).append({
            "key": key,
            "label": label,
            "category": category,
            "value_ms": value_ms,
            "value_text": format_request_duration(value_ms),
            "tone": tone,
            "status_label": _timeline_status_label(tone),
            "time": _timeline_event_time(events, key),
            "description": " · ".join(filter(None, description_parts)),
        })

    groups = [
        {"key": category, "label": label, "steps": steps_by_category[category]}
        for category, label in _TIMELINE_CATEGORIES
        if steps_by_category.get(category)
    ]
    legend_items: list[dict[str, Any]] = []
    if segments:
        legend_items.extend({
            "key": category,
            "label": label,
            "category": category,
            "tone": "info",
        } for category, label in _TIMELINE_CATEGORIES)
        if any(segment["tone"] == "warning" for segment in segments):
            legend_items.append({"key": "warning", "label": "超过阈值", "category": "state", "tone": "warning"})
        if any(segment["tone"] == "danger" for segment in segments):
            legend_items.append({"key": "danger", "label": "异常中断", "category": "state", "tone": "danger"})
    return {"segments": segments, "legend_items": legend_items, "groups": groups}


def _diagnostic_stage_text(
    summary: Mapping[str, Any],
    detail: Mapping[str, Any],
    monitor: Mapping[str, Any],
) -> str:
    stage = (
        _diagnostic_text(detail, "stage_label")
        or _diagnostic_text(detail, "stage")
        or _inline_value(monitor.get("stage_label"))
        or _inline_value(monitor.get("stage"))
    )
    if _clean(summary.get("outcome")) in {"success", "partial_success"} and stage.lower() in {
        "success", "completed", "complete", "done", "完成",
    }:
        return ""
    return stage


def build_request_detail_core(
    summary: Mapping[str, Any],
    detail: Mapping[str, Any],
    monitor: Mapping[str, Any],
    timings: Mapping[str, int],
    *,
    events: object = None,
    image_count: int = 0,
    request_shape: object = None,
    hide_account_identity: bool = False,
    suppress_timeline: bool = False,
) -> dict[str, Any]:
    primary_candidates = [
        request_detail_field("请求 ID", detail.get("call_id") or summary.get("id"), copyable=True),
        request_detail_field("接口", summary.get("endpoint"), copyable=True),
        request_detail_field("模型", summary.get("model"), copyable=True),
        None if hide_account_identity else request_detail_field("账号", summary.get("account_email"), copyable=True),
        request_detail_field(
            "密钥",
            _masked_key_label(" / ".join(filter(None, (_clean(summary.get("key_name")), _clean(summary.get("key_id")))))),
        ),
        request_detail_field("出口", request_egress_text(detail, monitor)),
        None if hide_account_identity else request_detail_field("会话 ID", summary.get("conversation_id"), copyable=True),
        request_detail_field("时间", _time_range_text(summary), wide=True),
    ]

    outcome = _clean(summary.get("outcome"))
    status_code = _int(summary.get("status_code"))
    error_code = _clean(summary.get("error_code"))
    public_error = _clean(summary.get("public_error"))
    reason = _diagnostic_text(detail, "reason") or _diagnostic_text(detail, "local_reason")
    upstream_error_type = _diagnostic_text(detail, "upstream_error_type") or _diagnostic_text(detail, "error_type")
    upstream_request_id = _diagnostic_text(detail, "upstream_request_id")
    stage = _diagnostic_stage_text(summary, detail, monitor)
    tool_invoked = _optional_bool(_diagnostic_raw(detail, "tool_invoked"))
    blocked = _optional_bool(_diagnostic_raw(detail, "blocked"))
    has_boolean_anomaly = tool_invoked is False or blocked is True
    show_failure_booleans = outcome in {"failed", "rate_limited"} or bool(error_code or public_error or reason) or has_boolean_anomaly
    has_diagnostics = bool(
        outcome in {"failed", "rate_limited"}
        or status_code >= 400
        or error_code
        or public_error
        or reason
        or upstream_error_type
        or upstream_request_id
        or stage
        or has_boolean_anomaly
    )
    diagnostic_fields: list[dict[str, Any] | None] = []
    if has_diagnostics:
        diagnostic_fields = [
            request_detail_field("状态码", status_code if status_code > 0 else ""),
            request_detail_field("错误码", error_code, copyable=True),
            request_detail_field("阶段", stage, copyable=True),
            request_detail_field("原因", reason, copyable=True),
            request_detail_field("上游错误", upstream_error_type, copyable=True),
            request_detail_field("上游请求 ID", upstream_request_id, copyable=True),
            request_detail_field("请求形状", detail.get("request_shape") or request_shape, copyable=True),
            request_detail_field("工具调用", tool_invoked) if show_failure_booleans and tool_invoked is not None else None,
            request_detail_field("阻断", blocked) if show_failure_booleans and blocked is not None else None,
            request_detail_field("上游文本长度", _diagnostic_raw(detail, "upstream_message_len")),
        ]

    duration_ms = _int(summary.get("duration_ms") or summary.get("elapsed_ms"))
    return {
        "primary_fields": [field for field in primary_candidates if field is not None],
        "diagnostic_fields": [field for field in diagnostic_fields if field is not None],
        "auto_expand_timeline": bool(
            outcome == "failed" or duration_ms >= 180_000 or _int(timings.get("stream_error_ms")) > 0
        ),
        "timeline": (
            build_request_timeline_presentation({}, ())
            if suppress_timeline
            else build_request_timeline_presentation(
                timings,
                events,
                image_count=image_count,
                request_shape=request_shape,
            )
        ),
    }
