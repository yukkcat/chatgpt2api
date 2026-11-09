from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from services.account_credentials import project_upstream_credential_availability
from services.proxy_management_service import project_proxy_assignment
from utils.diagnostics import sanitize_diagnostic_text


AccountStatusCategory = Literal["normal", "limited", "abnormal", "disabled"]
PresentationTone = Literal["neutral", "success", "warning", "error", "info"]

_STATUS_CATEGORY: dict[str, AccountStatusCategory] = {
    "正常": "normal",
    "限流": "limited",
    "异常": "abnormal",
    "禁用": "disabled",
}

_STATUS_LABEL: dict[AccountStatusCategory, str] = {
    "normal": "正常",
    "limited": "限流",
    "abnormal": "异常",
    "disabled": "禁用",
}

_STATUS_TONE: dict[AccountStatusCategory, PresentationTone] = {
    "normal": "success",
    "limited": "warning",
    "abnormal": "error",
    "disabled": "neutral",
}

_ACCESS_TOKEN_PRESENTATION = {
    "valid": ("AT 有效", "success"),
    "expiring": ("AT 临期", "warning"),
    "invalid": ("AT 失效", "error"),
}

_REFRESH_TOKEN_PRESENTATION = {
    "valid": ("RT 有效", "success"),
    "missing": ("RT 缺失", "neutral"),
    "invalid": ("RT 失效", "error"),
}

_CREDENTIAL_AVAILABILITY_PRESENTATION = {
    "usable": ("可用", "success"),
    "recoverable": ("可恢复", "warning"),
    "unavailable": ("不可用", "error"),
}

_PLAN_LABELS = {
    "free": "Free",
    "plus": "Plus",
    "pro": "Pro",
    "prolite": "ProLite",
    "team": "Team",
    "business": "Team",
    "enterprise": "Enterprise",
}

