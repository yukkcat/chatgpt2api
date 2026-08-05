from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    as_completed,
    wait,
)
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Iterator

import tiktoken
from curl_cffi.requests import exceptions as curl_exceptions

from services.account_service import ImageAccountSelectionError, account_service
from services.config import config
from services.image_failure import (
    ImageDownloadError,
    ImageFailure,
    ImageFailureError,
    ImageGenerationError,
    ImagePollTimeoutError,
    classify_conversation_failure,
    classify_image_exception,
    classify_message_facts,
    classify_task_failure,
    classify_upstream_message,
    extract_message_facts,
    image_failure,
    is_terminal_message_status,
    image_failure_priority,
    merge_message_failure,
    public_image_error_message,
    terminal_assistant_text,
)
from services.image_storage_service import image_storage_service
from services.image_upscale_service import upscale_image_if_needed
from services.openai_backend_api import OpenAIBackendAPI
from services.proxy_service import ImageEgressDeadlineError, proxy_settings
from services.realtime_monitor_service import realtime_monitor_service
from utils.helper import (
    IMAGE_MODELS,
    UpstreamHTTPError,
    extract_image_from_message_content,
    is_codex_image_model,
    is_supported_image_model,
    split_image_model,
)
from utils.image_tokens import count_image_content_tokens, image_size_from_bytes
from utils.log import logger
from utils.diagnostics import diagnostic_excerpt


def _monitor_image_stage(request: "ConversationRequest", event: str, **data: Any) -> None:
    if request.trace_image_perf and request.call_id:
        if request.monitor_attempt > 0 and "attempt" not in data:
            data["attempt"] = request.monitor_attempt
        realtime_monitor_service.stage(request.call_id, event, model=request.model, **data)


def _capture_failed_image_attempts(request: "ConversationRequest", exc: Exception) -> None:
    if not request.trace_image_perf or not request.call_id:
        return
    realtime_monitor_service.capture_image_attempts(
        request.call_id,
        getattr(exc, "image_attempts", None),
    )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _proxy_hash(proxy_url: object) -> str:
    value = str(proxy_url or "").strip()
    if not value:
        return "direct"
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]


def _backend_egress_data(backend: OpenAIBackendAPI) -> dict[str, Any]:
    profile = getattr(backend, "proxy_profile", None)
    proxy_url = getattr(profile, "proxy_url", "") if profile else ""
    return {
        "proxy_source": str(getattr(profile, "proxy_source", "") or "direct"),
        "proxy_hash": _proxy_hash(proxy_url),
        "egress_key": str(getattr(profile, "egress_key", "") or "direct"),
        "egress_label": str(getattr(profile, "egress_label", "") or ""),
        "proxy_group_id": str(getattr(profile, "proxy_group_id", "") or ""),
        "proxy_node_id": str(getattr(profile, "proxy_node_id", "") or ""),
        "proxy_node_name": str(getattr(profile, "proxy_node_name", "") or ""),
        "image_egress_limit": int(getattr(profile, "image_concurrency_limit", 0) or 0),
        "has_proxy": bool(proxy_url),
        "egress_mode": str(getattr(profile, "egress_mode", "") or "direct"),
    }


def _backend_http_timing_data(backend: OpenAIBackendAPI | None, name: str = "image_generation_stream") -> dict[str, Any]:
    if backend is None or not hasattr(backend, "pop_http_timing"):
        return {}
    try:
        return backend.pop_http_timing(name)
    except Exception:
        return {}


def _backend_image_result_timing_data(
        backend: OpenAIBackendAPI | None,
        fallback_resolve_ms: int,
) -> dict[str, int]:
    if backend is not None and hasattr(backend, "pop_image_result_timing"):
        try:
            timing = backend.pop_image_result_timing()
        except Exception:
            timing = {}
        if isinstance(timing, dict):
            normalized = {
                str(key): max(0, int(value or 0))
                for key, value in timing.items()
                if str(key).endswith("_ms") and int(value or 0) > 0
            }
            if normalized:
                return normalized
    return {"resolve_ms": max(0, int(fallback_resolve_ms))}


_IMAGE_PROGRESS_STAGE_EVENTS = {
    "uploading": "image_uploading",
    "bootstrapping": "image_bootstrapping",
    "getting_token": "image_getting_token",
    "preparing_conversation": "image_preparing_conversation",
    "starting_generation": "image_starting_generation",
    "generating": "image_generating",
}

_IMAGE_PROGRESS_DURATION_KEYS = {
    "uploading": "upload_ms",
    "bootstrapping": "bootstrap_ms",
    "getting_token": "requirements_ms",
    "preparing_conversation": "prepare_conversation_ms",
    "starting_generation": "generation_start_ms",
}


def _image_progress_callback_with_monitor(
        request: "ConversationRequest",
        index: int,
        total: int,
        account_email_getter: Callable[[], str],
) -> Callable[[str], None]:
    original_callback = request.progress_callback
    last_step = ""
    last_step_started = time.perf_counter()

    def report(step: str) -> None:
        nonlocal last_step, last_step_started
        now = time.perf_counter()
        step_name = str(step or "").strip()
        data: dict[str, Any] = {
            "index": index,
            "total": total,
        }
        account_email = account_email_getter()
        if account_email:
            data["account_email"] = account_email
        duration_key = _IMAGE_PROGRESS_DURATION_KEYS.get(last_step)
        if duration_key:
            data[duration_key] = int((now - last_step_started) * 1000)
        stage_event = _IMAGE_PROGRESS_STAGE_EVENTS.get(step_name)
        if stage_event:
            _monitor_image_stage(request, stage_event, **data)
        last_step = step_name
        last_step_started = now
        if original_callback:
            original_callback(step_name)

    return report


def _resolve_image_urls_with_monitor(
        backend: OpenAIBackendAPI,
        request: "ConversationRequest",
        conversation_id: str,
        file_ids: list[str],
        sediment_ids: list[str],
        index: int,
        total: int,
        path: str = "",
        **kwargs: Any,
) -> list[str]:
    resolve_started = time.perf_counter()
    try:
        image_urls = backend.resolve_conversation_image_urls(
            conversation_id,
            file_ids,
            sediment_ids,
            **kwargs,
        )
    except Exception as exc:
        if request.trace_image_perf:
            result_timing = _backend_image_result_timing_data(
                backend,
                _elapsed_ms(resolve_started),
            )
            _monitor_image_stage(
                request,
                "image_resolve_failed",
                conversation_id=conversation_id,
                index=index,
                total=total,
                status="failed",
                upstream_error=diagnostic_excerpt(repr(exc), 1000),
                **result_timing,
            )
            log_payload: dict[str, Any] = {
                "event": "image_resolve_failed",
                "call_id": request.call_id,
                "conversation_id": conversation_id,
                "error": repr(exc)[:300],
                **result_timing,
            }
            if path:
                log_payload["path"] = path
            logger.warning(log_payload)
        raise
    if request.trace_image_perf:
        result_timing = _backend_image_result_timing_data(
            backend,
            _elapsed_ms(resolve_started),
        )
        _monitor_image_stage(
            request,
            "image_resolve_done",
            conversation_id=conversation_id,
            url_count=len(image_urls),
            index=index,
            total=total,
            **result_timing,
        )
        log_payload = {
            "event": "image_resolve_done",
            "call_id": request.call_id,
            "conversation_id": conversation_id,
            "url_count": len(image_urls),
            **result_timing,
        }
        if path:
            log_payload["path"] = path
        logger.info(log_payload)
    return image_urls


def _download_image_bytes_with_monitor(
        backend: OpenAIBackendAPI,
        request: "ConversationRequest",
        conversation_id: str,
        image_urls: list[str],
        index: int,
        total: int,
        path: str = "",
) -> list[bytes]:
    download_started = time.perf_counter()
    try:
        downloaded_images = backend.download_image_bytes(image_urls)
    except Exception as exc:
        if not getattr(exc, "conversation_id", ""):
            setattr(exc, "conversation_id", conversation_id)
        if request.trace_image_perf:
            download_ms = _elapsed_ms(download_started)
            _monitor_image_stage(
                request,
                "image_download_failed",
                conversation_id=conversation_id,
                download_ms=download_ms,
                url_count=len(image_urls),
                index=index,
                total=total,
                status="failed",
                upstream_error=diagnostic_excerpt(repr(exc), 1000),
            )
            log_payload: dict[str, Any] = {
                "event": "image_download_failed",
                "call_id": request.call_id,
                "conversation_id": conversation_id,
                "download_ms": download_ms,
                "url_count": len(image_urls),
                "error": repr(exc)[:300],
            }
            if path:
                log_payload["path"] = path
            logger.warning(log_payload)
        raise
    if request.trace_image_perf:
        download_ms = _elapsed_ms(download_started)
        download_bytes = sum(len(image) for image in downloaded_images)
        download_kbps = int((download_bytes / 1024) / (download_ms / 1000)) if download_ms > 0 else 0
        _monitor_image_stage(
            request,
            "image_download_done",
            conversation_id=conversation_id,
            download_ms=download_ms,
            download_bytes=download_bytes,
            download_kbps=download_kbps,
            url_count=len(image_urls),
            image_count=len(downloaded_images),
            index=index,
            total=total,
        )
        log_payload = {
            "event": "image_download_done",
            "call_id": request.call_id,
            "conversation_id": conversation_id,
            "download_ms": download_ms,
            "download_bytes": download_bytes,
            "download_kbps": download_kbps,
            "url_count": len(image_urls),
            "image_count": len(downloaded_images),
        }
        if path:
            log_payload["path"] = path
        logger.info(log_payload)
    return downloaded_images


def is_token_invalid_error(message: str) -> bool:
    text = str(message or "").lower()
    return (
        "token_invalidated" in text
        or "token_revoked" in text
        or "authentication token has been invalidated" in text
        or "invalidated oauth token" in text
    )


def encode_images(images: Iterable[tuple[bytes, str, str]]) -> list[str]:
    return [base64.b64encode(data).decode("ascii") for data, _, _ in images if data]


def save_image_bytes(
        image_data: bytes,
        base_url: str | None = None,
        *,
        deadline_monotonic: float | None = None,
) -> str:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return image_storage_service.save(
                image_data,
                base_url,
                deadline_monotonic=deadline_monotonic,
            ).url
        except ImageFailureError as exc:
            if exc.failure.code == "task_interrupted":
                raise
            last_error = exc
        except Exception as exc:
            last_error = exc
        logger.warning({
            "event": "image_result_storage_retry" if attempt == 0 else "image_result_storage_failed",
            "attempt": attempt + 1,
            "error": diagnostic_excerpt(repr(last_error), 500),
        })
    raise ImageDownloadError(
        f"image result storage failed: {diagnostic_excerpt(last_error, 500)}"
    ) from last_error


def message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and str(item.get("type") or "") in {"text", "input_text", "output_text"}:
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return ""


def normalize_messages(messages: object, system: Any = None) -> list[dict[str, Any]]:
    normalized = []
    if config.global_system_prompt:
        normalized.append({"role": "system", "content": config.global_system_prompt})
    system_text = message_text(system)
    if system_text:
        normalized.append({"role": "system", "content": system_text})
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role", "user")
            content = message.get("content", "")
            text = message_text(content)
            images: list[tuple[bytes, str]] = []
            if role == "user":
                images.extend(extract_image_from_message_content(content))
                if isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict) or part.get("type") != "image":
                            continue
                        data = part.get("data")
                        if isinstance(data, (bytes, bytearray)) and all(existing[0] != bytes(data) for existing in images):
                            images.append((bytes(data), str(part.get("mime") or "image/png")))
            if images:
                parts: list[Any] = []
                if text:
                    parts.append({"type": "text", "text": text})
                for data, mime in images:
                    parts.append({"type": "image", "data": data, "mime": mime})
                normalized.append({"role": role, "content": parts})
            else:
                normalized.append({"role": role, "content": text})
    return normalized


