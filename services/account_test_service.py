from __future__ import annotations

import time
from typing import Literal, cast

from services.account_processing import account_processing_slot
from services.account_service import account_service
from services.openai_backend_api import OpenAIBackendAPI
from services.protocol.conversation import (
    ConversationRequest,
    collect_image_outputs,
    conversation_events,
    stream_codex_image_outputs,
    stream_image_outputs,
)
from utils.diagnostics import sanitize_diagnostic_text
from utils.helper import build_chat_image_markdown_content, is_codex_image_model


def _account_label(account: dict[str, object], account_id: str) -> str:
    return str(account.get("email") or account.get("name") or account_id).strip()


def _base_result(
    *,
    account_id: str,
    account_label: str,
    mode: Literal["chat", "image"],
    model: str,
    duration_ms: int,
) -> dict[str, object]:
    return {
        "account_id": account_id,
        "account_label": account_label,
        "mode": mode,
        "mode_label": "对话" if mode == "chat" else "画图",
        "model": model,
        "duration_ms": max(0, duration_ms),
    }


def _quota_label(account: dict[str, object]) -> str:
    if account_service.is_unlimited_image_quota_account(account):
        return "无限"
    if bool(account.get("image_quota_unknown")):
        return "未知"
    return str(max(0, int(account.get("quota") or 0)))


class AccountTestService:
    """Execute one upstream capability test against one selected account."""

    def execute(
        self,
        payload: dict[str, object],
    ) -> dict[str, object]:
        account_id = str(payload.get("account_id") or "").strip()
        mode = cast(
            Literal["chat", "image"],
            str(payload.get("mode") or "chat").strip(),
        )
        model = str(payload.get("model") or "").strip()
        prompt = str(payload.get("prompt") or "").strip()
        call_id = str(payload.get("_call_id") or "").strip()
        trace_image_perf = bool(payload.get("_trace_image_perf"))
        started = time.perf_counter()
        account = account_service.get_account_by_id(account_id)
        if account is None:
            raise LookupError("account not found")

        label = _account_label(account, account_id)
        quota_before_label = _quota_label(account)
        quota_after_label = quota_before_label
        quota_deducted = False
        try:
            if mode == "image":
                images, updated_account = self._execute_image(
                    account,
                    model=model,
                    prompt=prompt,
                    call_id=call_id,
                    trace_image_perf=trace_image_perf,
                )
                content = build_chat_image_markdown_content({
                    "data": [{"url": image} for image in images],
                })
                quota_after_label = _quota_label(updated_account)
                quota_deducted = (
                    quota_before_label.isdigit()
                    and quota_after_label.isdigit()
                    and int(quota_after_label) < int(quota_before_label)
                )
            else:
                content = self._execute_chat(account, model=model, prompt=prompt)
                images = []
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            message = sanitize_diagnostic_text(str(exc)).strip() or "账号测试失败"
            return {
                **_base_result(
                    account_id=account_id,
                    account_label=label,
                    mode=mode,
                    model=model,
                    duration_ms=duration_ms,
                ),
                "status": "failed",
                "status_label": "测试失败",
                "tone": "danger",
                "content": "",
                "quota_before_label": quota_before_label,
                "quota_after_label": quota_before_label,
                "quota_deducted": False,
                "error_code": type(exc).__name__,
                "error_message": message,
                "_call_status": "failed",
                "_call_error": message,
                "_account_email": label,
            }

        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            **_base_result(
                account_id=account_id,
                account_label=label,
                mode=mode,
                model=model,
                duration_ms=duration_ms,
            ),
            "status": "success",
            "status_label": "测试通过",
            "tone": "success",
            "content": content,
            "quota_before_label": quota_before_label,
            "quota_after_label": quota_after_label,
            "quota_deducted": quota_deducted,
            "error_code": "",
            "error_message": "",
            "_account_email": label,
            "_image_urls": images,
        }

    @staticmethod
    def _execute_chat(account: dict[str, object], *, model: str, prompt: str) -> str:
        access_token = str(account.get("access_token") or "").strip()
        active_token = account_service.ensure_access_token(
            access_token,
            event="account_test_chat",
            raise_on_error=True,
        )
        backend: OpenAIBackendAPI | None = None
        with account_processing_slot():
            try:
                backend = OpenAIBackendAPI(access_token=active_token)
                text = "".join(
                    str(event.get("delta") or "")
                    for event in conversation_events(
                        backend,
                        model=model,
                        prompt=prompt,
                    )
                    if event.get("type") == "conversation.delta"
                ).strip()
            finally:
                if backend is not None:
                    backend.close()
        account_service.mark_text_used(active_token)
        return text

    @staticmethod
    def _execute_image(
        account: dict[str, object],
        *,
        model: str,
        prompt: str,
        call_id: str,
        trace_image_perf: bool,
    ) -> tuple[list[str], dict[str, object]]:
        access_token = str(account.get("access_token") or "").strip()
        active_token = account_service.ensure_access_token(
            access_token,
            event="account_test_image",
            raise_on_error=True,
            image_scope=True,
        )
        backend: OpenAIBackendAPI | None = None
        with account_processing_slot():
            try:
                backend = OpenAIBackendAPI(access_token=active_token)
                request = ConversationRequest(
                    model=model,
                    prompt=prompt,
                    response_format="b64_json",
                    call_id=call_id,
                    trace_image_perf=trace_image_perf,
                )
                stream = (
                    stream_codex_image_outputs
                    if is_codex_image_model(model)
                    else stream_image_outputs
                )
                result = collect_image_outputs(stream(backend, request))
            finally:
                if backend is not None:
                    backend.close()

        images = [
            str(item).strip()
            for item in result.get("_image_urls", [])
            if str(item).strip()
        ]
        if not images:
            for item in result.get("data", []):
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if url:
                    images.append(url)
                    continue
                encoded = str(item.get("b64_json") or "").strip()
                if encoded:
                    images.append(f"data:image/png;base64,{encoded}")
        if not images:
            raise RuntimeError("上游没有返回图片")

        updated = account_service.mark_image_result(active_token, True)
        if updated is None:
            raise RuntimeError("图片已生成，但账号额度更新失败")
        return list(dict.fromkeys(images)), updated


account_test_service = AccountTestService()
