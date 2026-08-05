from __future__ import annotations

import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

from services.account_service import (
    RefreshCredentialsChangedError,
    TerminalRefreshTokenError,
    account_service,
)
from services.config import DATA_DIR
from services.content_filter import request_text
from services.log_service import LOG_TYPE_CALL, log_service
from services.openai_backend_api import EDITABLE_FILE_MODEL, OpenAIBackendAPI
from services.storage.editable_file_task_repository import EditableFileTaskRepository
from utils.file_names import is_safe_public_filename
from utils.helper import new_uuid
from utils.timezone import beijing_from_timestamp, beijing_now_str

TASK_STATUS_QUEUED = "queued"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_SUCCESS = "success"
TASK_STATUS_ERROR = "error"
UNFINISHED_STATUSES = {TASK_STATUS_QUEUED, TASK_STATUS_RUNNING}
TERMINAL_STATUSES = {TASK_STATUS_SUCCESS, TASK_STATUS_ERROR}
TASK_STATUS_PRESENTATION = {
    TASK_STATUS_QUEUED: {
        "label": "等待中",
        "tone": "muted",
        "icon": "lucide:loader-circle",
    },
    TASK_STATUS_RUNNING: {
        "label": "生成中",
        "tone": "warning",
        "icon": "lucide:loader-circle",
    },
    TASK_STATUS_SUCCESS: {
        "label": "已完成",
        "tone": "success",
        "icon": "lucide:file-check-2",
    },
    TASK_STATUS_ERROR: {
        "label": "失败",
        "tone": "danger",
        "icon": "lucide:circle-alert",
    },
}
EDITABLE_FILE_PLAN_TYPES = ("Plus", "Team", "Pro", "Enterprise")
EDITABLE_FILE_ROOT = DATA_DIR / "files"
EDITABLE_FILE_TASK_ID_MAX_LENGTH = 160
EDITABLE_FILE_TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
EDITABLE_FILE_STORAGE_PREFIX = "asset-"
EDITABLE_FILE_EXTENSIONS = {
    "ppt": {".ppt", ".pptx", ".zip"},
    "psd": {".psd", ".zip"},
}


def _now_iso() -> str:
    return beijing_now_str()


def _clean(value: object, default: str = "") -> str:
    return str(value or default).strip()


def _owner_id(identity: dict[str, object]) -> str:
    return _clean(identity.get("id")) or "anonymous"


def _task_key(owner_id: str, task_id: str) -> str:
    return f"{owner_id}:{task_id}"


def _resolve_task_id(client_task_id: str) -> str:
    task_id = _clean(client_task_id)
    if not task_id:
        return new_uuid()
    if (
        len(task_id) > EDITABLE_FILE_TASK_ID_MAX_LENGTH
        or task_id in {".", ".."}
        or EDITABLE_FILE_TASK_ID_PATTERN.fullmatch(task_id) is None
    ):
        raise EditableFileTaskInvalidIdError(
            "client_task_id must be 1-160 characters using letters, numbers, '.', '_' or '-'"
        )
    return task_id


def _is_storage_id(value: object) -> bool:
    storage_id = _clean(value)
    if not storage_id.startswith(EDITABLE_FILE_STORAGE_PREFIX):
        return False
    try:
        uuid_value = storage_id.removeprefix(EDITABLE_FILE_STORAGE_PREFIX)
        return str(UUID(uuid_value)) == uuid_value
    except (ValueError, AttributeError):
        return False


def _storage_id(task: dict[str, Any]) -> str:
    storage_id = _clean(task.get("storage_id"))
    if not _is_storage_id(storage_id):
        raise ValueError("editable file task storage id is invalid")
    return storage_id


def _elapsed_seconds(task: dict[str, Any]) -> int:
    start = float(task.get("started_ts") or task.get("created_ts") or 0)
    end = float(task.get("ended_ts") or time.time())
    return max(0, int(end - start)) if start else 0


def _file_url(path: Path, base_url: str) -> str:
    rel = path.resolve().relative_to(EDITABLE_FILE_ROOT.resolve()).as_posix()
    prefix = str(base_url or "").strip().rstrip("/")
    return f"{prefix}/files/{quote(rel, safe='/')}" if prefix else f"/files/{quote(rel, safe='/')}"