def prompt_with_global_system(prompt: str) -> str:
    return f"{config.global_system_prompt}\n\n{prompt}" if config.global_system_prompt else prompt


def assistant_history_text(messages: list[dict[str, Any]]) -> str:
    return "".join(str(item.get("content") or "") for item in messages if item.get("role") == "assistant")


def assistant_history_messages(messages: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("content") or "") for item in messages if item.get("role") == "assistant" and item.get("content")]


def build_image_prompt(prompt: str, size: str | None, quality: str = "auto") -> str:
    hints = []
    if size:
        hints.append(f"输出图片尺寸为 {size}。")
    if quality:
        hints.append(f"输出图片质量为 {quality}。")
    return f"{prompt.strip()}\n\n{''.join(hints)}" if hints else prompt


def encoding_for_model(model: str):
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        try:
            return tiktoken.get_encoding("o200k_base")
        except KeyError:
            return tiktoken.get_encoding("cl100k_base")


def count_message_image_tokens(messages: list[dict[str, Any]], model: str) -> int:
    return sum(count_image_content_tokens(message.get("content"), model) for message in messages)


def count_message_text_tokens(messages: list[dict[str, Any]], model: str) -> int:
    encoding = encoding_for_model(model)
    total = 0
    for message in messages:
        total += 3
        for key, value in message.items():
            if key == "content" and isinstance(value, list):
                total += len(encoding.encode(message_text(value)))
            elif isinstance(value, str):
                total += len(encoding.encode(value))
            else:
                continue
            if key == "name":
                total += 1
    return total + 3


def count_message_tokens(messages: list[dict[str, Any]], model: str) -> int:
    return count_message_text_tokens(messages, model) + count_message_image_tokens(messages, model)


def count_text_tokens(text: str, model: str) -> int:
    return len(encoding_for_model(model).encode(text))


def format_image_result(
    items: list[dict[str, Any]],
    prompt: str,
    response_format: str,
    base_url: str | None = None,
    created: int | None = None,
    message: str = "",
    requested_size: str | None = None,
    deadline_monotonic: float | None = None,
) -> dict[str, Any]:
    data: list[dict[str, Any]] = []
    image_urls: list[str] = []
    for item in items:
        b64_json = str(item.get("b64_json") or "").strip()
        if not b64_json:
            continue
        revised_prompt = str(item.get("revised_prompt") or prompt).strip() or prompt
        image_bytes = base64.b64decode(b64_json)
        image_bytes = upscale_image_if_needed(image_bytes, requested_size)
        stored_url = save_image_bytes(
            image_bytes,
            base_url,
            deadline_monotonic=deadline_monotonic,
        )
        if stored_url:
            image_urls.append(stored_url)
        asset: dict[str, Any] = {"revised_prompt": revised_prompt}
        if response_format == "b64_json":
            asset["b64_json"] = base64.b64encode(image_bytes).decode("ascii")
        else:
            asset["url"] = stored_url
        dimensions = image_size_from_bytes(image_bytes)
        if dimensions:
            asset["width"], asset["height"] = dimensions
        data.append(asset)
    result: dict[str, Any] = {"created": created or int(time.time()), "data": data}
    if image_urls:
        result["_image_urls"] = image_urls
    if message and not data:
        result["message"] = message
    return result


@dataclass
class ConversationRequest:
    model: str = "auto"
    prompt: str = ""
    messages: list[dict[str, Any]] | None = None
    thinking_effort: str = ""
    images: list[str] | None = None
    n: int = 1
    size: str | None = None
    quality: str = "auto"
    response_format: str = "b64_json"
    base_url: str | None = None
    message_as_error: bool = False
    progress_callback: Any = None  # Callable[[str], None] | None
    call_id: str = ""
    trace_image_perf: bool = False
    monitor_attempt: int = 0
    deadline_monotonic: float = 0.0


@dataclass
class ConversationState:
    text: str = ""
    raw_text: str = ""
    conversation_id: str = ""
    file_ids: list[str] = field(default_factory=list)
    sediment_ids: list[str] = field(default_factory=list)
    blocked: bool = False
    tool_invoked: bool | None = None
    turn_use_case: str = ""
    async_task_type: str = ""
    message_type: str = ""
    message_facts: dict[str, Any] = field(default_factory=dict)
    terminal_tool_arguments: dict[str, Any] | None = None
    failure: ImageFailure | None = None


@dataclass
class ImageOutput:
    kind: str
    model: str
    index: int
    total: int
    created: int = field(default_factory=lambda: int(time.time()))
    text: str = ""
    upstream_event_type: str = ""
    data: list[dict[str, Any]] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    image_attempts: list[dict[str, Any]] = field(default_factory=list)
    account_email: str = ""
    conversation_id: str = ""
    failure: ImageFailure | None = field(default=None, repr=False)

    def to_chunk(self) -> dict[str, Any]:
        chunk: dict[str, Any] = {
            "object": "image.generation.chunk",
            "created": self.created,
            "model": self.model,
            "index": self.index,
            "total": self.total,
            "progress_text": self.text,
            "upstream_event_type": self.upstream_event_type,
            "data": [],
        }
        if self.account_email:
            chunk["_account_email"] = self.account_email
        if self.conversation_id:
            chunk["_conversation_id"] = self.conversation_id
        if self.image_urls:
            chunk["_image_urls"] = list(self.image_urls)
        if self.image_attempts:
            chunk["_image_attempts"] = [dict(item) for item in self.image_attempts]
        if self.kind == "message":
            chunk.update({
                "object": "image.generation.message",
                "message": self.text,
            })
            chunk.pop("progress_text", None)
            chunk.pop("upstream_event_type", None)
        elif self.kind == "result":
            chunk.update({
                "object": "image.generation.result",
                "data": self.data,
            })
            chunk.pop("progress_text", None)
            chunk.pop("upstream_event_type", None)
        return chunk


def assistant_message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    parts = content.get("parts") or []
    if isinstance(parts, list) and parts:
        text = "".join(part for part in parts if isinstance(part, str))
        if text:
            return text
    # Fallback: content_type "code" stores text in the "text" field instead of "parts"
    text_field = str(content.get("text") or "")
    if text_field:
        return text_field
    return ""


def is_image_generation_arguments(
        text: str,
        *,
        role: str = "",
        content_type: str = "",
) -> bool:
    """Return whether an assistant code message contains image tool arguments."""
    if str(role or "").strip().lower() != "assistant":
        return False
    if str(content_type or "").strip().lower() != "code":
        return False
    try:
        arguments = json.loads(str(text or "").strip())
    except (TypeError, ValueError):
        return False
    if not isinstance(arguments, dict):
        return False
    prompt = arguments.get("prompt")
    instructions = arguments.get("instructions")
    has_prompt = any(
        isinstance(value, str) and bool(value.strip())
        for value in (prompt, instructions)
    )
    has_image_options = any(
        field in arguments
        for field in (
            "size",
            "n",
            "transparent_background",
            "is_style_transfer",
            "referenced_image_ids",
        )
    )
    # Some upstream responses omit the prompt and only retain these two tool arguments.
    return bool(
        (has_prompt and has_image_options)
        or ("size" in arguments and "n" in arguments)
    )


def strip_history(text: str, history_text: str = "") -> str:
    text = str(text or "")
    history_text = str(history_text or "")
    while history_text and text.startswith(history_text):
        text = text[len(history_text):]
    return text


