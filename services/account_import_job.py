"""Canonical job and error projection for remote account import adapters."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
import threading
import time
import uuid
from typing import Protocol

from services.account_operation_events import (
    append_account_operation_event,
    append_account_operation_events,
    normalize_account_operation_events,
    project_account_operation_presentation,
)
from services.account_service import account_service
from utils.diagnostics import sanitize_diagnostic_text


_IMPORT_JOB_STAGES = {
    "read_credentials",
    "save_accounts",
    "sync_accounts",
    "completed",
}

_IMPORT_JOB_STAGE_LABELS = {
    "read_credentials": "读取凭据",
    "save_accounts": "保存账号",
    "sync_accounts": "同步账号与额度",
    "completed": "完成",
}

_CHECKPOINT_INTERVAL_SECONDS = 0.25
_CHECKPOINT_ITEM_COUNT = 20
_ERROR_DETAILS_LIMIT = 20


class ImportJobFailureAccumulator:
    """Track the full failure count while retaining only recent details."""

    def __init__(
        self,
        raw: object = None,
        *,
        details_limit: int = _ERROR_DETAILS_LIMIT,
    ) -> None:
        job = raw if isinstance(raw, dict) else {}
        raw_errors = job.get("errors")
        errors = raw_errors if isinstance(raw_errors, list) else []
        self._details_limit = max(1, int(details_limit))
        self._details = [
            dict(error) for error in errors[-self._details_limit:]
            if isinstance(error, dict)
        ]
        self._total = max(
            self._as_count(job.get("failed_total")),
            self._as_count(job.get("failed")),
            len(errors),
        )

    @staticmethod
    def _as_count(value: object) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @property
    def total(self) -> int:
        return self._total

    @property
    def details(self) -> list[dict]:
        return [dict(error) for error in self._details]

    def append(self, error: dict) -> None:
        self._total += 1
        self._details.append(dict(error))
        if len(self._details) > self._details_limit:
            del self._details[:-self._details_limit]

    def extend(self, errors: Iterable[dict]) -> None:
        for error in errors:
            self.append(error)


class ImportJobCheckpointGate:
    """Limit progress persistence while keeping short imports responsive."""

    def __init__(
        self,
        *,
        interval_seconds: float = _CHECKPOINT_INTERVAL_SECONDS,
        item_count: int = _CHECKPOINT_ITEM_COUNT,
    ) -> None:
        self._interval_seconds = max(0.01, float(interval_seconds))
        self._item_count = max(1, int(item_count))
        self._pending = 0
        self._last_checkpoint = time.monotonic()

    def mark(self) -> bool:
        self._pending += 1
        now = time.monotonic()
        if (
            self._pending < self._item_count
            and now - self._last_checkpoint < self._interval_seconds
        ):
            return False
        self._pending = 0
        self._last_checkpoint = now
        return True


def import_job_is_active(raw: object) -> bool:
    return isinstance(raw, dict) and _clean(raw.get("status")).lower() in {
        "pending",
        "running",
    }


def resolve_import_item_statuses(raw_result: object, total: int) -> list[str]:
    bounded_total = max(0, int(total or 0))
    result = raw_result if isinstance(raw_result, dict) else {}
    raw_statuses = result.get("item_results")
    if isinstance(raw_statuses, list) and len(raw_statuses) == bounded_total:
        statuses = [str(status or "").strip().lower() for status in raw_statuses]
        if all(status in {"added", "skipped", "invalid"} for status in statuses):
            return statuses

    added = max(0, min(bounded_total, int(result.get("added") or 0)))
    return ["added"] * added + ["skipped"] * (bounded_total - added)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_import_error(
    raw: object,
    *,
    default_stage: str = "fetch",
    default_name: str = "remote account",
    sensitive_values: Iterable[object] = (),
    proxy_values: Iterable[object] = (),
) -> dict[str, str]:
    sensitive_values = tuple(sensitive_values)
    proxy_values = tuple(proxy_values)
    item = raw if isinstance(raw, dict) else {}
    fallback_stage = _clean(default_stage).lower()
    if fallback_stage not in {"fetch", "sync"}:
        fallback_stage = "fetch"
    stage = _clean(item.get("stage") or fallback_stage).lower()
    if stage not in {"fetch", "sync"}:
        stage = fallback_stage
    name = sanitize_diagnostic_text(
        _clean(
            item.get("name")
            or item.get("id")
            or item.get("email")
            or item.get("token")
            or default_name
        ),
        sensitive_values=sensitive_values,
        proxy_values=proxy_values,
        limit=500,
    ) or sanitize_diagnostic_text(
        default_name,
        sensitive_values=sensitive_values,
        proxy_values=proxy_values,
        limit=500,
    ) or "remote account"
    error = sanitize_diagnostic_text(
        _clean(item.get("error") or item.get("message") or raw or "unknown error"),
        sensitive_values=sensitive_values,
        proxy_values=proxy_values,
        limit=2000,
    )
    return {"stage": stage, "name": name, "error": error or "unknown error"}


def import_error_event_identity(
    raw: object,
    normalized: object,
) -> tuple[str, str]:
    """Project a sync error onto the stable account identity used by task events."""
    item = raw if isinstance(raw, dict) else {}
    error = normalized if isinstance(normalized, dict) else {}
    account_id = _clean(
        item.get("account_id")
        or item.get("id")
        or error.get("name")
        or "account sync"
    )
    account_label = _clean(
        item.get("account_label")
        or item.get("email")
        or account_id
    )
    return account_id, account_label


def next_import_job_failed_total(current: object, updates: object) -> int:
    """Keep a bounded error detail list from lowering the real failure count."""

    current_job = current if isinstance(current, dict) else {}
    next_values = updates if isinstance(updates, dict) else {}

    def as_count(value: object) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    current_errors = current_job.get("errors")
    if not isinstance(current_errors, list):
        current_errors = []
    next_errors = next_values.get("errors")
    if not isinstance(next_errors, list):
        next_errors = []

    current_total = max(
        as_count(current_job.get("failed_total")),
        as_count(current_job.get("failed")),
        len(current_errors),
    )
    reported_total = max(
        as_count(next_values.get("failed_total")),
        as_count(next_values.get("failed")),
        len(next_errors),
    )
    if reported_total >= current_total:
        return reported_total

    # A restarted worker resumes from the persisted tail of diagnostics. Its
    # next checkpoint appends to that tail, while `failed=len(errors)` is no
    # longer the lifetime count after compaction.
    if current_errors and next_errors[:len(current_errors)] == current_errors:
        return current_total + len(next_errors) - len(current_errors)
    return current_total


class RemoteImportJobStore(Protocol):
    """Persistence Interface shared by CPA and Sub2API import adapters."""

    def start_import_job(self, source_id: str, import_job: dict) -> dict | None: ...

    def get_import_job(self, source_id: str) -> dict | None: ...

    def set_import_job(
        self,
        source_id: str,
        import_job: dict | None,
        *,
        expected_job_id: str | None = None,
    ) -> dict | None: ...


ImportErrorContextProvider = Callable[..., dict[str, tuple[str, ...]]]
RemoteImportAccount = tuple[str, dict]


def _import_account_label(account_id: object, payload: object = None) -> str:
    if isinstance(payload, dict):
        email = _clean(payload.get("email"))
        if email:
            return email
    return _clean(account_id)


class RemoteAccountImportJob:
    """Own the common lifecycle after a remote import adapter selects accounts.

    CPA and Sub2API remain responsible for their remote protocols. This Module
    owns job reservation, stale-worker protection, progress checkpoints, local
    Account Pool persistence, account/quota synchronization, events, and the
    terminal projection shared by both adapters.
    """

    def __init__(
        self,
        store: RemoteImportJobStore,
        *,
        source_id: str,
        total: int,
        worker_label: str,
        error_context: ImportErrorContextProvider,
        job_id: str = "",
    ) -> None:
        self._store = store
        self._source_id = _clean(source_id)
        self._total = max(0, int(total or 0))
        self._worker_label = _clean(worker_label) or "remote import worker"
        self._error_context = error_context
        self._job_id = _clean(job_id)
        self._completed = 0
        self._failures = ImportJobFailureAccumulator()
        self._events: list[dict] = []
        self._checkpoint = ImportJobCheckpointGate()

    @property
    def job_id(self) -> str:
        return self._job_id

    def _context(self, *sources: object) -> dict[str, tuple[str, ...]]:
        context = self._error_context(*sources)
        if not isinstance(context, dict):
            return {"sensitive_values": (), "proxy_values": ()}
        return {
            "sensitive_values": tuple(context.get("sensitive_values") or ()),
            "proxy_values": tuple(context.get("proxy_values") or ()),
        }

    @staticmethod
    def _saved_job(saved: object) -> dict | None:
        if not isinstance(saved, dict):
            return None
        job = saved.get("import_job")
        return dict(job) if isinstance(job, dict) else None

    def reserve(self) -> dict | None:
        now = _now_iso()
        self._job_id = self._job_id or uuid.uuid4().hex
        job = {
            "job_id": self._job_id,
            "status": "pending",
            "stage": "read_credentials",
            "stage_total": self._total,
            "stage_completed": 0,
            "created_at": now,
            "updated_at": now,
            "total": self._total,
            "completed": 0,
            "added": 0,
            "skipped": 0,
            "synced": 0,
            "failed": 0,
            "errors": [],
        }
        return self._saved_job(self._store.start_import_job(self._source_id, job))

    def update(
        self,
        *,
        expected_job_id: str | None = None,
        **updates: object,
    ) -> dict | None:
        current = self._store.get_import_job(self._source_id)
        if current is None:
            return None
        next_job = {**current, **updates, "updated_at": _now_iso()}
        if "errors" in updates or "failed" in updates or "failed_total" in updates:
            failed_total = next_import_job_failed_total(current, updates)
            next_job["failed"] = failed_total
            next_job["failed_total"] = failed_total
        saved = self._store.set_import_job(
            self._source_id,
            next_job,
            expected_job_id=expected_job_id,
        )
        return self._saved_job(saved)

    def _current_owned_job(self) -> dict | None:
        current = self._store.get_import_job(self._source_id)
        if not isinstance(current, dict):
            return None
        current_job_id = _clean(current.get("job_id"))
        if not self._job_id:
            self._job_id = current_job_id
        if not self._job_id or current_job_id != self._job_id:
            return None
        return current

    def begin(self) -> bool:
        current = self._current_owned_job()
        if current is None:
            return False
        started = self.update(
            expected_job_id=self._job_id,
            status="running",
            stage="read_credentials",
            stage_total=self._total,
            stage_completed=0,
        )
        if started is None:
            return False
        self._completed = int(started.get("completed") or 0)
        self._failures = ImportJobFailureAccumulator(started)
        self._events = list(started.get("events") or [])
        self._checkpoint = ImportJobCheckpointGate()
        return True

    def record_fetch(self, account_id: str, *, error: str = "") -> bool:
        self._completed += 1
        if error:
            normalized_error = normalize_import_error(
                {"stage": "fetch", "name": account_id, "error": error},
                default_stage="fetch",
                default_name=account_id,
                **self._context(),
            )
            self._failures.append(normalized_error)
            self._events = append_account_operation_event(
                self._events,
                account_id=account_id,
                account_label=account_id,
                action="import_account",
                status="failed",
                message=normalized_error["error"],
                existing_events_normalized=True,
                **self._context(),
            )
        if not self._checkpoint.mark():
            return True
        return self.update(
            expected_job_id=self._job_id,
            completed=self._completed,
            stage_completed=self._completed,
            failed_total=self._failures.total,
            errors=self._failures.details,
            events=self._events,
        ) is not None

    def fail(self, *, name: str, error: str) -> bool:
        current = self._current_owned_job()
        if current is None:
            return False
        normalized_error = normalize_import_error(
            {"stage": "fetch", "name": name, "error": error},
            default_stage="fetch",
            default_name=name,
            **self._context(),
        )
        failures = ImportJobFailureAccumulator(current)
        failures.append(normalized_error)
        events = append_account_operation_event(
            current.get("events"),
            account_id=name,
            account_label=name,
            action="import_account",
            status="failed",
            message=normalized_error["error"],
            **self._context(),
        )
        return self.update(
            expected_job_id=self._job_id,
            status="failed",
            stage="completed",
            stage_total=self._total,
            stage_completed=int(current.get("stage_completed") or 0),
            failed_total=failures.total,
            errors=failures.details,
            events=events,
        ) is not None

    def start_worker(
        self,
        *,
        target: Callable[..., object],
        args: tuple[object, ...],
        name: str,
    ) -> None:
        thread = threading.Thread(
            target=target,
            args=args,
            name=name,
            daemon=True,
        )
        try:
            thread.start()
        except Exception as exc:
            self.fail(
                name=self._worker_label,
                error=str(exc) or "import worker could not start",
            )
            raise

    def run_guarded(
        self,
        target: Callable[..., object],
        *args: object,
        **kwargs: object,
    ) -> None:
        try:
            target(*args, **kwargs)
        except Exception:
            self.fail(
                name=self._worker_label,
                error="remote import worker failed",
            )

    def finish(self, fetched_accounts: list[RemoteImportAccount]) -> bool:
        if not fetched_accounts:
            events = append_account_operation_event(
                self._events,
                action="import_account",
                status="failed",
                message="没有可用的账号凭据",
                existing_events_normalized=True,
                **self._context(),
            )
            return self.update(
                expected_job_id=self._job_id,
                status="failed",
                completed=self._completed,
                failed_total=self._failures.total,
                errors=self._failures.details,
                events=events,
            ) is not None

        payloads = [payload for _account_id, payload in fetched_accounts]
        if self.update(
            expected_job_id=self._job_id,
            stage="save_accounts",
            stage_total=1,
            stage_completed=0,
            completed=self._completed,
            failed_total=self._failures.total,
            errors=self._failures.details,
            events=self._events,
        ) is None:
            return False

        try:
            add_result = account_service.add_account_items(
                payloads,
                return_items=False,
                return_item_results=True,
            )
        except Exception as exc:
            storage_error = normalize_import_error(
                {
                    "stage": "sync",
                    "name": "local account storage",
                    "error": str(exc) or "account storage failed",
                },
                default_stage="sync",
                default_name="local account storage",
                **self._context(payloads),
            )["error"]
            self._failures.extend(
                normalize_import_error(
                    {
                        "stage": "sync",
                        "name": account_id,
                        "error": storage_error,
                    },
                    default_stage="sync",
                    default_name=account_id,
                    **self._context(),
                )
                for account_id, _payload in fetched_accounts
            )
            events = append_account_operation_events(
                self._events,
                [
                    {
                        "account_id": account_id,
                        "account_label": _import_account_label(account_id, payload),
                        "action": "import_account",
                        "status": "failed",
                        "message": f"账号保存失败：{storage_error}",
                    }
                    for account_id, payload in fetched_accounts
                ],
                existing_events_normalized=True,
                **self._context(),
            )
            return self.update(
                expected_job_id=self._job_id,
                status="failed",
                completed=self._total,
                failed_total=self._failures.total,
                errors=self._failures.details,
                events=events,
            ) is not None

        item_statuses = resolve_import_item_statuses(
            add_result,
            len(fetched_accounts),
        )
        invalid_errors = [
            normalize_import_error(
                {
                    "stage": "sync",
                    "name": account_id,
                    "error": "账号数据无效，未导入",
                },
                default_stage="sync",
                default_name=account_id,
                **self._context(),
            )
            for (account_id, _payload), status in zip(
                fetched_accounts,
                item_statuses,
            )
            if status == "invalid"
        ]
        self._failures.extend(invalid_errors)
        self._events = append_account_operation_events(
            self._events,
            [
                {
                    "account_id": account_id,
                    "account_label": _import_account_label(account_id, payload),
                    "action": "import_account",
                    "status": (
                        "success"
                        if status == "added"
                        else "failed"
                        if status == "invalid"
                        else "skipped"
                    ),
                    "message": (
                        "账号导入成功"
                        if status == "added"
                        else "账号数据无效，未导入"
                        if status == "invalid"
                        else "账号已存在，凭据已更新"
                    ),
                }
                for (account_id, payload), status in zip(
                    fetched_accounts,
                    item_statuses,
                )
            ],
            existing_events_normalized=True,
            **self._context(),
        )
        if self.update(
            expected_job_id=self._job_id,
            stage_completed=1,
            failed_total=self._failures.total,
            errors=self._failures.details,
            events=self._events,
        ) is None:
            return False

        sync_payloads = [
            payload
            for (_account_id, payload), status in zip(
                fetched_accounts,
                item_statuses,
            )
            if status != "invalid"
        ]
        tokens = [_clean(payload.get("access_token")) for payload in sync_payloads]
        if self.update(
            expected_job_id=self._job_id,
            stage="sync_accounts",
            stage_total=len(tokens),
            stage_completed=0,
        ) is None:
            return False

        try:
            sync_result = (
                account_service.sync_accounts_and_quota(tokens)
                if tokens
                else {"synced": 0, "errors": []}
            )
            raw_sync_errors = list(sync_result.get("errors") or [])
            sync_errors = [
                normalize_import_error(
                    item,
                    default_stage="sync",
                    default_name="account sync",
                    **self._context(sync_payloads),
                )
                for item in raw_sync_errors
            ]
        except Exception as exc:
            sync_result = {"synced": 0}
            raw_sync_errors = [{
                "stage": "sync",
                "name": "account sync",
                "error": str(exc) or "sync failed",
            }]
            sync_errors = [
                normalize_import_error(
                    raw_sync_errors[0],
                    default_stage="sync",
                    default_name="account sync",
                    **self._context(sync_payloads),
                )
            ]

        self._failures.extend(sync_errors)
        sync_event_identities = [
            import_error_event_identity(raw_error, sync_error)
            for raw_error, sync_error in zip(raw_sync_errors, sync_errors)
        ]
        self._events = append_account_operation_events(
            self._events,
            [
                {
                    "account_id": identity[0],
                    "account_label": identity[1],
                    "action": "import_account",
                    "status": "failed",
                    "message": sync_error.get("error"),
                }
                for sync_error, identity in zip(
                    sync_errors,
                    sync_event_identities,
                )
            ],
            existing_events_normalized=True,
            **self._context(),
        )
        return self.update(
            expected_job_id=self._job_id,
            status="completed",
            stage="completed",
            stage_total=self._total,
            stage_completed=self._total,
            completed=self._total,
            added=int(add_result.get("added") or 0),
            skipped=int(add_result.get("skipped") or 0),
            synced=int(sync_result.get("synced") or 0),
            failed_total=self._failures.total,
            errors=self._failures.details,
            events=self._events,
        ) is not None


def normalize_import_job(
    raw: object,
    *,
    fail_unfinished: bool,
    sensitive_values: Iterable[object] = (),
    proxy_values: Iterable[object] = (),
) -> dict | None:
    if not isinstance(raw, dict):
        return None
    sensitive_values = tuple(sensitive_values)
    proxy_values = tuple(proxy_values)
    status = _clean(raw.get("status")) or "failed"
    if fail_unfinished and status in {"pending", "running"}:
        status = "failed"
    stage = _clean(raw.get("stage")).lower()
    if stage not in _IMPORT_JOB_STAGES:
        stage = "completed" if status in {"completed", "failed"} else "read_credentials"
    if status in {"completed", "failed"}:
        stage = "completed"
    raw_errors = raw.get("errors") if isinstance(raw.get("errors"), list) else []
    normalized_errors = [
        normalize_import_error(
            item,
            sensitive_values=sensitive_values,
            proxy_values=proxy_values,
        )
        for item in raw_errors
    ]
    # The total is needed for an accurate result, while keeping every remote
    # error would make a long-running job progressively larger to persist and
    # return. Keep the newest diagnostics, which are the most actionable.
    errors = normalized_errors[-_ERROR_DETAILS_LIMIT:]
    raw_failed_total = raw.get("failed_total")
    if raw_failed_total is None:
        raw_failed_total = raw.get("failed")
    try:
        failed_total = max(0, int(raw_failed_total or 0))
    except (TypeError, ValueError):
        failed_total = 0
    failed_total = max(failed_total, len(normalized_errors))
    events = normalize_account_operation_events(
        raw.get("events"),
        sensitive_values=sensitive_values,
        proxy_values=proxy_values,
    )
    created_at = _clean(raw.get("created_at")) or _now_iso()
    total = max(0, int(raw.get("total") or 0))
    completed = max(0, min(total, int(raw.get("completed") or 0)))
    stage_total = max(0, int(raw.get("stage_total") or total))
    stage_completed = max(
        0,
        min(
            stage_total,
            int(raw.get("stage_completed") or completed),
        ),
    )
    if status == "completed":
        stage_completed = stage_total
    terminal = status in {"completed", "failed"}
    progress_total = total if terminal else stage_total
    progress_completed = (
        total
        if status == "completed"
        else completed
        if terminal
        else stage_completed
    )
    stage_label = _IMPORT_JOB_STAGE_LABELS[stage]
    error = (
        _clean(errors[0].get("error")) if status == "failed" and errors else ""
    )
    if status == "failed" and not error:
        error = "导入失败"
    import_result = {
        "added": max(0, int(raw.get("added") or 0)),
        "skipped": max(0, int(raw.get("skipped") or 0)),
        "synced": max(
            0,
            int((raw.get("synced") if "synced" in raw else raw.get("refreshed")) or 0),
        ),
        "failed": failed_total,
    }
    presentation = project_account_operation_presentation({
        "total": progress_total,
        "processed": progress_completed,
        "done": terminal,
        "error": error or None,
        "stage_label": stage_label,
        "import_result": import_result,
        "events": events,
    })
    result_message = ""
    if terminal:
        if error:
            result_message = f"导入失败 · {error}" if error != "导入失败" else error
        else:
            result_message = str(presentation["message"]).replace("任务", "导入", 1)
    return {
        "job_id": _clean(raw.get("job_id")) or uuid.uuid4().hex,
        "status": status,
        "created_at": created_at,
        "updated_at": _clean(raw.get("updated_at")) or created_at,
        "stage": stage,
        "stage_label": stage_label,
        "stage_total": stage_total,
        "stage_completed": stage_completed,
        "terminal": terminal,
        "progress_total": progress_total,
        "progress_completed": progress_completed,
        "status_label": presentation["status_label"],
        "tone": presentation["tone"],
        "error": error,
        "summary_items": presentation["summary_items"],
        "result_message": result_message,
        "result_tone": presentation["tone"] if terminal else "info",
        "total": total,
        "completed": completed,
        "added": import_result["added"],
        "skipped": import_result["skipped"],
        "synced": import_result["synced"],
        # `failed` stays as the backwards-compatible count. New consumers can
        # use the explicit name and still show the full count after errors are
        # compacted for storage.
        "failed": failed_total,
        "failed_total": failed_total,
        "errors": errors,
        "events": events,
    }
