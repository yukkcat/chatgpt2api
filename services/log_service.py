from __future__ import annotations

import json
import itertools
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from services.call_record_service import CallRecordService
from services.storage.call_record_repository import CallRecordCursorMismatch

from services.image_failure import (
    ImageFailure,
    ImageGenerationError,
    classify_image_exception,
    is_text_review_failure_code,
    public_image_error_message,
)
from services.protocol.error_response import anthropic_error_response, openai_error_response
from services.realtime_monitor_service import realtime_monitor_service
from utils.diagnostics import (
    diagnostic_excerpt,
    exception_diagnostic_fields,
    scrub_diagnostic_value,
)
from utils.helper import anthropic_sse_stream, image_sse_stream, sse_json_stream
from utils.log import logger
from utils.timezone import beijing_from_timestamp, beijing_now_str

LOG_TYPE_CALL = "call"
LOG_TYPE_ACCOUNT = "account"
INTERNAL_RESPONSE_KEYS = {
    "_account_email",
    "_call_error",
    "_conversation_id",
    "_call_id",
    "_call_status",
    "_image_urls",
    "_image_attempts",
}
LOG_IMAGE_URL_RE = re.compile(r"(?:!\[[^\]]*\]\()(?P<url>(?:https?://|/images/|/image-thumbnails/)[^\s)\"']+)\)")
PERF_WAIT_WARN_MS = 1000
REQUEST_TEXT_EXCERPT_LIMIT = 1000
REQUEST_TEXT_FULL_LIMIT = 50000

LogService = CallRecordService
LogCursorMismatch = CallRecordCursorMismatch
log_service = LogService()


def cleanup_old_logs() -> dict[str, int | bool]:
    from services.config import config
    from services.retention_cleanup_service import retention_cleanup_coordinator

    return retention_cleanup_coordinator.run_logs(config.log_retention_days)


def _auto_cleanup_worker(stop_event: threading.Event) -> None:
    from services.retention_cleanup_service import retention_cleanup_coordinator

    retention_cleanup_coordinator.scheduler_worker(stop_event)


def start_log_cleanup_scheduler(stop_event: threading.Event) -> threading.Thread:
    from services.retention_cleanup_service import start_retention_cleanup_scheduler

    return start_retention_cleanup_scheduler(stop_event)


def _collect_urls(value: object) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "url" and isinstance(item, str):
                urls.append(item)
            elif key in {"urls", "_image_urls"} and isinstance(item, list):
                urls.extend(str(url) for url in item if isinstance(url, str))
            else:
                urls.extend(_collect_urls(item))
    elif isinstance(value, list):
        for item in value:
            urls.extend(_collect_urls(item))
    elif isinstance(value, str):
        urls.extend(match.group("url").rstrip(".,;") for match in LOG_IMAGE_URL_RE.finditer(value))
    return urls


def _collect_account_emails(value: object) -> list[str]:
    emails: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"_account_email", "account_email"} and isinstance(item, str) and item.strip():
                emails.append(item.strip())
            else:
                emails.extend(_collect_account_emails(item))
    elif isinstance(value, list):
        for item in value:
            emails.extend(_collect_account_emails(item))
    return emails


def _collect_conversation_ids(value: object) -> list[str]:
    ids: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "_conversation_id" and isinstance(item, str) and item.strip():
                ids.append(item.strip())
            else:
                ids.extend(_collect_conversation_ids(item))
    elif isinstance(value, list):
        for item in value:
            ids.extend(_collect_conversation_ids(item))
    return ids