def sanitize_output_text(text: str) -> str:
    text = str(text or "")

    def is_internal_annotation_part(part: str) -> bool:
        value = part.strip()
        if not value:
            return True
        lower = value.lower()
        return bool(
            re.fullmatch(r"turn\d+[a-z]*\d*", lower)
            or re.fullmatch(r"turn\d+\w*", lower)
            or lower.startswith(("turn", "source", "sources"))
        )

    def readable_annotation_part(parts: list[str]) -> str:
        for part in parts:
            value = part.strip()
            if value and not is_internal_annotation_part(value):
                return value
        return ""

    def replace_annotation(match: re.Match[str]) -> str:
        payload = match.group(1)
        parts = [part.strip() for part in payload.split("\ue202")]
        kind = (parts[0] if parts else "").lower()
        data = parts[1:]
        if kind == "url":
            label = data[0] if data else ""
            url = data[1] if len(data) > 1 else ""
            if label and url.startswith(("http://", "https://")):
                return f"{label} ({url})"
            return label or url
        if kind == "cite":
            return readable_annotation_part(data)
        return readable_annotation_part(data)

    # ChatGPT web sometimes returns rich annotation markers using private-use
    # characters. API clients cannot render those. Preserve readable labels
    # from entity/link annotations, while removing internal citation pointers.
    text = re.sub(r"\ue200([^\ue201]*)\ue201", replace_annotation, text)
    text = re.sub(r"\ue200[^\ue201]*$", "", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    return text


def assistant_raw_text(event: dict[str, Any], current_text: str = "", history_text: str = "") -> str:
    for candidate in (event, event.get("v")):
        if not isinstance(candidate, dict):
            continue
        message = candidate.get("message")
        if not isinstance(message, dict):
            continue
        role = str((message.get("author") or {}).get("role") or "").strip().lower()
        if role != "assistant":
            continue
        text = assistant_message_text(message)
        if text:
            return strip_history(text, history_text)
    return apply_text_patch(event, current_text, history_text)


def assistant_text(event: dict[str, Any], current_text: str = "", history_text: str = "") -> str:
    return sanitize_output_text(assistant_raw_text(event, current_text, history_text))


def event_assistant_text(event: dict[str, Any], history_text: str = "") -> str:
    for candidate in (event, event.get("v")):
        if not isinstance(candidate, dict):
            continue
        message = candidate.get("message")
        if isinstance(message, dict) and (message.get("author") or {}).get("role") == "assistant":
            return strip_history(assistant_message_text(message), history_text)
    return ""


def apply_text_patch(event: dict[str, Any], current_text: str = "", history_text: str = "") -> str:
    if event.get("p") in {"/message/content/parts/0", "/message/content/text"}:
        return apply_patch_op(event, current_text, history_text)

    operations = event.get("v")
    if isinstance(operations, str) and current_text and not event.get("p") and not event.get("o"):
        return current_text + operations

    if event.get("o") == "patch" and isinstance(operations, list):
        text = current_text
        for item in operations:
            if isinstance(item, dict):
                text = apply_text_patch(item, text, history_text)
        return text

    if not isinstance(operations, list):
        return current_text

    text = current_text
    for item in operations:
        if isinstance(item, dict):
            text = apply_text_patch(item, text, history_text)
    return text


def apply_patch_op(operation: dict[str, Any], current_text: str, history_text: str = "") -> str:
    op = operation.get("o")
    value = str(operation.get("v") or "")
    if op == "append":
        return current_text + value
    if op == "replace":
        return strip_history(value, history_text)
    return current_text


def add_unique(values: list[str], candidates: list[str]) -> None:
    for candidate in candidates:
        if candidate and candidate not in values:
            values.append(candidate)


FILE_SERVICE_ID_RE = re.compile(r"file-service://([A-Za-z0-9_-]+)")
FILE_ID_RE = re.compile(r"\b(file[-_](?!service\b)[A-Za-z0-9_-]+)\b")
# 真正的图片文件 ID 格式：file_00000000 + 24位十六进制字符（共32字符）
# 用于过滤非图片文件 ID（如 file_upload_business_upsell）
REAL_IMAGE_FILE_ID_RE = re.compile(r"\bfile_00000000[a-f0-9]{24}\b")
SEDIMENT_ID_RE = re.compile(r"sediment://([A-Za-z0-9_-]+)")


def extract_conversation_ids(payload: str) -> tuple[str, list[str], list[str]]:
    conversation_match = re.search(r'"conversation_id"\s*:\s*"([^"]+)"', payload)
    conversation_id = conversation_match.group(1) if conversation_match else ""
    file_ids: list[str] = []
    # Negative lookahead excludes "file-service" (URI prefix, not a real id).
    add_unique(file_ids, FILE_SERVICE_ID_RE.findall(payload))
    # 只提取真正的图片文件 ID（file_00000000... 格式），过滤非图片文件 ID（如 file_upload_business_upsell）
    add_unique(file_ids, REAL_IMAGE_FILE_ID_RE.findall(payload))
    sediment_ids = SEDIMENT_ID_RE.findall(payload)
    return conversation_id, file_ids, sediment_ids


def is_image_tool_event(event: dict[str, Any]) -> bool:
    value = event.get("v")
    message = event.get("message") or (value.get("message") if isinstance(value, dict) else None)
    if not isinstance(message, dict):
        return False
    metadata = message.get("metadata") or {}
    author = message.get("author") or {}
    content = message.get("content") or {}
    if author.get("role") != "tool":
        return False
    if metadata.get("async_task_type") == "image_gen":
        return True
    if content.get("content_type") != "multimodal_text":
        return False
    return any(
        isinstance(part, dict) and (
                part.get("content_type") == "image_asset_pointer"
                or str(part.get("asset_pointer") or "").startswith(("file-service://", "sediment://"))
        )
        for part in content.get("parts") or []
    )


def _is_user_message_event(event: dict[str, Any]) -> bool:
    """检查事件是否来自 user 角色消息。"""
    value = event.get("v")
    message = event.get("message") or (value.get("message") if isinstance(value, dict) else None)
    if isinstance(message, dict):
        author = message.get("author") or {}
        if str(author.get("role") or "").strip().lower() == "user":
            return True
    return False


def update_conversation_state(
        state: ConversationState,
        payload: str,
        event: dict[str, Any] | None = None,
        message_text: str = "",
        classify_terminal_text_as_image_failure: bool = True,
) -> None:
    conversation_id, file_ids, sediment_ids = extract_conversation_ids(payload)
    if conversation_id and not state.conversation_id:
        state.conversation_id = conversation_id
    # Generated ids must come from an explicit tool message or a tool patch.
    # tool_invoked also covers later assistant references, so it is not an
    # output boundary by itself.
    is_patch_event = isinstance(event, dict) and event.get("o") == "patch"
    is_user_msg = isinstance(event, dict) and _is_user_message_event(event)
    event_facts = extract_message_facts(event) if isinstance(event, dict) else {}
    event_role = str(event_facts.get("role") or state.message_facts.get("role") or "").strip().lower()
    has_asset_pointer = (
        "asset_pointer" in payload
        or "file-service://" in payload
        or "sediment://" in payload
    )
    image_context = (
        (isinstance(event, dict) and is_image_tool_event(event))
        or (is_patch_event and not is_user_msg and event_role == "tool" and has_asset_pointer)
    )
    if image_context:
        add_unique(state.file_ids, file_ids)
        add_unique(state.sediment_ids, sediment_ids)
    if not isinstance(event, dict):
        return
    state.conversation_id = str(event.get("conversation_id") or state.conversation_id)
    value = event.get("v")
    if isinstance(value, dict):
        state.conversation_id = str(value.get("conversation_id") or state.conversation_id)
    if event.get("type") == "moderation":
        moderation = event.get("moderation_response")
        if isinstance(moderation, dict) and moderation.get("blocked") is True:
            state.blocked = True
    if event.get("type") == "server_ste_metadata":
        metadata = event.get("metadata")
        if isinstance(metadata, dict):
            if isinstance(metadata.get("tool_invoked"), bool):
                state.tool_invoked = metadata["tool_invoked"]
            state.turn_use_case = str(metadata.get("turn_use_case") or state.turn_use_case)

    facts = event_facts
    if facts.get("blocked") is True:
        state.blocked = True
    if facts.get("turn_use_case"):
        state.turn_use_case = str(facts["turn_use_case"])
    if facts.get("async_task_type"):
        state.async_task_type = str(facts["async_task_type"])
    if facts.get("message_type"):
        state.message_type = str(facts["message_type"])
    role = str(facts.get("role") or "").strip().lower()
    current_role = str(state.message_facts.get("role") or "").strip().lower()
    message_id = str(facts.get("message_id") or "").strip()
    current_message_id = str(state.message_facts.get("message_id") or "").strip()
    should_update_facts = False
    if role in {"assistant", "tool"}:
        if (
            (current_role and current_role != role)
            or (message_id and current_message_id and message_id != current_message_id)
        ):
            state.message_facts = {}
        should_update_facts = True
    elif not role and current_role in {"assistant", "tool"}:
        should_update_facts = True
    if should_update_facts:
        accumulated_codes = set(state.message_facts.get("codes") or ())
        state.message_facts.update(facts)
        incoming_codes = set(facts.get("codes") or ())
        if accumulated_codes or incoming_codes:
            state.message_facts["codes"] = accumulated_codes.union(incoming_codes)

    current_role = str(state.message_facts.get("role") or "").strip().lower()
    current_content_type = str(state.message_facts.get("content_type") or "").strip().lower()
    current_status = str(state.message_facts.get("status") or "").strip().lower()
    current_end_turn = state.message_facts.get("end_turn")
    is_terminal = current_end_turn is True or (
        current_end_turn is None and is_terminal_message_status(current_status)
    )
    if is_terminal and is_image_generation_arguments(
        message_text,
        role=current_role,
        content_type=current_content_type,
    ):
        state.terminal_tool_arguments = {
            "text": str(message_text or "").strip(),
            "content_type": current_content_type,
            "status": current_status,
            "end_turn": current_end_turn is True,
        }

    if image_context or state.tool_invoked is True:
        state.terminal_tool_arguments = None

    has_image_output = bool(state.file_ids or state.sediment_ids)
    if has_image_output:
        state.failure = None
        state.terminal_tool_arguments = None
        return

    candidate_failure = classify_message_facts(
        role=str(state.message_facts.get("role") or ""),
        content_type=str(state.message_facts.get("content_type") or ""),
        status=str(state.message_facts.get("status") or ""),
        end_turn=bool(state.message_facts.get("end_turn")),
        is_error=bool(state.message_facts.get("is_error")),
        blocked=state.blocked,
        has_image_output=False,
        has_text=bool(state.message_facts.get("has_text")),
        turn_use_case=str(state.message_facts.get("turn_use_case") or state.turn_use_case),
        async_task_type=str(state.message_facts.get("async_task_type") or ""),
        message_type=str(state.message_facts.get("message_type") or ""),
        codes=state.message_facts.get("codes") or (),
        raw_detail=message_text or state.raw_text,
    )
    if (
        candidate_failure is not None
        and candidate_failure.code == "upstream_text_reply"
        and not classify_terminal_text_as_image_failure
    ):
        candidate_failure = None
    if candidate_failure is not None:
        # Explicit codes outrank terminal text; terminal text only replaces a
        # generic tool error from the same turn.
        state.failure = merge_message_failure(state.failure, candidate_failure)


def conversation_base_event(event_type: str, state: ConversationState, **extra: Any) -> dict[str, Any]:
    return {
        "type": event_type,
        "text": state.text,
        "conversation_id": state.conversation_id,
        "file_ids": list(state.file_ids),
        "sediment_ids": list(state.sediment_ids),
        "blocked": state.blocked,
        "tool_invoked": state.tool_invoked,
        "turn_use_case": state.turn_use_case,
        "async_task_type": state.async_task_type,
        "message_type": state.message_type,
        "message_role": str(state.message_facts.get("role") or ""),
        "content_type": str(state.message_facts.get("content_type") or ""),
        "_terminal_tool_arguments": (
            dict(state.terminal_tool_arguments)
            if state.terminal_tool_arguments is not None else None
        ),
        "_image_failure": state.failure,
        **extra,
    }


def iter_conversation_payloads(
        payloads: Iterator[str],
        history_text: str = "",
        history_messages: list[str] | None = None,
        *,
        classify_terminal_text_as_image_failure: bool = True,
) -> Iterator[dict[str, Any]]:
    state = ConversationState()
    history_messages = history_messages or []
    history_index = 0
    for payload in payloads:
        # print(f"[upstream_sse] {payload}", flush=True)
        if not payload:
            continue
        if payload == "[DONE]":
            yield conversation_base_event("conversation.done", state, done=True)
            break
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            update_conversation_state(state, payload)
            yield conversation_base_event("conversation.raw", state, payload=payload)
            continue
        if not isinstance(event, dict):
            yield conversation_base_event("conversation.event", state, raw=event)
            continue
        next_raw_text = assistant_raw_text(event, state.raw_text, history_text)
        update_conversation_state(
            state,
            payload,
            event,
            next_raw_text,
            classify_terminal_text_as_image_failure=classify_terminal_text_as_image_failure,
        )
        if history_index < len(history_messages) and event_assistant_text(event, history_text) == history_messages[history_index]:
            history_index += 1
            state.raw_text = ""
            state.text = ""
            continue
        next_text = sanitize_output_text(next_raw_text)
        state.raw_text = next_raw_text
        if next_text != state.text:
            delta = next_text[len(state.text):] if next_text.startswith(state.text) else next_text
            state.text = next_text
            yield conversation_base_event("conversation.delta", state, raw=event, delta=delta)
            continue
        yield conversation_base_event("conversation.event", state, raw=event)


def conversation_events(
    backend: OpenAIBackendAPI,
    messages: list[dict[str, Any]] | None = None,
    model: str = "auto",
    prompt: str = "",
    images: list[str] | None = None,
    size: str | None = None,
    quality: str = "auto",
    thinking_effort: str = "",
) -> Iterator[dict[str, Any]]:
    normalized = normalize_messages(messages or ([{"role": "user", "content": prompt}] if prompt else []))
    image_model = is_supported_image_model(model)
    history_text = "" if image_model else assistant_history_text(normalized)
    history_messages = [] if image_model else assistant_history_messages(normalized)
    final_prompt = prompt_with_global_system(build_image_prompt(prompt, size, quality)) if image_model else prompt
    payloads = backend.stream_conversation(
        messages=normalized,
        model=model,
        prompt=final_prompt,
        images=images if image_model else None,
        system_hints=["picture_v2"] if image_model else None,
        thinking_effort=thinking_effort if not image_model else "",
    )
    yield from iter_conversation_payloads(
        payloads,
        history_text,
        history_messages,
        classify_terminal_text_as_image_failure=image_model,
    )


def _text_account_email(access_token: str) -> str:
    account = account_service.get_account(access_token)
    if not account:
        return ""
    return str(account.get("email") or "").strip()


def _remember_text_account(backend: OpenAIBackendAPI, access_token: str) -> str:
    email = _text_account_email(access_token)
    setattr(backend, "account_email", email)
    return email


def text_backend() -> OpenAIBackendAPI:
    access_token = account_service.get_text_access_token()
    backend = OpenAIBackendAPI(access_token=access_token)
    _remember_text_account(backend, access_token)
    return backend


def stream_text_deltas(backend: OpenAIBackendAPI, request: ConversationRequest) -> Iterator[str]:
    attempted_tokens: set[str] = set()
    token = getattr(backend, "access_token", "")
    emitted = False
    auth_failures = 0
    while True:
        if token and token in attempted_tokens:
            raise RuntimeError("no available text account")
        if token:
            attempted_tokens.add(token)
        account_snapshot = account_service.get_account(token) or {}
        active_backend: OpenAIBackendAPI | None = None
        try:
            _remember_text_account(backend, token)
            active_backend = OpenAIBackendAPI(access_token=token)
            _remember_text_account(active_backend, token)
            for event in conversation_events(
                active_backend,
                messages=request.messages,
                model=request.model,
                prompt=request.prompt,
                thinking_effort=request.thinking_effort,
            ):
                structured_failure = event.get("_image_failure")
                if isinstance(structured_failure, ImageFailure):
                    raise ImageFailureError(failure=structured_failure)
                if event.get("type") != "conversation.delta":
                    continue
                delta = str(event.get("delta") or "")
                if delta:
                    emitted = True
                    yield delta
            account_service.mark_text_used(token)
            return
        except Exception as exc:
            auth_failure = bool(token and _is_account_auth_failure(exc))
            if auth_failure:
                try:
                    account_service.schedule_auth_verification(
                        token,
                        "text_stream",
                        expected_access_token=token,
                        expected_refresh_token=str(
                            account_snapshot.get("refresh_token") or ""
                        ),
                        expected_last_token_refresh_at=account_snapshot.get(
                            "last_token_refresh_at"
                        ),
                    )
                except Exception as schedule_error:
                    logger.warning({
                        "event": "auth_verification_schedule_failed",
                        "source": "text_stream",
                        "error": diagnostic_excerpt(schedule_error, 300),
                    })
                auth_failures += 1
            if auth_failure and not emitted and auth_failures < 2:
                token = account_service.get_text_access_token(attempted_tokens)
                if token:
                    continue
            if token and not getattr(exc, "account_email", ""):
                setattr(exc, "account_email", _text_account_email(token))
            raise
        finally:
            if active_backend is not None:
                active_backend.close()


def collect_text(backend: OpenAIBackendAPI, request: ConversationRequest) -> str:
    return "".join(stream_text_deltas(backend, request))


def _failure_raw_text(failure: ImageFailure | None, fallback: str = "") -> str:
    if failure is None:
        return str(fallback or "").strip()
    raw_detail = failure.raw_detail
    if isinstance(raw_detail, str):
        return raw_detail.strip() or str(fallback or "").strip()
    if raw_detail not in (None, ""):
        try:
            return json.dumps(raw_detail, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return repr(raw_detail)
    return str(fallback or "").strip()


def _is_account_auth_failure(exc: Exception) -> bool:
    failure = classify_image_exception(exc)
    if failure.capability != "auth":
        return False
    setattr(exc, "failure", failure)
    return True


def _get_detailed_failure_from_tasks(
    backend: OpenAIBackendAPI,
    conversation_id: str,
    timeout_secs: float = 10.0,
    wait_secs: float = 2.0,
) -> tuple[ImageFailure | None, str]:
    """Return the most specific structured task failure and its diagnostic text."""
    import time as _time
    try:
        if wait_secs > 0:
            _time.sleep(wait_secs)
        tasks = backend._query_backend_tasks(conversation_id=conversation_id, timeout_secs=timeout_secs)
        if not tasks:
            return None, ""

        selected_failure: ImageFailure | None = None
        for task in tasks:
            candidate = classify_task_failure(task)
            if candidate is None:
                continue
            error_msg, metadata = backend.image_task_diagnostics(task)
            raw_error = error_msg or _failure_raw_text(candidate)
            if raw_error:
                candidate = candidate.with_raw_detail(raw_error)
            logger.info({
                "event": "image_task_structured_error",
                "conversation_id": conversation_id,
                "failure_code": candidate.code,
                "error_msg": diagnostic_excerpt(raw_error, 1000),
                "metadata": metadata,
            })
            selected_failure = merge_message_failure(selected_failure, candidate)
        if selected_failure is None:
            return None, ""
        selected_error = _failure_raw_text(selected_failure)
        return (
            selected_failure.with_raw_detail(selected_error or selected_failure.raw_detail),
            selected_error,
        )
    except Exception as exc:
        if _is_account_auth_failure(exc):
            raise
        logger.warning({
            "event": "image_task_error_query_failed",
            "conversation_id": conversation_id,
            "error": diagnostic_excerpt(exc, 300),
        })
        return None, ""


def _recover_image_conversation_id(
        backend: OpenAIBackendAPI,
        request: ConversationRequest,
        *,
        reason: str,
        message: str = "",
        started_at: float | None = None,
) -> str:
    """从最近对话中补救 conversation_id；只做一次，失败不影响主流程。"""
    if not request.prompt:
        return ""
    try:
        recovered_id = backend.find_conversation_by_prompt(
            request.prompt,
            started_at or time.time(),
            timeout_secs=5.0,
        )
        if recovered_id:
            logger.info({
                "event": "image_conversation_id_recovered",
                "reason": reason,
                "conversation_id": recovered_id,
                "message_preview": message[:200],
            })
            return recovered_id
    except Exception as exc:
        if _is_account_auth_failure(exc):
            raise
        logger.warning({
            "event": "image_conversation_id_recovery_failed",
            "reason": reason,
            "error": repr(exc)[:300],
        })
    return ""


def _image_stream_timeout_task_diagnostics(
        backend: OpenAIBackendAPI,
        conversation_id: str,
) -> tuple[ImageFailure | None, str, list[dict[str, Any]], str]:
    """Collect a small task summary after an upstream SSE timeout."""
    try:
        tasks = backend._query_backend_tasks(conversation_id=conversation_id, timeout_secs=5.0)
    except Exception as exc:
        if _is_account_auth_failure(exc):
            raise
        return None, "", [], diagnostic_excerpt(repr(exc), 1000)

    summaries: list[dict[str, Any]] = []
    task_failure: ImageFailure | None = None
    task_error = ""
    for task in tasks[:5]:
        if not isinstance(task, dict):
            continue
        error_msg, metadata = backend.image_task_diagnostics(task)
        failure = classify_task_failure(task)
        if failure is not None:
            if error_msg:
                failure = failure.with_raw_detail(error_msg)
            task_failure = merge_message_failure(task_failure, failure)
            task_error = _failure_raw_text(task_failure, task_error)
        summary: dict[str, Any] = {
            "id": str(task.get("id") or task.get("task_id") or "")[:80],
            "status": str(task.get("status") or metadata.get("status") or "")[:80],
            "type": str(task.get("type") or metadata.get("async_task_type") or "")[:80],
            "is_error": failure is not None,
        }
        for key in ("conversation_id", "original_conversation_id"):
            value = task.get(key)
            if value not in (None, ""):
                summary[key] = str(value)[:80]
        if failure is not None and error_msg:
            summary["error_preview"] = diagnostic_excerpt(error_msg, 500)
        summaries.append({key: value for key, value in summary.items() if value not in (None, "")})
    return task_failure, task_error, summaries, ""


def _image_stream_timeout_error(
        raw_error: str,
        conversation_id: str,
        followup: dict[str, Any],
        conversation_snapshot: dict[str, Any] | None = None,
        upstream_error: str = "",
        raw_upstream_message: str = "",
        failure_code: str = "image_stream_timeout",
) -> ImageGenerationError:
    exc = ImageGenerationError(
        raw_error,
        code=failure_code,
        conversation_id=conversation_id,
        raw_error=raw_error,
        upstream_error=diagnostic_excerpt(upstream_error, 4000),
        raw_upstream_message=diagnostic_excerpt(raw_upstream_message, 4000),
    )
    if failure_code == "image_stream_timeout":
        setattr(exc, "stream_timeout_secs", config.image_stream_timeout_secs)
    setattr(exc, "stream_timeout_followup", followup)
    if followup.get("task_error"):
        setattr(exc, "last_task_error", followup["task_error"])
    if conversation_snapshot:
        setattr(exc, "last_conversation_snapshot", conversation_snapshot)
    return exc


def _recover_after_image_stream_timeout(
        backend: OpenAIBackendAPI,
        request: ConversationRequest,
        last: dict[str, Any],
        timeout_error: Exception,
        index: int,
        total: int,
        stream_started_at: float,
        *,
        failure_code: str = "image_stream_timeout",
) -> ImageOutput:
    is_timeout = failure_code == "image_stream_timeout"
    recovery_reason = "stream_timeout" if is_timeout else "stream_interrupted"
    recovery_path = f"{recovery_reason}_followup"
    followup_reason = "sse_timeout" if is_timeout else "sse_interrupted"
    raw_error = str(timeout_error) or (
        f"SSE stream exceeded {config.image_stream_timeout_secs}s"
        if is_timeout else "SSE stream interrupted"
    )
    conversation_id = str(last.get("conversation_id") or "")
    file_ids = [str(item) for item in last.get("file_ids") or []]
    sediment_ids = [str(item) for item in last.get("sediment_ids") or []]
    message = str(last.get("text") or "").strip()

    if not conversation_id and not file_ids:
        conversation_id = _recover_image_conversation_id(
            backend,
            request,
            reason=recovery_reason,
            message=message or raw_error,
            started_at=stream_started_at,
        )

    followup: dict[str, Any] = {
        "reason": followup_reason,
        "conversation_id": conversation_id,
        "stream_error": raw_error,
        "last_stream_state": {
            "conversation_id": str(last.get("conversation_id") or ""),
            "file_ids": file_ids,
            "sediment_ids": sediment_ids,
            "blocked": bool(last.get("blocked")),
            "tool_invoked": last.get("tool_invoked"),
            "turn_use_case": str(last.get("turn_use_case") or ""),
            "async_task_type": str(last.get("async_task_type") or ""),
            "message_type": str(last.get("message_type") or ""),
            "text_preview": diagnostic_excerpt(message, 1000),
        },
    }
    if is_timeout:
        followup["timeout_secs"] = config.image_stream_timeout_secs
    stream_failure = last.get("_image_failure")
    stream_failure = stream_failure if isinstance(stream_failure, ImageFailure) else None
    task_failure: ImageFailure | None = None
    task_error = ""
    task_summaries: list[dict[str, Any]] = []
    task_probe_error = ""
    conversation_snapshot: dict[str, Any] = {}
    latest_assistant_text = ""
    conversation_failure: ImageFailure | None = None
    conversation_probe_error = ""

    if conversation_id and not (file_ids or sediment_ids):
        task_failure, task_error, task_summaries, task_probe_error = _image_stream_timeout_task_diagnostics(
            backend,
            conversation_id,
        )
        try:
            conversation = backend._get_conversation(conversation_id, timeout_secs=10)
            conversation_snapshot, snapshot_assistant_text = backend._conversation_poll_snapshot(conversation)
            latest_assistant_text = terminal_assistant_text(conversation) or snapshot_assistant_text
            for record in backend._extract_image_tool_records(conversation):
                add_unique(file_ids, [str(item) for item in record.get("file_ids") or []])
                add_unique(sediment_ids, [str(item) for item in record.get("sediment_ids") or []])
            conversation_failure = classify_conversation_failure(conversation)
            terminal_message = next(
                (
                    item
                    for item in reversed(conversation_snapshot.get("messages") or [])
                    if (
                        isinstance(item, dict)
                        and str(item.get("role") or "").strip().lower() == "assistant"
                        and str(item.get("content_type") or "").strip().lower() in {"text", "code"}
                        and bool(item.get("text_preview"))
                    )
                ),
                None,
            )
            if (
                terminal_message is not None
                and str(terminal_message.get("content_type") or "").strip().lower() == "code"
                and is_image_generation_arguments(
                    latest_assistant_text,
                    role="assistant",
                    content_type="code",
                )
            ):
                conversation_failure = merge_message_failure(
                    conversation_failure,
                    image_failure("image_tool_error", raw_detail=latest_assistant_text),
                )
        except Exception as exc:
            if _is_account_auth_failure(exc):
                raise
            conversation_probe_error = diagnostic_excerpt(repr(exc), 1000)

    terminal_failure: ImageFailure | None = None
    for failure in (stream_failure, task_failure, conversation_failure):
        terminal_failure = merge_message_failure(terminal_failure, failure)
    failure_detail = _failure_raw_text(terminal_failure, message)

    followup.update({
        "failure_code": terminal_failure.code if terminal_failure else "",
        "task_error": diagnostic_excerpt(task_error, 2000),
        "task_count": len(task_summaries),
        "tasks": task_summaries,
        "task_probe_error": task_probe_error,
        "conversation_probe_error": conversation_probe_error,
        "conversation_message_count": len(conversation_snapshot.get("messages") or []) if conversation_snapshot else 0,
        "latest_assistant_text": diagnostic_excerpt(latest_assistant_text, 2000),
        "conversation_failure": diagnostic_excerpt(_failure_raw_text(conversation_failure), 2000),
        "recovered_file_ids": file_ids,
        "recovered_sediment_ids": sediment_ids,
    })

    if file_ids or sediment_ids:
        try:
            image_urls = _resolve_image_urls_with_monitor(
                backend,
                request,
                conversation_id,
                file_ids,
                sediment_ids,
                index=index,
                total=total,
                path=recovery_path,
                poll=False,
            )
            result_output = _image_result_output_from_urls(
                backend,
                request,
                conversation_id,
                image_urls,
                index,
                total,
                path=recovery_path,
            )
            if result_output:
                logger.info({
                    "event": f"image_{recovery_reason}_recovered_result",
                    "call_id": request.call_id,
                    "conversation_id": conversation_id,
                    "file_ids": file_ids,
                    "sediment_ids": sediment_ids,
                    "url_count": len(image_urls),
                })
                return result_output
        except ImageDownloadError:
            raise
        except Exception as exc:
            followup["result_recovery_error"] = diagnostic_excerpt(repr(exc), 1000)
            raise

    if terminal_failure is not None:
        terminal_upstream_text = latest_assistant_text
        if (
            not terminal_upstream_text
            and stream_failure is not None
            and str(last.get("message_role") or "").strip().lower() == "assistant"
            and str(last.get("content_type") or "").strip().lower() in {"text", "code"}
        ):
            terminal_upstream_text = message
        terminal_exc = ImageGenerationError(
            failure_detail or raw_error,
            failure=terminal_failure.with_raw_detail(failure_detail or terminal_failure.raw_detail),
            conversation_id=conversation_id,
            raw_error=raw_error,
            upstream_error=(
                "" if terminal_failure.code == "upstream_text_reply" else failure_detail
            ),
            raw_upstream_message=terminal_upstream_text,
        )
        if is_timeout:
            setattr(terminal_exc, "stream_timeout_secs", config.image_stream_timeout_secs)
        setattr(terminal_exc, "stream_timeout_followup", followup)
        if conversation_snapshot:
            setattr(terminal_exc, "last_conversation_snapshot", conversation_snapshot)
        raise terminal_exc

    logger.warning({
        "event": f"image_{recovery_reason}_followup",
        "call_id": request.call_id,
        "conversation_id": conversation_id,
        "task_error": diagnostic_excerpt(task_error, 500),
        "task_count": len(task_summaries),
        "file_ids": file_ids,
        "sediment_ids": sediment_ids,
        "conversation_probe_error": conversation_probe_error,
        "task_probe_error": task_probe_error,
    })
    timeout_upstream_text = latest_assistant_text
    if (
        not timeout_upstream_text
        and str(last.get("message_role") or "").strip().lower() == "assistant"
        and str(last.get("content_type") or "").strip().lower() in {"text", "code"}
    ):
        timeout_upstream_text = message
    raise _image_stream_timeout_error(
        raw_error,
        conversation_id,
        followup,
        conversation_snapshot,
        upstream_error=task_error,
        raw_upstream_message=timeout_upstream_text,
        failure_code=failure_code,
    )


def _cleanup_image_conversations_after_success(backend: OpenAIBackendAPI, outputs: Iterable[ImageOutput]) -> None:
    if not config.image_remove_conversation_after_result:
        return
    conversation_ids: list[str] = []
    seen: set[str] = set()
    for output in outputs:
        conversation_id = str(getattr(output, "conversation_id", "") or "").strip()
        if output.kind != "result" or not conversation_id or conversation_id in seen:
            continue
        seen.add(conversation_id)
        conversation_ids.append(conversation_id)
    for conversation_id in conversation_ids:
        try:
            backend.delete_conversation(conversation_id)
            logger.info({"event": "image_conversation_removed", "conversation_id": conversation_id})
        except Exception as exc:
            logger.warning({
                "event": "image_conversation_remove_failed",
                "conversation_id": conversation_id,
                "error": diagnostic_excerpt(exc, 500),
            })


def _image_result_output_from_urls(
        backend: OpenAIBackendAPI,
        request: ConversationRequest,
        conversation_id: str,
        image_urls: list[str],
        index: int,
        total: int,
        *,
        path: str = "",
) -> ImageOutput | None:
    if not image_urls:
        return None
    if request.progress_callback:
        request.progress_callback("receiving_image")
    downloaded_images = _download_image_bytes_with_monitor(
        backend,
        request,
        conversation_id,
        image_urls,
        index,
        total,
        path=path,
    )
    image_items = [
        {"b64_json": base64.b64encode(image_data).decode("ascii")}
        for image_data in downloaded_images
    ]
    formatted = format_image_result(
        image_items,
        request.prompt,
        request.response_format,
        request.base_url,
        int(time.time()),
        requested_size=request.size,
        deadline_monotonic=request.deadline_monotonic or None,
    )
    data = formatted["data"]
    if not data:
        return None
    return ImageOutput(
        kind="result",
        model=request.model,
        index=index,
        total=total,
        data=data,
        image_urls=list(formatted.get("_image_urls") or []),
        conversation_id=conversation_id,
    )


def stream_image_outputs(
        backend: OpenAIBackendAPI,
        request: ConversationRequest,
        index: int = 1,
        total: int = 1,
) -> Iterator[ImageOutput]:
    """执行一张 ChatGPT 图片任务。

    统一原则：上游 SSE 只负责启动/生成阶段；SSE 结束后只进入一次结果解析/轮询。
    不再在文本回复、空结果、轮询超时后叠加多轮长重试，避免一个配置的 300 秒被隐式放大到十几分钟。
    """
    last: dict[str, Any] = {}
    conversation_stream_started = time.perf_counter()
    conversation_wall_started = time.time()
    try:
        for event in conversation_events(
                backend,
                prompt=request.prompt,
                model=request.model,
                images=request.images or [],
                size=request.size,
                quality=request.quality,
        ):
            last = event
            if event.get("type") == "conversation.delta":
                yield ImageOutput(
                    kind="progress",
                    model=request.model,
                    index=index,
                    total=total,
                    text=str(event.get("delta") or ""),
                    upstream_event_type="conversation.delta",
                )
                continue
            if event.get("type") == "conversation.event":
                raw = event.get("raw")
                raw_type = str(raw.get("type") or "") if isinstance(raw, dict) else ""
                yield ImageOutput(
                    kind="progress",
                    model=request.model,
                    index=index,
                    total=total,
                    upstream_event_type=raw_type,
                )
    except (TimeoutError, curl_exceptions.Timeout) as exc:
        yield _recover_after_image_stream_timeout(
            backend,
            request,
            last,
            exc,
            index,
            total,
            conversation_wall_started,
        )
        return
    except curl_exceptions.RequestException as exc:
        if not any((
            last.get("conversation_id"),
            last.get("file_ids"),
            last.get("sediment_ids"),
        )):
            raise
        yield _recover_after_image_stream_timeout(
            backend,
            request,
            last,
            exc,
            index,
            total,
            conversation_wall_started,
            failure_code="image_stream_interrupted",
        )
        return

    conversation_id = str(last.get("conversation_id") or "")
    file_ids = [str(item) for item in last.get("file_ids") or []]
    sediment_ids = [str(item) for item in last.get("sediment_ids") or []]
    message = str(last.get("text") or "").strip()
    stream_failure = last.get("_image_failure")
    stream_failure = stream_failure if isinstance(stream_failure, ImageFailure) else None
    terminal_tool_arguments = last.get("_terminal_tool_arguments")
    terminal_tool_arguments = (
        terminal_tool_arguments if isinstance(terminal_tool_arguments, dict) else None
    )
    turn_use_case = str(last.get("turn_use_case") or "").strip().lower()
    async_task_type = str(last.get("async_task_type") or "").strip().lower()
    message_type = str(last.get("message_type") or "").strip().lower()
    has_image_arguments = is_image_generation_arguments(
        message,
        role=str(last.get("message_role") or ""),
        content_type=str(last.get("content_type") or ""),
    )
    should_poll_for_image = bool(
        (
            request.images
            or turn_use_case == "image gen"
            or async_task_type == "image_gen"
            or message_type in {"image_gen", "image_generation"}
            or has_image_arguments
        )
        and stream_failure is None
    )
    is_text_reply = bool(
        stream_failure is not None
        and stream_failure.code == "upstream_text_reply"
    )
    conversation_stream_ms = int((time.perf_counter() - conversation_stream_started) * 1000)
    http_timing = _backend_http_timing_data(backend)
    _monitor_image_stage(
        request,
        "image_stream_resolve_start",
        conversation_id=conversation_id,
        conversation_stream_ms=conversation_stream_ms,
        index=index,
        total=total,
        **http_timing,
    )
    logger.info({
        "event": "image_stream_resolve_start",
        "call_id": request.call_id,
        "conversation_id": conversation_id,
        "file_ids": file_ids,
        "sediment_ids": sediment_ids,
        "tool_invoked": last.get("tool_invoked"),
        "turn_use_case": turn_use_case,
        "async_task_type": async_task_type,
        "message_type": message_type,
        "has_image_arguments": has_image_arguments,
        "has_terminal_tool_arguments": terminal_tool_arguments is not None,
        "is_text_reply": is_text_reply,
        "should_poll_for_image": should_poll_for_image,
        "conversation_stream_ms": conversation_stream_ms,
        **http_timing,
    })
    if request.progress_callback:
        request.progress_callback("image_stream_resolve_start")

    if is_text_reply:
        logger.info({
            "event": "image_stream_text_reply_detected",
            "conversation_id": conversation_id,
            "message_preview": message[:200],
        })

    if terminal_tool_arguments is not None and not file_ids and not sediment_ids and stream_failure is None:
        argument_text = str(terminal_tool_arguments.get("text") or message).strip()
        terminal_failure = image_failure(
            "image_tool_error",
            raw_detail=argument_text,
        )
        yield ImageOutput(
            kind="message",
            model=request.model,
            index=index,
            total=total,
            text=argument_text,
            conversation_id=conversation_id,
            failure=terminal_failure,
        )
        return
    if not conversation_id and not file_ids and (sediment_ids or should_poll_for_image or stream_failure is not None):
        conversation_id = _recover_image_conversation_id(
            backend,
            request,
            reason="stream_result",
            message=message,
            started_at=conversation_wall_started,
        )

    if not file_ids and not sediment_ids and last.get("blocked"):
        _task_failure, detailed_error = _get_detailed_failure_from_tasks(backend, conversation_id)
        policy_failure = image_failure(
            "content_policy_violation",
            raw_detail=detailed_error or message,
        )
        yield ImageOutput(
            kind="message",
            model=request.model,
            index=index,
            total=total,
            text=detailed_error or message or public_image_error_message(policy_failure),
            conversation_id=conversation_id,
            failure=policy_failure,
        )
        return

    if is_text_reply and conversation_id and not file_ids and not sediment_ids:
        task_failure, task_error = _get_detailed_failure_from_tasks(
            backend,
            conversation_id,
            timeout_secs=5.0,
            wait_secs=0.0,
        )
        previous_code = stream_failure.code
        merged_failure = merge_message_failure(stream_failure, task_failure)
        stream_failure = merged_failure
        if task_failure is not None and merged_failure.code != previous_code:
            stream_failure = merged_failure.with_raw_detail(
                task_error or merged_failure.raw_detail or message
            )
            message = task_error or message
            logger.info({
                "event": "image_text_reply_structured_failure",
                "conversation_id": conversation_id,
                "failure_code": stream_failure.code,
                "error": diagnostic_excerpt(message, 1000),
            })

    if stream_failure is not None and not file_ids and not sediment_ids:
        yield ImageOutput(
            kind="message",
            model=request.model,
            index=index,
            total=total,
            text=_failure_raw_text(stream_failure, message),
            conversation_id=conversation_id,
            failure=stream_failure,
        )
        return

    if message and not file_ids and not sediment_ids and not should_poll_for_image and not is_text_reply:
        yield ImageOutput(
            kind="message",
            model=request.model,
            index=index,
            total=total,
            text=message,
            conversation_id=conversation_id,
            failure=image_failure("no_image_generated", raw_detail=message),
        )
        return

    image_urls = _resolve_image_urls_with_monitor(
        backend,
        request,
        conversation_id,
        file_ids,
        sediment_ids,
        poll_timeout_secs=config.image_poll_timeout_secs,
        index=index,
        total=total,
    )
    result_output = _image_result_output_from_urls(
        backend,
        request,
        conversation_id,
        image_urls,
        index,
        total,
    )
    if result_output:
        yield result_output
        return

    if message and not should_poll_for_image:
        yield ImageOutput(
            kind="message",
            model=request.model,
            index=index,
            total=total,
            text=message,
            conversation_id=conversation_id,
            failure=stream_failure or image_failure("no_image_generated", raw_detail=message),
        )
        return

    if conversation_id:
        failure = image_failure("no_image_generated")
        yield ImageOutput(
            kind="message",
            model=request.model,
            index=index,
            total=total,
            text=public_image_error_message(failure),
            conversation_id=conversation_id,
            failure=failure,
        )
        return

    failure = image_failure("no_image_generated")
    yield ImageOutput(
        kind="message",
        model=request.model,
        index=index,
        total=total,
        text=public_image_error_message(failure),
        conversation_id=conversation_id,
        failure=failure,
    )

def _codex_response_images(value: Any) -> list[str]:
    if isinstance(value, dict):
        if value.get("type") == "image_generation_call" and isinstance(value.get("result"), str):
            result = value["result"].strip()
            if result:
                return [result.split(",", 1)[1] if result.startswith("data:image/") else result]
        images: list[str] = []
        for item in value.values():
            images.extend(_codex_response_images(item))
        return images
    if isinstance(value, list):
        images: list[str] = []
        for item in value:
            images.extend(_codex_response_images(item))
        return images
    return []


def stream_codex_image_outputs(
        backend: OpenAIBackendAPI,
        request: ConversationRequest,
        index: int = 1,
        total: int = 1,
) -> Iterator[ImageOutput]:
    codex_started = time.perf_counter()
    events = list(backend.iter_codex_image_response_events(
        prompt=request.prompt,
        images=request.images or [],
        size=request.size,
        quality=request.quality,
    ))
    images = _codex_response_images(events)
    failure: ImageFailure | None = None
    for event in events:
        candidate = classify_upstream_message(event)
        failure = merge_message_failure(
            failure,
            candidate,
        )
    if images and failure is not None and failure.capability == "auth":
        backend._schedule_auth_recovery("codex_image_response_after_success")
    if request.trace_image_perf:
        _monitor_image_stage(
            request,
            "image_codex_response_done",
            response_ms=int((time.perf_counter() - codex_started) * 1000),
            image_count=len(images),
            index=index,
            total=total,
        )
        logger.info({
            "event": "image_codex_response_done",
            "call_id": request.call_id,
            "model": request.model,
            "index": index,
            "total": total,
            "response_ms": int((time.perf_counter() - codex_started) * 1000),
            "image_count": len(images),
        })
    if not images:
        if failure is not None:
            raise ImageGenerationError(
                "",
                failure=failure,
                raw_error="",
                upstream_error=diagnostic_excerpt(
                    _failure_raw_text(failure), 4000
                ),
                raw_upstream_message=diagnostic_excerpt(failure.public_detail, 4000),
            )
        raise ImageGenerationError(
            "No image result found in response",
            failure=image_failure("no_image_generated"),
        )
    formatted = format_image_result(
        [{"b64_json": item, "revised_prompt": request.prompt} for item in images],
        request.prompt,
        request.response_format,
        request.base_url,
        int(time.time()),
        requested_size=request.size,
        deadline_monotonic=request.deadline_monotonic or None,
    )
    data = formatted["data"]
    if data:
        yield ImageOutput(
            kind="result",
            model=request.model,
            index=index,
            total=total,
            data=data,
            image_urls=list(formatted.get("_image_urls") or []),
        )
        return
    raise ImageGenerationError(
        "No image result found in response",
        failure=image_failure("no_image_generated"),
    )


def _generate_single_image(
        request: ConversationRequest,
        index: int,
        total: int,
) -> list[ImageOutput]:
    """为单张图片执行生成逻辑（含重试），返回结果列表。

    该函数在独立线程中运行，每个线程使用不同的账号，
    实现并行生图，避免串行超时阻塞。
    """
    account_email = ""
    retry_token = ""
    attempted_tokens: set[str] = set()
    fallback_retry_pending = False
    fallback_retry_used = False
    fallback_from_egress: dict[str, Any] = {}
    image_attempts: list[dict[str, Any]] = []
    retry_error: ImageGenerationError | None = None
    pending_switch_attempt_index: int | None = None
    account_attempt_started = 0.0
    max_account_attempts = (
        config.image_max_account_attempts
        if config.image_account_retry_enabled
        else 1
    )
    single_started = time.perf_counter()

    def attach_attempts(value: Any) -> Any:
        value.image_attempts = [dict(item) for item in image_attempts]
        return value

    def attach_attempts_to_outputs(outputs: list[ImageOutput]) -> None:
        attempts = [dict(item) for item in image_attempts]
        for output in outputs:
            output.image_attempts = attempts

    def retry_with_different_account(
        failure: ImageFailure,
        error: ImageGenerationError | None = None,
    ) -> bool:
        nonlocal retry_token, fallback_retry_pending, retry_error, pending_switch_attempt_index
        if (
            failure.code == "task_interrupted"
            or (
                request.deadline_monotonic > 0
                and time.monotonic() >= request.deadline_monotonic
            )
            or not failure.switch_account
            or len(image_attempts) >= max_account_attempts
        ):
            return False
        retry_token = ""
        fallback_retry_pending = False
        retry_error = attach_attempts(error or ImageGenerationError(
            public_image_error_message(failure),
            failure=failure,
            account_email=account_email,
            raw_error="",
        ))
        pending_switch_attempt_index = len(image_attempts) - 1
        return True

    while True:
        request.monitor_attempt = len(image_attempts) + 1
        account_wait_started = time.perf_counter()
        stream_started = 0.0
        try:
            if retry_token:
                token = retry_token
                retry_token = ""
            else:
                if request.progress_callback:
                    request.progress_callback("getting_account")
                _monitor_image_stage(
                    request,
                    "image_getting_account",
                    max_account_attempts=max_account_attempts,
                    index=index,
                    total=total,
                )
                plan_type, _ = split_image_model(request.model)
                codex_model = is_codex_image_model(request.model)
                token = account_service.get_available_access_token(
                    plan_type=plan_type,
                    source_type="codex" if codex_model else None,
                    plan_types=("plus", "team", "pro") if codex_model and not plan_type else None,
                    excluded_tokens=attempted_tokens,
                    deadline_monotonic=request.deadline_monotonic or None,
                )
                attempted_tokens.add(token)
                account_attempt_started = account_wait_started
                fallback_retry_pending = False
                fallback_retry_used = False
                fallback_from_egress = {}
        except ImageAccountSelectionError as exc:
            _monitor_image_stage(
                request,
                "image_local_rejected",
                local_reason="account_pool",
                status="failed",
                index=index,
                total=total,
            )
            if retry_error is not None:
                raise attach_attempts(retry_error) from exc
            raise ImageGenerationError(
                str(exc) or "image generation failed",
                failure=image_failure(exc.code, raw_detail=str(exc)),
                account_email=account_email,
                image_attempts=image_attempts,
            ) from exc
        except RuntimeError as exc:
            _monitor_image_stage(
                request,
                "image_local_rejected",
                local_reason="account_pool",
                status="failed",
                index=index,
                total=total,
            )
            if retry_error is not None:
                raise attach_attempts(retry_error) from exc
            raise ImageGenerationError(
                str(exc) or "image generation failed",
                failure=image_failure("no_available_account"),
                account_email=account_email,
                image_attempts=image_attempts,
            ) from exc

        emitted_for_token = False
        returned_message = False
        returned_result = False
        image_slot_finalized = False
        attempt_started = account_attempt_started or account_wait_started
        attempt_conversation_id = ""
        attempt_access_token = token
        attempt_refresh_token = ""
        attempt_last_token_refresh_at = None

        def finalize_image_slot(
            success: bool,
            *,
            failure: ImageFailure | None = None,
            error: ImageGenerationError | None = None,
            quota_consumed: bool | None = None,
        ) -> None:
            nonlocal image_slot_finalized
            if image_slot_finalized:
                return
            image_slot_finalized = True
            try:
                if failure is not None and failure.code == "task_interrupted":
                    account_service.release_image_slot(token)
                else:
                    account_service.mark_image_result(
                        token,
                        success,
                        failure=failure,
                        quota_consumed=quota_consumed,
                        capabilities={"auth", "image_generation"}
                        | ({"file_upload"} if request.images else set()),
                        expected_access_token=attempt_access_token,
                        expected_refresh_token=attempt_refresh_token,
                        expected_last_token_refresh_at=attempt_last_token_refresh_at,
                    )
            except Exception as exc:
                logger.warning({
                    "event": "image_account_result_update_failed",
                    "account_email": account_email,
                    "success": success,
                    "failure_code": failure.code if failure is not None else "",
                    "error": diagnostic_excerpt(exc, 500),
                })
                try:
                    account_service.release_image_slot(token)
                except Exception as release_exc:
                    logger.warning({
                        "event": "image_account_slot_release_failed",
                        "account_email": account_email,
                        "error": diagnostic_excerpt(release_exc, 500),
                    })
            attempt: dict[str, Any] = {
                "slot": index,
                "attempt": len(image_attempts) + 1,
                "account_email": account_email,
                "status": (
                    "success"
                    if success
                    else "text_review"
                    if failure is not None and failure.outcome == "text"
                    else "failed"
                ),
                "duration_ms": max(0, int((time.perf_counter() - attempt_started) * 1000)),
            }
            if attempt_conversation_id:
                attempt["conversation_id"] = attempt_conversation_id
            if failure is not None:
                raw_error = str(getattr(error, "raw_error", "") or "").strip()
                if failure.code == "image_poll_timeout":
                    raw_error = ""
                upstream_error = str(
                    getattr(error, "upstream_error", "")
                    or getattr(error, "last_task_error", "")
                    or ""
                ).strip()
                raw_upstream_message = str(
                    getattr(error, "raw_upstream_message", "")
                    or getattr(error, "upstream_message_preview", "")
                    or getattr(error, "last_assistant_text", "")
                    or ""
                ).strip()
                public_error = (
                    error.public_error
                    if error is not None
                    else public_image_error_message(failure)
                )
                failure_fields = {
                    **failure.diagnostic_fields(),
                    "public_error": public_error,
                    "account_failure": failure.verify_account,
                    "switched_account": False,
                }
                if raw_error:
                    failure_fields["raw_error"] = raw_error
                if upstream_error:
                    failure_fields["upstream_error"] = upstream_error
                if raw_upstream_message:
                    failure_fields["raw_upstream_message"] = raw_upstream_message
                attempt.update(failure_fields)
            image_attempts.append(attempt)
            if failure is not None and request.trace_image_perf:
                _monitor_image_stage(
                    request,
                    "image_attempt_failed",
                    status="text_review" if failure.outcome == "text" else "failed",
                    **failure.diagnostic_fields(),
                    public_error=attempt.get("public_error", ""),
                    raw_error=attempt.get("raw_error", ""),
                    account_failure=failure.verify_account,
                    account_email=account_email,
                    conversation_id=attempt_conversation_id,
                    stream_error_ms=(
                        int((time.perf_counter() - stream_started) * 1000)
                        if stream_started > 0 else 0
                    ),
                    index=index,
                    total=total,
                )

        account_wait_ms = int((time.perf_counter() - account_wait_started) * 1000)
        account = account_service.get_account(token) or {}
        attempt_refresh_token = str(account.get("refresh_token") or "").strip()
        attempt_last_token_refresh_at = account.get("last_token_refresh_at")
        account_email = str(account.get("email") or "").strip()
        if pending_switch_attempt_index is not None:
            previous_attempt = image_attempts[pending_switch_attempt_index]
            previous_attempt["switched_account"] = True
            logger.warning({
                "event": "image_cross_account_retry",
                "call_id": request.call_id,
                "failure_code": previous_attempt.get("failure_code", ""),
                "account_email": previous_attempt.get("account_email", ""),
                "next_account_email": account_email,
                "attempted_account_count": len(image_attempts) + 1,
                "max_account_attempts": max_account_attempts,
                "index": index,
            })
            if request.trace_image_perf:
                _monitor_image_stage(
                    request,
                    "image_cross_account_retry",
                    status="retrying",
                    failure_code=previous_attempt.get("failure_code", ""),
                    account_email=account_email,
                    previous_account_email=previous_attempt.get("account_email", ""),
                    account_switch_count=len(image_attempts),
                    max_account_attempts=max_account_attempts,
                    index=index,
                    total=total,
                )
            pending_switch_attempt_index = None
        retry_error = None
        _monitor_image_stage(
            request,
            "image_account_lookup",
            account_wait_ms=account_wait_ms,
            account_email=account_email,
            account_found=bool(account),
            max_account_attempts=max_account_attempts,
            index=index,
            total=total,
        )
        if account_wait_ms >= 5000:
            logger.warning({
                "event": "image_account_wait_slow",
                "call_id": request.call_id,
                "account_wait_ms": account_wait_ms,
                "account_email": account_email,
                "index": index,
            })
        logger.debug({
            "event": "image_account_lookup",
            "call_id": request.call_id,
            "token_prefix": token[:12] + "..." if len(token) > 12 else token,
            "account_email": account_email,
            "account_found": bool(account),
            "account_wait_ms": account_wait_ms,
            "index": index,
        })
        backend: OpenAIBackendAPI | None = None
        egress_acquired = False
        try:
            egress_started = time.perf_counter()
            fallback_profile = None
            using_fallback_profile = fallback_retry_pending
            fallback_retry_pending = False
            if using_fallback_profile:
                fallback_profile = proxy_settings.get_fallback_profile(
                    upstream=True,
                    reserve_image_egress=True,
                    deadline_monotonic=request.deadline_monotonic or None,
                )
                if fallback_profile is None:
                    raise ImageGenerationError(
                        "fallback proxy is not configured",
                        failure=image_failure("upstream_connection_failed"),
                        account_email=account_email,
                    )
            backend = OpenAIBackendAPI(
                access_token=token,
                proxy_profile=fallback_profile,
                reserve_image_egress=fallback_profile is None,
                deadline_monotonic=request.deadline_monotonic or None,
            )
            if request.trace_image_perf:
                egress_data = _backend_egress_data(backend)
                if using_fallback_profile:
                    egress_data.update({
                        "fallback_retry": True,
                        "fallback_from_egress_key": fallback_from_egress.get("egress_key", ""),
                        "fallback_from_egress_label": fallback_from_egress.get("egress_label", ""),
                    })
                _monitor_image_stage(
                    request,
                    "image_egress_waiting",
                    account_email=account_email,
                    index=index,
                    total=total,
                    **egress_data,
                )
            egress_acquired = bool(
                getattr(backend.proxy_profile, "image_egress_reserved", False)
            )
            egress_acquire_ms = proxy_settings.acquire_image_egress(
                backend.proxy_profile,
                deadline_monotonic=request.deadline_monotonic or None,
            )
            egress_acquired = (
                int(getattr(backend.proxy_profile, "image_concurrency_limit", 0) or 0) > 0
            )
            egress_wait_ms = int((time.perf_counter() - egress_started) * 1000)
            if request.trace_image_perf:
                egress_data = _backend_egress_data(backend)
                if using_fallback_profile:
                    egress_data.update({
                        "fallback_retry": True,
                        "fallback_from_egress_key": fallback_from_egress.get("egress_key", ""),
                        "fallback_from_egress_label": fallback_from_egress.get("egress_label", ""),
                    })
                _monitor_image_stage(
                    request,
                    "image_egress_ready",
                    egress_wait_ms=egress_wait_ms,
                    egress_acquire_ms=egress_acquire_ms,
                    account_email=account_email,
                    index=index,
                    total=total,
                    **egress_data,
                )
                logger.debug({
                    "event": "image_egress_ready",
                    "call_id": request.call_id,
                    "model": request.model,
                    "index": index,
                    "total": total,
                    "account_email": account_email,
                    "egress_wait_ms": egress_wait_ms,
                    "egress_acquire_ms": egress_acquire_ms,
                    **egress_data,
                })
            if request.progress_callback or request.trace_image_perf:
                backend.progress_callback = _image_progress_callback_with_monitor(
                    request,
                    index,
                    total,
                    lambda: account_email,
                )
            stream_fn = stream_codex_image_outputs if is_codex_image_model(request.model) else stream_image_outputs
            outputs: list[ImageOutput] = []
            stream_started = time.perf_counter()
            for output in stream_fn(backend, request, index, total):
                if account_email and not output.account_email:
                    output.account_email = account_email
                if output.conversation_id:
                    attempt_conversation_id = output.conversation_id
                if output.kind == "message" and request.message_as_error:
                    failure = output.failure or image_failure(
                        "no_image_generated",
                        raw_detail=output.text,
                    )
                    raise ImageGenerationError(
                        output.text,
                        failure=failure,
                        account_email=account_email,
                        conversation_id=output.conversation_id,
                        raw_error="",
                        raw_upstream_message=output.text or "",
                    )
                emitted_for_token = True
                returned_message = output.kind == "message"
                returned_result = returned_result or output.kind == "result"
                outputs.append(output)
            stream_ms = int((time.perf_counter() - stream_started) * 1000)
            if request.trace_image_perf:
                _monitor_image_stage(
                    request,
                    "image_single_stream_done",
                    stream_ms=stream_ms,
                    returned_message=returned_message,
                    returned_result=returned_result,
                    account_email=account_email,
                    index=index,
                    total=total,
                )
                logger.info({
                    "event": "image_single_stream_done",
                    "call_id": request.call_id,
                    "model": request.model,
                    "index": index,
                    "total": total,
                    "stream_ms": stream_ms,
                    "returned_message": returned_message,
                    "returned_result": returned_result,
                    "account_email": account_email,
                })
            if returned_message:
                message_output = outputs[-1] if outputs else None
                message_failure = (
                    message_output.failure
                    if message_output is not None and message_output.failure is not None
                    else image_failure(
                        "no_image_generated",
                        raw_detail=message_output.text if message_output is not None else "",
                    )
                )
                message_error = ImageGenerationError(
                    message_output.text if message_output is not None else "image generation failed",
                    failure=message_failure,
                    account_email=account_email,
                    conversation_id=attempt_conversation_id,
                    raw_error="",
                    raw_upstream_message=message_output.text if message_output is not None else "",
                    image_attempts=image_attempts,
                )
                finalize_image_slot(False, failure=message_failure, error=message_error)
                attach_attempts_to_outputs(outputs)
                if retry_with_different_account(message_failure, message_error):
                    continue
                if request.trace_image_perf:
                    _monitor_image_stage(
                        request,
                        "image_single_done",
                        total_ms=int((time.perf_counter() - single_started) * 1000),
                        status="message",
                        account_email=account_email,
                        index=index,
                        total=total,
                    )
                    logger.info({
                        "event": "image_single_done",
                        "call_id": request.call_id,
                        "model": request.model,
                        "index": index,
                        "total": total,
                        "total_ms": int((time.perf_counter() - single_started) * 1000),
                        "status": "message",
                        "account_email": account_email,
                    })
                return outputs
            if not returned_result:
                missing_result_failure = image_failure("no_image_generated")
                if emitted_for_token:
                    attempt_conversation_id = outputs[-1].conversation_id if outputs else ""
                raise ImageGenerationError(
                    "upstream completed without generating images",
                    failure=missing_result_failure,
                    account_email=account_email,
                    conversation_id=attempt_conversation_id,
                    image_attempts=image_attempts,
                )
            _cleanup_image_conversations_after_success(backend, outputs)
            finalize_image_slot(True)
            attach_attempts_to_outputs(outputs)
            if request.trace_image_perf:
                _monitor_image_stage(
                    request,
                    "image_single_done",
                    total_ms=int((time.perf_counter() - single_started) * 1000),
                    status="success",
                    account_email=account_email,
                    index=index,
                    total=total,
                )
                logger.info({
                    "event": "image_single_done",
                    "call_id": request.call_id,
                    "model": request.model,
                    "index": index,
                    "total": total,
                    "total_ms": int((time.perf_counter() - single_started) * 1000),
                    "status": "success",
                    "account_email": account_email,
                })
            return outputs
        except Exception as exc:
            failure = (
                image_failure("task_interrupted", raw_detail=str(exc))
                if isinstance(exc, ImageEgressDeadlineError)
                else classify_image_exception(exc)
            )
            attempt_conversation_id = str(getattr(exc, "conversation_id", "") or attempt_conversation_id)
            stream_error_ms = int((time.perf_counter() - stream_started) * 1000) if stream_started > 0 else 0
            http_timing = _backend_http_timing_data(backend)
            quick_timeout_retry_ms = min(30000, max(5000, int(config.image_stream_timeout_secs * 1000 * 0.2)))
            early_connection_failure = (
                not emitted_for_token
                and (stream_error_ms == 0 or stream_error_ms <= quick_timeout_retry_ms)
                and failure.code in {
                    "upstream_connection_failed",
                    "upstream_connection_timeout",
                    "upstream_unavailable",
                }
            )
            fallback_reference = proxy_settings.get_fallback_proxy_reference()
            if early_connection_failure and fallback_reference and not fallback_retry_used:
                fallback_retry_used = True
                fallback_retry_pending = True
                retry_token = token
                fallback_from_egress = _backend_egress_data(backend) if backend is not None else {}
                logger.warning({
                    "event": "image_stream_fallback_retry",
                    "request_token": token,
                    "account_email": account_email,
                    "index": index,
                    "fallback_proxy_configured": True,
                    "fallback_from_egress_key": fallback_from_egress.get("egress_key", ""),
                    "fallback_from_egress_label": fallback_from_egress.get("egress_label", ""),
                    "stream_error_ms": stream_error_ms,
                    "error": str(exc)[:200],
                })
                if request.trace_image_perf:
                    _monitor_image_stage(
                        request,
                        "image_egress_fallback_retry",
                        account_email=account_email,
                        index=index,
                        total=total,
                        status="retrying",
                        fallback_from_egress_key=fallback_from_egress.get("egress_key", ""),
                        fallback_from_egress_label=fallback_from_egress.get("egress_label", ""),
                    )
                continue

            if isinstance(exc, ImageGenerationError):
                image_error = exc
                if account_email and not image_error.account_email:
                    image_error.account_email = account_email
            else:
                upstream_http_error = isinstance(exc, UpstreamHTTPError)
                explicit_raw_error = getattr(exc, "raw_error", None)
                raw_error = (
                    ""
                    if upstream_http_error
                    else str(explicit_raw_error or "").strip()
                    if explicit_raw_error is not None
                    else (
                        ""
                        if failure.code == "image_poll_timeout"
                        else str(exc).strip() or "image generation failed"
                    )
                )
                upstream_error = str(
                    getattr(exc, "upstream_error", "")
                    or getattr(exc, "last_task_error", "")
                    or (str(exc) if upstream_http_error else "")
                )
                raw_upstream_message = str(
                    getattr(exc, "raw_upstream_message", "")
                    or ""
                )
                image_error = ImageGenerationError(
                    raw_error,
                    failure=failure,
                    account_email=account_email,
                    conversation_id=attempt_conversation_id,
                    raw_error=raw_error,
                    upstream_error=upstream_error,
                    raw_upstream_message=raw_upstream_message,
                    image_attempts=image_attempts,
                )
                for attr in (
                    "conversation_id",
                    "poll_attempts",
                    "poll_timeout_secs",
                    "last_task_error",
                    "last_conversation_snapshot",
                    "last_assistant_text",
                    "stream_timeout_secs",
                    "stream_timeout_followup",
                ):
                    if hasattr(exc, attr):
                        setattr(image_error, attr, getattr(exc, attr))

            logger.warning({
                "event": "image_attempt_failed",
                "request_token": token,
                "account_email": account_email,
                "error": diagnostic_excerpt(image_error.raw_error or str(image_error), 1000),
                "public_error": diagnostic_excerpt(image_error.public_error, 1000),
                "failure_code": failure.code,
                "status_code": failure.status_code,
                "account_failure": failure.verify_account,
                "stream_error_ms": stream_error_ms,
                "index": index,
                **http_timing,
            })
            finalize_image_slot(
                False,
                failure=failure,
                error=image_error,
                quota_consumed=(failure.code == "image_download_failed"),
            )
            attach_attempts(image_error)
            if retry_with_different_account(failure, image_error):
                continue
            if image_error is exc:
                raise
            raise image_error from exc
        finally:
            if egress_acquired and backend is not None:
                proxy_settings.release_image_egress(backend.proxy_profile)
            if backend is not None:
                backend.close()


def _select_image_pool_error(errors: dict[int, Exception]) -> Exception | None:
    """Select one deterministic failure and retain every slot's attempts."""
    if not errors:
        return None

    def score(item: tuple[int, Exception]) -> tuple[int, int]:
        slot, exc = item
        failure = classify_image_exception(exc)
        return (
            image_failure_priority(failure),
            -slot,
        )

    _, selected = max(errors.items(), key=score)
    selected_failure = classify_image_exception(selected)
    setattr(selected, "failure", selected_failure)

    attempts: list[dict[str, Any]] = []
    for slot, exc in sorted(errors.items()):
        raw_attempts = getattr(exc, "image_attempts", None)
        if not isinstance(raw_attempts, (list, tuple)):
            continue
        for attempt_number, raw_attempt in enumerate(raw_attempts, start=1):
            if not isinstance(raw_attempt, dict):
                continue
            attempt = dict(raw_attempt)
            attempt.setdefault("slot", slot)
            attempt.setdefault("attempt", attempt_number)
            if attempt not in attempts:
                attempts.append(attempt)

    attempts.sort(
        key=lambda item: (
            int(item.get("slot") or 0),
            int(item.get("attempt") or 0),
        )
    )
    if attempts:
        setattr(selected, "image_attempts", attempts)
    return selected


def stream_image_outputs_with_pool(request: ConversationRequest) -> Iterator[ImageOutput]:
    """并行生成多张图片，每张图片使用独立线程和账号，互不阻塞。"""
    if not is_supported_image_model(request.model):
        _monitor_image_stage(
            request,
            "image_local_rejected",
            local_reason="unsupported_model",
            status="failed",
        )
        raise ImageGenerationError(
            "unsupported image model,supported models: " + ", ".join(sorted(IMAGE_MODELS)),
            failure=image_failure("unsupported_model"),
        )

    if request.deadline_monotonic <= 0:
        request.deadline_monotonic = (
            time.monotonic() + max(0.001, float(config.image_request_timeout_secs))
        )

    if request.n <= 1:
        # 单张图片，直接执行（无需线程池开销）
        outputs = _generate_single_image(replace(request), 1, 1)
        if not outputs:
            raise ImageGenerationError(
                "image generation completed without output",
                failure=image_failure("no_image_generated"),
            )
        for output in outputs:
            yield output
        return

    # 多张图片：根据配置选择并行或串行执行
    if not config.image_parallel_generation:
        logger.info({
            "event": "image_serial_generation_start",
            "n": request.n,
            "model": request.model,
        })
        successful_slots: set[int] = set()
        errors: dict[int, Exception] = {}
        for index in range(1, request.n + 1):
            try:
                outputs = _generate_single_image(replace(request), index, request.n)
            except Exception as exc:
                _capture_failed_image_attempts(request, exc)
                errors[index] = exc
                logger.warning({
                    "event": "image_serial_generation_error",
                    "index": index,
                    "error": str(exc)[:300],
                })
                if time.monotonic() >= request.deadline_monotonic:
                    break
                continue
            if any(output.kind == "result" and output.data for output in outputs):
                successful_slots.add(index)
            for output in outputs:
                yield output
        if successful_slots:
            for index, exc in errors.items():
                logger.warning({
                    "event": "image_serial_partial_failure",
                    "failed_index": index,
                    "error": str(exc)[:200],
                })
            return
        if selected_error := _select_image_pool_error(errors):
            raise selected_error
        raise ImageGenerationError(
            "no account in the pool could generate images",
            failure=image_failure("no_available_account"),
        )

    logger.info({
        "event": "image_parallel_generation_start",
        "n": request.n,
        "model": request.model,
    })
    # 每张图片一个线程，同时启动
    futures = {}
    errors: dict[int, Exception] = {}
    successful_slots: set[int] = set()
    processed_futures = set()
    executor = ThreadPoolExecutor(max_workers=request.n)

    def consume_future(future: Any) -> list[ImageOutput]:
        index = futures[future]
        processed_futures.add(future)
        try:
            outputs = future.result()
        except Exception as exc:
            _capture_failed_image_attempts(request, exc)
            errors[index] = exc
            error_text = str(exc)
            logger.warning({
                "event": "image_parallel_generation_error",
                "index": index,
                "error": error_text[:300],
            })
            if not successful_slots:
                logger.warning({
                    "event": "image_parallel_failure_before_success",
                    "failed_index": index,
                    "error": error_text[:200],
                })
            return []
        if any(output.kind == "result" and output.data for output in outputs):
            successful_slots.add(index)
        return outputs

    try:
        for index in range(1, request.n + 1):
            future = executor.submit(_generate_single_image, replace(request), index, request.n)
            futures[future] = index

        # yield 结果：按完成顺序立即输出，不再等所有图片都结束后才返回成功结果。
        try:
            remaining = max(0.0, request.deadline_monotonic - time.monotonic())
            for future in as_completed(futures, timeout=remaining):
                for output in consume_future(future):
                    yield output
        except FuturesTimeoutError:
            pending = [future for future in futures if future not in processed_futures]
            done, _ = wait(pending, timeout=0.05)
            for future in done:
                for output in consume_future(future):
                    yield output
            for future in pending:
                if future in processed_futures:
                    continue
                index = futures[future]
                future.cancel()
                errors[index] = ImageGenerationError(
                    f"image slot {index} exceeded the request deadline",
                    failure=image_failure("task_interrupted"),
                )
    finally:
        for future in futures:
            if not future.done():
                future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

    # 如果有失败但也有成功，记录警告
    if successful_slots:
        for index in range(1, request.n + 1):
            if index in errors:
                logger.warning({
                    "event": "image_parallel_partial_failure",
                    "failed_index": index,
                    "error": str(errors[index])[:200],
                })
        return

    if selected_error := _select_image_pool_error(errors):
        raise selected_error
    raise ImageGenerationError(
        "no account in the pool could generate images",
        failure=image_failure("no_available_account"),
    )


def _image_stream_payload(output: ImageOutput, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    item = {"type": event_type, **payload}
    if output.account_email:
        item["_account_email"] = output.account_email
    if output.conversation_id:
        item["_conversation_id"] = output.conversation_id
    if output.image_attempts:
        item["_image_attempts"] = [dict(attempt) for attempt in output.image_attempts]
    return item


def stream_image_chunks(
    outputs: Iterable[ImageOutput],
    event_prefix: str = "image_generation",
    usage_builder: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None,
    partial_images: object = 0,
) -> Iterator[dict[str, Any]]:
    prefix = str(event_prefix or "image_generation").strip() or "image_generation"
    # ChatGPT Web only gives us final image bytes here. Emitting those bytes as a
    # synthetic partial_image makes some clients display the same image twice.
    for output in outputs:
        if output.kind == "result":
            for item_index, item in enumerate(output.data):
                if not isinstance(item, dict):
                    continue
                b64_json = str(item.get("b64_json") or "").strip()
                if not b64_json:
                    continue
                completed: dict[str, Any] = {"b64_json": b64_json}
                if usage_builder:
                    usage = usage_builder([item])
                    if usage:
                        completed["usage"] = usage
                completed_payload = _image_stream_payload(output, f"{prefix}.completed", completed)
                if output.image_urls:
                    completed_payload["_image_urls"] = list(output.image_urls)
                yield completed_payload
        elif output.kind == "message" and output.text:
            yield _image_stream_payload(
                output,
                f"{prefix}.failed",
                {"error": {"message": output.text, "type": "image_generation_error"}},
            )


def collect_image_outputs(
        outputs: Iterable[ImageOutput],
        result_callback: Callable[[list[dict[str, Any]]], None] | None = None,
) -> dict[str, Any]:
    created = None
    data: list[dict[str, Any]] = []
    message = ""
    progress_parts: list[str] = []
    account_email = ""
    conversation_id = ""
    image_urls: list[str] = []
    image_attempts: list[dict[str, Any]] = []
    failed_output: ImageOutput | None = None
    for output in outputs:
        created = created or output.created
        if output.account_email and not account_email:
            account_email = output.account_email
        if output.conversation_id and not conversation_id:
            conversation_id = output.conversation_id
        for attempt in output.image_attempts:
            if isinstance(attempt, dict) and attempt not in image_attempts:
                image_attempts.append(dict(attempt))
        if output.kind == "progress" and output.text:
            progress_parts.append(output.text)
        elif output.kind == "message":
            message = output.text
            if output.failure is not None and failed_output is None:
                failed_output = output
        elif output.kind == "result":
            data.extend(output.data)
            image_urls.extend(output.image_urls)
            if callable(result_callback) and output.data:
                result_callback([dict(item) for item in data])

    if failed_output is not None:
        failure = failed_output.failure or image_failure(
            "no_image_generated",
            raw_detail=failed_output.text,
        )
        raise ImageGenerationError(
            failed_output.text or public_image_error_message(failure),
            failure=failure,
            account_email=failed_output.account_email or account_email,
            conversation_id=failed_output.conversation_id or conversation_id,
            image_attempts=image_attempts,
        )

    result: dict[str, Any] = {"created": created or int(time.time()), "data": data}
    if not data:
        text = message or "".join(progress_parts).strip()
        if text:
            result["message"] = text
    if account_email:
        result["_account_email"] = account_email
    if conversation_id:
        result["_conversation_id"] = conversation_id
    if image_urls:
        result["_image_urls"] = list(dict.fromkeys(image_urls))
    if image_attempts:
        result["_image_attempts"] = image_attempts
    return result
