from __future__ import annotations

import asyncio
import io
import json
import re
import uuid
import zipfile
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from contracts.auth import (
    UserKeyCreateRequest,
    UserKeyCreateResult,
    UserKeyDeleteResult,
    UserKeyListView,
    UserKeyUpdateRequest,
    UserKeyUpdateResult,
)
from contracts.account_test import AccountTestRequest, AccountTestResult
from services.auth_service import auth_service

from api.support import (
    require_admin,
    sanitize_cpa_pool,
    sanitize_cpa_pools,
    sanitize_sub2api_server,
    sanitize_sub2api_servers,
)
from services.account_operation_events import (
    normalize_account_operation_events,
    project_account_operation_presentation,
)
from services.account_test_service import account_test_service
from services.account_service import account_service
from services.account_view import account_detail, account_row, account_status_category
from services.config import config
from services.cpa_service import cpa_config, cpa_import_service, list_remote_files
from services.log_service import LoggedCall
from services.oauth_login_service import OAuthLoginError, oauth_login_service
from services.proxy_management_service import project_proxy_assignment, proxy_management_service
from services.sub2api_service import (
    list_remote_accounts as sub2api_list_remote_accounts,
    list_remote_groups as sub2api_list_remote_groups,
    sub2api_config,
    sub2api_import_service,
)
from utils.diagnostics import sanitize_diagnostic_text
from utils.helper import anonymize_token


_ACCOUNT_OPERATION_TASKS: set[asyncio.Task[Any]] = set()


def _schedule_account_operation(coroutine: Any) -> Any:
    task = asyncio.create_task(coroutine)
    if isinstance(task, asyncio.Task):
        _ACCOUNT_OPERATION_TASKS.add(task)
        task.add_done_callback(_ACCOUNT_OPERATION_TASKS.discard)
    return task


class AccountSelectionScope(BaseModel):
    mode: Literal["explicit", "filter", "all"] = "explicit"
    account_ids: list[str] = Field(default_factory=list)
    excluded_account_ids: list[str] = Field(default_factory=list)
    keyword: str = ""
    status: str = "all"
    group_id: str = "all"


class AccountSelectionPreviewRequest(BaseModel):
    selection: AccountSelectionScope


class AccountCreateRequest(BaseModel):
    tokens: list[str] = Field(default_factory=list)
    accounts: list[dict[str, Any]] = Field(default_factory=list)
    sync_after_import: bool | None = None
    refresh: bool | None = None
    restore: bool = False
    return_items: bool = True


class AccountDeleteRequest(BaseModel):
    account_ids: list[str] = Field(default_factory=list)
    tokens: list[str] = Field(default_factory=list)
    selection: AccountSelectionScope | None = None


class AccountImportCleanupRequest(BaseModel):
    access_tokens: list[str] = Field(default_factory=list)
    account_ids: list[str] = Field(default_factory=list)
    remove: bool = False


class AccountOperationRequest(BaseModel):
    account_ids: list[str] = Field(default_factory=list)
    access_tokens: list[str] = Field(default_factory=list)
    selection: AccountSelectionScope | None = None


class AccountExportRequest(BaseModel):
    account_ids: list[str] = Field(default_factory=list)
    access_tokens: list[str] = Field(default_factory=list)
    format: Literal["json", "zip", "txt"] = "json"
    selection: AccountSelectionScope | None = None


class AccountUpdateRequest(BaseModel):
    id: str = ""
    access_token: str = ""
    type: str | None = None
    source_type: str | None = None
    quota: int | None = None
    proxy: str | None = None
    group_id: str | None = None


class AccountBatchUpdateRequest(BaseModel):
    account_ids: list[str] = Field(default_factory=list)
    access_tokens: list[str] = Field(default_factory=list)
    selection: AccountSelectionScope | None = None
    status: Literal["正常", "限流", "异常", "禁用"] | None = None
    operation: Literal["update", "enable", "disable", "reset"] | None = None


class AccountGroupBindRequest(BaseModel):
    account_ids: list[str] = Field(default_factory=list)
    access_tokens: list[str] = Field(default_factory=list)
    selection: AccountSelectionScope | None = None
    group_id: str = ""


class AccountGroupRequest(BaseModel):
    id: str = ""
    name: str = ""
    proxy: str = ""
    proxy_group_id: str = ""
    enabled: bool = True
    notes: str = ""
    create_only: bool = False


class CPAPoolCreateRequest(BaseModel):
    name: str = ""
    base_url: str = ""
    secret_key: str = ""


class CPAPoolUpdateRequest(BaseModel):
    name: str | None = None
    base_url: str | None = None
    secret_key: str | None = None


class CPAImportRequest(BaseModel):
    names: list[str] = Field(default_factory=list)


class Sub2APIServerCreateRequest(BaseModel):
    name: str = ""
    base_url: str = ""
    email: str = ""
    password: str = ""
    api_key: str = ""
    group_id: str = ""


class Sub2APIServerUpdateRequest(BaseModel):
    name: str | None = None
    base_url: str | None = None
    email: str | None = None
    password: str | None = None
    api_key: str | None = None
    group_id: str | None = None


class Sub2APIImportGroupBinding(BaseModel):
    remote_group_id: str = ""
    name: str = ""
    account_ids: list[str] = Field(default_factory=list)


class Sub2APIImportRequest(BaseModel):
    account_ids: list[str] = Field(default_factory=list)
    group_bindings: list[Sub2APIImportGroupBinding] = Field(default_factory=list)
    create_account_groups: bool = True


class OAuthLoginStartRequest(BaseModel):
    """起始 OAuth 桥。email_hint 可选，仅用于让 OpenAI 登录页预填邮箱。"""
    email_hint: str = ""


class OAuthLoginFinishRequest(BaseModel):
    """提交 callback。callback 既可以是完整 URL 也可以只填 code。"""
    session_id: str = ""
    callback: str = ""


def _account_payload_token(item: dict[str, Any]) -> str:
    return str(item.get("access_token") or item.get("accessToken") or "").strip()


def _unique_tokens(tokens: list[str]) -> list[str]:
    return list(dict.fromkeys(str(token or "").strip() for token in tokens if str(token or "").strip()))


