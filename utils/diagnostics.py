from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


EXCEPTION_DIAGNOSTIC_ATTRS: tuple[tuple[str, str], ...] = (
    ("code", "error_code"),
    ("raw_error", "raw_error"),
    ("upstream_error", "upstream_error"),
    ("upstream_error_type", "upstream_error_type"),
    ("upstream_request_id", "upstream_request_id"),
    ("can_resume_poll", "can_resume_poll"),
    ("raw_upstream_message", "raw_upstream_message"),
    ("raw_upstream_message_len", "raw_upstream_message_len"),
    ("raw_upstream_message_truncated", "raw_upstream_message_truncated"),
    ("upstream_message_preview", "upstream_message_preview"),
    ("upstream_message_len", "upstream_message_len"),
    ("upstream_message_truncated", "upstream_message_truncated"),
    ("tool_invoked", "tool_invoked"),
    ("terminal_message", "terminal_message"),
    ("blocked", "blocked"),
    ("poll_attempts", "poll_attempts"),
    ("poll_timeout_secs", "poll_timeout_secs"),
    ("stream_timeout_secs", "stream_timeout_secs"),
    ("stream_timeout_followup", "stream_timeout_followup"),
    ("last_task_error", "last_task_error"),
    ("last_conversation_snapshot", "last_conversation_snapshot"),
    ("image_attempts", "image_attempts"),
)

_DIAGNOSTIC_SECRET_KEYS = {
    "access_token",
    "accesstoken",
    "refresh_token",
    "refreshtoken",
    "id_token",
    "idtoken",
    "authorization",
    "proxy_authorization",
    "proxyauthorization",
    "password",
    "proxy_password",
    "proxypassword",
}

_DIAGNOSTIC_PROXY_KEYS = {
    "proxy",
    "proxy_url",
    "proxyurl",
}

_NON_SECRET_PROXY_VALUES = {
    "default",
    "direct",
    "inherit",
    "system",
}


def sanitize_diagnostic_text(
    value: object,
    *,
    sensitive_values: Iterable[object] = (),
    proxy_values: Iterable[object] = (),
    limit: int = 0,
) -> str:
    """Remove credentials from diagnostics before storage or projection."""
    text = str(value or "").strip()
    if not text:
        return ""
    proxies = sorted(
        {
            proxy
            for item in proxy_values
            if (proxy := str(item or "").strip())
            and proxy.casefold() not in _NON_SECRET_PROXY_VALUES
        },
        key=len,
        reverse=True,
    )
    secrets = sorted(
        {str(item or "").strip() for item in sensitive_values if str(item or "").strip()},
        key=len,
        reverse=True,
    )
    for proxy in proxies:
        text = text.replace(proxy, "[proxy]")
    for secret in secrets:
        text = text.replace(secret, "[credential]")
    text = re.sub(
        r"(?i)([a-z][a-z0-9+.-]*://)[^\s/@:]+(?::[^\s/@]*)?@",
        r"\1***@",
        text,
    )
    text = re.sub(
        r"(?i)(?<![a-z0-9])((?:\[[0-9a-f:.]+\]|localhost|"
        r"\d{1,3}(?:\.\d{1,3}){3}|"
        r"(?=[a-z0-9.-]*[a-z])[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?):\d{1,5}):"
        r"[^:\s,;]+:[^\s,;]+",
        r"\1:***:***",
        text,
    )
    text = re.sub(
        r"(?i)\b((?:Proxy-)?Authorization\s*:\s*(?:Basic|Bearer))\s+"
        r"[A-Za-z0-9._~+/=-]+",
        r"\1 [credential]",
        text,
    )
    text = re.sub(
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer [credential]",
        text,
    )
    text = re.sub(
        r"(?i)([?&](?:(?:proxy[_-]?)?(?:user(?:name)?|pass(?:word)?)|"
        r"access_token|refresh_token|id_token)=)[^&#\s]+",
        r"\1***",
        text,
    )
    text = re.sub(
        r"(?i)((?<![a-z0-9_])[\"']?(?:access[_-]?token|refresh[_-]?token|"
        r"id[_-]?token|password)"
        r"[\"']?\s*[:=]\s*[\"']?)[^\s,;\"'&}]+",
        r"\1[credential]",
        text,
    )
    return text if limit <= 0 or len(text) <= limit else f"{text[:limit]}..."


def _collect_diagnostic_values(
    value: object,
    sensitive_values: list[object],
    proxy_values: list[object],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if normalized_key in _DIAGNOSTIC_SECRET_KEYS and item not in (None, ""):
                sensitive_values.append(item)
            elif normalized_key in _DIAGNOSTIC_PROXY_KEYS and item not in (None, ""):
                proxy_values.append(item)
            _collect_diagnostic_values(item, sensitive_values, proxy_values)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_diagnostic_values(item, sensitive_values, proxy_values)


def _scrub_diagnostic_value(
    value: object,
    sensitive_values: list[object],
    proxy_values: list[object],
) -> object:
    if isinstance(value, dict):
        result: dict[object, object] = {}
        for key, item in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if normalized_key in _DIAGNOSTIC_SECRET_KEYS and item not in (None, ""):
                result[key] = "[credential]"
            else:
                result[key] = _scrub_diagnostic_value(
                    item,
                    sensitive_values,
                    proxy_values,
                )
        return result
    if isinstance(value, list):
        return [
            _scrub_diagnostic_value(
                item,
                sensitive_values,
                proxy_values,
            )
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _scrub_diagnostic_value(
                item,
                sensitive_values,
                proxy_values,
            )
            for item in value
        )
    if isinstance(value, str):
        return sanitize_diagnostic_text(
            value,
            sensitive_values=sensitive_values,
            proxy_values=proxy_values,
        )
    return value


def scrub_diagnostic_value(
    value: object,
    *,
    sensitive_values: Iterable[object] = (),
    proxy_values: Iterable[object] = (),
) -> object:
    """Recursively sanitize strings and credential-bearing mapping fields."""
    collected_sensitive_values = list(sensitive_values)
    collected_proxy_values = list(proxy_values)
    _collect_diagnostic_values(
        value,
        collected_sensitive_values,
        collected_proxy_values,
    )
    return _scrub_diagnostic_value(
        value,
        collected_sensitive_values,
        collected_proxy_values,
    )


def diagnostic_excerpt(value: object, limit: int = 1000) -> str:
    """Return a bounded diagnostic string for logs and upstream error details."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 15].rstrip() + "...[truncated]"


def exception_diagnostic_fields(
    exc: Exception,
    *,
    include_status_code: bool = False,
    string_limit: int = 4000,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    attrs = EXCEPTION_DIAGNOSTIC_ATTRS
    if include_status_code:
        attrs = (("status_code", "status_code"), *attrs)
    for attr, key in attrs:
        if not hasattr(exc, attr):
            continue
        value = getattr(exc, attr)
        if value in (None, ""):
            continue
        if isinstance(value, str):
            value = diagnostic_excerpt(value, string_limit)
        fields[key] = value
    followup = fields.get("stream_timeout_followup")
    if isinstance(followup, dict) and "diagnosis" not in fields:
        fields["diagnosis"] = followup
    return fields