def _editable_access_token() -> str:
    attempted_tokens: set[str] = set()
    while True:
        accounts = [
            item for item in account_service.list_accounts()
            if (token := _clean(item.get("access_token")))
               and token not in attempted_tokens
               and account_service._is_account_selectable(item, allow_limited=True)
               and account_service._account_matches_any_plan_type(item, EDITABLE_FILE_PLAN_TYPES)
        ]
        if not accounts:
            raise RuntimeError("no available plus/team/pro account")
        accounts.sort(key=lambda item: _clean(item.get("last_used_at")))
        token = _clean(accounts[0].get("access_token"))
        attempted_tokens.add(token)
        try:
            return account_service.ensure_access_token(token, event="editable_file_task")
        except (TerminalRefreshTokenError, RefreshCredentialsChangedError):
            continue


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    raw_status = _clean(task.get("status"), TASK_STATUS_ERROR)
    status = raw_status if raw_status in TASK_STATUS_PRESENTATION else TASK_STATUS_ERROR
    presentation = TASK_STATUS_PRESENTATION[status]
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    delete_pending = bool(task.get("delete_pending"))
    can_download = not delete_pending and status == TASK_STATUS_SUCCESS and bool(
        _clean(result.get("primary_url")) or _clean(result.get("zip_url"))
    )
    item = {
        "id": task.get("id"),
        "status": status,
        "status_label": presentation["label"],
        "status_tone": presentation["tone"],
        "status_icon": presentation["icon"],
        "is_active": status in UNFINISHED_STATUSES,
        "kind": task.get("kind"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "elapsed_seconds": _elapsed_seconds(task),
        "can_download": can_download,
        "can_delete": status in TERMINAL_STATUSES,
    }
    for key in ("result", "error"):
        if task.get(key):
            item[key] = task[key]
    return item


class EditableFileTaskNotFoundError(LookupError):
    pass


class EditableFileTaskNotTerminalError(RuntimeError):
    pass


class EditableFileTaskInvalidIdError(ValueError):
    pass


class EditableFileTaskCleanupError(RuntimeError):
    pass


class EditableFileTaskService:
    def __init__(
        self,
        *,
        repository: EditableFileTaskRepository | None = None,
        database_url: str | None = None,
    ) -> None:
        if repository is not None and database_url is not None:
            raise ValueError("provide repository or database_url, not both")
        self._lock = threading.RLock()
        self._repository = repository or EditableFileTaskRepository(database_url)
        with self._lock:
            self._recover_pending_deletions_locked()
            self._recover_unfinished_locked()

    def submit_ppt(self, identity: dict[str, object], *, client_task_id: str = "", prompt: str = "", base64_images: list[str] | None = None, base_url: str = "") -> dict[str, Any]:
        return self._submit(identity, client_task_id=client_task_id, kind="ppt", prompt=prompt, base64_images=base64_images or [], base_url=base_url)

    def submit_psd(self, identity: dict[str, object], *, client_task_id: str = "", prompt: str = "", base64_images: list[str] | None = None, base_url: str = "") -> dict[str, Any]:
        return self._submit(identity, client_task_id=client_task_id, kind="psd", prompt=prompt, base64_images=base64_images or [], base_url=base_url)

    def list_tasks(
            self,
            identity: dict[str, object],
            task_ids: list[str],
            *,
            limit: int = 0,
    ) -> dict[str, Any]:
        owner = _owner_id(identity)
        requested = [_clean(item) for item in task_ids if _clean(item)]
        with self._lock:
            if requested:
                stored = self._repository.list_for_owner(owner, task_ids=requested)
                by_id = {_clean(task.get("id")): task for task in stored}
                items = [by_id[task_id] for task_id in requested if task_id in by_id]
                return {
                    "items": [_public_task(item) for item in items],
                    "missing_ids": [task_id for task_id in requested if task_id not in by_id],
                }
            items = self._repository.list_for_owner(owner, limit=limit)
        return {"items": [_public_task(item) for item in items], "missing_ids": []}

    def delete_task(
            self,
            identity: dict[str, object],
            task_id: str,
    ) -> dict[str, Any]:
        owner = _owner_id(identity)
        normalized_task_id = _clean(task_id)
        with self._lock:
            task = self._repository.get(owner, normalized_task_id)
            if task is None:
                raise EditableFileTaskNotFoundError("editable file task not found")
            if task.get("status") not in TERMINAL_STATUSES:
                raise EditableFileTaskNotTerminalError(
                    "editable file task is not terminal"
                )

            if not task.get("delete_pending"):
                task = self._repository.update(
                    owner,
                    normalized_task_id,
                    delete_pending=True,
                ) or task

            self._remove_task_files(task)
            self._repository.delete(owner, normalized_task_id)
        return {"task_id": normalized_task_id, "deleted": True}

    def _submit(self, identity: dict[str, object], *, client_task_id: str, kind: str, prompt: str, base64_images: list[str], base_url: str) -> dict[str, Any]:
        task_id = _resolve_task_id(client_task_id)
        owner = _owner_id(identity)
        key = _task_key(owner, task_id)
        now = _now_iso()
        with self._lock:
            ts = time.time()
            task, created = self._repository.create({
                "id": task_id,
                "storage_id": f"{EDITABLE_FILE_STORAGE_PREFIX}{new_uuid()}",
                "owner_id": owner,
                "status": TASK_STATUS_QUEUED,
                "kind": kind,
                "model": EDITABLE_FILE_MODEL,
                "created_at": now,
                "updated_at": now,
                "created_ts": ts,
                "updated_ts": ts,
            })
            if not created:
                return _public_task(task)
        threading.Thread(target=self._run_task, args=(key, kind, prompt, base64_images, dict(identity), base_url), name=f"{kind}-file-task-{task_id[:16]}", daemon=True).start()
        return _public_task(task)

    def _run_task(self, key: str, kind: str, prompt: str, base64_images: list[str], identity: dict[str, object], base_url: str) -> None:
        started = time.time()
        token = ""
        account_email = ""
        staging_dir: Path | None = None
        published_dir: Path | None = None
        success_recorded = False
        self._update_task(key, status=TASK_STATUS_RUNNING, error="", started_ts=started)
        try:
            if kind == "psd" and not base64_images:
                raise ValueError("base64_images is empty")
            token = _editable_access_token()
            account = account_service.get_account(token) or {}
            account_email = _clean(account.get("email"))
            with self._lock:
                owner_id, task_id = key.rsplit(":", 1)
                stored_task = self._repository.get(owner_id, task_id) or {}
            if not stored_task:
                return
            staging_dir = self._staging_dir(stored_task)
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            with OpenAIBackendAPI(token) as backend:
                result = backend.export_psd_zip(base64_images, prompt, staging_dir) if kind == "psd" else backend.export_ppt_zip(base64_images, prompt, staging_dir)
            account_service.mark_text_used(token)
            primary_path, zip_path = self._publish_files(
                stored_task,
                result.primary_path,
                result.zip_path,
            )
            published_dir = primary_path.parent
            data = {"conversation_id": result.conversation_id, "primary_url": _file_url(primary_path, base_url), "zip_url": _file_url(zip_path, base_url)}
            self._update_task(key, status=TASK_STATUS_SUCCESS, result=data, account_email=account_email, error="", ended_ts=time.time())
            success_recorded = True
            self._log_call(identity, kind, started, request_text(prompt), account_email=account_email, result=data)
        except Exception as exc:
            cleanup_paths = [staging_dir]
            if not success_recorded:
                cleanup_paths.append(published_dir)
            cleanup_succeeded = self._remove_directories(cleanup_paths)
            error = str(exc) or "editable file task failed"
            if not cleanup_succeeded:
                error = f"{error}; generated files could not be removed"
            self._update_task(key, status=TASK_STATUS_ERROR, error=error, account_email=account_email, ended_ts=time.time())
            self._log_call(identity, kind, started, request_text(prompt), status="failed", error=error, account_email=account_email)

    def public_file_path(self, relative_path: str) -> Path:
        value = str(relative_path or "")
        if "\\" in value or any(ord(character) < 32 for character in value):
            raise FileNotFoundError(value)
        raw = value.lstrip("/")
        root = EDITABLE_FILE_ROOT.resolve()
        requested = Path(raw)
        parts = requested.parts
        if len(parts) != 3:
            raise FileNotFoundError(raw)

        kind, storage_id, filename = parts
        allowed_extensions = EDITABLE_FILE_EXTENSIONS.get(kind)
        if (
            allowed_extensions is None
            or not _is_storage_id(storage_id)
            or not is_safe_public_filename(filename)
            or Path(filename).suffix.lower() not in allowed_extensions
        ):
            raise FileNotFoundError(raw)

        try:
            path = (root / requested).resolve()
            path.relative_to(root)
            if not path.is_file():
                raise FileNotFoundError(raw)
        except (OSError, RuntimeError, ValueError) as exc:
            raise FileNotFoundError(raw) from exc
        return path

    def _publish_files(
            self,
            task: dict[str, Any],
            primary_path: Path,
            zip_path: Path,
    ) -> tuple[Path, Path]:
        staging_dir = self._staging_dir(task)
        output_dir = self._output_dir(task)
        primary = Path(primary_path).resolve()
        archive = Path(zip_path).resolve()
        kind = _clean(task.get("kind"))
        allowed_extensions = EDITABLE_FILE_EXTENSIONS[kind]
        if (
            primary.parent != staging_dir
            or archive.parent != staging_dir
            or not primary.is_file()
            or not archive.is_file()
            or not is_safe_public_filename(primary.name)
            or not is_safe_public_filename(archive.name)
            or primary.suffix.lower() not in (allowed_extensions - {".zip"})
            or archive.suffix.lower() != ".zip"
        ):
            raise RuntimeError("editable file export produced invalid artifacts")
        if output_dir.exists():
            raise RuntimeError("editable file output directory already exists")

        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging_dir.replace(output_dir)
        return output_dir / primary.name, output_dir / archive.name

    @staticmethod
    def _output_dir(task: dict[str, Any]) -> Path:
        root = EDITABLE_FILE_ROOT.resolve()
        kind = _clean(task.get("kind"))
        if kind not in {"ppt", "psd"}:
            raise ValueError("editable file task kind is invalid")
        storage_id = _storage_id(task)
        kind_root = (root / kind).resolve()
        output_dir = (kind_root / storage_id).resolve()
        kind_root.relative_to(root)
        output_dir.relative_to(root)
        if output_dir.parent != kind_root:
            raise ValueError("editable file task output directory is invalid")
        return output_dir

    @staticmethod
    def _staging_dir(task: dict[str, Any]) -> Path:
        root = EDITABLE_FILE_ROOT.resolve()
        kind = _clean(task.get("kind"))
        if kind not in EDITABLE_FILE_EXTENSIONS:
            raise ValueError("editable file task kind is invalid")
        storage_id = _storage_id(task)
        staging_root = (root / ".staging" / kind).resolve()
        staging_dir = (staging_root / storage_id).resolve()
        staging_root.relative_to(root)
        staging_dir.relative_to(staging_root)
        if staging_dir.parent != staging_root:
            raise ValueError("editable file task staging directory is invalid")
        return staging_dir

    def _remove_task_files(
            self,
            task: dict[str, Any],
            *,
            strict: bool = True,
    ) -> bool:
        directories: list[Path] = []
        for resolver in (self._staging_dir, self._output_dir):
            try:
                directories.append(resolver(task))
            except ValueError:
                continue
        succeeded = self._remove_directories(directories)
        if not succeeded and strict:
            raise EditableFileTaskCleanupError(
                "editable file task files could not be removed"
            )
        return succeeded

    @staticmethod
    def _remove_directories(directories: list[Path | None]) -> bool:
        succeeded = True
        for directory in dict.fromkeys(path for path in directories if path is not None):
            try:
                if directory.exists():
                    shutil.rmtree(directory)
                if directory.exists():
                    succeeded = False
            except OSError:
                succeeded = False
        return succeeded

    def _update_task(self, key: str, **updates: Any) -> None:
        with self._lock:
            owner_id, task_id = key.rsplit(":", 1)
            updates["updated_at"] = _now_iso()
            updates["updated_ts"] = time.time()
            self._repository.update(owner_id, task_id, **updates)

    def _recover_unfinished_locked(self) -> None:
        for task in self._repository.list_by_status(UNFINISHED_STATUSES):
            self._remove_task_files(task, strict=False)
            now = time.time()
            self._repository.update(
                _clean(task.get("owner_id")),
                _clean(task.get("id")),
                status=TASK_STATUS_ERROR,
                error="服务已重启，未完成的任务已中断",
                ended_ts=now,
                updated_at=_now_iso(),
                updated_ts=now,
            )

    def _recover_pending_deletions_locked(self) -> None:
        for task in self._repository.list_delete_pending():
            if self._remove_task_files(task, strict=False):
                self._repository.delete(
                    _clean(task.get("owner_id")),
                    _clean(task.get("id")),
                )

    def _log_call(
            self,
            identity: dict[str, object],
            kind: str,
            started: float,
            request_preview: str,
            *,
            status: str = "success",
            error: str = "",
            account_email: str = "",
            result: dict[str, str] | None = None,
    ) -> None:
        detail = {
            "key_id": identity.get("id"),
            "key_name": identity.get("name"),
            "role": identity.get("role"),
            "endpoint": f"/v1/{kind}/generations",
            "model": EDITABLE_FILE_MODEL,
            "started_at": beijing_from_timestamp(started),
            "ended_at": _now_iso(),
            "duration_ms": int((time.time() - started) * 1000),
            "status": status,
        }
        if request_preview:
            detail["request_text"] = request_preview
        if account_email:
            detail["account_email"] = account_email
        if error:
            detail["error"] = error
        if result:
            detail["result"] = result
        try:
            log_service.add(LOG_TYPE_CALL, f"{kind.upper()}生成任务{'失败' if status == 'failed' else '完成'}", detail)
        except Exception:
            pass


editable_file_task_service = EditableFileTaskService()