def _download_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _safe_export_name(value: str, fallback: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return (clean or fallback)[:80]


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _slug_id(value: object) -> str:
    raw = _clean_text(value).lower()
    chars: list[str] = []
    for char in raw:
        if char.isalnum() or char in {"-", "_"}:
            chars.append(char)
        elif char.isspace():
            chars.append("-")
    return "".join(chars).strip("-_")


def _config_dict_list(key: str) -> list[dict[str, Any]]:
    raw = config.get().get(key)
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _account_group_id(value: object) -> str:
    return _slug_id(value)


def _account_group_payload(groups: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    accounts = account_service.list_accounts()
    counts: dict[str, int] = {}
    for account in accounts:
        group_id = _clean_text(account.get("group_id"))
        if group_id:
            counts[group_id] = counts.get(group_id, 0) + 1
    proxy_groups = [
        group.model_dump(mode="json")
        for group in proxy_management_service.list_groups().groups
    ]
    proxy_group_names = {
        _clean_text(group.get("id")): _clean_text(group.get("name"))
        for group in proxy_groups
        if _clean_text(group.get("id"))
    }
    normalized_groups = []
    for group in groups if groups is not None else _config_dict_list("account_groups"):
        group_id = _account_group_id(group.get("id"))
        if not group_id:
            continue
        projection = project_proxy_assignment(
            group.get("proxy"),
            legacy_group_id=group.get("proxy_group_id"),
            group_names=proxy_group_names,
        )
        normalized_groups.append(
            {
                "id": group_id,
                "name": _clean_text(group.get("name")) or group_id,
                "proxy": projection.reference,
                "proxy_group_id": projection.group_id,
                "proxy_mode": projection.mode,
                "proxy_label": projection.label,
                "enabled": bool(group.get("enabled", True)),
                "notes": _clean_text(group.get("notes")),
                "account_count": counts.get(group_id, 0),
            }
        )
    return {
        "groups": normalized_groups,
        "proxy_groups": proxy_groups,
    }


def _upsert_account_group(body: AccountGroupRequest) -> dict[str, Any]:
    group_id = _account_group_id(body.id or body.name)
    if not group_id:
        raise ValueError("account group id is required")

    def persist(normalized_references: list[str]) -> dict[str, Any]:
        groups = _config_dict_list("account_groups")
        exists = any(_account_group_id(group.get("id")) == group_id for group in groups)
        if body.create_only and exists:
            raise ValueError("account group already exists")
        projection = project_proxy_assignment(normalized_references[0])
        item = {
            "id": group_id,
            "name": body.name.strip() or group_id,
            "proxy": projection.reference,
            "proxy_group_id": projection.group_id,
            "enabled": body.enabled,
            "notes": body.notes.strip(),
        }
        next_groups = [
            group
            for group in groups
            if _account_group_id(group.get("id")) != group_id
        ]
        next_groups.append(item)
        updated = config.update({"account_groups": next_groups})
        payload = _account_group_payload(updated.get("account_groups", []))
        projected_group = next(
            group for group in payload["groups"]
            if group["id"] == group_id
        )
        return {
            "group": projected_group,
            **payload,
        }

    return proxy_management_service.mutate_assignment_references(
        [(body.proxy, body.proxy_group_id)],
        persist,
    )


def _account_status_category(account: dict[str, Any]) -> Literal["normal", "limited", "abnormal", "disabled"]:
    return account_status_category(account)


def _account_group_names() -> dict[str, str]:
    return {
        group_id: _clean_text(group.get("name")) or group_id
        for group in _config_dict_list("account_groups")
        if (group_id := _account_group_id(group.get("id")))
    }


def _account_available(account: dict[str, Any]) -> bool:
    checker = getattr(account_service, "is_image_account_available", None)
    if callable(checker):
        return bool(checker(account))
    return _account_status_category(account) == "normal" and account.get("last_remote_check_result") != "pending"


def _account_unlimited_quota(account: dict[str, Any]) -> bool:
    checker = getattr(account_service, "is_unlimited_image_quota_account", None)
    return bool(checker(account)) if callable(checker) else False


def _account_for_api(
        account: dict[str, Any],
        group_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    group_id = _clean_text(account.get("group_id"))
    return account_row(
        account,
        available=_account_available(account),
        unlimited_quota=_account_unlimited_quota(account),
        group_name=(group_names or {}).get(group_id, group_id),
    )


def _account_detail_for_api(account: dict[str, Any]) -> dict[str, Any]:
    group_id = _clean_text(account.get("group_id"))
    group_names = _account_group_names()
    return account_detail(
        account,
        available=_account_available(account),
        unlimited_quota=_account_unlimited_quota(account),
        group_name=group_names.get(group_id, group_id),
    )


def _get_account_by_id(account_id: str) -> dict[str, Any] | None:
    getter = getattr(account_service, "get_account_by_id", None)
    if callable(getter):
        return getter(account_id)
    normalized = _clean_text(account_id).lower()
    return next(
        (
            account for account in account_service.list_accounts()
            if _clean_text(account.get("management_id")).lower() == normalized
        ),
        None,
    )


def _get_account_by_token_identity(access_token: str) -> dict[str, Any] | None:
    getter = getattr(account_service, "get_account_by_token_identity", None)
    if callable(getter):
        return getter(access_token)
    return account_service.get_account(access_token)


def _accounts_by_id() -> dict[str, dict[str, Any]]:
    return {
        account_id: account
        for account in account_service.list_accounts()
        if (account_id := _clean_text(account.get("management_id")).lower())
    }


def _partition_account_ids(account_ids: list[str]) -> tuple[list[str], list[str]]:
    requested = list(dict.fromkeys(
        _clean_text(account_id).lower()
        for account_id in account_ids
        if _clean_text(account_id)
    ))
    existing_ids = set(_accounts_by_id())
    return (
        [account_id for account_id in requested if account_id in existing_ids],
        [account_id for account_id in requested if account_id not in existing_ids],
    )


def _resolve_account_targets(
        account_ids: list[str],
        legacy_tokens: list[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    ids = list(dict.fromkeys(_clean_text(item).lower() for item in account_ids if _clean_text(item)))
    tokens: list[str] = []
    missing_ids: list[str] = []
    resolved_ids: list[str] = []
    resolver = getattr(account_service, "resolve_account_ids", None)
    if ids and callable(resolver):
        tokens, missing_ids = resolver(ids)
        missing = set(missing_ids)
        resolved_ids = [item for item in ids if item not in missing]
    elif ids:
        for account_id in ids:
            account = _get_account_by_id(account_id)
            token = _clean_text((account or {}).get("access_token"))
            if token:
                tokens.append(token)
                resolved_ids.append(account_id)
            else:
                missing_ids.append(account_id)

    for token in _unique_tokens(legacy_tokens or []):
        account = account_service.get_account(token)
        if account is None:
            continue
        tokens.append(_clean_text(account.get("access_token")) or token)
        account_id = _clean_text(account.get("management_id"))
        if account_id:
            resolved_ids.append(account_id)
    return _unique_tokens(tokens), list(dict.fromkeys(resolved_ids)), missing_ids


def _account_not_found_errors(account_ids: list[str]) -> list[dict[str, str]]:
    return [
        {"id": account_id, "code": "account_not_found", "message": "account not found"}
        for account_id in dict.fromkeys(
            _clean_text(item) for item in account_ids if _clean_text(item)
        )
    ]


def _account_targets(
        account_ids: list[str],
        legacy_tokens: list[str] | None = None,
) -> tuple[list[tuple[str, str]], list[str]]:
    tokens, _resolved_ids, missing_ids = _resolve_account_targets(account_ids, legacy_tokens)
    targets: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for token in tokens:
        account = account_service.get_account(token)
        account_id = _clean_text((account or {}).get("management_id"))
        current_token = _clean_text((account or {}).get("access_token")) or token
        if not account_id or account_id in seen_ids:
            continue
        seen_ids.add(account_id)
        targets.append((current_token, account_id))
    return targets, missing_ids


def _refresh_error_id_map(targets: list[tuple[str, str]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for token, account_id in targets:
        if not token or not account_id:
            continue
        mapping[token] = account_id
        mapping[anonymize_token(token)] = account_id
    return mapping


def _refresh_error_context() -> tuple[dict[str, str], list[str], list[str]]:
    targets: list[tuple[str, str]] = []
    sensitive_values: list[str] = []
    proxy_values: list[str] = []
    for account in account_service.list_accounts():
        token = _clean_text(account.get("access_token"))
        account_id = _clean_text(account.get("management_id"))
        if token and account_id:
            targets.append((token, account_id))
        for key in ("access_token", "refresh_token", "id_token"):
            value = _clean_text(account.get(key))
            if value:
                sensitive_values.append(value)
        proxy = _clean_text(account.get("proxy"))
        if proxy:
            proxy_values.append(proxy)
    return (
        _refresh_error_id_map(targets),
        _unique_tokens(sensitive_values),
        _unique_tokens(proxy_values),
    )


def _selected_refresh_context(
    targets: list[tuple[str, str]],
) -> tuple[list[str], list[str], dict[str, str], list[str], list[str]]:
    access_tokens = [token for token, _account_id in targets]
    target_ids = [account_id for _token, account_id in targets]
    id_by_token_hint = _refresh_error_id_map(targets)
    sensitive_values = list(access_tokens)
    proxy_values: list[str] = []
    for token, _account_id in targets:
        account = account_service.get_account(token) or {}
        for key in ("refresh_token", "id_token"):
            value = _clean_text(account.get(key))
            if value:
                sensitive_values.append(value)
        proxy = _clean_text(account.get("proxy"))
        if proxy:
            proxy_values.append(proxy)
    return access_tokens, target_ids, id_by_token_hint, sensitive_values, proxy_values


def _sanitize_refresh_errors(
        errors: object,
        *,
        id_by_token_hint: dict[str, str] | None = None,
        sensitive_values: list[str] | None = None,
        proxy_values: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(errors, list):
        return []
    result: list[dict[str, Any]] = []
    id_by_token_hint = id_by_token_hint or {}
    sensitive_values = [value for value in (sensitive_values or []) if value]
    proxy_values = [value for value in (proxy_values or []) if value]
    diagnostic_keys = (
        "failure_code",
        "failure_scope",
        "failure_capability",
        "failure_retryable",
        "failure_account_failure",
        "failure_retry_after",
        "status_code",
        "error_type",
    )
    for error in errors:
        if isinstance(error, dict):
            token_hint = _clean_text(error.get("token"))
            message = _clean_text(error.get("error") or error.get("message")) or "account refresh failed"
            code = _clean_text(error.get("code") or error.get("failure_code")) or "account_refresh_failed"
            item: dict[str, Any] = {
                "id": _clean_text(error.get("id")) or id_by_token_hint.get(token_hint, ""),
                "code": code,
                "message": message,
            }
            for key in diagnostic_keys:
                if key in error and error.get(key) is not None:
                    item[key] = error.get(key)
        else:
            item = {
                "id": "",
                "code": "account_refresh_failed",
                "message": _clean_text(error) or "account refresh failed",
            }
        item["message"] = sanitize_diagnostic_text(
            item["message"],
            sensitive_values=sensitive_values,
            proxy_values=proxy_values,
            limit=2000,
        )
        for key in diagnostic_keys:
            value = item.get(key)
            if isinstance(value, str):
                item[key] = sanitize_diagnostic_text(
                    value,
                    sensitive_values=sensitive_values,
                    proxy_values=proxy_values,
                    limit=500,
                )
        result.append(item)
    return result


def _project_accounts(account_ids: list[str]) -> list[dict[str, Any]]:
    requested_ids = list(dict.fromkeys(
        _clean_text(account_id).lower()
        for account_id in account_ids
        if _clean_text(account_id)
    ))
    if not requested_ids:
        return []
    accounts_by_id = _accounts_by_id()
    group_names = _account_group_names()
    return [
        _account_for_api(accounts_by_id[account_id], group_names)
        for account_id in requested_ids
        if account_id in accounts_by_id
    ]


def _account_operation_labels(
    targets: list[tuple[str, str]],
) -> dict[str, str]:
    labels: dict[str, str] = {}
    for token, account_id in targets:
        normalized_id = _clean_text(account_id)
        if not normalized_id:
            continue
        account = account_service.get_account(token) or {}
        labels[normalized_id] = _clean_text(account.get("email")) or normalized_id
    return labels


def _account_status_operation(
    status: str | None,
    operation: str | None,
) -> tuple[str, str, str]:
    requested = _clean_text(operation).lower()
    expected_status = {
        "enable": "正常",
        "disable": "禁用",
        "reset": "正常",
    }
    if requested in expected_status and status != expected_status[requested]:
        raise HTTPException(
            status_code=400,
            detail={"error": f"operation {requested} requires status {expected_status[requested]}"},
        )
    resolved = requested or "update"
    return {
        "enable": ("enable_account", "账号已启用", "账号启用失败"),
        "disable": ("disable_account", "账号已禁用", "账号禁用失败"),
        "reset": ("reset_account", "账号状态已重置", "账号状态重置失败"),
        "update": ("update_account", "账号已更新", "账号更新失败"),
    }[resolved]


def _account_mutation_events(
    *,
    action: str,
    success_ids: list[str] | None = None,
    removed_ids: list[str] | None = None,
    errors: list[dict[str, Any]] | None = None,
    labels: dict[str, str] | None = None,
    success_message: str,
    removed_message: str = "",
) -> list[dict[str, Any]]:
    labels = labels or {}
    normalized_errors = [
        item for item in (errors or []) if isinstance(item, dict)
    ]
    error_ids = {
        _clean_text(item.get("id"))
        for item in normalized_errors
        if _clean_text(item.get("id"))
    }
    raw_events: list[dict[str, Any]] = []
    sequence = 0
    for account_id in dict.fromkeys(success_ids or []):
        normalized_id = _clean_text(account_id)
        if not normalized_id or normalized_id in error_ids:
            continue
        sequence += 1
        raw_events.append({
            "sequence": sequence,
            "account_id": normalized_id,
            "account_label": labels.get(normalized_id, normalized_id),
            "action": action,
            "status": "success",
            "message": success_message,
        })
    for account_id in dict.fromkeys(removed_ids or []):
        normalized_id = _clean_text(account_id)
        if not normalized_id or normalized_id in error_ids:
            continue
        sequence += 1
        raw_events.append({
            "sequence": sequence,
            "account_id": normalized_id,
            "account_label": labels.get(normalized_id, normalized_id),
            "action": action,
            "status": "success" if action == "delete_account" else "failed",
            "message": removed_message or success_message,
        })
    for raw_error in normalized_errors:
        account_id = _clean_text(raw_error.get("id"))
        error_code = _clean_text(raw_error.get("code") or raw_error.get("failure_code"))
        error_message = _clean_text(raw_error.get("message") or raw_error.get("error"))
        if error_code and error_message:
            event_message = f"{error_code} · {error_message}"
        else:
            event_message = error_message or error_code or "account operation failed"
        sequence += 1
        raw_events.append({
            "sequence": sequence,
            "account_id": account_id,
            "account_label": labels.get(account_id, account_id),
            "action": action,
            "status": "failed",
            "message": event_message,
        })
    return normalize_account_operation_events(raw_events)


def _account_mutation_payload(
        *,
        updated_ids: list[str] | None = None,
        removed_ids: list[str] | None = None,
        errors: list[dict[str, Any]] | None = None,
        events: list[dict[str, Any]] | None = None,
        include_items: bool = True,
        **counts: Any,
) -> dict[str, Any]:
    updated = list(dict.fromkeys(_clean_text(item) for item in (updated_ids or []) if _clean_text(item)))
    removed = list(dict.fromkeys(_clean_text(item) for item in (removed_ids or []) if _clean_text(item)))
    removed_set = set(removed)
    updated = [account_id for account_id in updated if account_id not in removed_set]
    if "updated" in counts:
        counts["updated"] = len(updated)
    if "removed" in counts:
        counts["removed"] = len(removed)
    payload = {
        **counts,
        "updated_ids": updated,
        "removed_ids": removed,
        "errors": list(errors or []),
        "events": normalize_account_operation_events(events or []),
        "items": _project_accounts(updated) if include_items else [],
    }
    return payload


def _account_mutation_response(**mutation: Any) -> dict[str, Any]:
    payload = _account_mutation_payload(**mutation)
    total = len({
        *payload["updated_ids"],
        *payload["removed_ids"],
        *(
            _clean_text(item.get("id"))
            for item in payload["errors"]
            if isinstance(item, dict) and _clean_text(item.get("id"))
        ),
    })
    payload.update(project_account_operation_presentation({
        "total": total,
        "processed": total,
        "done": True,
        "events": payload["events"],
        "result": payload,
    }))
    return payload


def _init_account_mutation_progress(
    progress_id: str,
    *,
    total: int,
    missing_ids: list[str],
    action: str,
) -> None:
    account_service.init_refresh_progress(progress_id, total)
    for missing_id in missing_ids:
        account_service.update_refresh_progress(
            progress_id,
            missing_id,
            account_id=missing_id,
            account_label=missing_id,
            action=action,
            event_status="failed",
            event_message="account_not_found · 账号不存在",
        )


def _publish_account_mutation_stage(
    progress_id: str,
    stage: str,
    total: int,
) -> None:
    count = max(0, int(total or 0))
    labels = {
        "prepare_accounts": f"\u6b63\u5728\u51c6\u5907 {count} \u4e2a\u8d26\u53f7",
        "save_accounts": f"\u6b63\u5728\u4fdd\u5b58 {count} \u4e2a\u8d26\u53f7",
        "publish_results": "\u8d26\u53f7\u53d8\u66f4\u5df2\u4fdd\u5b58\uff0c\u6b63\u5728\u6574\u7406\u7ed3\u679c",
    }
    account_service.update_refresh_progress_stage(
        progress_id,
        stage,
        labels.get(stage, "\u6b63\u5728\u5904\u7406\u8d26\u53f7"),
    )


def _publish_account_mutation_progress(
    progress_id: str,
    *,
    targets: list[tuple[str, str]],
    labels: dict[str, str],
    events: list[dict[str, Any]],
) -> None:
    events_by_id = {
        _clean_text(event.get("account_id")): event
        for event in events
        if isinstance(event, dict) and _clean_text(event.get("account_id"))
    }
    for token, account_id in targets:
        event = events_by_id.get(account_id, {})
        event_status = _clean_text(event.get("status")) or "info"
        account = account_service.get_account(token) or {
            "management_id": account_id,
            "email": labels.get(account_id, account_id),
            "status": "异常" if event_status == "failed" else "正常",
            "quota": 0,
        }
        account_service.update_refresh_progress(
            progress_id,
            token,
            account,
            account_id=account_id,
            account_label=labels.get(account_id, account_id),
            action=_clean_text(event.get("action")),
            event_status=event_status,
            event_message=_clean_text(event.get("message")),
        )


def _account_operation_progress_for_api(
    progress: dict[str, Any],
    *,
    legacy_sync_alias: bool = False,
) -> dict[str, Any]:
    payload = {
        key: progress.get(key)
        for key in (
            "total",
            "processed",
            "done",
            "stage",
            "stage_label",
            "status_counts",
            "total_quota",
        )
        if key in progress
    }
    payload["events"] = normalize_account_operation_events(progress.get("events"))
    payload["error"] = "账号操作失败" if progress.get("error") else None
    result = progress.get("result")
    if not isinstance(result, dict):
        payload["result"] = None
        payload.update(project_account_operation_presentation(payload))
        return payload
    id_by_token_hint, sensitive_values, proxy_values = _refresh_error_context()
    updated_ids = [
        _clean_text(item) for item in result.get("updated_ids", []) if _clean_text(item)
    ]
    removed_ids = [
        _clean_text(item) for item in result.get("removed_ids", []) if _clean_text(item)
    ]
    result_counts: dict[str, int] = {
        "skipped": max(0, int(result.get("skipped") or 0)),
    }
    if "synced" in result:
        synced = max(0, int(result.get("synced") or 0))
        if legacy_sync_alias:
            result_counts["refreshed"] = synced
        else:
            result_counts["synced"] = synced
    elif "refreshed" in result:
        result_counts["refreshed"] = max(0, int(result.get("refreshed") or 0))
    for key in ("updated", "removed", "added"):
        if key in result:
            result_counts[key] = max(0, int(result.get(key) or 0))
    payload["result"] = _account_mutation_payload(
        **result_counts,
        updated_ids=updated_ids,
        removed_ids=removed_ids,
        errors=_sanitize_refresh_errors(
            result.get("errors"),
            id_by_token_hint=id_by_token_hint,
            sensitive_values=sensitive_values,
            proxy_values=proxy_values,
        ),
        events=normalize_account_operation_events(result.get("events")),
    )
    payload.update(project_account_operation_presentation(
        payload,
        legacy_sync_alias=legacy_sync_alias,
    ))
    return payload


def _status_matches_filter(account: dict[str, Any], status_filter: str) -> bool:
    status_filter = status_filter.strip().lower()
    if not status_filter or status_filter == "all":
        return True
    if status_filter in {"normal", "limited", "abnormal", "disabled"}:
        return _account_status_category(account) == status_filter
    status = _clean_text(account.get("status"))
    status_map = {
        "normal": "\u6b63\u5e38",
        "limited": "\u9650\u6d41",
        "abnormal": "\u5f02\u5e38",
        "disabled": "\u7981\u7528",
    }
    expected = status_map.get(status_filter)
    return status == expected if expected else status.lower() == status_filter


def _account_matches_keyword(account: dict[str, Any], keyword: str) -> bool:
    needle = keyword.strip().lower()
    if not needle:
        return True
    fields = (
        account.get("access_token"),
        account.get("email"),
        account.get("user_id"),
        account.get("type"),
        account.get("source_type"),
        account.get("status"),
        account.get("proxy"),
        account.get("group_id"),
    )
    return any(needle in _clean_text(value).lower() for value in fields)


def _account_matches_group(account: dict[str, Any], group_id: str) -> bool:
    group_id = group_id.strip()
    if not group_id or group_id == "all":
        return True
    current = _clean_text(account.get("group_id"))
    if group_id == "__ungrouped__":
        return not current
    return current == group_id


def _account_matches_filters(
        account: dict[str, Any],
        *,
        keyword: str,
        status: str,
        group_id: str,
) -> bool:
    return (
        _account_matches_keyword(account, keyword)
        and _status_matches_filter(account, status)
        and _account_matches_group(account, group_id)
    )


def _filtered_accounts(
        accounts: list[dict[str, Any]],
        *,
        keyword: str,
        status: str,
        group_id: str,
) -> list[dict[str, Any]]:
    return [
        account
        for account in accounts
        if _account_matches_filters(
            account,
            keyword=keyword,
            status=status,
            group_id=group_id,
        )
    ]


def _account_selection_members(
        selection: AccountSelectionScope,
) -> list[tuple[str, str]]:
    accounts = account_service.list_accounts()
    if selection.mode == "filter":
        accounts = _filtered_accounts(
            accounts,
            keyword=selection.keyword,
            status=selection.status,
            group_id=selection.group_id,
        )

    members: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for account in accounts:
        account_id = _clean_text(account.get("management_id")).lower()
        access_token = _clean_text(account.get("access_token"))
        if not account_id or not access_token or account_id in seen_ids:
            continue
        seen_ids.add(account_id)
        members.append((access_token, account_id))
    return members


def _account_selection_targets(
        selection: AccountSelectionScope | None,
        account_ids: list[str] | None = None,
        legacy_tokens: list[str] | None = None,
        *,
        default_all: bool = False,
) -> tuple[list[tuple[str, str]], list[str]]:
    legacy_ids = list(account_ids or [])
    legacy_tokens = list(legacy_tokens or [])
    mode = selection.mode if selection is not None else ("all" if default_all and not legacy_ids and not legacy_tokens else "explicit")

    if mode == "explicit":
        selected_ids = [*(selection.account_ids if selection is not None else []), *legacy_ids]
        return _account_targets(selected_ids, legacy_tokens)

    excluded_ids = {
        _clean_text(account_id).lower()
        for account_id in (selection.excluded_account_ids if selection is not None else [])
        if _clean_text(account_id)
    }
    scope = selection or AccountSelectionScope(mode="all")
    targets = [
        (access_token, account_id)
        for access_token, account_id in _account_selection_members(scope)
        if account_id not in excluded_ids
    ]
    return targets, []


def _account_selection_preview(selection: AccountSelectionScope) -> dict[str, Any]:
    if selection.mode == "explicit":
        targets, missing_ids = _account_selection_targets(selection)
        return {
            "matching_count": len(targets),
            "selected_count": len(targets),
            "excluded_account_ids": [],
            "errors": _account_not_found_errors(missing_ids),
        }

    excluded_ids = {
        _clean_text(account_id).lower()
        for account_id in selection.excluded_account_ids
        if _clean_text(account_id)
    }
    matching_ids = [account_id for _access_token, account_id in _account_selection_members(selection)]
    matching_set = set(matching_ids)
    valid_excluded_ids = [
        account_id for account_id in selection.excluded_account_ids
        if _clean_text(account_id).lower() in matching_set
    ]
    valid_excluded_ids = list(dict.fromkeys(
        _clean_text(account_id).lower()
        for account_id in valid_excluded_ids
        if _clean_text(account_id).lower() in excluded_ids
    ))
    return {
        "matching_count": len(matching_ids),
        "selected_count": max(0, len(matching_ids) - len(valid_excluded_ids)),
        "excluded_account_ids": valid_excluded_ids,
        "errors": [],
    }


def _accounts_page(
        *,
        page: int,
        page_size: int,
        keyword: str,
        status: str,
        group_id: str,
) -> dict[str, Any]:
    items = account_service.list_accounts()
    filtered = _filtered_accounts(
        items,
        keyword=keyword,
        status=status,
        group_id=group_id,
    )
    safe_page = max(1, page)
    safe_page_size = max(1, min(page_size, 500))
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    group_names = _account_group_names()
    return {
        "items": [_account_for_api(item, group_names) for item in filtered[start:end]],
        "total": len(filtered),
        "all_total": len(items),
        "page": safe_page,
        "page_size": safe_page_size,
    }


def _account_zip_bytes(items: list[dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, item in enumerate(items, start=1):
            raw_name = item.get("email") or item.get("account_id") or f"account-{index:03d}"
            base_name = _safe_export_name(raw_name, f"account-{index:03d}")
            name = base_name
            suffix = 2
            while name in used_names:
                name = f"{base_name}-{suffix}"
                suffix += 1
            used_names.add(name)
            archive.writestr(
                f"{name}.json",
                json.dumps(item, ensure_ascii=False, indent=2) + "\n",
            )
    return buf.getvalue()


def _account_export_summary(requested: int, exported: int) -> dict[str, int]:
    requested = max(0, int(requested))
    exported = max(0, int(exported))
    return {
        "requested": requested,
        "exported": exported,
        "skipped": max(0, requested - exported),
    }


def _account_export_headers(summary: dict[str, int]) -> dict[str, str]:
    return {
        "X-Export-Requested": str(summary["requested"]),
        "X-Exported": str(summary["exported"]),
        "X-Skipped": str(summary["skipped"]),
    }


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/auth/users", response_model=UserKeyListView)
    async def list_user_keys(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        items = await run_in_threadpool(auth_service.list_keys, role="user")
        return {"items": items}

    @router.post("/api/auth/users", response_model=UserKeyCreateResult)
    async def create_user_key(body: UserKeyCreateRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            item, raw_key = await run_in_threadpool(auth_service.create_key, role="user", name=body.name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        return {"item": item, "raw_key": raw_key}

    @router.post("/api/auth/users/{key_id}", response_model=UserKeyUpdateResult)
    async def update_user_key(
            key_id: str,
            body: UserKeyUpdateRequest,
            authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        updates = {
            key: value
            for key, value in {
                "name": body.name,
                "enabled": body.enabled,
                "key": body.key,
            }.items()
            if value is not None
        }
        if not updates:
            raise HTTPException(status_code=400, detail={"error": "还没有检测到改动，请修改后再保存"})
        try:
            item = await run_in_threadpool(auth_service.update_key, key_id, updates, role="user")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        if item is None:
            raise HTTPException(status_code=404, detail={"error": "这条用户密钥不存在，可能已经被删除"})
        return {"item": item}

    @router.delete("/api/auth/users/{key_id}", response_model=UserKeyDeleteResult)
    async def delete_user_key(key_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        deleted = await run_in_threadpool(auth_service.delete_key, key_id, role="user")
        if not deleted:
            raise HTTPException(status_code=404, detail={"error": "这条用户密钥不存在，可能已经被删除"})
        return {"deleted_id": key_id}

    @router.get("/api/accounts")
    async def get_accounts(
            page: int = Query(default=1, ge=1),
            page_size: int = Query(default=500, ge=1, le=500),
            keyword: str = "",
            status: str = "all",
            group_id: str = "all",
            authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        return _accounts_page(
            page=page,
            page_size=page_size,
            keyword=keyword,
            status=status,
            group_id=group_id,
        )

    @router.post("/api/accounts/selection-preview")
    async def preview_account_selection(
        body: AccountSelectionPreviewRequest,
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        return await run_in_threadpool(_account_selection_preview, body.selection)

    @router.get("/api/accounts/{account_id}")
    async def get_account_detail(account_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        account = _get_account_by_id(account_id)
        if account is None:
            raise HTTPException(status_code=404, detail={"error": "account not found"})
        return {"item": _account_detail_for_api(account)}

    @router.post(
        "/api/accounts/{account_id}/test",
        response_model=AccountTestResult,
    )
    async def test_account(
        account_id: str,
        body: AccountTestRequest,
        authorization: str | None = Header(default=None),
    ):
        identity = require_admin(authorization)
        if _get_account_by_id(account_id) is None:
            raise HTTPException(status_code=404, detail={"error": "account not found"})
        payload = {**body.model_dump(), "account_id": account_id}
        call = LoggedCall(
            identity,
            "/api/accounts/{account_id}/test",
            body.model,
            "账号画图测试" if body.mode == "image" else "账号对话测试",
            request_text=body.prompt,
            image_request=body.mode == "image",
        )
        return await call.run(account_test_service.execute, payload)

    @router.get("/api/accounts/{account_id}/access-token")
    async def get_account_access_token(
        account_id: str,
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        account = _get_account_by_id(account_id)
        if account is None:
            raise HTTPException(status_code=404, detail={"error": "account not found"})
        access_token = _clean_text(account.get("access_token"))
        if not access_token:
            raise HTTPException(status_code=404, detail={"error": "access token not found"})
        return JSONResponse(
            {"access_token": access_token},
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/api/accounts/{account_id}/refresh-token")
    async def get_account_refresh_token(
        account_id: str,
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        account = _get_account_by_id(account_id)
        if account is None:
            raise HTTPException(status_code=404, detail={"error": "account not found"})
        refresh_token = _clean_text(account.get("refresh_token"))
        if not refresh_token:
            raise HTTPException(status_code=404, detail={"error": "refresh token not found"})
        return JSONResponse(
            {"refresh_token": refresh_token},
            headers={"Cache-Control": "no-store"},
        )


    @router.get("/api/account-groups")
    async def list_account_groups(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return _account_group_payload()

    @router.post("/api/account-groups")
    async def save_account_group(body: AccountGroupRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            return _upsert_account_group(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.delete("/api/account-groups/{group_id}")
    async def delete_account_group(group_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        normalized = _account_group_id(group_id)
        groups = _config_dict_list("account_groups")
        next_groups = [group for group in groups if _account_group_id(group.get("id")) != normalized]
        if len(next_groups) == len(groups):
            raise HTTPException(status_code=404, detail={"error": "account group not found"})
        updated = config.update({"account_groups": next_groups})
        targets = [
            (
                _clean_text(account.get("access_token")),
                _clean_text(account.get("management_id")),
            )
            for account in account_service.list_accounts()
            if _clean_text(account.get("group_id")) == normalized
            and _clean_text(account.get("access_token"))
            and _clean_text(account.get("management_id"))
        ]
        if targets:
            result = await run_in_threadpool(
                account_service.update_accounts,
                [token for token, _account_id in targets],
                {"group_id": ""},
                quiet=True,
            )
        else:
            result = {
                "updated_ids": [],
                "removed_ids": [],
                "missing_tokens": [],
            }
        updated_ids = list(result.get("updated_ids") or [])
        removed_ids = list(result.get("removed_ids") or [])
        id_by_token = {token: account_id for token, account_id in targets}
        removed_ids.extend(
            id_by_token[token]
            for token in result.get("missing_tokens") or []
            if token in id_by_token
        )
        return {
            "deleted": normalized,
            **_account_group_payload(updated.get("account_groups", [])),
            **_account_mutation_payload(
                updated_ids=updated_ids,
                removed_ids=removed_ids,
            ),
        }

    @router.post("/api/accounts")
    async def create_accounts(body: AccountCreateRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        account_payloads = [item for item in body.accounts if isinstance(item, dict)]
        payload_tokens = [_account_payload_token(item) for item in account_payloads]
        tokens = _unique_tokens([*body.tokens, *payload_tokens])
        if not tokens:
            raise HTTPException(status_code=400, detail={"error": "tokens is required"})
        try:
            if account_payloads:
                result = await run_in_threadpool(
                    account_service.add_account_items,
                    account_payloads,
                    return_items=False,
                    restore=body.restore,
                )
                payload_token_set = set(_unique_tokens(payload_tokens))
                extra_tokens = [token for token in tokens if token not in payload_token_set]
                if extra_tokens:
                    extra_result = await run_in_threadpool(
                        account_service.add_accounts,
                        extra_tokens,
                        return_items=False,
                    )
                    result["added"] = int(result.get("added") or 0) + int(extra_result.get("added") or 0)
                    result["skipped"] = int(result.get("skipped") or 0) + int(extra_result.get("skipped") or 0)
            else:
                result = await run_in_threadpool(
                    account_service.add_accounts,
                    tokens,
                    return_items=False,
                )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": str(exc)},
            ) from exc

        targets: list[tuple[str, str]] = []
        sensitive_values = list(tokens)
        proxy_values: list[str] = []
        for token in tokens:
            account = _get_account_by_token_identity(token)
            account_id = _clean_text((account or {}).get("management_id"))
            active_token = _clean_text((account or {}).get("access_token")) or token
            if account_id:
                targets.append((active_token, account_id))
            for key in ("refresh_token", "id_token"):
                value = _clean_text((account or {}).get(key))
                if value:
                    sensitive_values.append(value)
            proxy = _clean_text((account or {}).get("proxy"))
            if proxy:
                proxy_values.append(proxy)

        sync_after_import = (
            bool(body.sync_after_import)
            if body.sync_after_import is not None
            else bool(body.refresh)
            if body.refresh is not None
            else True
        )
        if not sync_after_import:
            updated_ids = [account_id for _token, account_id in targets]
            labels = _account_operation_labels(targets)
            payload = _account_mutation_response(
                added=max(0, int(result.get("added") or 0)),
                skipped=max(0, int(result.get("skipped") or 0)),
                synced=0,
                updated_ids=updated_ids,
                events=_account_mutation_events(
                    action="import_account",
                    success_ids=updated_ids,
                    labels=labels,
                    success_message="\u8d26\u53f7\u5df2\u4fdd\u5b58",
                ),
                include_items=body.return_items,
            )
            if body.sync_after_import is None and body.refresh is not None:
                payload["refreshed"] = payload["synced"]
            return payload

        refresh_result = await run_in_threadpool(
            account_service.sync_accounts_and_quota,
            _unique_tokens([active_token for active_token, _account_id in targets]),
        )
        updated_ids, removed_ids = _partition_account_ids([
            account_id for _token, account_id in targets
        ])
        sanitized_errors = _sanitize_refresh_errors(
            refresh_result.get("errors"),
            id_by_token_hint=_refresh_error_id_map(targets),
            sensitive_values=sensitive_values,
            proxy_values=proxy_values,
        )
        labels = _account_operation_labels(targets)
        payload = _account_mutation_response(
            added=max(0, int(result.get("added") or 0)),
            skipped=max(0, int(result.get("skipped") or 0)),
            synced=max(0, int(refresh_result.get("synced") or 0)),
            updated_ids=updated_ids,
            removed_ids=removed_ids,
            errors=sanitized_errors,
            events=_account_mutation_events(
                action="import_account",
                success_ids=updated_ids,
                removed_ids=removed_ids,
                errors=sanitized_errors,
                labels=labels,
                success_message="\u8d26\u53f7\u5df2\u4fdd\u5b58",
                removed_message="\u8d26\u53f7\u4fdd\u5b58\u540e\u5df2\u88ab\u79fb\u9664",
            ),
            include_items=body.return_items,
        )
        if body.sync_after_import is None and body.refresh is not None:
            payload["refreshed"] = payload["synced"]
        return payload

    @router.delete("/api/accounts")
    async def delete_accounts(body: AccountDeleteRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        if not body.selection and not body.account_ids and not body.tokens:
            raise HTTPException(status_code=400, detail={"error": "account_ids is required"})
        targets, missing_ids = _account_selection_targets(
            body.selection,
            body.account_ids,
            body.tokens,
        )
        if not targets:
            raise HTTPException(status_code=400, detail={"error": "no valid accounts selected"})
        labels = _account_operation_labels(targets)
        tokens = [token for token, _account_id in targets]
        target_ids = [account_id for _token, account_id in targets]
        id_by_token = {token: account_id for token, account_id in targets}
        progress_id = str(uuid.uuid4())
        initial_errors = _account_not_found_errors(missing_ids)
        _init_account_mutation_progress(
            progress_id,
            total=len(targets) + len(missing_ids),
            missing_ids=missing_ids,
            action="delete_account",
        )
        _publish_account_mutation_stage(progress_id, "prepare_accounts", len(targets))

        async def _do_delete_accounts() -> None:
            try:
                raw_result = await run_in_threadpool(
                    account_service.delete_accounts,
                    tokens,
                    return_items=False,
                    progress_callback=lambda stage, total: _publish_account_mutation_stage(
                        progress_id,
                        stage,
                        total,
                    ),
                )
                removed_ids = list(raw_result.get("removed_ids") or [])
                missing_target_ids = [
                    id_by_token[token]
                    for token in raw_result.get("missing_tokens") or []
                    if token in id_by_token
                ]
                errors = _account_not_found_errors([
                    *missing_ids,
                    *missing_target_ids,
                ])
                events = _account_mutation_events(
                    action="delete_account",
                    removed_ids=removed_ids,
                    errors=errors,
                    labels=labels,
                    success_message="\u8d26\u53f7\u5df2\u5220\u9664",
                )
                result = _account_mutation_payload(
                    removed=max(0, int(raw_result.get("removed") or 0)),
                    removed_ids=removed_ids,
                    errors=errors,
                    events=events,
                    include_items=False,
                )
                _publish_account_mutation_progress(
                    progress_id,
                    targets=targets,
                    labels=labels,
                    events=events,
                )
                account_service.finish_refresh_progress(progress_id, result)
            except Exception:
                account_service.finish_refresh_progress(
                    progress_id,
                    error="account deletion failed",
                )

        _schedule_account_operation(_do_delete_accounts())
        return {
            "progress_id": progress_id,
            "target_ids": target_ids,
            "errors": initial_errors,
        }

    @router.post("/api/accounts/import-cleanup")
    async def cleanup_imported_abnormal_accounts(
            body: AccountImportCleanupRequest,
            authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        requested_ids = list(dict.fromkeys(
            _clean_text(item).lower() for item in body.account_ids if _clean_text(item)
        ))
        legacy_tokens = _unique_tokens(body.access_tokens)
        if not requested_ids and not legacy_tokens:
            raise HTTPException(status_code=400, detail={"error": "account_ids is required"})
        targets, missing_ids = _account_targets(requested_ids, legacy_tokens)
        abnormal_targets = [
            (token, account_id)
            for token, account_id in targets
            if _status_matches_filter(account_service.get_account(token) or {}, "abnormal")
        ]
        labels = _account_operation_labels(abnormal_targets)
        removed_ids: list[str] = []
        deletion_missing_ids: list[str] = []
        if body.remove and abnormal_targets:
            delete_result = account_service.delete_accounts(
                [token for token, _account_id in abnormal_targets],
                return_items=False,
            )
            removed_ids = list(delete_result.get("removed_ids") or [])
            id_by_token = {token: account_id for token, account_id in abnormal_targets}
            deletion_missing_ids = [
                id_by_token[token]
                for token in delete_result.get("missing_tokens") or []
                if token in id_by_token
            ]
        return _account_mutation_payload(
            checked=len(targets),
            abnormal=len(abnormal_targets),
            removed=len(removed_ids),
            removed_ids=removed_ids,
            errors=_account_not_found_errors([*missing_ids, *deletion_missing_ids]),
            events=(
                _account_mutation_events(
                    action="delete_account",
                    removed_ids=removed_ids,
                    errors=_account_not_found_errors([*missing_ids, *deletion_missing_ids]),
                    labels=labels,
                    success_message="账号已删除",
                    removed_message="导入后异常账号已删除",
                )
                if body.remove
                else []
            ),
            include_items=False,
        )

    @router.post("/api/accounts/refresh-access-token")
    async def refresh_access_tokens(
        body: AccountOperationRequest,
        authorization: str | None = Header(default=None),
    ):
        """Force RT-to-AT exchange only; no account metadata or quota request."""
        require_admin(authorization)
        targets, missing_ids = _account_selection_targets(
            body.selection,
            body.account_ids,
            body.access_tokens,
            default_all=False,
        )
        if not targets:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "no valid accounts selected",
                    "errors": _account_not_found_errors(missing_ids),
                },
            )

        progress_id = str(uuid.uuid4())
        (
            access_tokens,
            target_ids,
            id_by_token_hint,
            sensitive_values,
            proxy_values,
        ) = _selected_refresh_context(targets)
        account_service.init_refresh_progress(
            progress_id,
            len(access_tokens) + len(missing_ids),
        )
        for missing_id in missing_ids:
            account_service.update_refresh_progress(
                progress_id,
                missing_id,
                account_id=missing_id,
                action="refresh_access_token",
                event_status="failed",
                event_message="account_not_found · \u8d26\u53f7\u4e0d\u5b58\u5728",
            )

        async def _do_refresh_access_tokens():
            try:
                raw_result = await run_in_threadpool(
                    account_service.refresh_access_tokens,
                    access_tokens,
                    progress_id,
                    finalize_progress=False,
                )
                result = _account_mutation_payload(
                    refreshed=max(0, int(raw_result.get("refreshed") or 0)),
                    skipped=max(0, int(raw_result.get("skipped") or 0)),
                    updated_ids=list(raw_result.get("updated_ids") or []),
                    removed_ids=list(raw_result.get("removed_ids") or []),
                    errors=[
                        *_account_not_found_errors(missing_ids),
                        *_sanitize_refresh_errors(
                            raw_result.get("errors"),
                            id_by_token_hint=id_by_token_hint,
                            sensitive_values=sensitive_values,
                            proxy_values=proxy_values,
                        ),
                    ],
                    include_items=False,
                )
                account_service.finish_refresh_progress(
                    progress_id,
                    result,
                )
            except Exception:
                account_service.finish_refresh_progress(
                    progress_id,
                    error="access token refresh failed",
                )

        _schedule_account_operation(_do_refresh_access_tokens())
        return {
            "progress_id": progress_id,
            "target_ids": target_ids,
            "errors": _account_not_found_errors(missing_ids),
        }

    @router.post("/api/accounts/sync")
    @router.post("/api/accounts/refresh")
    async def sync_accounts_and_quota(
        body: AccountOperationRequest,
        authorization: str | None = Header(default=None),
    ):
        """Synchronize remote account metadata and image quota.

        The /refresh path remains as a compatibility alias for existing clients.
        """
        require_admin(authorization)
        targets, missing_ids = _account_selection_targets(
            body.selection,
            body.account_ids,
            body.access_tokens,
            default_all=True,
        )
        if not targets:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "no valid accounts selected",
                    "errors": _account_not_found_errors(missing_ids),
                },
            )

        progress_id = str(uuid.uuid4())
        (
            access_tokens,
            target_ids,
            id_by_token_hint,
            sensitive_values,
            proxy_values,
        ) = _selected_refresh_context(targets)
        account_service.init_refresh_progress(
            progress_id,
            len(access_tokens) + len(missing_ids),
        )
        for missing_id in missing_ids:
            account_service.update_refresh_progress(
                progress_id,
                missing_id,
                account_id=missing_id,
                action="sync_account",
                event_status="failed",
                event_message="account_not_found · \u8d26\u53f7\u4e0d\u5b58\u5728",
            )

        async def _do_sync_accounts_and_quota():
            try:
                raw_result = await run_in_threadpool(
                    account_service.sync_accounts_and_quota,
                    access_tokens,
                    progress_id,
                    finalize_progress=False,
                )
                updated_ids, removed_ids = _partition_account_ids(target_ids)
                result = _account_mutation_payload(
                    synced=max(0, int(raw_result.get("synced") or 0)),
                    updated_ids=updated_ids,
                    removed_ids=removed_ids,
                    errors=[
                        *_account_not_found_errors(missing_ids),
                        *_sanitize_refresh_errors(
                            raw_result.get("errors"),
                            id_by_token_hint=id_by_token_hint,
                            sensitive_values=sensitive_values,
                            proxy_values=proxy_values,
                        ),
                    ],
                    include_items=False,
                )
                account_service.finish_refresh_progress(
                    progress_id,
                    result,
                )
            except Exception:
                account_service.finish_refresh_progress(
                    progress_id,
                    error="account and quota synchronization failed",
                )

        _schedule_account_operation(_do_sync_accounts_and_quota())

        return {
            "progress_id": progress_id,
            "target_ids": target_ids,
            "errors": _account_not_found_errors(missing_ids),
        }

    async def get_account_operation_progress(
        progress_id: str,
        *,
        legacy_sync_alias: bool = False,
    ) -> dict[str, Any]:
        progress = account_service.get_refresh_progress(progress_id)
        if progress is None:
            raise HTTPException(status_code=404, detail={"error": "progress not found"})
        return _account_operation_progress_for_api(
            progress,
            legacy_sync_alias=legacy_sync_alias,
        )

    @router.get("/api/accounts/operations/{progress_id}")
    async def get_canonical_account_operation_progress(
        progress_id: str,
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        return await get_account_operation_progress(progress_id)

    @router.get("/api/accounts/refresh/progress/{progress_id}")
    async def get_legacy_account_refresh_progress(
        progress_id: str,
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        return await get_account_operation_progress(
            progress_id,
            legacy_sync_alias=True,
        )

    @router.post("/api/accounts/export")
    async def export_accounts(body: AccountExportRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        targets, missing_ids = _account_selection_targets(
            body.selection,
            body.account_ids,
            body.access_tokens,
            default_all=True,
        )
        missing_legacy_tokens = [
            token
            for token in _unique_tokens(body.access_tokens)
            if _get_account_by_token_identity(token) is None
        ]
        if missing_ids or missing_legacy_tokens:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "one or more accounts were not found",
                    "errors": [
                        *_account_not_found_errors(missing_ids),
                        *[
                            {
                                "id": anonymize_token(token),
                                "code": "account_not_found",
                                "message": "legacy access token was not found",
                            }
                            for token in missing_legacy_tokens
                        ],
                    ],
                },
            )
        if not targets:
            raise HTTPException(status_code=400, detail={"error": "no valid accounts selected"})
        access_tokens = [token for token, _account_id in targets]
        items = account_service.build_export_items(
            access_tokens,
            full=body.format != "zip",
        )
        if not items:
            raise HTTPException(status_code=400, detail={"error": "没有可导出的账号"})
        summary = _account_export_summary(len(targets), len(items))
        export_headers = _account_export_headers(summary)

        timestamp = _download_timestamp()
        if body.format == "zip":
            content = _account_zip_bytes(items)
            return Response(
                content,
                media_type="application/zip",
                headers={
                    **export_headers,
                    "Content-Disposition": f'attachment; filename="codex-accounts-{timestamp}.zip"',
                },
            )

        if body.format == "txt":
            content = "\n".join(str(item.get("access_token") or "") for item in items) + "\n"
            return Response(
                content,
                media_type="text/plain; charset=utf-8",
                headers={
                    **export_headers,
                    "Content-Disposition": f'attachment; filename="codex-access-tokens-{timestamp}.txt"',
                },
            )

        payload: dict[str, Any] | list[dict[str, Any]] = items[0] if len(items) == 1 else items
        return Response(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            media_type="application/json",
            headers={
                **export_headers,
                "Content-Disposition": f'attachment; filename="codex-accounts-{timestamp}.json"',
            },
        )

    @router.post("/api/accounts/update")
    async def update_account(body: AccountUpdateRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        account_id = _clean_text(body.id).lower()
        legacy_token = _clean_text(body.access_token)
        if account_id:
            current = _get_account_by_id(account_id)
        elif legacy_token:
            current = account_service.get_account(legacy_token)
            account_id = _clean_text((current or {}).get("management_id"))
        else:
            raise HTTPException(status_code=400, detail={"error": "account id is required"})
        if current is None or not account_id:
            raise HTTPException(status_code=404, detail={"error": "account not found"})
        updates = {
            key: value
            for key, value in {
                "type": body.type,
                "source_type": body.source_type,
                "quota": body.quota,
                "proxy": body.proxy,
                "group_id": body.group_id,
            }.items()
            if value is not None
        }
        if not updates:
            raise HTTPException(status_code=400, detail={"error": "no updates provided"})
        access_token = _clean_text(current.get("access_token"))
        labels = _account_operation_labels([(access_token, account_id)])
        try:
            account = account_service.update_account(access_token, updates)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": str(exc)},
            ) from exc
        if account is None:
            if _get_account_by_id(account_id) is None:
                payload = _account_mutation_response(
                    updated=0,
                    removed=1,
                    removed_ids=[account_id],
                    events=_account_mutation_events(
                        action="update_account",
                        removed_ids=[account_id],
                        labels=labels,
                        success_message="账号已更新",
                        removed_message="账号更新失败",
                    ),
                    include_items=False,
                )
                payload["item"] = None
                return payload
            raise HTTPException(status_code=404, detail={"error": "account not found"})
        payload = _account_mutation_response(
            updated=1,
            removed=0,
            updated_ids=[account_id],
            events=_account_mutation_events(
                action="update_account",
                success_ids=[account_id],
                labels=labels,
                success_message="账号已更新",
            ),
        )
        payload["item"] = _account_for_api(account, _account_group_names())
        return payload
    @router.post("/api/accounts/batch-update")
    async def batch_update_accounts(body: AccountBatchUpdateRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        if not body.selection and not body.account_ids and not body.access_tokens:
            raise HTTPException(status_code=400, detail={"error": "account_ids is required"})
        updates = {key: value for key, value in {"status": body.status}.items() if value is not None}
        if not updates:
            raise HTTPException(status_code=400, detail={"error": "no updates provided"})
        action, success_message, failure_message = _account_status_operation(
            body.status,
            body.operation,
        )
        targets, missing_ids = _account_selection_targets(
            body.selection,
            body.account_ids,
            body.access_tokens,
        )
        if not targets:
            raise HTTPException(status_code=400, detail={"error": "no valid accounts selected"})
        labels = _account_operation_labels(targets)
        tokens = [token for token, _account_id in targets]
        target_ids = [account_id for _token, account_id in targets]
        id_by_token = {token: account_id for token, account_id in targets}
        progress_id = str(uuid.uuid4())
        initial_errors = _account_not_found_errors(missing_ids)
        _init_account_mutation_progress(
            progress_id,
            total=len(targets) + len(missing_ids),
            missing_ids=missing_ids,
            action=action,
        )
        _publish_account_mutation_stage(progress_id, "prepare_accounts", len(targets))

        async def _do_batch_update_accounts() -> None:
            try:
                raw_result = await run_in_threadpool(
                    account_service.update_accounts,
                    tokens,
                    updates,
                    quiet=True,
                    progress_callback=lambda stage, total: _publish_account_mutation_stage(
                        progress_id,
                        stage,
                        total,
                    ),
                )
                updated_ids = list(raw_result.get("updated_ids") or [])
                removed_ids = list(raw_result.get("removed_ids") or [])
                removed_ids.extend(
                    id_by_token[token]
                    for token in raw_result.get("missing_tokens") or []
                    if token in id_by_token
                )
                errors = _account_not_found_errors([
                    *missing_ids,
                    *removed_ids,
                ])
                events = _account_mutation_events(
                    action=action,
                    success_ids=updated_ids,
                    removed_ids=removed_ids,
                    errors=errors,
                    labels=labels,
                    success_message=success_message,
                    removed_message=failure_message,
                )
                result = _account_mutation_payload(
                    updated=len(updated_ids),
                    removed=len(removed_ids),
                    updated_ids=updated_ids,
                    removed_ids=removed_ids,
                    errors=errors,
                    events=events,
                    include_items=False,
                )
                _publish_account_mutation_progress(
                    progress_id,
                    targets=targets,
                    labels=labels,
                    events=events,
                )
                account_service.finish_refresh_progress(progress_id, result)
            except Exception:
                account_service.finish_refresh_progress(
                    progress_id,
                    error="account batch update failed",
                )

        _schedule_account_operation(_do_batch_update_accounts())
        return {
            "progress_id": progress_id,
            "target_ids": target_ids,
            "errors": initial_errors,
        }
    @router.post("/api/accounts/group")
    async def bind_accounts_group(body: AccountGroupBindRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        if not body.selection and not body.account_ids and not body.access_tokens:
            raise HTTPException(status_code=400, detail={"error": "account_ids is required"})
        group_id = "" if body.group_id.strip() == "__ungrouped__" else _account_group_id(body.group_id)
        if group_id and not any(group.get("id") == group_id for group in _account_group_payload()["groups"]):
            raise HTTPException(status_code=404, detail={"error": "account group not found"})
        targets, missing_ids = _account_selection_targets(
            body.selection,
            body.account_ids,
            body.access_tokens,
        )
        if not targets:
            raise HTTPException(status_code=400, detail={"error": "no valid accounts selected"})
        labels = _account_operation_labels(targets)
        result = await run_in_threadpool(
            account_service.update_accounts,
            [token for token, _account_id in targets],
            {"group_id": group_id},
            quiet=True,
        )
        updated_ids = list(result.get("updated_ids") or [])
        removed_ids = list(result.get("removed_ids") or [])
        id_by_token = {token: account_id for token, account_id in targets}
        removed_ids.extend(
            id_by_token[token]
            for token in result.get("missing_tokens") or []
            if token in id_by_token
        )
        errors = _account_not_found_errors([
            *missing_ids,
            *removed_ids,
        ])
        return {
            "group_id": group_id,
            **_account_group_payload(),
            **_account_mutation_response(
                updated=len(updated_ids),
                removed=len(removed_ids),
                updated_ids=updated_ids,
                removed_ids=removed_ids,
                errors=errors,
                events=_account_mutation_events(
                    action="bind_account_group",
                    success_ids=updated_ids,
                    removed_ids=removed_ids,
                    errors=errors,
                    labels=labels,
                    success_message=(
                        "账号组已更新" if group_id else "账号已移出账号组"
                    ),
                    removed_message="账号组更新失败",
                ),
                include_items=False,
            ),
        }
    @router.post("/api/accounts/oauth/start")
    async def start_oauth_login(
            body: OAuthLoginStartRequest,
            authorization: str | None = Header(default=None),
    ):
        """登记一次 PKCE 会话，返回可让用户浏览器打开的 authorize URL。"""
        require_admin(authorization)
        try:
            return await run_in_threadpool(oauth_login_service.start, body.email_hint)
        except OAuthLoginError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.post("/api/accounts/oauth/finish")
    async def finish_oauth_login(
            body: OAuthLoginFinishRequest,
            authorization: str | None = Header(default=None),
    ):
        """收用户从浏览器抓回的 callback URL / code，换出 token 三件套并落盘。"""
        require_admin(authorization)
        print(
            "[oauth-login] finish called: "
            f"session_present={bool(body.session_id)}, "
            f"callback_present={bool(body.callback)}, "
            f"callback_length={len(body.callback or '')}",
            flush=True,
        )
        try:
            tokens = await run_in_threadpool(oauth_login_service.finish, body.session_id, body.callback)
        except OAuthLoginError as exc:
            print(f"[oauth-login] finish rejected: {type(exc).__name__}", flush=True)
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

        payload = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "id_token": tokens["id_token"],
            "source_type": "web",
        }
        add_result = await run_in_threadpool(
            account_service.add_account_items,
            [payload],
            False,
        )
        account = account_service.get_account(tokens["access_token"])
        account_id = _clean_text((account or {}).get("management_id"))
        if not account_id:
            raise HTTPException(status_code=500, detail={"error": "created account could not be resolved"})
        return _account_mutation_payload(
            added=max(0, int(add_result.get("added") or 0)),
            skipped=max(0, int(add_result.get("skipped") or 0)),
            synced=0,
            updated_ids=[account_id],
        )

    @router.get("/api/cpa/pools")
    async def list_cpa_pools(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"pools": sanitize_cpa_pools(cpa_config.list_pools())}

    @router.post("/api/cpa/pools")
    async def create_cpa_pool(body: CPAPoolCreateRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        if not body.base_url.strip():
            raise HTTPException(status_code=400, detail={"error": "base_url is required"})
        if not body.secret_key.strip():
            raise HTTPException(status_code=400, detail={"error": "secret_key is required"})
        pool = cpa_config.add_pool(name=body.name, base_url=body.base_url, secret_key=body.secret_key)
        return {"pool": sanitize_cpa_pool(pool), "pools": sanitize_cpa_pools(cpa_config.list_pools())}

    @router.post("/api/cpa/pools/{pool_id}")
    async def update_cpa_pool(pool_id: str, body: CPAPoolUpdateRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            pool = cpa_config.update_pool(pool_id, body.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={"error": "CPA import job is active"},
            ) from exc
        if pool is None:
            raise HTTPException(status_code=404, detail={"error": "pool not found"})
        return {"pool": sanitize_cpa_pool(pool), "pools": sanitize_cpa_pools(cpa_config.list_pools())}

    @router.delete("/api/cpa/pools/{pool_id}")
    async def delete_cpa_pool(pool_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            deleted = cpa_config.delete_pool(pool_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={"error": "CPA import job is active"},
            ) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail={"error": "pool not found"})
        return {"pools": sanitize_cpa_pools(cpa_config.list_pools())}

    @router.get("/api/cpa/pools/{pool_id}/files")
    async def cpa_pool_files(pool_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        pool = cpa_config.get_pool(pool_id)
        if pool is None:
            raise HTTPException(status_code=404, detail={"error": "pool not found"})
        return {"pool_id": pool_id, "files": await run_in_threadpool(list_remote_files, pool)}

    @router.post("/api/cpa/pools/{pool_id}/import")
    async def cpa_pool_import(pool_id: str, body: CPAImportRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        pool = cpa_config.get_pool(pool_id)
        if pool is None:
            raise HTTPException(status_code=404, detail={"error": "pool not found"})
        try:
            job = cpa_import_service.start_import(pool, body.names)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        return {"import_job": job}

    @router.get("/api/cpa/pools/{pool_id}/import")
    async def cpa_pool_import_progress(pool_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        pool = cpa_config.get_pool(pool_id)
        if pool is None:
            raise HTTPException(status_code=404, detail={"error": "pool not found"})
        return {"import_job": pool.get("import_job")}

    @router.get("/api/sub2api/servers")
    async def list_sub2api_servers(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"servers": sanitize_sub2api_servers(sub2api_config.list_servers())}

    @router.post("/api/sub2api/servers")
    async def create_sub2api_server(body: Sub2APIServerCreateRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        if not body.base_url.strip():
            raise HTTPException(status_code=400, detail={"error": "base_url is required"})
        has_login = body.email.strip() and body.password.strip()
        has_api_key = bool(body.api_key.strip())
        if not has_login and not has_api_key:
            raise HTTPException(status_code=400, detail={"error": "email+password or api_key is required"})
        server = sub2api_config.add_server(
            name=body.name,
            base_url=body.base_url,
            email=body.email,
            password=body.password,
            api_key=body.api_key,
            group_id=body.group_id,
        )
        return {"server": sanitize_sub2api_server(server), "servers": sanitize_sub2api_servers(sub2api_config.list_servers())}

    @router.post("/api/sub2api/servers/{server_id}")
    async def update_sub2api_server(server_id: str, body: Sub2APIServerUpdateRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            server = sub2api_config.update_server(server_id, body.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={"error": "Sub2API import job is active"},
            ) from exc
        if server is None:
            raise HTTPException(status_code=404, detail={"error": "server not found"})
        return {"server": sanitize_sub2api_server(server), "servers": sanitize_sub2api_servers(sub2api_config.list_servers())}

    @router.delete("/api/sub2api/servers/{server_id}")
    async def delete_sub2api_server(server_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        try:
            deleted = sub2api_config.delete_server(server_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={"error": "Sub2API import job is active"},
            ) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail={"error": "server not found"})
        return {"servers": sanitize_sub2api_servers(sub2api_config.list_servers())}

    @router.get("/api/sub2api/servers/{server_id}/groups")
    async def sub2api_server_groups(server_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        server = sub2api_config.get_server(server_id)
        if server is None:
            raise HTTPException(status_code=404, detail={"error": "server not found"})
        try:
            groups = await run_in_threadpool(sub2api_list_remote_groups, server)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc
        return {"server_id": server_id, "groups": groups}

    @router.get("/api/sub2api/servers/{server_id}/accounts")
    async def sub2api_server_accounts(
        server_id: str,
        group_id: str | None = Query(default=None),
        authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        server = sub2api_config.get_server(server_id)
        if server is None:
            raise HTTPException(status_code=404, detail={"error": "server not found"})
        if group_id is not None:
            server = {**server, "group_id": group_id}
        try:
            accounts = await run_in_threadpool(sub2api_list_remote_accounts, server)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc
        return {"server_id": server_id, "accounts": accounts}

    @router.post("/api/sub2api/servers/{server_id}/import")
    async def sub2api_server_import(server_id: str, body: Sub2APIImportRequest, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        server = sub2api_config.get_server(server_id)
        if server is None:
            raise HTTPException(status_code=404, detail={"error": "server not found"})
        try:
            job = sub2api_import_service.start_import(
                server,
                body.account_ids,
                group_bindings=[binding.model_dump() for binding in body.group_bindings],
                create_account_groups=body.create_account_groups,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        return {"import_job": job}

    @router.get("/api/sub2api/servers/{server_id}/import")
    async def sub2api_server_import_progress(server_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        server = sub2api_config.get_server(server_id)
        if server is None:
            raise HTTPException(status_code=404, detail={"error": "server not found"})
        return {"import_job": server.get("import_job")}

    return router