_SOURCE_LABELS = {
    "web": "Web",
    "codex": "Codex",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _timestamp_seconds(value: object) -> int | None:
    if isinstance(value, (int, float)):
        timestamp = int(value)
        return timestamp // 1000 if timestamp > 10_000_000_000 else timestamp
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _credential_lifecycle(account: dict[str, Any]) -> dict[str, Any]:
    access_token = _text(account.get("access_token"))
    remotely_invalid = _text(account.get("last_remote_check_result")).lower() == "invalid"
    availability = project_upstream_credential_availability(
        access_token,
        _text(account.get("refresh_token")),
        access_confirmed_invalid=remotely_invalid,
        refresh_confirmed_invalid=bool(account.get("refresh_token_invalid_at")),
    )
    access = availability.access
    refresh_status = availability.refresh_status
    access_label, access_tone = _ACCESS_TOKEN_PRESENTATION[access.status]
    refresh_label, refresh_tone = _REFRESH_TOKEN_PRESENTATION[refresh_status]
    availability_label, availability_tone = _CREDENTIAL_AVAILABILITY_PRESENTATION[availability.status]
    return {
        "access_token_status": access.status,
        "access_token_label": access_label,
        "access_token_tone": access_tone,
        "access_token_issued_at": access.issued_at,
        "access_token_expires_at": access.expires_at,
        "refresh_token_status": refresh_status,
        "refresh_token_label": refresh_label,
        "refresh_token_tone": refresh_tone,
        "can_refresh_access_token": refresh_status == "valid",
        "credential_availability": availability.status,
        "credential_availability_label": availability_label,
        "credential_availability_tone": availability_tone,
        "refresh_token_invalid_at": _timestamp_seconds(account.get("refresh_token_invalid_at")),
        "last_token_refresh_at": _timestamp_seconds(account.get("last_token_refresh_at")),
        "last_token_refresh_error": _diagnostic(
            account.get("last_token_refresh_error"), account, 2000
        ) or None,
        "last_token_refresh_error_at": _timestamp_seconds(account.get("last_token_refresh_error_at")),
    }


def _diagnostic(value: object, account: dict[str, Any], limit: int = 500) -> str:
    return sanitize_diagnostic_text(
        value,
        sensitive_values=(
            account.get("access_token"),
            account.get("refresh_token"),
            account.get("id_token"),
        ),
        proxy_values=(account.get("proxy"),),
        limit=limit,
    )


def _plan(account: dict[str, Any]) -> tuple[str, str]:
    raw = _text(account.get("type"))
    key = raw.lower().replace("-", "").replace("_", "").replace(" ", "")
    return raw, _PLAN_LABELS.get(key, raw or "未知")


def _source(account: dict[str, Any]) -> tuple[str, str]:
    source = _text(account.get("source_type")).lower()
    source = source if source in _SOURCE_LABELS else "web"
    return source, _SOURCE_LABELS[source]


def _backend_status_category(account: dict[str, Any]) -> AccountStatusCategory:
    return _STATUS_CATEGORY.get(_text(account.get("status")), "normal")


def _effective_status_category(
    backend_category: AccountStatusCategory,
    credential_lifecycle: dict[str, Any],
) -> AccountStatusCategory:
    if backend_category in {"disabled", "abnormal"}:
        return backend_category
    if credential_lifecycle["credential_availability"] == "unavailable":
        return "abnormal"
    return backend_category


def _status(
    account: dict[str, Any],
    credential_lifecycle: dict[str, Any],
) -> tuple[AccountStatusCategory, str, PresentationTone, str, str, str]:
    backend_category = _backend_status_category(account)
    category = _effective_status_category(backend_category, credential_lifecycle)
    remote_result = _text(account.get("last_remote_check_result")).lower()
    raw_error = _diagnostic(
        (
            account.get("last_remote_check_error")
            or account.get("last_token_refresh_error")
            or account.get("last_refresh_error")
        ),
        account,
    )

    if backend_category == "disabled":
        reason_code, reason = "disabled", "账号已手动禁用"
    elif backend_category == "abnormal":
        reason_code, reason = "auth_invalid", "远程确认账号登录态已失效"
    elif category == "abnormal":
        reason_code, reason = "credentials_unavailable", "AT 已失效，且没有可用 RT，账号无法参与调度"
    elif backend_category == "limited":
        reason_code, reason = "image_quota_exhausted", "远程确认图片额度已用完"
    elif remote_result == "pending":
        reason_code, reason = "verification_pending", "正在核验账号状态"
    elif remote_result == "error" or raw_error:
        reason_code, reason = "remote_check_failed", "最近一次账号检测失败，尚未确认账号失效"
    elif credential_lifecycle["credential_availability"] == "recoverable":
        reason_code, reason = "access_token_refresh_required", "AT 已失效，将使用 RT 自动刷新"
    else:
        reason_code, reason = "", "账号已启用，当前凭据可调用"

    return (
        category,
        _STATUS_LABEL[category],
        _STATUS_TONE[category],
        reason_code,
        reason,
        raw_error,
    )


def account_status_category(account: dict[str, Any]) -> AccountStatusCategory:
    """Project the effective management category without mutating stored status."""
    return _effective_status_category(
        _backend_status_category(account),
        _credential_lifecycle(account),
    )


def account_memory_state(account: dict[str, Any]) -> Literal["enabled", "disabled", "unknown"]:
    value = account.get("memory_enabled")
    if value is True:
        return "enabled"
    if value is False:
        return "disabled"
    return "unknown"


def account_memory_clear_status(account: dict[str, Any]) -> Literal["never", "verified", "pending", "failed"]:
    """Project the latest clear attempt, not whether memories currently exist."""
    status = _text(account.get("memory_clear_status"))
    if status == "verified":
        return "verified"
    if status == "pending":
        return "pending"
    if status == "failed":
        return "failed"
    return "never"


def _memory(account: dict[str, Any], credential_lifecycle: dict[str, Any]) -> dict[str, Any]:
    state = account_memory_state(account)
    label, tone = {
        "enabled": ("开启", "success"),
        "disabled": ("关闭", "neutral"),
        "unknown": ("未确认", "neutral"),
    }[state]
    operation = _text(account.get("memory_operation_status"))
    if operation not in {"verified", "pending", "failed"}:
        operation = ""
    operation_label, operation_tone = {
        "verified": ("", "success"),
        "pending": ("待验证", "warning"),
        "failed": ("操作失败", "error"),
    }.get(operation, ("", "neutral"))
    clear_status = account_memory_clear_status(account)
    clear_label, clear_tone = {
        "never": ("未操作", "neutral"),
        "verified": ("清空成功", "success"),
        "pending": ("待验证", "warning"),
        "failed": ("清空失败", "error"),
    }[clear_status]
    actions = []
    if credential_lifecycle["credential_availability"] != "unavailable":
        if state != "enabled":
            actions.append({"key": "enable_memory", "label": "开启记忆"})
        if state != "disabled":
            actions.append({"key": "disable_memory", "label": "关闭记忆"})
        actions.append({"key": "refresh_memory", "label": "刷新记忆状态"})
        actions.append({"key": "clear_memory", "label": "清空记忆"})
    return {
        "memory_state": state,
        "memory_label": label,
        "memory_tone": tone,
        "memory_checked_at": _timestamp_seconds(account.get("memory_checked_at")),
        "memory_operation_status": operation,
        "memory_operation_label": operation_label,
        "memory_operation_tone": operation_tone,
        "memory_operation_error": _diagnostic(account.get("memory_operation_error"), account),
        "memory_operation_at": _timestamp_seconds(account.get("memory_operation_at")),
        "memory_clear_status": clear_status,
        "memory_clear_label": clear_label,
        "memory_clear_tone": clear_tone,
        "memory_clear_at": _timestamp_seconds(account.get("memory_clear_at")),
        "memory_cleared_at": _timestamp_seconds(account.get("memory_cleared_at")),
        "memory_clear_error": _diagnostic(account.get("memory_clear_error"), account),
        "memory_actions": actions,
    }


def _proxy(account: dict[str, Any]) -> tuple[str, str, str, str]:
    projection = project_proxy_assignment(
        account.get("proxy"),
        legacy_group_id=account.get("proxy_group_id"),
    )
    mode = "custom" if projection.mode == "profile" else projection.mode
    safe_reference = "custom" if projection.mode == "custom" else projection.reference
    return (
        safe_reference,
        mode,
        projection.group_id,
        projection.label,
    )


def account_row(
    account: dict[str, Any],
    *,
    available: bool,
    unlimited_quota: bool,
    group_name: str = "",
) -> dict[str, Any]:
    access_token = _text(account.get("access_token"))
    account_id = _text(account.get("management_id"))
    backend_category = _backend_status_category(account)
    credential_lifecycle = _credential_lifecycle(account)
    category, status_label, status_tone, reason_code, reason, raw_error = _status(
        account,
        credential_lifecycle,
    )
    plan, plan_label = _plan(account)
    source, source_label = _source(account)
    proxy, proxy_mode, proxy_group_id, proxy_label = _proxy(account)
    quota_unknown = bool(account.get("image_quota_unknown"))
    quota_remaining = max(0, int(account.get("quota") or 0))
    if unlimited_quota:
        quota_state = "unlimited"
        quota_label = "无限"
    elif quota_unknown:
        quota_state = "unknown"
        quota_label = "未知"
    elif quota_remaining <= 0:
        quota_state = "exhausted"
        quota_label = "0"
    else:
        quota_state = "available"
        quota_label = str(quota_remaining)

    email = _text(account.get("email"))
    user_id = _text(account.get("user_id"))
    enabled = backend_category != "disabled"
    enabled_action = "disable" if enabled else "enable"
    return {
        "id": account_id,
        "email": email,
        "user_id": user_id,
        "display_name": email or user_id or account_id,
        "plan": plan,
        "plan_label": plan_label,
        "source": source,
        "source_label": source_label,
        "source_plan_label": f"{source_label} / {plan_label}",
        "backend_status": _STATUS_LABEL[backend_category],
        "status_category": category,
        "status_label": status_label,
        "status_tone": status_tone,
        "status_reason_code": reason_code,
        "status_reason": reason,
        "status_raw_error": raw_error,
        "enabled": enabled,
        "enabled_action": enabled_action,
        "enabled_action_label": "停用账号" if enabled_action == "disable" else "恢复启用",
        "available": bool(available),
        **credential_lifecycle,
        **_memory(account, credential_lifecycle),
        "quota_remaining": quota_remaining,
        "quota_unknown": quota_unknown,
        "quota_unlimited": bool(unlimited_quota),
        "quota_state": quota_state,
        "quota_label": quota_label,
        "quota_reset_at": _timestamp_seconds(account.get("restore_at")),
        "group_id": _text(account.get("group_id")),
        "group_name": group_name,
        "proxy": proxy,
        "proxy_mode": proxy_mode,
        "proxy_group_id": proxy_group_id,
        "proxy_label": proxy_label,
        "success_count": max(0, int(account.get("success") or 0)),
        "failure_count": max(0, int(account.get("fail") or 0)),
        "image_inflight": max(0, int(account.get("image_inflight") or 0)),
        "last_remote_check_result": _text(account.get("last_remote_check_result")),
        "last_remote_check_attempt_at": _timestamp_seconds(account.get("last_remote_check_attempt_at")),
        "last_remote_checked_at": _timestamp_seconds(account.get("last_remote_checked_at")),
        "created_at": _timestamp_seconds(account.get("created_at")),
        "last_used_at": _timestamp_seconds(account.get("last_used_at")),
    }


def account_detail(
    account: dict[str, Any],
    *,
    available: bool,
    unlimited_quota: bool,
    group_name: str = "",
) -> dict[str, Any]:
    return {
        **account_row(
            account,
            available=available,
            unlimited_quota=unlimited_quota,
            group_name=group_name,
        ),
        "configuration": {
            "type": _text(account.get("type")),
            "source_type": _text(account.get("source_type")),
            "quota": max(0, int(account.get("quota") or 0)),
            "proxy": _text(account.get("proxy")),
            "group_id": _text(account.get("group_id")),
        },
        "diagnostics": {
            "remote_check_error": _diagnostic(account.get("last_remote_check_error"), account, 2000),
            "refresh_error": _diagnostic(account.get("last_refresh_error"), account, 2000),
            "token_refresh_error": _diagnostic(account.get("last_token_refresh_error"), account, 2000),
            "last_invalid_at": _timestamp_seconds(account.get("last_invalid_at")),
            "last_refresh_error_at": _timestamp_seconds(account.get("last_refresh_error_at")),
            "last_token_refresh_at": _timestamp_seconds(account.get("last_token_refresh_at")),
        },
    }