IMAGE_ATTEMPT_KEYS = {
    "slot",
    "attempt",
    "account_email",
    "status",
    "failure_code",
    "failure_scope",
    "failure_capability",
    "failure_retryable",
    "failure_account_failure",
    "failure_retry_after",
    "status_code",
    "error_type",
    "public_error",
    "raw_error",
    "upstream_error",
    "raw_upstream_message",
    "account_failure",
    "switched_account",
    "conversation_id",
    "duration_ms",
    "monitor",
}
IMAGE_ATTEMPT_INTEGER_KEYS = {
    "slot", "attempt", "duration_ms", "status_code", "failure_retry_after",
}
IMAGE_ATTEMPT_BOOLEAN_KEYS = {
    "failure_retryable", "failure_account_failure", "account_failure", "switched_account",
}


def _normalize_image_attempt_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return None


def _normalize_image_attempt_int(key: str, value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(1 if key in {"slot", "attempt"} else 0, parsed)


def _normalize_image_attempt_monitor(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    monitor: dict[str, object] = {}
    raw_metrics = value.get("metrics")
    if isinstance(raw_metrics, dict):
        metrics: dict[str, int] = {}
        for key, item in raw_metrics.items():
            if not str(key).endswith("_ms"):
                continue
            try:
                parsed = max(0, int(item))
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                metrics[str(key)] = parsed
        if metrics:
            monitor["metrics"] = metrics
    raw_events = value.get("events")
    if isinstance(raw_events, list):
        events: list[dict[str, object]] = []
        for raw_event in raw_events[-40:]:
            if not isinstance(raw_event, dict):
                continue
            event: dict[str, object] = {}
            for key, item in raw_event.items():
                if str(key).endswith("_ms"):
                    try:
                        parsed = max(0, int(item))
                    except (TypeError, ValueError):
                        continue
                    if parsed > 0:
                        event[str(key)] = parsed
                elif key in IMAGE_ATTEMPT_INTEGER_KEYS:
                    parsed = _normalize_image_attempt_int(key, item)
                    if parsed is not None:
                        event[key] = parsed
                elif key in IMAGE_ATTEMPT_BOOLEAN_KEYS:
                    parsed = _normalize_image_attempt_bool(item)
                    if parsed is not None:
                        event[key] = parsed
                elif key in {
                    "time", "event", "label", "status",
                    "failure_code", "failure_scope", "failure_capability",
                    "error_type", "public_error",
                }:
                    text = str(item or "").strip()
                    if text:
                        event[key] = text
            if event:
                events.append(event)
        if events:
            monitor["events"] = events
    return monitor or None


def _normalize_image_attempt(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    if not ({"slot", "attempt", "status"} <= value.keys()):
        return None
    attempt: dict[str, object] = {}
    for key in IMAGE_ATTEMPT_KEYS:
        item = value.get(key)
        if item in (None, ""):
            continue
        if key == "monitor":
            monitor = _normalize_image_attempt_monitor(item)
            if monitor:
                attempt[key] = monitor
        elif key in IMAGE_ATTEMPT_INTEGER_KEYS:
            parsed = _normalize_image_attempt_int(key, item)
            if parsed is not None:
                attempt[key] = parsed
        elif key in IMAGE_ATTEMPT_BOOLEAN_KEYS:
            parsed = _normalize_image_attempt_bool(item)
            if parsed is not None:
                attempt[key] = parsed
        else:
            text = str(item).strip()
            if text:
                attempt[key] = text
    if not ({"slot", "attempt", "status"} <= attempt.keys()):
        return None
    return attempt


def collect_image_attempts(value: object) -> list[dict[str, object]]:
    attempts: list[dict[str, object]] = []
    seen: set[str] = set()
    pending: list[object] = [value]
    visited: set[int] = set()
    while pending:
        item = pending.pop()
        if isinstance(item, BaseException):
            pending.append(getattr(item, "image_attempts", None))
            continue
        if isinstance(item, dict):
            identity = id(item)
            if identity in visited:
                continue
            visited.add(identity)
            normalized = _normalize_image_attempt(item)
            if normalized is not None:
                signature = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
                if signature not in seen:
                    seen.add(signature)
                    attempts.append(normalized)
                continue
            for key, child in item.items():
                if key in {"_image_attempts", "image_attempts"} or isinstance(child, (dict, list, tuple)):
                    pending.append(child)
        elif isinstance(item, (list, tuple)):
            pending.extend(reversed(item))
    return attempts


IMAGE_TRACE_REQUEST_KEYS = {
    "n",
    "size",
    "quality",
    "response_format",
    "stream",
    "partial_images",
}


def _image_trace_metadata(body: dict[str, Any]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for key in IMAGE_TRACE_REQUEST_KEYS:
        if key not in body:
            continue
        value = body.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (str, int, float, bool)):
            metadata[key] = value
    images = body.get("images")
    if isinstance(images, list) and images:
        metadata["input_image_count"] = len(images)
    return metadata


def _image_result_metrics(value: object) -> dict[str, object]:
    metrics = {
        "result_data_count": 0,
        "result_url_count": 0,
        "result_b64_count": 0,
        "result_b64_chars": 0,
    }

    def visit(item: object) -> None:
        if isinstance(item, dict):
            if "data" in item and isinstance(item.get("data"), list):
                metrics["result_data_count"] = max(
                    int(metrics["result_data_count"]),
                    len(item.get("data") or []),
                )
            url = item.get("url")
            if isinstance(url, str) and url.strip():
                metrics["result_url_count"] = int(metrics["result_url_count"]) + 1
            b64_json = item.get("b64_json")
            if isinstance(b64_json, str) and b64_json.strip():
                metrics["result_b64_count"] = int(metrics["result_b64_count"]) + 1
                metrics["result_b64_chars"] = int(metrics["result_b64_chars"]) + len(b64_json)
            for nested in item.values():
                if isinstance(nested, (dict, list)):
                    visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return {
        key: value
        for key, value in metrics.items()
        if value
    }


def _strip_internal_response_fields(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _strip_internal_response_fields(item)
            for key, item in value.items()
            if key not in INTERNAL_RESPONSE_KEYS
        }
    if isinstance(value, list):
        return [_strip_internal_response_fields(item) for item in value]
    return value


def _request_excerpt(text: object, limit: int = REQUEST_TEXT_EXCERPT_LIMIT) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _request_full_text(text: object, limit: int = REQUEST_TEXT_FULL_LIMIT) -> tuple[str, bool]:
    value = str(text or "").strip()
    if not value:
        return "", False
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized, False
    return normalized[: limit - 1].rstrip() + "…", True


def _exception_log_fields(exc: Exception, *, image: bool = False) -> dict[str, object]:
    fields = exception_diagnostic_fields(exc, include_status_code=True)
    attempts = collect_image_attempts(exc)
    if attempts:
        fields["image_attempts"] = attempts
    failure = getattr(exc, "failure", None)
    if image or failure is not None:
        failure = _final_image_failure(exc)
        fields.update(failure.diagnostic_fields())
        fields["error_code"] = failure.code
        fields["public_error"] = _public_image_exception_message(exc, failure)
        if failure.code == "image_poll_timeout":
            fields.pop("raw_error", None)
        elif "raw_error" not in fields and not hasattr(exc, "raw_error"):
            fields["raw_error"] = diagnostic_excerpt(str(exc), 4000)
    return fields


def _final_image_failure(exc: Exception) -> ImageFailure:
    failure = getattr(exc, "failure", None)
    if isinstance(failure, ImageFailure):
        return failure
    return classify_image_exception(exc)


def _public_image_exception_message(
    exc: Exception,
    failure: ImageFailure | None = None,
) -> str:
    public_error = getattr(exc, "public_error", "")
    if isinstance(public_error, str) and public_error.strip():
        return public_error.strip()
    return public_image_error_message(failure or _final_image_failure(exc), exc)


def _image_error_payload(exc: Exception) -> dict[str, object]:
    failure = _final_image_failure(exc)
    return {
        "error": {
            "message": _public_image_exception_message(exc, failure),
            "type": failure.error_type,
            "param": getattr(exc, "param", None),
            "code": failure.code,
        }
    }


def _image_error_response(exc: Exception) -> JSONResponse:
    failure = _final_image_failure(exc)
    return openai_error_response(_image_error_payload(exc), failure.status_code)


def _protocol_error_response(exc: Exception, status_code: int, sse: str) -> JSONResponse:
    message = str(exc)
    if sse == "anthropic":
        return anthropic_error_response(message, status_code)
    return openai_error_response(message, status_code)


def _next_item(items):
    try:
        return True, next(items)
    except StopIteration:
        return False, None


@dataclass
class LoggedCall:
    identity: dict[str, object]
    endpoint: str
    model: str
    summary: str
    started: float = field(default_factory=time.time)
    request_text: str = ""
    request_shape: dict[str, int] | None = None
    image_request: bool = False
    call_id: str = field(default_factory=lambda: uuid4().hex[:16])
    perf_timings: dict[str, int] = field(default_factory=dict)
    trace_metadata: dict[str, object] = field(default_factory=dict)

    async def run(self, handler, *args, sse: str = "openai"):
        if args and isinstance(args[0], dict):
            self.attach_trace_metadata(args[0])
        image_request = self._is_image_request()
        trace_perf = self._trace_image_perf()
        if trace_perf:
            realtime_monitor_service.start(
                self.call_id,
                endpoint=self.endpoint,
                model=self.model,
                summary=self.summary,
                role=str(self.identity.get("role") or ""),
                key_name=str(self.identity.get("name") or ""),
            )
        handler_submitted = time.perf_counter()

        def _call_handler():
            handler_started = time.perf_counter()
            queue_ms = int((handler_started - handler_submitted) * 1000)
            if trace_perf:
                self.perf_timings["handler_queue_ms"] = queue_ms
                realtime_monitor_service.stage(
                    self.call_id,
                    "handler_started",
                    handler_queue_ms=queue_ms,
                    endpoint=self.endpoint,
                    model=self.model,
                )
            if trace_perf and queue_ms >= PERF_WAIT_WARN_MS:
                logger.warning({
                    "event": "api_handler_threadpool_wait_slow",
                    "call_id": self.call_id,
                    "endpoint": self.endpoint,
                    "model": self.model,
                    "queue_ms": queue_ms,
                })
            try:
                return handler(*args)
            finally:
                if trace_perf:
                    self.perf_timings["handler_exec_ms"] = int((time.perf_counter() - handler_started) * 1000)

        try:
            result = await run_in_threadpool(_call_handler)
        except ImageGenerationError as exc:
            self.log("调用失败", status="failed", error=_public_image_exception_message(exc), account_email=getattr(exc, "account_email", ""),
                     conversation_id=getattr(exc, "conversation_id", ""),
                     extra=_exception_log_fields(exc, image=image_request))
            return _image_error_response(exc)
        except HTTPException as exc:
            self.log("调用失败", status="failed", error=str(exc.detail))
            raise
        except Exception as exc:
            self.log("调用失败", status="failed", error=(
                _public_image_exception_message(exc) if image_request else str(exc)
            ), account_email=getattr(exc, "account_email", ""),
                     extra=_exception_log_fields(exc, image=image_request))
            if image_request:
                return _image_error_response(exc)
            return _protocol_error_response(exc, 502, sse)

        if isinstance(result, dict):
            projected_status = str(result.get("_call_status") or "success").strip().lower()
            if projected_status not in {"success", "failed", "text_review"}:
                projected_status = "success"
            projected_error = str(result.get("_call_error") or "").strip()
            projected_extra: dict[str, object] = {}
            if projected_status != "success" and result.get("error_code"):
                projected_extra["error_code"] = result["error_code"]
            self.log(
                "调用失败" if projected_status == "failed" else "调用完成",
                result,
                status=projected_status,
                error=projected_error,
                account_email=str(result.get("_account_email") or ""),
                conversation_id=str(result.get("_conversation_id") or ""),
                extra=projected_extra or None,
            )
            return _strip_internal_response_fields(result)

        if self.endpoint.startswith("/v1/images"):
            sender = lambda items: image_sse_stream(items, error_builder=_image_error_payload)
        else:
            if sse == "anthropic":
                sender = anthropic_sse_stream
            elif image_request:
                sender = lambda items: sse_json_stream(items, error_builder=_image_error_payload)
            else:
                sender = sse_json_stream
        first_item_submitted = time.perf_counter()

        def _next_item_with_timing():
            first_item_started = time.perf_counter()
            queue_ms = int((first_item_started - first_item_submitted) * 1000)
            if trace_perf:
                self.perf_timings["stream_first_queue_ms"] = queue_ms
                realtime_monitor_service.stage(
                    self.call_id,
                    "stream_first_item",
                    stream_first_queue_ms=queue_ms,
                    endpoint=self.endpoint,
                    model=self.model,
                )
            if trace_perf and queue_ms >= PERF_WAIT_WARN_MS:
                logger.warning({
                    "event": "api_stream_first_item_threadpool_wait_slow",
                    "call_id": self.call_id,
                    "endpoint": self.endpoint,
                    "model": self.model,
                    "queue_ms": queue_ms,
                })
            try:
                return _next_item(result)
            finally:
                if trace_perf:
                    self.perf_timings["stream_first_exec_ms"] = int((time.perf_counter() - first_item_started) * 1000)

        try:
            has_first, first = await run_in_threadpool(_next_item_with_timing)
        except ImageGenerationError as exc:
            self.log("调用失败", status="failed", error=_public_image_exception_message(exc), account_email=getattr(exc, "account_email", ""),
                     conversation_id=getattr(exc, "conversation_id", ""),
                     extra=_exception_log_fields(exc, image=image_request))
            return _image_error_response(exc)
        except HTTPException as exc:
            self.log("调用失败", status="failed", error=str(exc.detail))
            raise
        except Exception as exc:
            self.log("调用失败", status="failed", error=(
                _public_image_exception_message(exc) if image_request else str(exc)
            ), account_email=getattr(exc, "account_email", ""),
                     extra=_exception_log_fields(exc, image=image_request))
            if image_request:
                return _image_error_response(exc)
            return _protocol_error_response(exc, 502, sse)
        if not has_first:
            self.log("流式调用结束")
            return StreamingResponse(sender(()), media_type="text/event-stream")
        return StreamingResponse(sender(self.stream(itertools.chain([first], result))), media_type="text/event-stream")

    def _is_image_request(self) -> bool:
        if self.image_request or self.endpoint.startswith("/v1/images"):
            return True
        model = str(self.model or "").strip().lower()
        if self.endpoint in {"/v1/chat/completions", "/v1/responses"}:
            return "image" in model
        return False

    def _trace_image_perf(self) -> bool:
        return self._is_image_request()

    def attach_trace_metadata(self, body: dict[str, Any]) -> None:
        if not isinstance(body, dict):
            return
        if not self._trace_image_perf():
            return
        body["_call_id"] = self.call_id
        body["_trace_image_perf"] = True
        self.trace_metadata.update(_image_trace_metadata(body))

    def stream(self, items):
        urls: list[str] = []
        account_emails: list[str] = []
        conversation_ids: list[str] = []
        image_attempts: list[dict[str, object]] = []
        failed = False
        image_request = self._is_image_request()
        try:
            for item in items:
                urls.extend(_collect_urls(item))
                account_emails.extend(_collect_account_emails(item))
                conversation_ids.extend(_collect_conversation_ids(item))
                image_attempts = collect_image_attempts([image_attempts, item])
                yield _strip_internal_response_fields(item)
        except Exception as exc:
            failed = True
            extra = _exception_log_fields(exc, image=image_request)
            combined_attempts = collect_image_attempts([image_attempts, exc])
            if combined_attempts:
                extra["image_attempts"] = combined_attempts
            self.log(
                "流式调用失败",
                status="failed",
                error=(
                    _public_image_exception_message(exc)
                    if image_request else str(exc)
                ),
                urls=urls,
                account_email=(account_emails[0] if account_emails else getattr(exc, "account_email", "")),
                conversation_id=(conversation_ids[0] if conversation_ids else getattr(exc, "conversation_id", "")),
                extra=extra,
            )
            if image_request and not hasattr(exc, "to_openai_error"):
                from services.image_failure import ImageGenerationError, classify_image_exception

                raw_error = str(exc) or "image generation failed"
                raise ImageGenerationError(
                    raw_error,
                    failure=classify_image_exception(exc),
                    raw_error=raw_error,
                ) from exc
            raise
        finally:
            if not failed:
                extra = {"image_attempts": image_attempts} if image_attempts else None
                self.log("流式调用结束", urls=urls, account_email=account_emails[0] if account_emails else "",
                         conversation_id=conversation_ids[0] if conversation_ids else "", extra=extra)

    def log(self, suffix: str, result: object = None, status: str = "success", error: str = "",
            urls: list[str] | None = None, account_email: str = "", conversation_id: str = "",
            extra: dict[str, object] | None = None) -> None:
        failure_code = (extra or {}).get("error_code") or (extra or {}).get("failure_code")
        if is_text_review_failure_code(failure_code):
            status = "text_review"
            suffix = "文本"
        detail = {
            "key_id": self.identity.get("id"),
            "key_name": self.identity.get("name"),
            "role": self.identity.get("role"),
            "endpoint": self.endpoint,
            "model": self.model,
            "call_id": self.call_id,
            "started_at": beijing_from_timestamp(self.started),
            "ended_at": beijing_now_str(),
            "duration_ms": int((time.time() - self.started) * 1000),
            "status": status,
            "image_request": self._is_image_request(),
        }
        if self.perf_timings:
            detail["perf"] = dict(self.perf_timings)
        request_excerpt = _request_excerpt(self.request_text)
        if request_excerpt:
            detail["request_text"] = request_excerpt
            request_full, request_full_truncated = _request_full_text(self.request_text)
            if request_full and request_full != request_excerpt:
                detail["request_text_full"] = request_full
                detail["request_text_truncated"] = request_full_truncated
        if self.request_shape:
            detail["request_shape"] = self.request_shape
        if self.trace_metadata:
            detail["request_meta"] = dict(self.trace_metadata)
        if error:
            detail["error"] = error
        if extra:
            for key, value in extra.items():
                if value in (None, ""):
                    continue
                detail[key] = value
        attempts = collect_image_attempts([result, extra])
        if attempts:
            detail["image_attempts"] = attempts
        email = str(account_email or "").strip()
        if not email:
            emails = _collect_account_emails(result)
            email = emails[0] if emails else ""
        if email:
            detail["account_email"] = email
        conv_id = str(conversation_id or "").strip()
        if not conv_id:
            conv_ids = _collect_conversation_ids(result)
            conv_id = conv_ids[0] if conv_ids else ""
        if conv_id:
            detail["conversation_id"] = conv_id
        collected_urls = [*(urls or []), *_collect_urls(result)]
        if collected_urls and not self.endpoint.startswith("/v1/search"):
            detail["urls"] = list(dict.fromkeys(collected_urls))
        if self._trace_image_perf():
            image_metrics = _image_result_metrics(result)
            if image_metrics:
                detail.update(image_metrics)
        if self._trace_image_perf():
            realtime_monitor_service.finish(detail)
        log_service.add(LOG_TYPE_CALL, f"{self.summary}{suffix}", detail)
