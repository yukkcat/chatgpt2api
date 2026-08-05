from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Condition, Lock, Thread
from typing import Any, Callable
from uuid import uuid4

from services.account_credentials import (
    ACCESS_TOKEN_REFRESH_SKEW_SECONDS,
    access_token_expires_in_seconds,
    access_token_issued_at,
    decode_access_token_payload,
    project_upstream_credential_availability,
)
from services.account_processing import (
    account_processing_batch,
    account_processing_slot,
    account_processing_worker_count,
)
from services.account_operation_events import (
    ACCOUNT_OPERATION_EVENT_LIMIT,
    normalize_account_operation_event,
)
from services.config import config
from services.image_failure import ImageFailure, classify_image_exception, image_failure
from services.log_service import (
    LOG_TYPE_ACCOUNT,
    log_service,
)
from services.storage.base import (
    StorageBackend,
    StorageMutation,
    StorageRevisionConflictError,
)
from utils.diagnostics import sanitize_diagnostic_text
from utils.helper import anonymize_token

_RemoteCheckMarker = tuple[str, str, str, str, bool | None, str, str]
_CredentialGeneration = tuple[str, str, str]



class ImageAccountSelectionError(RuntimeError):
    """图片账号调度失败。

    这是“本次请求为什么没拿到账号”的错误，不等同于账号持久状态。
    账号是否限流/异常仍由远程配额确认或鉴权结果决定。
    """

    # 控制流只认两个 pool outcomes；deadline_exceeded is request-scoped and
    # never changes a persisted Upstream Account state.
    #   quota_exhausted -> 远程确认额度耗尽，告诉客户端别重试（429）
    #   unavailable     -> 其它一切（没号/全忙/预检失败/上游波动），可重试（503）
    DEFAULTS: dict[str, tuple[int, str, str]] = {
        "quota_exhausted": (429, "insufficient_quota", "insufficient_quota"),
        "unavailable": (503, "server_error", "no_available_account"),
        "deadline_exceeded": (503, "server_error", "task_interrupted"),
    }

    def __init__(self, kind: str, message: str = "") -> None:
        defaults = self.DEFAULTS.get(kind, self.DEFAULTS["unavailable"])
        self.kind = kind if kind in self.DEFAULTS else "unavailable"
        self.status_code, self.error_type, self.code = defaults
        detail = message or self.kind.replace("_", " ")
        super().__init__(f"image_account_selection:{self.kind}; {detail}")


class OAuthRefreshError(RuntimeError):
    """Structured OAuth token refresh failure."""

    def __init__(self, status_code: int, error_code: str = "", description: str = "") -> None:
        self.status_code = int(status_code or 0)
        self.error_code = str(error_code or "").strip()
        self.description = str(description or "").strip()[:300]
        details = [f"oauth_refresh_http_{self.status_code}"]
        if self.error_code:
            details.append(self.error_code)
        if self.description and self.description.casefold() != self.error_code.casefold():
            details.append(self.description)
        super().__init__(": ".join(details))


class TerminalRefreshTokenError(OAuthRefreshError):
    """The refresh credential is revoked, expired, or otherwise unusable."""

    def __init__(self, status_code: int, error_code: str = "", description: str = "") -> None:
        super().__init__(status_code, error_code, description)
        self.failure = image_failure("auth_invalid", raw_detail=str(self))


class RefreshCredentialsChangedError(RuntimeError):
    """Refresh credentials changed while an OAuth request was in flight."""

    def __init__(self) -> None:
        message = "OAuth refresh credentials changed during refresh."
        self.failure = image_failure("upstream_unavailable", raw_detail=message)
        super().__init__(message)


class AccountService:
    """账号池服务，使用 token -> account 的 dict 保存账号。"""

    _ACCESS_TOKEN_REFRESH_SKEW_SECONDS = ACCESS_TOKEN_REFRESH_SKEW_SECONDS
    _TOKEN_REFRESH_ERROR_BACKOFF_SECONDS = 5 * 60
    _POOL_HEALTH_REFRESH_BATCH_SIZE = 10
    _IMAGE_FAILURE_REFRESH_DEDUP_SECONDS = 30
    _ACCESS_TOKEN_FINGERPRINT_LIMIT = 8
    _REFRESH_PROGRESS_COMPLETED_TTL_SECONDS = 10 * 60
    _REFRESH_PROGRESS_ACTIVE_TTL_SECONDS = 60 * 60
    _REFRESH_PROGRESS_PRUNE_INTERVAL_SECONDS = 60
    _REFRESH_PROGRESS_EVENT_LIMIT = ACCOUNT_OPERATION_EVENT_LIMIT
    _STORAGE_MUTATION_MAX_ATTEMPTS = 4
    _ACCOUNT_SNAPSHOT_TTL_SECONDS = 5.0
    _GIT_ACCOUNT_SNAPSHOT_TTL_SECONDS = 60.0
    # Operational totals only; resettable state such as invalid_count stays LWW.
    _ADDITIVE_ACCOUNT_COUNTER_FIELDS = frozenset({"success", "fail"})
    _OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
    _OAUTH_CLIENT_ID = "app_2SKx67EdpoN0G6j64rFvigXD"
    _OAUTH_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    )
    _TERMINAL_REFRESH_ERROR_CODES = frozenset({
        "invalid_grant",
        "invalid_refresh_token",
        "refresh_token_invalidated",
    })
    _TERMINAL_REFRESH_MESSAGE_FRAGMENTS = ("session has ended",)
    # 刷新进度追踪
    _refresh_progress: dict[str, dict] = {}
    _refresh_progress_lock = Lock()
    _refresh_progress_last_pruned_at = 0.0

    def __init__(
        self,
        storage_backend: StorageBackend,
        *,
        proxy_reference_mutation: Callable[
            [list[tuple[object, object]], Callable[[list[str]], Any]],
            Any,
        ] | None = None,
    ):
        self.storage = storage_backend
        self._proxy_reference_mutation = proxy_reference_mutation
        self._lock = Lock()
        self._oauth_refresh_flights_lock = Lock()
        self._oauth_refresh_flights: dict[_CredentialGeneration, Future[str]] = {}
        self._image_slot_condition = Condition(self._lock)
        self._account_snapshot_refresh_lock = Lock()
        self._index = 0
        self._persisted_accounts: dict[str, dict] = {}
        self._accounts_revision = ""
        self._accounts = self._load_accounts()
        self._account_snapshot_checked_at = time.monotonic()
        self._image_inflight: dict[str, int] = {}
        self._image_failure_refresh_lock = Lock()
        self._image_failure_refresh_active: set[str] = set()
        self._image_failure_refresh_active_scopes: dict[str, str] = {}
        self._image_failure_refresh_rerun: set[str] = set()
        self._image_failure_refresh_pending: deque[str] = deque()
        self._image_failure_refresh_pending_set: set[str] = set()
        self._image_failure_refresh_pending_scopes: dict[str, str] = {}
        self._image_failure_refresh_started_at: dict[str, float] = {}
        self._token_aliases: dict[str, str] = {}
        self._cumulative_total = self._load_cumulative_total()

    def _get_cumulative_file(self) -> Path:
        storage_path = getattr(self.storage, "file_path", None)
        if isinstance(storage_path, Path):
            return storage_path.with_name(".cumulative_total")
        from services.config import DATA_DIR
        return DATA_DIR / ".cumulative_total"

    def _load_cumulative_total(self) -> int:
        try:
            f = self._get_cumulative_file()
            if f.exists():
                return int(f.read_text().strip())
        except Exception:
            pass
        return len(self._accounts)

    def _save_cumulative_total(self) -> None:
        try:
            self._get_cumulative_file().write_text(str(self._cumulative_total))
        except Exception:
            pass

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _decode_jwt_payload(token: str) -> dict:
        return decode_access_token_payload(token)

    @staticmethod
    def _management_id_for_token(access_token: str) -> str:
        digest = hashlib.sha256(str(access_token or "").encode("utf-8")).hexdigest()[:24]
        return f"acct_{digest}"

    @staticmethod
    def _access_token_fingerprint(access_token: str) -> str:
        return hashlib.sha256(str(access_token or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _scrub_diagnostic_secrets(
        account: dict,
        values: list[object],
    ) -> None:
        secrets = [str(value or "").strip() for value in values]
        secrets = [secret for secret in secrets if secret]
        if not secrets:
            return
        for key in (
            "last_remote_check_error",
            "last_refresh_error",
            "last_token_refresh_error",
        ):
            value = account.get(key)
            if not isinstance(value, str):
                continue
            account[key] = sanitize_diagnostic_text(
                value,
                sensitive_values=secrets,
            )

    @classmethod
    def _normalize_access_token_fingerprints(
        cls,
        value: object,
        access_token: str,
    ) -> list[str]:
        candidates = value if isinstance(value, list) else []
        fingerprints = [
            str(item or "").strip().lower()
            for item in candidates
            if len(str(item or "").strip()) == 64
            and all(char in "0123456789abcdef" for char in str(item or "").strip().lower())
        ]
        current = cls._access_token_fingerprint(access_token)
        fingerprints = list(dict.fromkeys(fingerprints))
        first = fingerprints[0] if fingerprints else current
        recent = [fingerprint for fingerprint in fingerprints[1:] if fingerprint != current]
        if current != first:
            recent.append(current)
        return [first, *recent[-(cls._ACCESS_TOKEN_FINGERPRINT_LIMIT - 1):]]

    @classmethod
    def _normalize_management_id(cls, value: object, access_token: str) -> str:
        candidate = str(value or "").strip().lower()
        suffix = candidate[5:] if candidate.startswith("acct_") else ""
        if len(suffix) == 24 and all(char in "0123456789abcdef" for char in suffix):
            return candidate
        return cls._management_id_for_token(access_token)


    @classmethod
    def _unique_management_id(
        cls,
        access_token: str,
        preferred: object,
        used_ids: set[str],
    ) -> str:
        candidate = cls._normalize_management_id(preferred, access_token)
        if candidate not in used_ids:
            return candidate
        counter = 1
        while True:
            digest = hashlib.sha256(
                f"{access_token}\0{counter}".encode("utf-8")
            ).hexdigest()[:24]
            candidate = f"acct_{digest}"
            if candidate not in used_ids:
                return candidate
            counter += 1

    @staticmethod
    def _parse_time(value: object) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            try:
                parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _timestamp_to_iso(value: object) -> str:
        try:
            ts = int(value)
        except (TypeError, ValueError):
            return ""
        tz = timezone(timedelta(hours=8))
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz).isoformat()

    def _normalize_loaded_accounts(
        self,
        accounts: list[Any],
        *,
        recover_interrupted_checks: bool,
    ) -> tuple[dict[str, dict], bool]:
        loaded: dict[str, dict] = {}
        used_management_ids: set[str] = set()
        changed = False
        for item in accounts:
            normalized = self._normalize_account(item)
            if normalized is None:
                changed = True
                continue
            access_token = str(normalized.get("access_token") or "").strip()
            previous = loaded.get(access_token)
            if previous is not None:
                used_management_ids.discard(
                    str(previous.get("management_id") or "").strip().lower()
                )
            management_id = self._unique_management_id(
                access_token,
                normalized.get("management_id"),
                used_management_ids,
            )
            if management_id != normalized.get("management_id"):
                normalized["management_id"] = management_id
                changed = True
            if (
                recover_interrupted_checks
                and normalized.get("last_remote_check_result") == "pending"
                and normalized.get("pending_auth_scope") != "image"
            ):
                normalized["last_remote_check_result"] = "error"
                normalized["last_remote_check_error"] = (
                    normalized.get("last_remote_check_error")
                    or "Account verification was interrupted by a service restart."
                )
                normalized["last_remote_check_error_at"] = datetime.now(timezone.utc).isoformat()
                normalized["pending_auth_remove_invalid"] = None
                normalized["pending_auth_scope"] = None
                normalized.pop("pending_auth_verification_id", None)
                changed = True
            if normalized != item:
                changed = True
            used_management_ids.add(management_id)
            loaded[normalized["access_token"]] = normalized
        return loaded, changed

    def _load_accounts(self) -> dict[str, dict]:
        last_conflict: StorageRevisionConflictError | None = None
        for _ in range(self._STORAGE_MUTATION_MAX_ATTEMPTS):
            loaded, revision, changed = self._read_accounts_snapshot(
                recover_interrupted_checks=True,
            )
            if changed:
                try:
                    result = self.storage.replace_accounts(
                        list(loaded.values()),
                        expected_revision=revision,
                    )
                except StorageRevisionConflictError as exc:
                    last_conflict = exc
                    continue
                revision = result.revision
            self._persisted_accounts = deepcopy(loaded)
            self._accounts_revision = revision
            return loaded
        assert last_conflict is not None
        raise last_conflict

    def _read_accounts_snapshot(
        self,
        *,
        recover_interrupted_checks: bool = False,
    ) -> tuple[dict[str, dict], str, bool]:
        snapshot = self.storage.load_accounts_snapshot()
        loaded, changed = self._normalize_loaded_accounts(
            snapshot.items,
            recover_interrupted_checks=recover_interrupted_checks,
        )
        return loaded, snapshot.revision, changed

    def _account_snapshot_ttl_seconds(self) -> float:
        ttl = max(0.0, float(self._ACCOUNT_SNAPSHOT_TTL_SECONDS))
        try:
            backend_type = str(self.storage.get_backend_info().get("type") or "").strip().lower()
        except Exception:
            return ttl
        if backend_type == "git":
            return max(ttl, float(self._GIT_ACCOUNT_SNAPSHOT_TTL_SECONDS))
        return ttl

    def _apply_account_view_locked(
        self,
        accounts: dict[str, dict],
        *,
        persisted_accounts: dict[str, dict],
        revision: str,
        snapshot_checked: bool = True,
        preserve_index: bool = False,
    ) -> None:
        token_rotations = self._passive_token_rotations_locked(accounts)
        self._accounts = accounts
        self._persisted_accounts = deepcopy(persisted_accounts)
        self._accounts_revision = revision
        for new_token, alias_sources in token_rotations:
            self._move_account_runtime_token_locked(new_token, alias_sources)
        if not preserve_index:
            self._index = self._index % len(self._accounts) if self._accounts else 0
        if snapshot_checked:
            self._account_snapshot_checked_at = time.monotonic()
        self._image_slot_condition.notify_all()

    def _refresh_accounts_snapshot_if_stale(
        self,
        *,
        wait_for_refresh: bool = False,
    ) -> bool:
        now = time.monotonic()
        ttl = self._account_snapshot_ttl_seconds()
        with self._lock:
            if (
                now - self._account_snapshot_checked_at
                < ttl
            ):
                return False

        if not self._account_snapshot_refresh_lock.acquire(blocking=wait_for_refresh):
            return False
        try:
            with self._lock:
                if (
                    time.monotonic() - self._account_snapshot_checked_at
                    < ttl
                ):
                    return False
                expected_revision = self._accounts_revision

            try:
                loaded, revision, _ = self._read_accounts_snapshot()
            except Exception:
                with self._lock:
                    if self._accounts_revision == expected_revision:
                        self._account_snapshot_checked_at = time.monotonic()
                return False

            with self._image_slot_condition:
                if self._accounts_revision != expected_revision:
                    return False
                self._account_snapshot_checked_at = time.monotonic()
                if revision == expected_revision:
                    return False
                self._apply_account_view_locked(
                    loaded,
                    persisted_accounts=loaded,
                    revision=revision,
                )
                return True
        finally:
            self._account_snapshot_refresh_lock.release()

    @staticmethod
    def _account_mutation(
        baseline: dict[str, dict],
        desired: dict[str, dict],
        revision: str,
    ) -> StorageMutation:
        return StorageMutation(
            upserts=tuple(
                deepcopy(account)
                for token, account in desired.items()
                if token not in baseline or baseline[token] != account
            ),
            delete_keys=tuple(token for token in baseline if token not in desired),
            expected_revision=revision,
        )

    @staticmethod
    def _integer_field(value: object) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _merge_additive_account_value(
        cls,
        field: str,
        baseline: dict,
        local: dict,
        remote: dict,
    ) -> int | None:
        if field not in baseline or field not in local or field not in remote:
            return None
        baseline_value = cls._integer_field(baseline[field])
        local_value = cls._integer_field(local[field])
        remote_value = cls._integer_field(remote[field])
        if baseline_value is None or local_value is None or remote_value is None:
            return None
        return max(0, remote_value + (local_value - baseline_value))

    @classmethod
    def _is_local_quota_consumption(cls, baseline: dict, local: dict) -> bool:
        # quota is also refreshed as an absolute upstream snapshot. A changed
        # last_used_at distinguishes an image-result decrement from that refresh.
        baseline_quota = cls._integer_field(baseline.get("quota"))
        local_quota = cls._integer_field(local.get("quota"))
        return bool(
            baseline_quota is not None
            and local_quota is not None
            and local_quota < baseline_quota
            and local.get("last_used_at") != baseline.get("last_used_at")
        )

    @classmethod
    def _merge_account_fields(
        cls,
        baseline: dict,
        local: dict,
        remote: dict,
    ) -> dict:
        merged = deepcopy(remote)
        for field in baseline.keys() | local.keys():
            baseline_has = field in baseline
            local_has = field in local
            if baseline_has == local_has and (
                not local_has or baseline[field] == local[field]
            ):
                continue
            if local_has:
                if field in cls._ADDITIVE_ACCOUNT_COUNTER_FIELDS:
                    additive_value = cls._merge_additive_account_value(
                        field,
                        baseline,
                        local,
                        remote,
                    )
                    if additive_value is not None:
                        merged[field] = additive_value
                        continue
                if field == "quota" and cls._is_local_quota_consumption(
                    baseline,
                    local,
                ):
                    additive_value = cls._merge_additive_account_value(
                        field,
                        baseline,
                        local,
                        remote,
                    )
                    if additive_value is not None:
                        merged[field] = additive_value
                        continue
                merged[field] = deepcopy(local[field])
            else:
                merged.pop(field, None)
        return merged

    @staticmethod
    def _rotated_account_token(
        accounts: dict[str, dict],
        baseline: dict[str, dict],
        old_token: str,
        old_account: dict,
    ) -> str | None:
        management_id = str(old_account.get("management_id") or "").strip()
        if not management_id:
            return None
        return next(
            (
                token
                for token, account in accounts.items()
                if token != old_token
                and token not in baseline
                and str(account.get("management_id") or "").strip() == management_id
            ),
            None,
        )

    @classmethod
    def _merge_accounts_after_conflict(
        cls,
        baseline: dict[str, dict],
        local: dict[str, dict],
        remote: dict[str, dict],
    ) -> dict[str, dict]:
        merged = deepcopy(remote)
        handled_local_tokens: set[str] = set()

        for token, baseline_account in baseline.items():
            if token in local:
                continue
            local_rotation = cls._rotated_account_token(
                local,
                baseline,
                token,
                baseline_account,
            )
            remote_rotation = cls._rotated_account_token(
                remote,
                baseline,
                token,
                baseline_account,
            )
            if local_rotation is None:
                # A local deletion is an explicit command. It also deletes a
                # concurrently rotated form of the same logical account.
                merged.pop(token, None)
                if remote_rotation is not None:
                    merged.pop(remote_rotation, None)
                continue

            handled_local_tokens.add(local_rotation)
            if token not in remote:
                # A remote deletion beats a stale token refresh. When both
                # processes rotated the account, retain the remote winner.
                continue
            merged.pop(token, None)
            merged[local_rotation] = cls._merge_account_fields(
                baseline_account,
                local[local_rotation],
                remote[token],
            )

        for token, local_account in local.items():
            if token in handled_local_tokens:
                continue
            baseline_account = baseline.get(token)
            if baseline_account is None:
                remote_account = remote.get(token)
                merged[token] = (
                    {**deepcopy(remote_account), **deepcopy(local_account)}
                    if remote_account is not None
                    else deepcopy(local_account)
                )
                continue
            if local_account == baseline_account:
                continue
            remote_account = remote.get(token)
            if remote_account is None:
                remote_rotation = cls._rotated_account_token(
                    remote,
                    baseline,
                    token,
                    baseline_account,
                )
                if remote_rotation is not None:
                    merged[remote_rotation] = cls._merge_account_fields(
                        baseline_account,
                        local_account,
                        remote[remote_rotation],
                    )
                    merged.pop(token, None)
                    continue
                # A remote deletion beats a stale background update. Keeping it
                # deleted also removes it from this process's in-memory view.
                merged.pop(token, None)
                continue
            merged[token] = cls._merge_account_fields(
                baseline_account,
                local_account,
                remote_account,
            )
        return merged

    def _prune_token_aliases_locked(self) -> None:
        aliases = dict(getattr(self, "_token_aliases", {}))
        compacted: dict[str, str] = {}
        for source in aliases:
            token = source
            seen: set[str] = set()
            while token not in self._accounts and token in aliases and token not in seen:
                seen.add(token)
                token = aliases[token]
            if token in self._accounts and token != source:
                compacted[source] = token
        self._token_aliases = compacted

    def _remove_account_runtime_state_locked(self, tokens: set[str]) -> None:
        removed_tokens = {str(token or "").strip() for token in tokens if token}
        if not removed_tokens:
            return
        for token in removed_tokens:
            self._image_inflight.pop(token, None)
        self._token_aliases = {
            source: target
            for source, target in self._token_aliases.items()
            if source not in removed_tokens and target not in removed_tokens
        }
        self._index = self._index % len(self._accounts) if self._accounts else 0

    def _restore_accounts_after_save_error(self) -> None:
        fallback = deepcopy(self._persisted_accounts)
        try:
            loaded, revision, _ = self._read_accounts_snapshot()
        except Exception:
            self._apply_account_view_locked(
                fallback,
                persisted_accounts=fallback,
                revision=self._accounts_revision,
                snapshot_checked=False,
                preserve_index=True,
            )
        else:
            self._apply_account_view_locked(
                loaded,
                persisted_accounts=loaded,
                revision=revision,
                preserve_index=True,
            )

    def _save_accounts(
        self,
        *,
        expected_credential_generation: _CredentialGeneration | None = None,
        conflict_existing_tokens: set[str] | None = None,
    ) -> bool:
        last_conflict: StorageRevisionConflictError | None = None
        for attempt in range(self._STORAGE_MUTATION_MAX_ATTEMPTS):
            mutation = self._account_mutation(
                self._persisted_accounts,
                self._accounts,
                self._accounts_revision,
            )
            if not mutation.upserts and not mutation.delete_keys:
                self._prune_token_aliases_locked()
                return True
            try:
                result = self.storage.mutate_accounts(mutation)
            except StorageRevisionConflictError as exc:
                last_conflict = exc
                if attempt + 1 >= self._STORAGE_MUTATION_MAX_ATTEMPTS:
                    self._restore_accounts_after_save_error()
                    raise
                try:
                    snapshot = self.storage.load_accounts_snapshot()
                    remote, _ = self._normalize_loaded_accounts(
                        snapshot.items,
                        recover_interrupted_checks=False,
                    )
                    if conflict_existing_tokens is not None:
                        conflict_existing_tokens.update(
                            token
                            for token in self._accounts
                            if token not in self._persisted_accounts and token in remote
                        )
                    if expected_credential_generation is not None:
                        expected_access_token = expected_credential_generation[0]
                        remote_account = remote.get(expected_access_token)
                        if (
                            remote_account is None
                            or self._credential_generation(
                                expected_access_token,
                                remote_account,
                            )
                            != expected_credential_generation
                        ):
                            self._apply_account_view_locked(
                                remote,
                                persisted_accounts=remote,
                                revision=snapshot.revision,
                            )
                            return False
                    merged = self._merge_accounts_after_conflict(
                        self._persisted_accounts,
                        self._accounts,
                        remote,
                    )
                    self._apply_account_view_locked(
                        merged,
                        persisted_accounts=remote,
                        revision=snapshot.revision,
                    )
                except Exception:
                    self._restore_accounts_after_save_error()
                    raise
                continue
            except Exception:
                self._restore_accounts_after_save_error()
                raise
            self._persisted_accounts = deepcopy(self._accounts)
            self._accounts_revision = result.revision
            self._account_snapshot_checked_at = time.monotonic()
            self._prune_token_aliases_locked()
            return True
        assert last_conflict is not None
        raise last_conflict

    @staticmethod
    def _is_account_selectable(
        account: dict,
        *,
        allow_limited: bool,
        allow_image_pending: bool = False,
    ) -> bool:
        if not isinstance(account, dict):
            return False
        allowed_statuses = {"正常", "限流"} if allow_limited else {"正常"}
        if account.get("status") not in allowed_statuses:
            return False
        credential_availability = project_upstream_credential_availability(
            str(account.get("access_token") or ""),
            str(account.get("refresh_token") or ""),
            access_confirmed_invalid=(
                str(account.get("last_remote_check_result") or "").strip().lower() == "invalid"
            ),
            refresh_confirmed_invalid=bool(account.get("refresh_token_invalid_at")),
        )
        if credential_availability.status == "unavailable":
            return False
        if account.get("last_remote_check_result") != "pending":
            return True
        return bool(
            allow_image_pending
            and account.get("pending_auth_scope") == "image"
        )

    @classmethod
    def _is_image_account_available(cls, account: dict) -> bool:
        if not cls._is_account_selectable(account, allow_limited=False):
            return False
        if bool(account.get("image_quota_unknown")):
            return True
        # quota 是展示/预估值，不能作为持久调度开关。
        # 只有远程确认后写入的“限流”状态才代表图片额度耗尽；否则 quota=0 也要允许进入预检，
        # 避免本地扣减或额度重置不同步时把账号锁死在候选池外。
        return account.get("status") == "正常" or int(account.get("quota") or 0) > 0

    @classmethod
    def _is_unlimited_image_quota_account(cls, account: dict) -> bool:
        if not isinstance(account, dict) or not bool(account.get("image_quota_unknown")):
            return False
        account_type = (cls._normalize_account_type(account.get("type")) or "").lower()
        return account_type in {"pro", "prolite"}

    @classmethod
    def _account_matches_plan_type(cls, account: dict, plan_type: str | None = None) -> bool:
        if not plan_type:
            return True
        normalized_plan = cls._normalize_account_type(plan_type)
        normalized_account = cls._normalize_account_type(account.get("type"))
        if not normalized_plan or not normalized_account:
            return False
        return normalized_plan.lower() == normalized_account.lower()

    @classmethod
    def _account_matches_source_type(cls, account: dict, source_type: str | None = None) -> bool:
        if not source_type:
            return True
        return cls._normalize_source_type(account.get("source_type")) == cls._normalize_source_type(source_type)

    @classmethod
    def _account_matches_any_plan_type(cls, account: dict, plan_types: set[str] | tuple[str, ...] | None = None) -> bool:
        if not plan_types:
            return True
        normalized_account = cls._normalize_account_type(account.get("type"))
        normalized_plans = {
            normalized
            for plan_type in plan_types
            if (normalized := cls._normalize_account_type(plan_type))
        }
        return bool(normalized_account and normalized_account in normalized_plans)

    @staticmethod
    def _normalize_source_type(value: object) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"codex", "cpa", "cpa_json", "remote_cpa", "sub2api"}:
            return "codex"
        return "web"

    @staticmethod
    def _normalize_account_type(value: object) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        key = raw.lower().replace("-", "_").replace(" ", "_")
        compact = key.replace("_", "")
        aliases = {
            "free": "free",
            "plus": "Plus",
            "pro": "Pro",
            "prolite": "ProLite",
            "team": "Team",
            "business": "Team",
            "enterprise": "Enterprise",
        }
        return aliases.get(compact) or aliases.get(key)

    @staticmethod
    def _has_value(value: object) -> bool:
        return value is not None and str(value).strip() != ""

    @staticmethod
    def _bool_value(value: object, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        raw = str(value or "").strip().lower()
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off", "none", "null", ""}:
            return False
        return default

    @classmethod
    def _normalize_account_status(cls, value: object, account: dict) -> str:
        if cls._bool_value(account.get("auto_disabled"), False):
            return "禁用"
        if account.get("enabled") is not None and not cls._bool_value(account.get("enabled"), True):
            return "禁用"
        raw = str(value or "").strip()
        if not raw:
            return "正常"
        aliases = {
            "正常": "正常",
            "normal": "正常",
            "ready": "正常",
            "限流": "限流",
            "limited": "限流",
            "rate_limited": "限流",
            "cooling": "限流",
            "backoff": "限流",
            "异常": "异常",
            "abnormal": "异常",
            "invalid": "异常",
            "error": "异常",
            "incomplete": "异常",
            "禁用": "禁用",
            "disabled": "禁用",
            "auto_disabled": "禁用",
        }
        return aliases.get(raw.lower(), aliases.get(raw, "正常"))

    @classmethod
    def _quota_value(cls, value: object, default: int = 0) -> int:
        if not cls._has_value(value):
            return max(0, int(default or 0))
        try:
            return max(0, int(float(str(value).strip())))
        except (TypeError, ValueError):
            return max(0, int(default or 0))

    @classmethod
    def _extract_image_quota_from_limits(cls, limits_progress: object) -> tuple[int | None, str | None, bool | None]:
        if not isinstance(limits_progress, list):
            return None, None, None
        if not limits_progress:
            return None, None, None

        for item in limits_progress:
            if not isinstance(item, dict):
                continue
            feature = str(
                item.get("feature_name")
                or item.get("feature")
                or item.get("name")
                or item.get("type")
                or ""
            ).strip().lower()
            if feature in {"image_gen", "image_generation", "image", "images"}:
                restore_at = str(
                    item.get("reset_after")
                    or item.get("restore_at")
                    or item.get("reset_at")
                    or ""
                ).strip() or None
                return cls._quota_value(item.get("remaining"), 0), restore_at, False

        return None, None, True

    def _normalize_account(self, item: dict) -> dict | None:
        if not isinstance(item, dict):
            return None
        access_token = item.get("access_token") or item.get("accessToken") or ""
        if not access_token:
            return None
        normalized = dict(item)
        normalized.pop("accessToken", None)
        normalized["access_token"] = access_token
        normalized["management_id"] = self._normalize_management_id(
            normalized.get("management_id"),
            access_token,
        )
        normalized["access_token_fingerprints"] = self._normalize_access_token_fingerprints(
            normalized.get("access_token_fingerprints"),
            access_token,
        )
        if str(normalized.get("type") or "").strip().lower() == "codex":
            normalized["export_type"] = "codex"
            normalized.pop("type", None)
        limits_progress = normalized.get("limits_progress")
        limits_progress = limits_progress if isinstance(limits_progress, list) else []
        derived_quota, derived_restore_at, derived_unknown = self._extract_image_quota_from_limits(limits_progress)
        has_explicit_quota = self._has_value(normalized.get("quota"))
        normalized["type"] = self._normalize_account_type(normalized.get("type"))
        normalized["status"] = self._normalize_account_status(normalized.get("status"), normalized)
        normalized.pop("enabled", None)
        normalized.pop("auto_disabled", None)
        normalized["email"] = normalized.get("email") or None
        normalized["user_id"] = normalized.get("user_id") or None
        normalized["proxy"] = str(normalized.get("proxy") or "").strip()
        source_type = normalized.get("source_type")
        if not source_type and str(normalized.get("export_type") or "").strip().lower() == "codex":
            source_type = "codex"
        normalized["source_type"] = self._normalize_source_type(source_type)
        if not has_explicit_quota and derived_quota is not None:
            normalized["quota"] = derived_quota
        normalized["quota"] = self._quota_value(normalized.get("quota"), 0)
        has_explicit_quota_state = self._has_value(normalized.get("image_quota_unknown"))
        if derived_unknown is not None and not has_explicit_quota_state:
            normalized["image_quota_unknown"] = derived_unknown
        elif not has_explicit_quota_state:
            normalized["image_quota_unknown"] = True
        normalized["image_quota_unknown"] = self._bool_value(normalized.get("image_quota_unknown"), True)
        has_confirmed_quota = (
            derived_unknown is False
            or (
                bool(normalized.get("last_remote_checked_at"))
                and not normalized["image_quota_unknown"]
            )
        )
        if normalized["status"] == "正常" and (not has_confirmed_quota or normalized["quota"] == 0):
            normalized["image_quota_unknown"] = True
        elif normalized["status"] == "限流":
            normalized["quota"] = 0
            normalized["image_quota_unknown"] = False
        normalized["limits_progress"] = limits_progress
        normalized["default_model_slug"] = normalized.get("default_model_slug") or None
        if derived_restore_at and not normalized.get("restore_at"):
            normalized["restore_at"] = derived_restore_at
        normalized["restore_at"] = normalized.get("restore_at") or None
        normalized["success"] = int(normalized.get("success") or 0)
        normalized["fail"] = int(normalized.get("fail") or 0)
        normalized["invalid_count"] = int(normalized.get("invalid_count") or 0)
        normalized["last_used_at"] = normalized.get("last_used_at")
        normalized["last_invalid_at"] = normalized.get("last_invalid_at") or None
        normalized["last_refresh_error"] = normalized.get("last_refresh_error") or None
        normalized["last_refresh_error_at"] = normalized.get("last_refresh_error_at") or None
        normalized["last_remote_checked_at"] = normalized.get("last_remote_checked_at") or None
        normalized["last_remote_check_attempt_at"] = normalized.get("last_remote_check_attempt_at") or None
        normalized["last_remote_check_error"] = normalized.get("last_remote_check_error") or None
        normalized["last_remote_check_error_at"] = normalized.get("last_remote_check_error_at") or None
        normalized["last_remote_check_event"] = normalized.get("last_remote_check_event") or None
        remote_check_result = str(normalized.get("last_remote_check_result") or "").strip().lower()
        normalized["last_remote_check_result"] = (
            remote_check_result
            if remote_check_result in {"pending", "ok", "error", "invalid"}
            else None
        )
        pending_remove = normalized.get("pending_auth_remove_invalid")
        normalized["pending_auth_remove_invalid"] = (
            self._bool_value(pending_remove)
            if normalized["last_remote_check_result"] == "pending" and pending_remove is not None
            else None
        )
        pending_scope = str(normalized.get("pending_auth_scope") or "").strip().lower()
        normalized["pending_auth_scope"] = (
            "image" if pending_scope == "image" else "account"
        ) if normalized["last_remote_check_result"] == "pending" else None
        verification_id = str(normalized.get("pending_auth_verification_id") or "").strip()
        if normalized["last_remote_check_result"] == "pending" and verification_id:
            normalized["pending_auth_verification_id"] = verification_id
        else:
            normalized.pop("pending_auth_verification_id", None)

        normalized["last_token_refresh_at"] = normalized.get("last_token_refresh_at") or None
        normalized["last_token_refresh_error"] = normalized.get("last_token_refresh_error") or None
        normalized["last_token_refresh_error_at"] = normalized.get("last_token_refresh_error_at") or None
        normalized["refresh_token_invalid_at"] = normalized.get("refresh_token_invalid_at") or None
        diagnostic_secrets = (
            normalized.get("access_token"),
            normalized.get("refresh_token"),
            normalized.get("id_token"),
        )
        diagnostic_proxies = (normalized.get("proxy"),)
        for key in (
            "last_remote_check_error",
            "last_refresh_error",
            "last_token_refresh_error",
        ):
            if normalized.get(key):
                normalized[key] = sanitize_diagnostic_text(
                    normalized[key],
                    sensitive_values=diagnostic_secrets,
                    proxy_values=diagnostic_proxies,
                )
        for key in (
            "capability_cooldowns",
            "capability_failure_counts",
            "capability_failure_codes",
            "capability_failed_at",
        ):
            normalized.pop(key, None)
        normalized["created_at"] = normalized.get("created_at") or AccountService._now()
        return normalized

    @staticmethod
    def _jwt_exp(access_token: str) -> int:
        try:
            return int(AccountService._decode_jwt_payload(access_token).get("exp") or 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _token_expires_in(cls, access_token: str) -> int | None:
        return access_token_expires_in_seconds(access_token)

    @classmethod
    def _token_needs_refresh(cls, access_token: str, *, force: bool = False) -> bool:
        if force:
            return True
        remaining = cls._token_expires_in(access_token)
        return remaining is not None and remaining <= cls._ACCESS_TOKEN_REFRESH_SKEW_SECONDS

    @classmethod
    def _token_issued_at(cls, access_token: str) -> datetime | None:
        issued_at = access_token_issued_at(access_token)
        if issued_at is None:
            return None
        return datetime.fromtimestamp(issued_at, tz=timezone.utc)

    @staticmethod
    def _safe_response_text(response: object, limit: int = 300) -> str:
        try:
            return str(getattr(response, "text", "") or "")[:limit]
        except Exception:
            return ""

    @staticmethod
    def _oauth_refresh_error_fields(data: object) -> tuple[str, str]:
        if not isinstance(data, dict):
            return "", ""
        error = data.get("error")
        nested = error if isinstance(error, dict) else {}
        code = str(
            nested.get("code")
            or data.get("code")
            or (error if isinstance(error, str) else "")
            or ""
        ).strip()
        description = str(
            data.get("error_description")
            or nested.get("message")
            or data.get("message")
            or nested.get("description")
            or ""
        ).strip()
        return code, description

    @classmethod
    def _is_terminal_refresh_error(cls, status_code: int, error_code: str, description: str) -> bool:
        if status_code in {408, 429} or status_code >= 500:
            return False
        normalized_code = str(error_code or "").strip().casefold()
        normalized_description = str(description or "").strip().casefold()
        if normalized_code in cls._TERMINAL_REFRESH_ERROR_CODES:
            return True
        return 400 <= status_code < 500 and any(
            fragment in normalized_description
            for fragment in cls._TERMINAL_REFRESH_MESSAGE_FRAGMENTS
        )

    def _resolve_access_token_locked(self, access_token: str) -> str:
        token = str(access_token or "").strip()
        seen: set[str] = set()
        while token and token not in self._accounts and token in self._token_aliases and token not in seen:
            seen.add(token)
            token = self._token_aliases.get(token, token)
        return token

    def resolve_access_token(self, access_token: str) -> str:
        if not access_token:
            return ""
        with self._lock:
            return self._resolve_access_token_locked(access_token)

    def _get_account_for_token(self, access_token: str) -> tuple[str, dict | None]:
        with self._lock:
            resolved = self._resolve_access_token_locked(access_token)
            account = self._accounts.get(resolved)
            return resolved, dict(account) if account else None

    def _credential_snapshot(self, access_token: str) -> tuple[str, str, dict | None]:
        resolved, account = self._get_account_for_token(access_token)
        if not account:
            return resolved, "", None
        active_token = str(account.get("access_token") or resolved or access_token).strip()
        refresh_token = str(account.get("refresh_token") or "").strip()
        return active_token, refresh_token, account

    @staticmethod
    def _credential_generation(
        access_token: str,
        account: dict | None,
    ) -> _CredentialGeneration:
        item = account or {}
        return (
            str(item.get("access_token") or access_token or "").strip(),
            str(item.get("refresh_token") or "").strip(),
            str(item.get("last_token_refresh_at") or "").strip(),
        )

    def _record_token_refresh_error(
        self,
        access_token: str,
        event: str,
        error: str,
        *,
        expected_access_token: str | None = None,
        expected_refresh_token: str | None = None,
        expected_last_token_refresh_at: str | None = None,
        terminal: bool = False,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            resolved = self._resolve_access_token_locked(access_token)
            current = self._accounts.get(resolved)
            if current is None:
                return False
            expected_generation = None
            if expected_access_token is not None and expected_refresh_token is not None:
                expected_generation = (
                    str(expected_access_token or "").strip(),
                    str(expected_refresh_token or "").strip(),
                    str(expected_last_token_refresh_at or "").strip(),
                )
                if self._credential_generation(resolved, current) != expected_generation:
                    return False
            next_item = dict(current)
            next_item["last_token_refresh_error"] = str(error or "refresh token failed")
            next_item["last_token_refresh_error_at"] = now
            if terminal:
                next_item["refresh_token_invalid_at"] = now
            account = self._normalize_account(next_item)
            if account is None:
                return False
            self._accounts[resolved] = account
            saved = self._save_accounts(
                expected_credential_generation=expected_generation,
            )
            if not saved:
                return False
            resolved = self._resolve_access_token_locked(resolved)
            persisted = self._accounts.get(resolved)
            if (
                persisted is None
                or persisted.get("last_token_refresh_error_at") != now
            ):
                return False
        log_service.add(
            LOG_TYPE_ACCOUNT,
            "refresh_token 刷新 access_token 失败",
            {
                "source": event,
                "token": anonymize_token(resolved),
                "error": str(persisted.get("last_token_refresh_error") or ""),
            },
        )
        return True

    @staticmethod
    def _credential_error_text(
        error: object,
        account: dict | None,
        *,
        access_token: str = "",
    ) -> str:
        account = account or {}
        return sanitize_diagnostic_text(
            error,
            sensitive_values=(
                access_token,
                account.get("access_token"),
                account.get("refresh_token"),
                account.get("id_token"),
            ),
            proxy_values=(account.get("proxy"),),
            limit=2000,
        )

    def _recent_token_refresh_error(self, account: dict) -> bool:
        last_error_at = self._parse_time(account.get("last_token_refresh_error_at"))
        if last_error_at is None:
            return False
        return (datetime.now(timezone.utc) - last_error_at).total_seconds() < self._TOKEN_REFRESH_ERROR_BACKOFF_SECONDS

    def _request_access_token_refresh(
        self,
        refresh_token: str,
        account: dict | None = None,
        *,
        image_scope: bool = False,
    ) -> dict[str, str]:
        from curl_cffi import requests
        from services.proxy_service import proxy_settings

        session = requests.Session(**proxy_settings.build_session_kwargs(account=account, impersonate="chrome110", verify=True))
        try:
            with account_processing_slot():
                response = session.post(
                    self._OAUTH_TOKEN_URL,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": self._OAUTH_USER_AGENT,
                    },
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": self._OAUTH_CLIENT_ID,
                    },
                    timeout=60,
                )
            raw_text = self._safe_response_text(response)
            try:
                data = response.json() if raw_text else {}
            except Exception:
                data = {}
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code != 200 or not isinstance(data, dict) or not data.get("access_token"):
                error_code, description = self._oauth_refresh_error_fields(data)
                description = description or raw_text
                error_type = (
                    TerminalRefreshTokenError
                    if self._is_terminal_refresh_error(status_code, error_code, description)
                    else OAuthRefreshError
                )
                raise error_type(status_code, error_code, description)
            return {
                "access_token": str(data.get("access_token") or "").strip(),
                "refresh_token": str(data.get("refresh_token") or refresh_token).strip(),
                "id_token": str(data.get("id_token") or "").strip(),
            }
        finally:
            session.close()

    def _move_account_runtime_token_locked(
        self,
        new_token: str,
        alias_sources: set[str],
    ) -> None:
        for source in alias_sources:
            if source != new_token:
                self._token_aliases[source] = new_token

        old_inflight = sum(
            int(self._image_inflight.pop(source, 0))
            for source in alias_sources
            if source != new_token
        )
        if old_inflight:
            self._image_inflight[new_token] = (
                int(self._image_inflight.get(new_token, 0)) + old_inflight
            )

        with self._image_failure_refresh_lock:
            old_scopes = [
                self._image_failure_refresh_pending_scopes.pop(source)
                for source in alias_sources
                if source in self._image_failure_refresh_pending_scopes
            ]
            pending = (
                new_token if token in alias_sources else token
                for token in self._image_failure_refresh_pending
            )
            self._image_failure_refresh_pending = deque(dict.fromkeys(pending))
            self._image_failure_refresh_pending_set = set(
                self._image_failure_refresh_pending
            )
            if old_scopes:
                current_scope = self._image_failure_refresh_pending_scopes.get(new_token)
                self._image_failure_refresh_pending_scopes[new_token] = (
                    "account"
                    if "account" in {*old_scopes, current_scope}
                    else "image"
                )
            old_started_at = max(
                (
                    self._image_failure_refresh_started_at.pop(source)
                    for source in alias_sources
                    if source in self._image_failure_refresh_started_at
                ),
                default=None,
            )
            if old_started_at is not None:
                self._image_failure_refresh_started_at[new_token] = max(
                    old_started_at,
                    self._image_failure_refresh_started_at.get(new_token, 0.0),
                )
            # Active workers keep their original key until their finally block.

    def _passive_token_rotations_locked(
        self,
        loaded: dict[str, dict],
    ) -> list[tuple[str, set[str]]]:
        loaded_by_management_id = {
            str(account.get("management_id") or "").strip(): token
            for token, account in loaded.items()
            if str(account.get("management_id") or "").strip()
        }
        rotations: list[tuple[str, set[str]]] = []
        for old_token, old_account in self._accounts.items():
            if old_token in loaded:
                continue
            management_id = str(old_account.get("management_id") or "").strip()
            new_token = loaded_by_management_id.get(management_id)
            if not new_token or new_token == old_token:
                continue
            alias_sources = {
                source
                for source in {old_token, *self._token_aliases}
                if self._resolve_access_token_locked(source) == old_token
            }
            rotations.append((new_token, alias_sources))
        return rotations

    def _apply_refreshed_tokens(
        self,
        old_access_token: str,
        token_data: dict,
        event: str,
        *,
        expected_access_token: str | None = None,
        expected_refresh_token: str,
        expected_last_token_refresh_at: str | None = None,
    ) -> str:
        now = datetime.now(timezone.utc).isoformat()
        expected_access_token = expected_access_token or old_access_token
        expected_generation = (
            str(expected_access_token or "").strip(),
            str(expected_refresh_token or "").strip(),
            str(expected_last_token_refresh_at or "").strip(),
        )
        with self._image_slot_condition:
            old_token = self._resolve_access_token_locked(old_access_token)
            current = self._accounts.get(old_token)
            if current is None:
                raise RefreshCredentialsChangedError()
            if self._credential_generation(old_token, current) != expected_generation:
                raise RefreshCredentialsChangedError()
            new_token = str(token_data.get("access_token") or old_token).strip()
            if not new_token:
                return old_token
            if new_token != old_token and new_token in self._accounts:
                raise RefreshCredentialsChangedError()

            next_item = dict(current)
            next_item["access_token"] = new_token
            if token_data.get("refresh_token"):
                next_item["refresh_token"] = str(token_data.get("refresh_token") or "").strip()
            if token_data.get("id_token"):
                next_item["id_token"] = str(token_data.get("id_token") or "").strip()
            self._scrub_diagnostic_secrets(
                next_item,
                [
                    current.get("access_token"),
                    current.get("refresh_token"),
                    current.get("id_token"),
                ],
            )
            next_item["last_token_refresh_at"] = now
            next_item["last_token_refresh_error"] = None
            next_item["last_token_refresh_error_at"] = None
            next_item["refresh_token_invalid_at"] = None
            next_item["invalid_count"] = 0
            next_item["last_invalid_at"] = None
            next_item["last_refresh_error"] = None
            next_item["last_refresh_error_at"] = None
            if current.get("status") == "\u5f02\u5e38":
                next_item["status"] = "\u6b63\u5e38"
            if current.get("last_remote_check_result") == "invalid":
                next_item["last_remote_check_result"] = None
                next_item["last_remote_check_error"] = None
                next_item["last_remote_check_error_at"] = None
                next_item["last_remote_check_event"] = None
                next_item["pending_auth_remove_invalid"] = None
                next_item["pending_auth_scope"] = None

            account = self._normalize_account(next_item)
            if account is None:
                return old_token

            rotated = new_token != old_token
            alias_sources = {
                source
                for source in {old_token, *self._token_aliases}
                if self._resolve_access_token_locked(source) == old_token
            }
            if rotated:
                self._accounts.pop(old_token, None)
            self._accounts[new_token] = account
            saved = self._save_accounts(
                expected_credential_generation=expected_generation,
            )
            final_token = (
                new_token
                if new_token in self._accounts
                else next(
                    (
                        token
                        for token, item in self._accounts.items()
                        if item.get("management_id") == current.get("management_id")
                    ),
                    None,
                )
            )
            if not saved or final_token != new_token:
                if final_token:
                    self._move_account_runtime_token_locked(
                        final_token,
                        alias_sources,
                    )
                else:
                    self._remove_account_runtime_state_locked(alias_sources)
                self._image_slot_condition.notify_all()
                raise RefreshCredentialsChangedError()
            if rotated:
                self._move_account_runtime_token_locked(
                    new_token,
                    alias_sources,
                )
            self._image_slot_condition.notify_all()

        log_service.add(
            LOG_TYPE_ACCOUNT,
            "refresh_token 已刷新 access_token",
            {"source": event, "token": anonymize_token(new_token), "rotated": rotated},
        )
        return new_token

    def _refresh_access_token_owner(
        self,
        active_token: str,
        refresh_token: str,
        account: dict,
        *,
        event: str,
        image_scope: bool,
    ) -> str:
        try:
            if image_scope:
                token_data = self._request_access_token_refresh(
                    refresh_token,
                    account,
                    image_scope=True,
                )
            else:
                token_data = self._request_access_token_refresh(refresh_token, account)
        except TerminalRefreshTokenError as exc:
            exc.expected_access_token = active_token
            exc.expected_refresh_token = refresh_token
            exc.expected_last_token_refresh_at = str(
                account.get("last_token_refresh_at") or ""
            )
            current_token, current_refresh_token, current = self._credential_snapshot(active_token)
            if not current or (current_token, current_refresh_token) != (active_token, refresh_token):
                raise RefreshCredentialsChangedError() from exc
            raise
        except Exception as exc:
            recorded = self._record_token_refresh_error(
                active_token,
                event,
                str(exc or ""),
                expected_access_token=active_token,
                expected_refresh_token=refresh_token,
                expected_last_token_refresh_at=str(
                    account.get("last_token_refresh_at") or ""
                ),
            )
            if recorded:
                raise
            raise RefreshCredentialsChangedError() from exc

        return self._apply_refreshed_tokens(
            active_token,
            token_data,
            event,
            expected_access_token=active_token,
            expected_refresh_token=refresh_token,
            expected_last_token_refresh_at=str(
                account.get("last_token_refresh_at") or ""
            ),
        )

    def _maintain_access_token(
        self,
        access_token: str,
        *,
        force: bool = False,
        event: str = "refresh_access_token",
        raise_on_error: bool = False,
        image_scope: bool = False,
        expected_credentials: _CredentialGeneration | None = None,
        skip_if_image_busy: bool = False,
    ) -> str:
        if not access_token:
            return ""
        for credential_attempt in range(2):
            resolved_token, account = self._get_account_for_token(access_token)
            if not account:
                raise RefreshCredentialsChangedError()
            active_token = str(account.get("access_token") or resolved_token or access_token)
            needs_refresh = self._token_needs_refresh(active_token, force=force)
            refresh_backoff = not force and self._recent_token_refresh_error(account)
            refresh_token = str(account.get("refresh_token") or "").strip()
            current_generation = self._credential_generation(active_token, account)
            if (
                expected_credentials is not None
                and current_generation != expected_credentials
            ):
                raise RefreshCredentialsChangedError()
            if not refresh_token:
                return active_token
            if account.get("refresh_token_invalid_at") and not force:
                remaining = self._token_expires_in(active_token)
                if remaining is None or remaining > 0:
                    return active_token
                raise TerminalRefreshTokenError(
                    400,
                    "invalid_refresh_token",
                    "refresh token is marked invalid",
                )

            key = current_generation
            if skip_if_image_busy:
                with self._image_slot_condition:
                    current_token = self._resolve_access_token_locked(active_token)
                    current = self._accounts.get(current_token)
                    current_generation = self._credential_generation(current_token, current)
                    if not current or current_generation != key or (
                        expected_credentials is not None
                        and current_generation != expected_credentials
                    ):
                        if expected_credentials is not None or credential_attempt > 0:
                            raise RefreshCredentialsChangedError()
                        continue
                    image_busy = int(self._image_inflight.get(current_token, 0)) > 1
                    with self._oauth_refresh_flights_lock:
                        future = self._oauth_refresh_flights.get(key)
                        owner = future is None
                        if future is None:
                            if image_busy or not needs_refresh or refresh_backoff:
                                return active_token
                            future = Future()
                            self._oauth_refresh_flights[key] = future
            else:
                with self._oauth_refresh_flights_lock:
                    future = self._oauth_refresh_flights.get(key)
                    owner = future is None
                    if future is None:
                        if not needs_refresh or refresh_backoff:
                            return active_token
                        future = Future()
                        self._oauth_refresh_flights[key] = future
            if owner:
                try:
                    result = self._refresh_access_token_owner(
                        active_token,
                        refresh_token,
                        account,
                        event=event,
                        image_scope=image_scope,
                    )
                except BaseException as exc:
                    future.set_exception(exc)
                else:
                    future.set_result(result)
            try:
                return future.result()
            except TerminalRefreshTokenError as exc:
                expected_access_token = str(
                    getattr(exc, "expected_access_token", active_token) or active_token
                )
                expected_refresh_token = str(
                    getattr(exc, "expected_refresh_token", refresh_token) or refresh_token
                )
                expected_last_token_refresh_at = str(
                    getattr(exc, "expected_last_token_refresh_at", "") or ""
                )
                current_token, current_refresh_token, current = self._credential_snapshot(active_token)
                if current and (current_token, current_refresh_token) != (
                    expected_access_token,
                    expected_refresh_token,
                ):
                    if expected_credentials is not None:
                        raise RefreshCredentialsChangedError() from exc
                    if credential_attempt == 0:
                        access_token = current_token
                        continue
                    raise RefreshCredentialsChangedError() from exc
                error_str = str(exc)
                recorded = self._record_token_refresh_error(
                    active_token,
                    event,
                    error_str,
                    expected_access_token=expected_access_token,
                    expected_refresh_token=expected_refresh_token,
                    expected_last_token_refresh_at=expected_last_token_refresh_at,
                    terminal=True,
                )
                if not recorded:
                    current_token, _current_refresh, current = self._credential_snapshot(
                        active_token
                    )
                    if current is not None:
                        if (
                            expected_credentials is not None
                            and self._credential_generation(current_token, current)
                            != expected_credentials
                        ):
                            raise RefreshCredentialsChangedError() from exc
                        return current_token
                    raise RefreshCredentialsChangedError() from exc
                raise
            except RefreshCredentialsChangedError:
                current_token, current = self._get_account_for_token(active_token)
                if current is None:
                    raise
                latest_generation = self._credential_generation(current_token, current)
                if expected_credentials is not None or latest_generation == current_generation:
                    raise
                # A concurrent successful exchange already produced a usable AT.
                if latest_generation[2] != current_generation[2]:
                    return str(current.get("access_token") or current_token or active_token)
                if credential_attempt == 0:
                    access_token = current_token
                    continue
                raise
            except Exception:
                if raise_on_error:
                    raise
                current_token, current = self._get_account_for_token(active_token)
                if current:
                    return str(current.get("access_token") or current_token or active_token)
                raise RefreshCredentialsChangedError()
            finally:
                if owner:
                    with self._oauth_refresh_flights_lock:
                        if self._oauth_refresh_flights.get(key) is future:
                            self._oauth_refresh_flights.pop(key, None)
        raise RefreshCredentialsChangedError()

    def ensure_access_token(
        self,
        access_token: str,
        *,
        event: str = "ensure_access_token",
        raise_on_error: bool = False,
        image_scope: bool = False,
        expected_credentials: _CredentialGeneration | None = None,
        skip_if_image_busy: bool = False,
    ) -> str:
        """Return a usable AT, renewing it through RT only when needed."""
        return self._maintain_access_token(
            access_token,
            force=False,
            event=event,
            raise_on_error=raise_on_error,
            image_scope=image_scope,
            expected_credentials=expected_credentials,
            skip_if_image_busy=skip_if_image_busy,
        )

    def force_refresh_access_token(
        self,
        access_token: str,
        *,
        event: str = "force_refresh_access_token",
        raise_on_error: bool = False,
        image_scope: bool = False,
        expected_credentials: _CredentialGeneration | None = None,
    ) -> str:
        """Force one RT-to-AT exchange for an explicit recovery or admin action."""
        return self._maintain_access_token(
            access_token,
            force=True,
            event=event,
            raise_on_error=raise_on_error,
            image_scope=image_scope,
            expected_credentials=expected_credentials,
        )

    def refresh_access_token(
        self,
        access_token: str,
        *,
        force: bool = False,
        event: str = "refresh_access_token",
        remove_invalid: bool | None = None,
        raise_on_error: bool = False,
        image_scope: bool = False,
        expected_credentials: _CredentialGeneration | None = None,
        skip_if_image_busy: bool = False,
    ) -> str:
        """Compatibility wrapper; new callers use ensure/force methods."""
        _ = remove_invalid
        operation = self.force_refresh_access_token if force else self.ensure_access_token
        kwargs = {
            "event": event,
            "raise_on_error": raise_on_error,
            "image_scope": image_scope,
            "expected_credentials": expected_credentials,
        }
        if not force:
            kwargs["skip_if_image_busy"] = skip_if_image_busy
        return operation(access_token, **kwargs)

    def list_expiring_access_tokens(self) -> list[str]:
        self._refresh_accounts_snapshot_if_stale()
        with self._lock:
            return [
                token
                for account in self._accounts.values()
                if account.get("status") in {"正常", "限流"}
                and account.get("last_remote_check_result") != "pending"
                and str(account.get("refresh_token") or "").strip()
                and not account.get("refresh_token_invalid_at")
                and (token := str(account.get("access_token") or "").strip())
                and self._token_needs_refresh(token)
            ]

    def list_tokens(self) -> list[str]:
        self._refresh_accounts_snapshot_if_stale()
        with self._lock:
            return list(self._accounts)

    def _list_ready_candidate_tokens(
            self,
            excluded_tokens: set[str] | None = None,
            plan_type: str | None = None,
            source_type: str | None = None,
            plan_types: set[str] | tuple[str, ...] | None = None,
    ) -> list[str]:
        excluded = set(excluded_tokens or set())
        return [
            token
            for item in self._accounts.values()
            if self._is_image_account_available(item)
               and self._account_matches_plan_type(item, plan_type)
               and self._account_matches_any_plan_type(item, plan_types)
               and self._account_matches_source_type(item, source_type)
               and (token := item.get("access_token") or "")
               and token not in excluded
        ]

    def _list_available_candidate_tokens(
            self,
            excluded_tokens: set[str] | None = None,
            plan_type: str | None = None,
            source_type: str | None = None,
            plan_types: set[str] | tuple[str, ...] | None = None,
    ) -> list[str]:
        max_concurrency = max(1, int(config.image_account_concurrency or 1))
        return [
            token
            for token in self._list_ready_candidate_tokens(
                excluded_tokens,
                plan_type,
                source_type,
                plan_types,
            )
            if int(self._image_inflight.get(token, 0)) < max_concurrency
        ]

    def _acquire_next_candidate_token(
            self,
            excluded_tokens: set[str] | None = None,
            plan_type: str | None = None,
            source_type: str | None = None,
            plan_types: set[str] | tuple[str, ...] | None = None,
            deadline_monotonic: float | None = None,
    ) -> str:
        while True:
            with self._image_slot_condition:
                remaining = (
                    float(deadline_monotonic) - time.monotonic()
                    if deadline_monotonic is not None
                    else None
                )
                if remaining is not None and remaining <= 0:
                    raise ImageAccountSelectionError(
                        "deadline_exceeded",
                        "image request deadline exceeded while waiting for an account slot",
                    )
                # Token refresh can rotate an attempted account's access token while
                # this request waits for a slot. Resolve aliases on every pass so the
                # same account cannot be selected again under its refreshed token.
                resolved_excluded_tokens = {
                    self._resolve_access_token_locked(token)
                    for token in (excluded_tokens or set())
                    if token
                }
                if not self._list_ready_candidate_tokens(
                    resolved_excluded_tokens,
                    plan_type,
                    source_type,
                    plan_types,
                ):
                    raise self._no_ready_candidate_error(
                        plan_type,
                        source_type,
                        plan_types,
                        resolved_excluded_tokens,
                    )
                tokens = self._list_available_candidate_tokens(
                    resolved_excluded_tokens,
                    plan_type,
                    source_type,
                    plan_types,
                )
                if tokens:
                    access_token = tokens[self._index % len(tokens)]
                    self._index += 1
                    self._image_inflight[access_token] = int(self._image_inflight.get(access_token, 0)) + 1
                    return access_token
                self._image_slot_condition.wait(
                    timeout=min(1.0, remaining) if remaining is not None else 1.0
                )
            # The wait can outlive the account snapshot TTL. Refresh outside the
            # account lock before considering another candidate so a remote delete
            # or disable cannot be leased from the stale in-memory view.
            self._refresh_accounts_snapshot_if_stale(wait_for_refresh=True)

    def _no_ready_candidate_error(
            self,
            plan_type: str | None,
            source_type: str | None,
            plan_types: set[str] | tuple[str, ...] | None,
            excluded_tokens: set[str] | None,
    ) -> "ImageAccountSelectionError":
        """没有任何 ready 候选时区分两种成因。

        这是“初筛阶段”的判据：只看本地缓存状态，此时还没走远程预检，
        不存在“预检失败”这一维度。匹配账号全部为“限流”（限流只由远程确认写入）
        -> 额度耗尽（429）；否则一律归为可重试的 unavailable（503）。

        注意：get_available_access_token 里的 429 判据更严
        （额外要求 not saw_unavailable_failure），因为那是“预检阶段”，
        会有上游波动等可重试失败混入，不能仅凭限流就下终结性结论。
        """
        excluded = set(excluded_tokens or set())
        matched = 0
        limited = 0
        for item in self._accounts.values():
            token = item.get("access_token") or ""
            if not token or token in excluded:
                continue
            if not (
                self._account_matches_plan_type(item, plan_type)
                and self._account_matches_any_plan_type(item, plan_types)
                and self._account_matches_source_type(item, source_type)
            ):
                continue
            matched += 1
            if str(item.get("status") or "") == "限流":
                limited += 1
        if matched > 0 and limited == matched:
            return ImageAccountSelectionError(
                "quota_exhausted",
                "all matched image accounts are remote-confirmed quota exhausted",
            )
        return ImageAccountSelectionError(
            "unavailable",
            "no image account is ready for current model/status filters",
        )

    def release_image_slot(self, access_token: str) -> None:
        if not access_token:
            return
        with self._image_slot_condition:
            access_token = self._resolve_access_token_locked(access_token)
            self._release_image_slot_locked(access_token)
            self._image_slot_condition.notify_all()

    def _release_image_slot_locked(self, access_token: str) -> None:
        current_inflight = int(self._image_inflight.get(access_token, 0))
        if current_inflight <= 1:
            self._image_inflight.pop(access_token, None)
        else:
            self._image_inflight[access_token] = current_inflight - 1

    def get_available_access_token(
            self,
            plan_type: str | None = None,
            source_type: str | None = None,
            plan_types: set[str] | tuple[str, ...] | None = None,
            excluded_tokens: set[str] | None = None,
            deadline_monotonic: float | None = None,
    ) -> str:
        """从候选池中获取一个可用的图片生图 token。

        基于本地缓存做初筛，然后通过 fetch_remote_info 做远程验证（token 有效性、配额等）。
        限制最大尝试次数防止 token rotation 导致无限循环。
        """
        self._refresh_accounts_snapshot_if_stale()
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise ImageAccountSelectionError(
                "deadline_exceeded",
                "image request deadline exceeded before account selection",
            )
        max_attempts = 20  # 防止无限循环
        externally_excluded = set(excluded_tokens or set())
        attempted_tokens: set[str] = set()
        # 控制流只保留两个出口，但最终是否能说“额度耗尽”必须谨慎：
        # 只要出现过非额度类失败，就说明不能断言全部账号都耗尽，应返回可重试的 unavailable。
        saw_remote_quota_exhausted = False
        saw_unavailable_failure = False
        for _attempt in range(max_attempts):
            try:
                access_token = self._acquire_next_candidate_token(
                    excluded_tokens=externally_excluded | attempted_tokens,
                    plan_type=plan_type,
                    source_type=source_type,
                    plan_types=plan_types,
                    deadline_monotonic=deadline_monotonic,
                )
            except ImageAccountSelectionError as exc:
                if exc.kind == "deadline_exceeded":
                    raise
                if attempted_tokens:
                    break
                raise
            attempted_tokens.add(access_token)
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                self.release_image_slot(access_token)
                raise ImageAccountSelectionError(
                    "deadline_exceeded",
                    "image request deadline exceeded before remote account validation",
                )
            try:
                account = self.fetch_remote_info(
                    access_token,
                    "get_available_access_token",
                    image_scope=True,
                )
            except Exception:
                # 预检失败（上游波动/网络/401 等）：这个号这次不可用，换下一个。
                # 401 已在 fetch_remote_info 内部走异常处理，这里不再二次分类。
                saw_unavailable_failure = True
                self.release_image_slot(access_token)
                if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                    raise ImageAccountSelectionError(
                        "deadline_exceeded",
                        "image request deadline exceeded during remote account validation",
                    )
                continue
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                self.release_image_slot(access_token)
                raise ImageAccountSelectionError(
                    "deadline_exceeded",
                    "image request deadline exceeded during remote account validation",
                )
            # fetch_remote_info 内部可能因 token rotation 导致 access_token 变化，
            # 把新 token 也加入排除列表，防止重复尝试
            resolved = str((account or {}).get("access_token") or "")
            if resolved and resolved != access_token:
                attempted_tokens.add(resolved)
            if (
                    self._is_image_account_available(account or {})
                    and self._account_matches_plan_type(account or {}, plan_type)
                    and self._account_matches_any_plan_type(account or {}, plan_types)
                    and self._account_matches_source_type(account or {}, source_type)
            ):
                return str((account or {}).get("access_token") or access_token)
            if str((account or {}).get("status") or "") == "限流":
                saw_remote_quota_exhausted = True
            else:
                saw_unavailable_failure = True
            self.release_image_slot(access_token)
        if saw_remote_quota_exhausted and not saw_unavailable_failure:
            raise ImageAccountSelectionError(
                "quota_exhausted",
                f"all usable image accounts remote-confirmed quota exhausted after {len(attempted_tokens)} attempts",
            )
        raise ImageAccountSelectionError(
            "unavailable",
            f"no image account available after {len(attempted_tokens)} attempts",
        )

    def get_text_access_token(self, excluded_tokens: set[str] | None = None) -> str:
        self._refresh_accounts_snapshot_if_stale()
        attempted = set(excluded_tokens or set())
        while True:
            with self._lock:
                candidates = [
                    token
                    for account in self._accounts.values()
                    if self._is_account_selectable(
                        account,
                        allow_limited=True,
                        allow_image_pending=True,
                    )
                       and (token := account.get("access_token") or "")
                       and token not in attempted
                ]
                if not candidates:
                    return ""
                access_token = candidates[self._index % len(candidates)]
                self._index += 1
            attempted.add(access_token)
            try:
                return self.ensure_access_token(access_token, event="get_text_access_token")
            except (TerminalRefreshTokenError, RefreshCredentialsChangedError):
                continue

    def mark_text_used(self, access_token: str) -> None:
        if not access_token:
            return
        with self._lock:
            access_token = self._resolve_access_token_locked(access_token)
            current = self._accounts.get(access_token)
            if current is None:
                return
            next_item = dict(current)
            next_item["last_used_at"] = self._now()
            account = self._normalize_account(next_item)
            if account is None:
                return
            self._accounts[access_token] = account
            self._save_accounts()

    def remove_invalid_token(
        self,
        access_token: str,
        event: str,
        quiet: bool = False,
        remove: bool | None = None,
        error: str | None = None,
    ) -> bool:
        return self.handle_invalid_token(
            access_token,
            event,
            error=error,
            quiet=quiet,
            remove=remove,
            expected_access_token=access_token,
        )

    def handle_invalid_token(
        self,
        access_token: str,
        event: str,
        error: str | None = None,
        quiet: bool = False,
        remove: bool | None = None,
        expected_access_token: str | None = None,
        expected_refresh_token: str | None = None,
        expected_remote_check_marker: _RemoteCheckMarker | None = None,
        token_refresh_error: str | None = None,
        refresh_token_terminal: bool = False,
    ) -> bool:
        """统一处理鉴权异常账号。

        口径固定为：先记录异常，再按“自动移除异常账号”配置删除或保留异常状态。
        """
        should_remove = config.auto_remove_invalid_accounts if remove is None else remove
        return self._apply_invalid_token_state(
            access_token,
            event,
            str(error or "invalid access token"),
            remove=bool(should_remove),
            expected_access_token=expected_access_token,
            expected_refresh_token=expected_refresh_token,
            expected_remote_check_marker=expected_remote_check_marker,
            token_refresh_error=token_refresh_error,
            refresh_token_terminal=refresh_token_terminal,
            quiet=quiet,
        )

    def get_account(self, access_token: str) -> dict | None:
        if not access_token:
            return None
        self._refresh_accounts_snapshot_if_stale()
        with self._lock:
            access_token = self._resolve_access_token_locked(access_token)
            account = self._accounts.get(access_token)
            return dict(account) if account else None

    def get_account_by_token_identity(self, access_token: str) -> dict | None:
        """Resolve a current account from either its current or a rotated access token."""
        token = str(access_token or "").strip()
        if not token:
            return None
        self._refresh_accounts_snapshot_if_stale()
        with self._lock:
            resolved = self._resolve_access_token_locked(token)
            account = self._accounts.get(resolved)
            if account is not None:
                return dict(account)

            fingerprint = self._access_token_fingerprint(token)
            for candidate in self._accounts.values():
                fingerprints = candidate.get("access_token_fingerprints")
                if isinstance(fingerprints, list) and fingerprint in fingerprints:
                    return dict(candidate)
        return None

    def get_account_by_id(self, account_id: str) -> dict | None:
        management_id = str(account_id or "").strip().lower()
        if not management_id:
            return None
        self._refresh_accounts_snapshot_if_stale()
        with self._lock:
            for account in self._accounts.values():
                if str(account.get("management_id") or "").strip().lower() == management_id:
                    result = dict(account)
                    access_token = str(result.get("access_token") or "").strip()
                    result["image_inflight"] = int(self._image_inflight.get(access_token, 0))
                    return result
        return None

    def resolve_account_ids(self, account_ids: list[str]) -> tuple[list[str], list[str]]:
        requested = list(dict.fromkeys(str(item or "").strip().lower() for item in account_ids if str(item or "").strip()))
        if not requested:
            return [], []
        self._refresh_accounts_snapshot_if_stale()
        with self._lock:
            token_by_id = {
                str(account.get("management_id") or "").strip().lower(): str(account.get("access_token") or "").strip()
                for account in self._accounts.values()
                if str(account.get("management_id") or "").strip()
                and str(account.get("access_token") or "").strip()
            }
        tokens = [token_by_id[item] for item in requested if item in token_by_id]
        missing = [item for item in requested if item not in token_by_id]
        return tokens, missing

    @classmethod
    def is_image_account_available(cls, account: dict) -> bool:
        return cls._is_image_account_available(account)

    @classmethod
    def is_unlimited_image_quota_account(cls, account: dict) -> bool:
        return cls._is_unlimited_image_quota_account(account)

    def list_accounts(self) -> list[dict]:
        """返回所有账号的副本，并为每个账号附加当前图片在途数 image_inflight。

        image_inflight 为内存态并发计数(账号正在生成、尚未结束的图片数)。号池空闲时
        若某账号该值持续 > 0，说明其并发槽位泄漏、已被静默排除出调度，可借此在 UI 上诊断。
        """
        self._refresh_accounts_snapshot_if_stale()
        with self._lock:
            result = []
            for item in self._accounts.values():
                account = dict(item)
                token = account.get("access_token") or ""
                account["image_inflight"] = int(self._image_inflight.get(token, 0))
                result.append(account)
            return result

    def list_limited_tokens(self) -> list[str]:
        self._refresh_accounts_snapshot_if_stale()
        with self._lock:
            return [
                token
                for item in self._accounts.values()
                if item.get("status") == "限流"
                   and item.get("last_remote_check_result") != "pending"
                   and (token := item.get("access_token") or "")
            ]

    def list_pending_auth_verification_tokens(self) -> list[str]:
        self._refresh_accounts_snapshot_if_stale()
        with self._lock:
            return [
                token
                for item in self._accounts.values()
                if item.get("last_remote_check_result") == "pending"
                and item.get("pending_auth_scope") == "image"
                and (token := str(item.get("access_token") or "").strip())
            ]

    def resume_pending_auth_verifications(self) -> int:
        tokens = self.list_pending_auth_verification_tokens()
        scheduled = 0
        for token in tokens:
            if self._schedule_account_refresh_after_image_failure(token):
                scheduled += 1
        return scheduled

    def _auto_remove_tokens_locked(
        self,
        *,
        remove_invalid: bool,
        remove_rate_limited: bool,
    ) -> tuple[list[str], list[str]]:
        invalid_tokens = [
            token
            for item in self._accounts.values()
            if remove_invalid
               and item.get("status") == "异常"
               and (token := item.get("access_token") or "")
        ]
        rate_limited_tokens = [
            token
            for item in self._accounts.values()
            if remove_rate_limited
               and item.get("status") == "限流"
               and (token := item.get("access_token") or "")
        ]
        return invalid_tokens, rate_limited_tokens

    def preview_auto_remove_accounts(
        self,
        *,
        remove_invalid: bool | None = None,
        remove_rate_limited: bool | None = None,
    ) -> dict[str, Any]:
        self._refresh_accounts_snapshot_if_stale()
        remove_invalid = config.auto_remove_invalid_accounts if remove_invalid is None else bool(remove_invalid)
        remove_rate_limited = (
            config.auto_remove_rate_limited_accounts
            if remove_rate_limited is None
            else bool(remove_rate_limited)
        )
        with self._lock:
            invalid_tokens, rate_limited_tokens = self._auto_remove_tokens_locked(
                remove_invalid=remove_invalid,
                remove_rate_limited=remove_rate_limited,
            )
        invalid = len(invalid_tokens)
        rate_limited = len(rate_limited_tokens)
        return {
            "dry_run": True,
            "invalid": invalid,
            "rate_limited": rate_limited,
            "total_removed": invalid + rate_limited,
            "auto_remove_invalid_accounts": remove_invalid,
            "auto_remove_rate_limited_accounts": remove_rate_limited,
        }

    def cleanup_auto_remove_accounts(
        self,
        *,
        remove_invalid: bool | None = None,
        remove_rate_limited: bool | None = None,
    ) -> dict[str, Any]:
        self._refresh_accounts_snapshot_if_stale()
        remove_invalid = config.auto_remove_invalid_accounts if remove_invalid is None else bool(remove_invalid)
        remove_rate_limited = (
            config.auto_remove_rate_limited_accounts
            if remove_rate_limited is None
            else bool(remove_rate_limited)
        )
        with self._lock:
            invalid_tokens, rate_limited_tokens = self._auto_remove_tokens_locked(
                remove_invalid=remove_invalid,
                remove_rate_limited=remove_rate_limited,
            )

        target_tokens = list(dict.fromkeys([*invalid_tokens, *rate_limited_tokens]))
        result = self.delete_accounts(target_tokens, return_items=False) if target_tokens else {"removed": 0}
        removed = int(result.get("removed") or 0)
        if removed:
            log_service.add(
                LOG_TYPE_ACCOUNT,
                "按账号自动移除策略清理账号",
                {
                    "removed": removed,
                    "invalid": len(invalid_tokens),
                    "rate_limited": len(rate_limited_tokens),
                },
            )
        return {
            "dry_run": False,
            "invalid": len(invalid_tokens),
            "rate_limited": len(rate_limited_tokens),
            "total_removed": removed,
            "auto_remove_invalid_accounts": remove_invalid,
            "auto_remove_rate_limited_accounts": remove_rate_limited,
        }

    def list_normal_tokens(self) -> list[str]:
        self._refresh_accounts_snapshot_if_stale()
        with self._lock:
            return [
                token
                for item in self._accounts.values()
                if item.get("status") == "正常"
                   and item.get("last_remote_check_result") != "pending"
                   and (token := item.get("access_token") or "")
            ]

    @classmethod
    def _pool_health_freshness_seconds(cls, freshness_seconds: int | float | None = None) -> int:
        if freshness_seconds is not None:
            try:
                return max(60, int(float(freshness_seconds)))
            except (TypeError, ValueError):
                pass
        return max(60, int(config.refresh_account_interval_minute) * 60)

    @classmethod
    def _remote_check_is_fresh(cls, account: dict, now: datetime, freshness_seconds: int) -> bool:
        checked_at = cls._parse_time(account.get("last_remote_checked_at"))
        return checked_at is not None and (now - checked_at).total_seconds() <= freshness_seconds

    @classmethod
    def _remote_check_attempt_is_recent(cls, account: dict, now: datetime, freshness_seconds: int) -> bool:
        attempted_at = cls._parse_time(account.get("last_remote_check_attempt_at"))
        return attempted_at is not None and (now - attempted_at).total_seconds() <= freshness_seconds

    @classmethod
    def _pool_health_metrics_from_accounts(
        cls,
        accounts: list[dict],
        *,
        now: datetime,
        freshness_seconds: int,
    ) -> dict[str, Any]:
        local_normal = [
            item
            for item in accounts
            if cls._is_account_selectable(item, allow_limited=False)
        ]
        confirmed_normal = [
            item
            for item in local_normal
            if cls._remote_check_is_fresh(item, now, freshness_seconds)
        ]
        latest_checked_at = ""
        for item in accounts:
            checked_at = cls._parse_time(item.get("last_remote_checked_at"))
            if checked_at is None:
                continue
            value = checked_at.isoformat()
            if not latest_checked_at or value > latest_checked_at:
                latest_checked_at = value
        return {
            "current_quota": sum(
                int(item.get("quota") or 0)
                for item in confirmed_normal
                if not item.get("image_quota_unknown")
            ),
            "current_available": len(confirmed_normal),
            "estimated_quota": sum(
                int(item.get("quota") or 0)
                for item in local_normal
                if not item.get("image_quota_unknown")
            ),
            "estimated_available": len(local_normal),
            "unconfirmed_available": max(0, len(local_normal) - len(confirmed_normal)),
            "unknown_quota_count": sum(1 for item in confirmed_normal if item.get("image_quota_unknown")),
            "pool_freshness_seconds": freshness_seconds,
            "pool_last_checked_at": latest_checked_at,
        }

    @classmethod
    def _pool_health_stale_tokens(
        cls,
        accounts: list[dict],
        *,
        now: datetime,
        freshness_seconds: int,
    ) -> list[str]:
        stale: list[tuple[float, str]] = []
        for item in accounts:
            token = str(item.get("access_token") or "").strip()
            if not token or item.get("status") != "正常":
                continue
            if cls._remote_check_is_fresh(item, now, freshness_seconds):
                continue
            if cls._remote_check_attempt_is_recent(item, now, freshness_seconds):
                continue
            checked_at = cls._parse_time(item.get("last_remote_checked_at"))
            sort_key = checked_at.timestamp() if checked_at else 0.0
            stale.append((sort_key, token))
        stale.sort(key=lambda item: item[0])
        return [token for _, token in stale]

    @staticmethod
    def _pool_health_target_reached(
        metrics: dict[str, Any],
        *,
        target_quota: int | None = None,
        target_available: int | None = None,
    ) -> bool:
        if target_quota is not None and int(metrics.get("current_quota") or 0) >= max(1, int(target_quota)):
            return True
        if target_available is not None and int(metrics.get("current_available") or 0) >= max(1, int(target_available)):
            return True
        return False

    def evaluate_account_pool(
        self,
        *,
        refresh_stale: bool = False,
        target_quota: int | None = None,
        target_available: int | None = None,
        freshness_seconds: int | float | None = None,
    ) -> dict[str, Any]:
        """Return registration-facing account pool metrics from remotely confirmed data.

        Local quota is useful for display, but registration stop decisions should not
        trust stale local quota.  This method refreshes only stale normal accounts,
        in small batches, until the requested target is confirmed or no eligible
        stale accounts remain.
        """
        freshness = self._pool_health_freshness_seconds(freshness_seconds)
        refreshed = 0
        refresh_errors: list[dict[str, Any]] = []

        while True:
            now = datetime.now(timezone.utc)
            accounts = self.list_accounts()
            metrics = self._pool_health_metrics_from_accounts(
                accounts,
                now=now,
                freshness_seconds=freshness,
            )
            if not refresh_stale:
                return {
                    **metrics,
                    "pool_refreshed": refreshed,
                    "pool_refresh_errors": refresh_errors,
                }
            if self._pool_health_target_reached(
                metrics,
                target_quota=target_quota,
                target_available=target_available,
            ):
                return {
                    **metrics,
                    "pool_refreshed": refreshed,
                    "pool_refresh_errors": refresh_errors,
                }

            stale_tokens = self._pool_health_stale_tokens(
                accounts,
                now=now,
                freshness_seconds=freshness,
            )
            if not stale_tokens:
                return {
                    **metrics,
                    "pool_refreshed": refreshed,
                    "pool_refresh_errors": refresh_errors,
                }

            batch = stale_tokens[: self._POOL_HEALTH_REFRESH_BATCH_SIZE]
            result = self.sync_accounts_and_quota(batch)
            refreshed += int(result.get("synced") or 0)
            refresh_errors.extend(result.get("errors") or [])

    @staticmethod
    def _account_payload_token(item: dict) -> str:
        return str(item.get("access_token") or item.get("accessToken") or "").strip()

    @staticmethod
    def _refresh_token_aware_updates(
        current: dict[str, Any],
        updates: dict[str, Any],
        *,
        preserve_lifecycle: bool = False,
    ) -> dict[str, Any]:
        normalized = dict(updates)
        if "refresh_token" not in normalized:
            return normalized
        current_refresh_token = str(current.get("refresh_token") or "").strip()
        updated_refresh_token = str(normalized.get("refresh_token") or "").strip()
        if preserve_lifecycle and "refresh_token_invalid_at" in normalized:
            normalized["refresh_token_invalid_at"] = (
                normalized.get("refresh_token_invalid_at") or None
            )
        else:
            normalized["refresh_token_invalid_at"] = (
                None
                if updated_refresh_token != current_refresh_token
                else current.get("refresh_token_invalid_at") or None
            )
        return normalized

    @staticmethod
    def _prepare_account_payload(item: dict, *, restore: bool = False) -> dict | None:
        if not isinstance(item, dict):
            return None
        access_token = AccountService._account_payload_token(item)
        if not access_token:
            return None
        payload = dict(item)
        payload.pop("accessToken", None)
        if not restore:
            payload.pop("management_id", None)
            payload.pop("access_token_fingerprints", None)
        payload["access_token"] = access_token
        # CPA/Codex 导出文件里的 `type=codex` 是导出格式，不是号池套餐类型。
        if str(payload.get("type") or "").strip().lower() == "codex":
            payload["export_type"] = "codex"
            payload["source_type"] = "codex"
            payload.pop("type", None)
        if str(payload.get("export_type") or "").strip().lower() == "codex":
            payload["source_type"] = "codex"
        if payload.get("plan_type") and not payload.get("type"):
            payload["type"] = str(payload.get("plan_type") or "").strip()
        return payload

    def _run_proxy_assignment_mutation(
        self,
        references: list[tuple[object, object]],
        mutation: Callable[[list[str]], Any],
    ) -> Any:
        if self._proxy_reference_mutation is not None:
            return self._proxy_reference_mutation(references, mutation)

        normalized: list[str] = []
        for value, legacy_group_id in references:
            raw = str(value or "").strip()
            if not raw and str(legacy_group_id or "").strip():
                raw = f"group:{str(legacy_group_id).strip()}"
            if raw.lower() == "global":
                raw = ""
            normalized.append(raw)
        return mutation(normalized)

    def _with_normalized_proxy_updates(
        self,
        updates: dict[str, Any],
        mutation: Callable[[dict[str, Any]], Any],
    ) -> Any:
        normalized_updates = dict(updates)
        if "proxy" not in normalized_updates and "proxy_group_id" not in normalized_updates:
            return mutation(normalized_updates)

        return self._run_proxy_assignment_mutation(
            [
                (
                    normalized_updates.get("proxy"),
                    normalized_updates.get("proxy_group_id"),
                )
            ],
            lambda normalized: mutation({
                **normalized_updates,
                "proxy": normalized[0],
            }),
        )

    @account_processing_batch
    def add_account_items(
        self,
        items: list[dict],
        return_items: bool = True,
        *,
        restore: bool = False,
        return_item_results: bool = False,
    ) -> dict:
        source_items = list(items)
        payloads: list[dict] = []
        payload_indices: list[int] = []
        for index, item in enumerate(source_items):
            payload = self._prepare_account_payload(item, restore=restore)
            if payload is None:
                continue
            payloads.append(payload)
            payload_indices.append(index)

        result = self._add_account_payloads(
            payloads,
            return_items=return_items,
            preserve_lifecycle=restore,
            return_item_results=return_item_results,
        )
        if return_item_results:
            aligned_results = ["invalid"] * len(source_items)
            for index, status in zip(
                payload_indices,
                result.get("item_results") or [],
            ):
                aligned_results[index] = status
            result["item_results"] = aligned_results
        return result

    @account_processing_batch
    def add_accounts(self, tokens: list[str], source_type: str = "web", return_items: bool = True) -> dict:
        tokens = list(dict.fromkeys(token for token in tokens if token))
        if not tokens:
            return {"added": 0, "skipped": 0, "items": self.list_accounts() if return_items else []}
        return self._add_account_payloads([
            {"access_token": token, "source_type": self._normalize_source_type(source_type)}
            for token in tokens
        ], return_items=return_items)

    def _add_account_payloads(
        self,
        payloads: list[dict],
        return_items: bool = True,
        *,
        preserve_lifecycle: bool = False,
        return_item_results: bool = False,
    ) -> dict:
        proxy_payload_indices = [
            index
            for index, payload in enumerate(payloads)
            if (
                isinstance(payload, dict)
                and self._account_payload_token(payload)
                and ("proxy" in payload or "proxy_group_id" in payload)
            )
        ]
        if not proxy_payload_indices:
            return self._add_account_payloads_impl(
                payloads,
                return_items=return_items,
                preserve_lifecycle=preserve_lifecycle,
                return_item_results=return_item_results,
            )

        references = [
            (
                payloads[index].get("proxy"),
                payloads[index].get("proxy_group_id"),
            )
            for index in proxy_payload_indices
        ]

        def persist(normalized_references: list[str]) -> dict:
            normalized_payloads = list(payloads)
            for index, proxy in zip(proxy_payload_indices, normalized_references):
                normalized_payloads[index] = {
                    **payloads[index],
                    "proxy": proxy,
                }
            return self._add_account_payloads_impl(
                normalized_payloads,
                return_items=return_items,
                preserve_lifecycle=preserve_lifecycle,
                return_item_results=return_item_results,
            )

        return self._run_proxy_assignment_mutation(references, persist)

    def _add_account_payloads_impl(
        self,
        payloads: list[dict],
        return_items: bool = True,
        *,
        preserve_lifecycle: bool = False,
        return_item_results: bool = False,
    ) -> dict:
        deduped: dict[str, dict] = {}
        input_tokens: list[str] = []
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            access_token = self._account_payload_token(payload)
            if not access_token:
                continue
            input_tokens.append(access_token)
            current = deduped.get(access_token, {})
            deduped[access_token] = {**current, **payload, "access_token": access_token}

        if not deduped:
            result = {
                "added": 0,
                "skipped": 0,
                "items": self.list_accounts() if return_items else [],
            }
            if return_item_results:
                result["item_results"] = []
            return result

        with self._lock:
            added = 0
            skipped = len(input_tokens) - len(deduped)
            outcomes_by_token: dict[str, str] = {}
            management_id_owners = {
                str(account.get("management_id") or "").strip().lower(): token
                for token, account in self._accounts.items()
                if str(account.get("management_id") or "").strip()
            }
            token_fingerprint_owners = {
                fingerprint: token
                for token, account in self._accounts.items()
                for fingerprint in self._normalize_access_token_fingerprints(
                    account.get("access_token_fingerprints"),
                    token,
                )
            }
            for access_token, payload in deduped.items():
                resolved_token = self._resolve_access_token_locked(access_token)
                if resolved_token != access_token and resolved_token in self._accounts:
                    # Re-importing a rotated token must not recreate its former account.
                    skipped += 1
                    outcomes_by_token[access_token] = "skipped"
                    continue
                current = self._accounts.get(access_token)
                if current is None:
                    fingerprint = self._access_token_fingerprint(access_token)
                    if fingerprint in token_fingerprint_owners:
                        # Persisted fingerprints preserve rotation lineage across restarts
                        # without storing former access tokens.
                        skipped += 1
                        outcomes_by_token[access_token] = "skipped"
                        continue
                    added += 1
                    outcomes_by_token[access_token] = "added"
                    current = {"created_at": self._now()}
                else:
                    skipped += 1
                    outcomes_by_token[access_token] = "skipped"
                incoming = self._refresh_token_aware_updates(
                    current,
                    payload,
                    preserve_lifecycle=preserve_lifecycle,
                )
                if not incoming.get("created_at"):
                    incoming.pop("created_at", None)
                merged = {**current, **incoming, "access_token": access_token}
                incoming_type = self._normalize_account_type(incoming.get("type"))
                current_type = self._normalize_account_type(current.get("type"))
                merged["type"] = incoming_type or current_type
                account = self._normalize_account(merged)
                if account is not None:
                    previous_management_id = str(
                        current.get("management_id") or ""
                    ).strip().lower()
                    used_management_ids = {
                        management_id
                        for management_id, owner in management_id_owners.items()
                        if owner != access_token
                    }
                    account["management_id"] = self._unique_management_id(
                        access_token,
                        account.get("management_id"),
                        used_management_ids,
                    )
                    self._accounts[access_token] = account
                    if (
                        previous_management_id
                        and previous_management_id != account["management_id"]
                        and management_id_owners.get(previous_management_id) == access_token
                    ):
                        management_id_owners.pop(previous_management_id, None)
                    management_id_owners[account["management_id"]] = access_token
                    for fingerprint in account["access_token_fingerprints"]:
                        token_fingerprint_owners[fingerprint] = access_token
            conflict_existing_tokens: set[str] = set()
            self._save_accounts(
                conflict_existing_tokens=conflict_existing_tokens,
            )
            for access_token in conflict_existing_tokens:
                if outcomes_by_token.get(access_token) != "added":
                    continue
                outcomes_by_token[access_token] = "skipped"
                added = max(0, added - 1)
                skipped += 1
            if added:
                self._cumulative_total += added
                self._save_cumulative_total()
            items = [dict(item) for item in self._accounts.values()] if return_items else []
            log_service.add(LOG_TYPE_ACCOUNT, f"新增 {added} 个账号，跳过 {skipped} 个",
                            {"added": added, "skipped": skipped})
        result = {"added": added, "skipped": skipped, "items": items}
        if return_item_results:
            seen_tokens: set[str] = set()
            item_results: list[str] = []
            for access_token in input_tokens:
                if access_token in seen_tokens:
                    item_results.append("skipped")
                    continue
                seen_tokens.add(access_token)
                item_results.append(outcomes_by_token.get(access_token, "skipped"))
            result["item_results"] = item_results
        return result

    @staticmethod
    def _report_account_mutation_progress(
        callback: Callable[[str, int], None] | None,
        stage: str,
        total: int,
    ) -> None:
        if callback is None:
            return
        try:
            callback(stage, max(0, int(total)))
        except Exception:
            # Progress reporting is auxiliary and must not change a committed mutation.
            pass

    @staticmethod
    def _add_account_log_best_effort(message: str, data: dict[str, Any]) -> None:
        try:
            log_service.add(LOG_TYPE_ACCOUNT, message, data)
        except Exception:
            # The account store is authoritative; diagnostics must not reverse its outcome.
            pass

    @account_processing_batch
    def delete_accounts(
        self,
        tokens: list[str],
        return_items: bool = True,
        *,
        progress_callback: Callable[[str, int], None] | None = None,
    ) -> dict:
        requested_tokens = list(dict.fromkeys(token for token in tokens if token))
        if not requested_tokens:
            return {
                "removed": 0,
                "removed_ids": [],
                "missing_tokens": [],
                "items": self.list_accounts() if return_items else [],
            }
        self._report_account_mutation_progress(
            progress_callback,
            "prepare_accounts",
            len(requested_tokens),
        )
        with self._lock:
            target_tokens: list[str] = []
            candidate_ids: list[str] = []
            missing_tokens: list[str] = []
            seen_tokens: set[str] = set()
            for requested_token in requested_tokens:
                access_token = self._resolve_access_token_locked(requested_token)
                if access_token in seen_tokens:
                    continue
                seen_tokens.add(access_token)
                account = self._accounts.get(access_token)
                if account is None:
                    missing_tokens.append(requested_token)
                    continue
                target_tokens.append(access_token)
                management_id = str(account.get("management_id") or "").strip().lower()
                if management_id:
                    candidate_ids.append(management_id)

            target_set = set(target_tokens)
            removed = sum(self._accounts.pop(token, None) is not None for token in target_tokens)
            if removed:
                self._report_account_mutation_progress(
                    progress_callback,
                    "save_accounts",
                    removed,
                )
                self._save_accounts()
                self._remove_account_runtime_state_locked(target_set)
                self._add_account_log_best_effort(
                    f"删除 {removed} 个账号",
                    {"removed": removed},
                )
            existing_ids = {
                str(account.get("management_id") or "").strip().lower()
                for account in self._accounts.values()
                if str(account.get("management_id") or "").strip()
            }
            removed_ids = [
                management_id
                for management_id in dict.fromkeys(candidate_ids)
                if management_id not in existing_ids
            ]
            items = [dict(item) for item in self._accounts.values()] if return_items else []
        self._report_account_mutation_progress(
            progress_callback,
            "publish_results",
            len(removed_ids),
        )
        return {
            "removed": len(removed_ids),
            "removed_ids": removed_ids,
            "missing_tokens": missing_tokens,
            "items": items,
        }

    def _normalized_account_update_locked(
            self,
            access_token: str,
            current: dict[str, Any],
            updates: dict[str, Any],
            *,
            preserve_disabled: bool = False,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Build one normalized account update while the account lock is held."""
        normalized_updates = self._refresh_token_aware_updates(current, updates)
        merged = {**current, **normalized_updates, "access_token": access_token}
        if (
            "proxy" in updates
            and str(current.get("proxy") or "").strip()
            != str(merged.get("proxy") or "").strip()
        ):
            self._scrub_diagnostic_secrets(merged, [current.get("proxy")])
        if preserve_disabled and current.get("status") == "禁用":
            merged["status"] = "禁用"
        if (
            current.get("status") == "限流"
            and "status" in updates
            and self._normalize_account_status(updates.get("status"), merged) == "正常"
            and "restore_at" not in updates
        ):
            merged["restore_at"] = None

        account = self._normalize_account(merged)
        if account is None:
            return None, None
        if account.get("status") == "异常" and config.auto_remove_invalid_accounts:
            return account, "自动移除异常账号"
        if account.get("status") == "限流" and config.auto_remove_rate_limited_accounts:
            return account, "自动移除额度耗尽账号"
        return account, None

    @account_processing_batch
    def update_accounts(
        self,
        access_tokens: list[str],
        updates: dict,
        *,
        quiet: bool = True,
        progress_callback: Callable[[str, int], None] | None = None,
    ) -> dict[str, Any]:
        if not updates or not any(str(token or "").strip() for token in access_tokens):
            return self._update_accounts_impl(
                access_tokens,
                updates,
                quiet=quiet,
                progress_callback=progress_callback,
            )
        return self._with_normalized_proxy_updates(
            updates,
            lambda normalized: self._update_accounts_impl(
                access_tokens,
                normalized,
                quiet=quiet,
                progress_callback=progress_callback,
            ),
        )

    def _update_accounts_impl(
        self,
        access_tokens: list[str],
        updates: dict,
        *,
        quiet: bool = True,
        progress_callback: Callable[[str, int], None] | None = None,
    ) -> dict[str, Any]:
        """Apply one update to many accounts with a single storage mutation."""
        requested_tokens = list(dict.fromkeys(
            str(token or "").strip() for token in access_tokens if str(token or "").strip()
        ))
        if not requested_tokens or not updates:
            return {
                "updated_ids": [],
                "removed_ids": [],
                "missing_tokens": requested_tokens,
            }

        self._report_account_mutation_progress(
            progress_callback,
            "prepare_accounts",
            len(requested_tokens),
        )

        with self._lock:
            requested: list[tuple[str, str]] = []
            missing_tokens: list[str] = []
            auto_remove_events: list[tuple[str, str]] = []
            seen_tokens: set[str] = set()
            changed = False

            for requested_token in requested_tokens:
                access_token = self._resolve_access_token_locked(requested_token)
                if access_token in seen_tokens:
                    continue
                seen_tokens.add(access_token)
                current = self._accounts.get(access_token)
                if current is None:
                    missing_tokens.append(requested_token)
                    continue

                management_id = str(current.get("management_id") or "").strip().lower()
                if not management_id:
                    missing_tokens.append(requested_token)
                    continue
                requested.append((access_token, management_id))

                account, auto_remove_message = self._normalized_account_update_locked(
                    access_token,
                    current,
                    updates,
                )
                if account is None:
                    missing_tokens.append(requested_token)
                    continue
                if auto_remove_message:
                    self._accounts.pop(access_token, None)
                    changed = True
                    auto_remove_events.append((access_token, auto_remove_message))
                    continue

                if account != current:
                    self._accounts[access_token] = account
                    changed = True

            if changed:
                self._report_account_mutation_progress(
                    progress_callback,
                    "save_accounts",
                    len(requested),
                )
                self._save_accounts()

            existing_ids = {
                str(account.get("management_id") or "").strip().lower()
                for account in self._accounts.values()
                if str(account.get("management_id") or "").strip()
            }
            updated_ids = [
                management_id
                for _token, management_id in requested
                if management_id in existing_ids
            ]
            removed_ids = [
                management_id
                for _token, management_id in requested
                if management_id not in existing_ids
            ]
            removed_tokens = {
                token
                for token, management_id in requested
                if management_id not in existing_ids
            }
            if removed_tokens:
                self._remove_account_runtime_state_locked(removed_tokens)

            for access_token, message in auto_remove_events:
                self._add_account_log_best_effort(
                    message,
                    {"token": anonymize_token(access_token)},
                )
            if not quiet and updated_ids:
                self._add_account_log_best_effort(
                    f"\u6279\u91cf\u66f4\u65b0 {len(updated_ids)} \u4e2a\u8d26\u53f7",
                    {"updated": len(updated_ids)},
                )

            result = {
                "updated_ids": updated_ids,
                "removed_ids": removed_ids,
                "missing_tokens": missing_tokens,
            }
        self._report_account_mutation_progress(
            progress_callback,
            "publish_results",
            len(result["updated_ids"]) + len(result["removed_ids"]),
        )
        return result

    @staticmethod
    def _remote_check_marker(
        account: dict | None,
    ) -> _RemoteCheckMarker:
        item = account or {}
        return (
            str(item.get("last_token_refresh_at") or ""),
            str(item.get("last_remote_check_result") or ""),
            str(item.get("last_remote_check_attempt_at") or ""),
            str(item.get("last_remote_check_event") or ""),
            item.get("pending_auth_remove_invalid"),
            str(item.get("pending_auth_scope") or ""),
            str(item.get("pending_auth_verification_id") or ""),
        )

    def update_account(
        self,
        access_token: str,
        updates: dict,
        quiet: bool = False,
        *,
        expected_access_token: str | None = None,
        expected_refresh_token: str | None = None,
        expected_remote_check_marker: _RemoteCheckMarker | None = None,
        preserve_disabled: bool = False,
    ) -> dict | None:
        if not access_token:
            return None
        return self._with_normalized_proxy_updates(
            updates,
            lambda normalized: self._update_account_impl(
                access_token,
                normalized,
                quiet,
                expected_access_token=expected_access_token,
                expected_refresh_token=expected_refresh_token,
                expected_remote_check_marker=expected_remote_check_marker,
                preserve_disabled=preserve_disabled,
            ),
        )

    def _update_account_impl(
        self,
        access_token: str,
        updates: dict,
        quiet: bool = False,
        *,
        expected_access_token: str | None = None,
        expected_refresh_token: str | None = None,
        expected_remote_check_marker: _RemoteCheckMarker | None = None,
        preserve_disabled: bool = False,
    ) -> dict | None:
        with self._lock:
            access_token = self._resolve_access_token_locked(access_token)
            current = self._accounts.get(access_token)
            if current is None:
                return None
            if expected_access_token is not None and (
                access_token != str(expected_access_token or "").strip()
            ):
                return None
            if expected_refresh_token is not None and (
                str(current.get("refresh_token") or "").strip()
                != str(expected_refresh_token or "").strip()
            ):
                return None
            if (
                expected_remote_check_marker is not None
                and self._remote_check_marker(current) != expected_remote_check_marker
            ):
                return None
            expected_generation = None
            if expected_access_token is not None and expected_refresh_token is not None:
                expected_generation = (
                    str(expected_access_token or "").strip(),
                    str(expected_refresh_token or "").strip(),
                    (
                        expected_remote_check_marker[0]
                        if expected_remote_check_marker is not None
                        else str(current.get("last_token_refresh_at") or "").strip()
                    ),
                )
            account, auto_remove_message = self._normalized_account_update_locked(
                access_token,
                current,
                updates,
                preserve_disabled=preserve_disabled,
            )
            if account is None:
                return None
            if auto_remove_message:
                self._accounts.pop(access_token, None)
                saved = self._save_accounts(
                    expected_credential_generation=expected_generation,
                )
                if not saved:
                    return None
                self._remove_account_runtime_state_locked({access_token})
                log_service.add(
                    LOG_TYPE_ACCOUNT,
                    auto_remove_message,
                    {"token": anonymize_token(access_token)},
                )
                return None
            self._accounts[access_token] = account
            saved = self._save_accounts(
                expected_credential_generation=expected_generation,
            )
            if not saved:
                return None
            access_token = self._resolve_access_token_locked(access_token)
            persisted = self._accounts.get(access_token)
            if persisted is None:
                return None
            if not quiet:
                log_service.add(LOG_TYPE_ACCOUNT, "更新账号",
                                {"token": anonymize_token(access_token), "status": persisted.get("status")})
            return dict(persisted)
        return None

    def _record_refresh_success(
        self,
        access_token: str,
        updates: dict,
        event: str = "fetch_remote_info",
        *,
        expected_access_token: str,
        expected_refresh_token: str,
        expected_remote_check_marker: _RemoteCheckMarker,
    ) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        return self.update_account(
            access_token,
            {
                **updates,
                "invalid_count": 0,
                "last_invalid_at": None,
                "last_refresh_error": None,
                "last_refresh_error_at": None,
                "last_remote_checked_at": now,
                "last_remote_check_attempt_at": now,
                "last_remote_check_error": None,
                "last_remote_check_error_at": None,
                "last_remote_check_event": event,
                "last_remote_check_result": "ok",
                "pending_auth_remove_invalid": None,
                "pending_auth_scope": None,
            },
            quiet=True,
            expected_access_token=expected_access_token,
            expected_refresh_token=expected_refresh_token,
            expected_remote_check_marker=expected_remote_check_marker,
            preserve_disabled=True,
        )

    def _record_remote_check_error(
        self,
        access_token: str,
        event: str,
        error: str,
        *,
        expected_access_token: str | None = None,
        expected_refresh_token: str | None = None,
        expected_remote_check_marker: _RemoteCheckMarker | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            access_token = self._resolve_access_token_locked(access_token)
            current = self._accounts.get(access_token)
            if current is None:
                return False
            if expected_access_token is not None and (
                access_token != str(expected_access_token or "").strip()
            ):
                return False
            if expected_refresh_token is not None and (
                str(current.get("refresh_token") or "").strip()
                != str(expected_refresh_token or "").strip()
            ):
                return False
            if (
                expected_remote_check_marker is not None
                and self._remote_check_marker(current) != expected_remote_check_marker
            ):
                return False
            expected_generation = None
            if expected_access_token is not None and expected_refresh_token is not None:
                expected_generation = (
                    str(expected_access_token or "").strip(),
                    str(expected_refresh_token or "").strip(),
                    (
                        expected_remote_check_marker[0]
                        if expected_remote_check_marker is not None
                        else str(current.get("last_token_refresh_at") or "").strip()
                    ),
                )
            next_item = dict(current)
            next_item["last_remote_check_attempt_at"] = now
            next_item["last_remote_check_error"] = str(error or "remote check failed")
            next_item["last_remote_check_error_at"] = now
            next_item["last_remote_check_event"] = event
            current_result = str(current.get("last_remote_check_result") or "")
            next_item["last_remote_check_result"] = (
                "invalid" if current_result == "invalid" else "error"
            )
            next_item["pending_auth_remove_invalid"] = None
            next_item["pending_auth_scope"] = None
            account = self._normalize_account(next_item)
            if account is not None:
                self._accounts[access_token] = account
                saved = self._save_accounts(
                    expected_credential_generation=expected_generation,
                )
                if not saved:
                    return False
                access_token = self._resolve_access_token_locked(access_token)
                persisted = self._accounts.get(access_token)
                return bool(
                    persisted is not None
                    and persisted.get("last_remote_check_error_at") == now
                )
        return False

    def _apply_invalid_token_state(
        self,
        access_token: str,
        event: str,
        error: str,
        *,
        remove: bool,
        expected_access_token: str | None = None,
        expected_refresh_token: str | None = None,
        expected_remote_check_marker: _RemoteCheckMarker | None = None,
        token_refresh_error: str | None = None,
        refresh_token_terminal: bool = False,
        quiet: bool = False,
    ) -> bool:
        _ = quiet
        now = datetime.now(timezone.utc)
        with self._lock:
            access_token = self._resolve_access_token_locked(access_token)
            current = self._accounts.get(access_token)
            if current is None:
                return False
            if expected_access_token is not None and (
                access_token != str(expected_access_token or "").strip()
            ):
                return False
            if expected_refresh_token is not None and (
                str(current.get("refresh_token") or "").strip()
                != str(expected_refresh_token or "").strip()
            ):
                return False
            if (
                expected_remote_check_marker is not None
                and self._remote_check_marker(current) != expected_remote_check_marker
            ):
                return False
            expected_generation = None
            if expected_access_token is not None and expected_refresh_token is not None:
                expected_generation = (
                    str(expected_access_token or "").strip(),
                    str(expected_refresh_token or "").strip(),
                    (
                        expected_remote_check_marker[0]
                        if expected_remote_check_marker is not None
                        else str(current.get("last_token_refresh_at") or "").strip()
                    ),
                )

            terminal_already_recorded = bool(
                refresh_token_terminal
                and token_refresh_error
                and current.get("refresh_token_invalid_at")
                and current.get("status") in {"异常", "禁用"}
                and current.get("last_remote_check_result") == "invalid"
                and str(current.get("last_token_refresh_error") or "")
                == str(token_refresh_error)
            )
            if terminal_already_recorded:
                account = dict(current)
                if not (remove and account.get("status") == "异常"):
                    return False
            else:
                next_item = dict(current)
                next_item["status"] = "禁用" if current.get("status") == "禁用" else "异常"
                next_item["quota"] = 0
                next_item["image_quota_unknown"] = True
                next_item["invalid_count"] = int(next_item.get("invalid_count") or 0) + 1
                next_item["last_invalid_at"] = now.isoformat()
                next_item["last_refresh_error"] = str(error or "invalid access token")
                next_item["last_refresh_error_at"] = now.isoformat()
                next_item["last_remote_checked_at"] = now.isoformat()
                next_item["last_remote_check_attempt_at"] = now.isoformat()
                next_item["last_remote_check_error"] = str(error or "invalid access token")
                next_item["last_remote_check_error_at"] = now.isoformat()
                next_item["last_remote_check_event"] = event
                next_item["last_remote_check_result"] = "invalid"
                next_item["pending_auth_remove_invalid"] = None
                next_item["pending_auth_scope"] = None
                if refresh_token_terminal and token_refresh_error:
                    next_item["last_token_refresh_error"] = str(token_refresh_error)
                    next_item["last_token_refresh_error_at"] = now.isoformat()
                    next_item["refresh_token_invalid_at"] = now.isoformat()
                account = self._normalize_account(next_item)
                if account is None:
                    return False

            final_status = str(account.get("status") or "异常")
            removed = bool(remove and final_status == "异常")
            if removed:
                self._accounts.pop(access_token, None)
            else:
                self._accounts[access_token] = account
            saved = self._save_accounts(
                expected_credential_generation=expected_generation,
            )
            if not saved:
                return False
            access_token = self._resolve_access_token_locked(access_token)
            persisted = self._accounts.get(access_token)
            if persisted is None:
                self._remove_account_runtime_state_locked({access_token})
                if not removed:
                    return False
            elif removed:
                return False
            else:
                account = dict(persisted)
                final_status = str(account.get("status") or "异常")

            diagnostic_error = self._credential_error_text(
                error,
                account,
                access_token=access_token,
            )
            if not terminal_already_recorded:
                log_service.add(
                    LOG_TYPE_ACCOUNT,
                    "账号鉴权确认失效" if final_status == "异常" else "已禁用账号鉴权确认失效",
                    {
                        "source": event,
                        "token": anonymize_token(access_token),
                        "status": final_status,
                        "error": diagnostic_error,
                    },
                )
            if removed:
                log_service.add(LOG_TYPE_ACCOUNT, "删除 1 个账号", {"removed": 1})
                log_service.add(
                    LOG_TYPE_ACCOUNT,
                    "自动移除异常账号",
                    {
                        "source": event,
                        "token": anonymize_token(access_token),
                        "error": diagnostic_error,
                    },
                )
        return removed

    @staticmethod
    def _mark_remote_check_pending(
        account: dict,
        event: str,
        now: str,
        *,
        remove_invalid: bool | None = None,
        scope: str = "account",
    ) -> None:
        existing_scope = (
            str(account.get("pending_auth_scope") or "").strip().lower()
            if account.get("last_remote_check_result") == "pending"
            else ""
        )
        account["last_remote_check_result"] = "pending"
        account["last_remote_check_event"] = event
        account["last_remote_check_attempt_at"] = now
        account["last_remote_check_error"] = None
        account["last_remote_check_error_at"] = None
        account["pending_auth_verification_id"] = uuid4().hex
        account["pending_auth_scope"] = (
            "account"
            if existing_scope == "account" or scope != "image"
            else "image"
        )
        requested_remove = (
            config.auto_remove_invalid_accounts
            if remove_invalid is None
            else bool(remove_invalid)
        )
        existing_remove = account.get("pending_auth_remove_invalid")
        account["pending_auth_remove_invalid"] = bool(existing_remove) or requested_remove

    def schedule_auth_verification(
        self,
        access_token: str,
        event: str,
        *,
        expected_access_token: str | None = None,
        expected_refresh_token: str | None = None,
        expected_last_token_refresh_at: str | None = None,
        remove_invalid: bool | None = None,
        scope: str = "account",
    ) -> bool:
        """Block a rejected account now and verify it in the background."""
        if not access_token:
            return False
        now = datetime.now(timezone.utc).isoformat()
        with self._image_slot_condition:
            access_token = self._resolve_access_token_locked(access_token)
            current = self._accounts.get(access_token)
            if current is None:
                return False
            expected_generation = None
            if expected_access_token is not None and expected_refresh_token is not None:
                expected_generation = (
                    str(expected_access_token or "").strip(),
                    str(expected_refresh_token or "").strip(),
                    str(expected_last_token_refresh_at or "").strip(),
                )
                if self._credential_generation(access_token, current) != expected_generation:
                    return False
            next_item = dict(current)
            self._mark_remote_check_pending(
                next_item,
                event,
                now,
                remove_invalid=remove_invalid,
                scope=scope,
            )
            account = self._normalize_account(next_item)
            if account is None:
                return False
            pending_verification_id = account.get("pending_auth_verification_id")
            self._accounts[access_token] = account
            saved = self._save_accounts(
                expected_credential_generation=expected_generation,
            )
            if not saved:
                return False
            access_token = self._resolve_access_token_locked(access_token)
            persisted = self._accounts.get(access_token)
            if (
                persisted is None
                or persisted.get("pending_auth_verification_id")
                != pending_verification_id
            ):
                return False
            pending_marker = self._remote_check_marker(persisted)
            pending_generation = self._credential_generation(access_token, persisted)
            self._image_slot_condition.notify_all()
        scheduled = self._schedule_account_refresh_after_image_failure(access_token, force=True)
        if not scheduled:
            self._record_remote_check_error(
                access_token,
                event,
                "Account verification could not be scheduled.",
                expected_access_token=pending_generation[0],
                expected_refresh_token=pending_generation[1],
                expected_remote_check_marker=pending_marker,
            )
        return scheduled

    def _verify_pending_auth(self, access_token: str, event: str) -> None:
        active_token, refresh_token, account = self._credential_snapshot(access_token)
        if not account or account.get("last_remote_check_result") != "pending":
            return
        pending_remove = account.get("pending_auth_remove_invalid")
        remove_invalid = (
            config.auto_remove_invalid_accounts
            if pending_remove is None
            else self._bool_value(pending_remove)
        )
        initial_token = active_token
        initial_refresh_token = refresh_token
        initial_remote_check_marker = self._remote_check_marker(account)

        from services.openai_backend_api import InvalidAccessTokenError, OpenAIBackendAPI

        def request_user_info(token: str) -> dict[str, Any]:
            with account_processing_slot():
                with OpenAIBackendAPI(token) as backend:
                    return backend.get_user_info()

        def reschedule_pending(token: str) -> None:
            current_token, _, current = self._credential_snapshot(token)
            if current and current.get("last_remote_check_result") == "pending":
                self._schedule_account_refresh_after_image_failure(
                    current_token,
                    force=True,
                )

        def snapshot_changed(token: str, refresh: str) -> bool:
            current_token, current_refresh, current = self._credential_snapshot(token)
            if current and (current_token, current_refresh) == (token, refresh):
                return False
            return True

        def request_user_info_for_snapshot(token: str, refresh: str) -> dict[str, Any]:
            try:
                result = request_user_info(token)
            except Exception as exc:
                if snapshot_changed(token, refresh):
                    raise RefreshCredentialsChangedError() from exc
                raise
            if snapshot_changed(token, refresh):
                raise RefreshCredentialsChangedError()
            return result

        try:
            result = request_user_info_for_snapshot(initial_token, initial_refresh_token)
        except InvalidAccessTokenError as initial_error:
            if not initial_refresh_token:
                self.handle_invalid_token(
                    initial_token,
                    event,
                    error=str(initial_error),
                    remove=remove_invalid,
                    expected_access_token=initial_token,
                    expected_refresh_token=initial_refresh_token,
                    expected_remote_check_marker=initial_remote_check_marker,
                )
                reschedule_pending(initial_token)
                return
            try:
                active_token = self.force_refresh_access_token(
                    initial_token,
                    event=f"{event}:auth_recovery",
                    raise_on_error=True,
                    image_scope=True,
                    expected_credentials=(
                        initial_token,
                        initial_refresh_token,
                        initial_remote_check_marker[0],
                    ),
                )
            except TerminalRefreshTokenError as refresh_error:
                self.handle_invalid_token(
                    initial_token,
                    event,
                    error=str(initial_error),
                    remove=remove_invalid,
                    expected_access_token=initial_token,
                    expected_refresh_token=initial_refresh_token,
                    expected_remote_check_marker=initial_remote_check_marker,
                    token_refresh_error=str(refresh_error),
                    refresh_token_terminal=True,
                )
                reschedule_pending(initial_token)
                return
            except Exception as exc:
                self._record_remote_check_error(
                    initial_token,
                    event,
                    str(exc),
                    expected_access_token=initial_token,
                    expected_refresh_token=initial_refresh_token,
                    expected_remote_check_marker=initial_remote_check_marker,
                )
                reschedule_pending(initial_token)
                return

            verification_token, verification_refresh_token, verification_account = (
                self._credential_snapshot(active_token)
            )
            if not verification_account:
                return
            verification_remote_check_marker = self._remote_check_marker(verification_account)
            try:
                result = request_user_info_for_snapshot(
                    verification_token,
                    verification_refresh_token,
                )
            except InvalidAccessTokenError as exc:
                self.handle_invalid_token(
                    verification_token,
                    event,
                    error=str(exc),
                    remove=remove_invalid,
                    expected_access_token=verification_token,
                    expected_refresh_token=verification_refresh_token,
                    expected_remote_check_marker=verification_remote_check_marker,
                )
                reschedule_pending(verification_token)
                return
            except Exception as exc:
                self._record_remote_check_error(
                    verification_token,
                    event,
                    str(exc),
                    expected_access_token=verification_token,
                    expected_refresh_token=verification_refresh_token,
                    expected_remote_check_marker=verification_remote_check_marker,
                )
                reschedule_pending(verification_token)
                return

            self._record_refresh_success(
                verification_token,
                result,
                event,
                expected_access_token=verification_token,
                expected_refresh_token=verification_refresh_token,
                expected_remote_check_marker=verification_remote_check_marker,
            )
            reschedule_pending(verification_token)
            return
        except Exception as exc:
            self._record_remote_check_error(
                initial_token,
                event,
                str(exc),
                expected_access_token=initial_token,
                expected_refresh_token=initial_refresh_token,
                expected_remote_check_marker=initial_remote_check_marker,
            )
            reschedule_pending(initial_token)
            return

        self._record_refresh_success(
            initial_token,
            result,
            event,
            expected_access_token=initial_token,
            expected_refresh_token=initial_refresh_token,
            expected_remote_check_marker=initial_remote_check_marker,
        )
        reschedule_pending(initial_token)

    def _refresh_account_after_image_failure(self, access_token: str) -> None:
        try:
            account = self.get_account(access_token) or {}
            event = str(account.get("last_remote_check_event") or "account_failure")
            if account.get("last_remote_check_result") == "pending":
                if account.get("pending_auth_scope") == "image":
                    self._verify_pending_auth(access_token, event)
                else:
                    self.fetch_remote_info(access_token, event)
            else:
                self.fetch_remote_info(access_token, event)
        except Exception as exc:
            account = self.get_account(access_token)
            log_service.add(
                LOG_TYPE_ACCOUNT,
                "鉴权失败后核验账号失败",
                {
                    "token": anonymize_token(access_token),
                    "error": self._credential_error_text(
                        exc,
                        account,
                        access_token=access_token,
                    ),
                },
            )

    def _schedule_account_refresh_after_image_failure(self, access_token: str, *, force: bool = False) -> bool:
        if not access_token:
            return False
        now = time.monotonic()
        with self._lock:
            access_token = self._resolve_access_token_locked(access_token)
            account = self._accounts.get(access_token) or {}
            requested_scope = (
                "image" if account.get("pending_auth_scope") == "image" else "account"
            )
            with self._image_failure_refresh_lock:
                cutoff = now - self._IMAGE_FAILURE_REFRESH_DEDUP_SECONDS
                self._image_failure_refresh_started_at = {
                    token: started_at
                    for token, started_at in self._image_failure_refresh_started_at.items()
                    if token in self._image_failure_refresh_active or started_at >= cutoff
                }
                active_refresh_token = next(
                    (
                        token for token in self._image_failure_refresh_active
                        if self._resolve_access_token_locked(token) == access_token
                    ),
                    None,
                )
                pending_refresh_token = next(
                    (
                        token for token in self._image_failure_refresh_pending_set
                        if self._resolve_access_token_locked(token) == access_token
                    ),
                    None,
                )
                last_started_at = max(
                    (
                        started_at
                        for token, started_at in self._image_failure_refresh_started_at.items()
                        if self._resolve_access_token_locked(token) == access_token
                    ),
                    default=0.0,
                )
                if active_refresh_token is not None:
                    if force:
                        self._image_failure_refresh_rerun.add(active_refresh_token)
                    return True
                if pending_refresh_token is not None:
                    existing_scope = self._image_failure_refresh_pending_scopes.get(
                        pending_refresh_token,
                        "account",
                    )
                    self._image_failure_refresh_pending_scopes[pending_refresh_token] = (
                        "account"
                        if "account" in {existing_scope, requested_scope}
                        else "image"
                    )
                    return True
                if (
                    not force
                    and now - last_started_at < self._IMAGE_FAILURE_REFRESH_DEDUP_SECONDS
                ):
                    return False
                self._image_failure_refresh_pending.append(access_token)
                self._image_failure_refresh_pending_set.add(access_token)
                self._image_failure_refresh_pending_scopes[access_token] = requested_scope
        self._start_pending_image_failure_refreshes()
        return True

    def _start_pending_image_failure_refreshes(self) -> None:
        while True:
            with self._image_failure_refresh_lock:
                if not self._image_failure_refresh_pending:
                    return

                task_count = (
                    len(self._image_failure_refresh_active)
                    + len(self._image_failure_refresh_pending)
                )
                max_workers = account_processing_worker_count(task_count)
                if len(self._image_failure_refresh_active) >= max_workers:
                    return

                access_token = self._image_failure_refresh_pending.popleft()
                refresh_scope = self._image_failure_refresh_pending_scopes.get(
                    access_token,
                    "account",
                )
                self._image_failure_refresh_pending_set.discard(access_token)
                self._image_failure_refresh_pending_scopes.pop(access_token, None)
                self._image_failure_refresh_active.add(access_token)
                self._image_failure_refresh_active_scopes[access_token] = refresh_scope
                self._image_failure_refresh_started_at[access_token] = time.monotonic()

            def refresh(token: str = access_token) -> None:
                try:
                    self._refresh_account_after_image_failure(token)
                finally:
                    with self._lock:
                        resolved_token = self._resolve_access_token_locked(token)
                        account = self._accounts.get(resolved_token)
                        with self._image_failure_refresh_lock:
                            self._image_failure_refresh_active.discard(token)
                            self._image_failure_refresh_active_scopes.pop(token, None)
                            rerun_requested = token in self._image_failure_refresh_rerun
                            self._image_failure_refresh_rerun.discard(token)
                            if (
                                rerun_requested
                                and account is not None
                                and account.get("last_remote_check_result") == "pending"
                                and resolved_token not in self._image_failure_refresh_pending_set
                            ):
                                self._image_failure_refresh_pending.append(resolved_token)
                                self._image_failure_refresh_pending_set.add(resolved_token)
                                self._image_failure_refresh_pending_scopes[resolved_token] = (
                                    "image"
                                    if account.get("pending_auth_scope") == "image"
                                    else "account"
                                )
                    self._start_pending_image_failure_refreshes()

            (
                expected_access_token,
                expected_refresh_token,
                expected_account,
            ) = self._credential_snapshot(access_token)
            expected_remote_check_marker = self._remote_check_marker(expected_account)
            try:
                Thread(
                    target=refresh,
                    name="image-account-refresh",
                    daemon=True,
                ).start()
            except Exception as exc:
                with self._image_failure_refresh_lock:
                    self._image_failure_refresh_active.discard(access_token)
                    self._image_failure_refresh_active_scopes.pop(access_token, None)
                self._record_remote_check_error(
                    access_token,
                    "image_failure",
                    str(exc),
                    expected_access_token=expected_access_token,
                    expected_refresh_token=expected_refresh_token,
                    expected_remote_check_marker=expected_remote_check_marker,
                )
                log_service.add(
                    LOG_TYPE_ACCOUNT,
                    "image failure refresh scheduling failed",
                    {
                        "token": anonymize_token(access_token),
                        "error": self._credential_error_text(
                            exc,
                            expected_account,
                            access_token=access_token,
                        ),
                    },
                )

    def mark_image_result(
        self,
        access_token: str,
        success: bool,
        *,
        failure: ImageFailure | None = None,
        quota_consumed: bool | None = None,
        capabilities: set[str] | tuple[str, ...] | None = None,
        expected_access_token: str | None = None,
        expected_refresh_token: str | None = None,
        expected_last_token_refresh_at: str | None = None,
    ) -> dict | None:
        # Retained as call metadata only; capability-specific account state is gone.
        _ = capabilities
        if not access_token:
            return None
        now = datetime.now(timezone.utc)
        should_verify_after_failure = False
        consumed_quota = success if quota_consumed is None else bool(quota_consumed)
        with self._image_slot_condition:
            access_token = self._resolve_access_token_locked(access_token)
            self._release_image_slot_locked(access_token)
            try:
                current = self._accounts.get(access_token)
                if current is None:
                    return None
                expected_generation = None
                if expected_access_token is not None and expected_refresh_token is not None:
                    expected_generation = (
                        str(expected_access_token or "").strip(),
                        str(expected_refresh_token or "").strip(),
                        str(expected_last_token_refresh_at or "").strip(),
                    )
                    if (
                        self._credential_generation(access_token, current)
                        != expected_generation
                    ):
                        return None
                next_item = dict(current)
                next_item["last_used_at"] = now.isoformat()
                image_quota_unknown = bool(next_item.get("image_quota_unknown"))
                if success:
                    next_item["success"] = int(next_item.get("success") or 0) + 1
                if consumed_quota:
                    if not image_quota_unknown:
                        current_quota = max(0, int(next_item.get("quota") or 0))
                        next_item["quota"] = max(0, current_quota - 1)
                        if current_quota <= 1:
                            # 本地扣减到 0 只能说明“展示值需要远程刷新”，不能直接证明账号已限流。
                            # 下一次调度会进入远程预检，由 get_user_info 的结果决定是否写入“限流”。
                            next_item["image_quota_unknown"] = True
                            next_item["last_quota_estimated_empty_at"] = now.isoformat()
                    if next_item.get("status") == "限流":
                        # 上游已经消耗图片额度，说明远程额度已恢复。
                        next_item["status"] = "正常"
                        next_item["image_quota_unknown"] = True
                        next_item["restore_at"] = None
                if not success and failure is not None and failure.verify_account:
                    next_item["fail"] = int(next_item.get("fail") or 0) + 1
                    self._mark_remote_check_pending(
                        next_item,
                        "image_failure",
                        now.isoformat(),
                        scope="image",
                    )
                    should_verify_after_failure = True
                account = self._normalize_account(next_item)
                if account is None:
                    return None
                self._accounts[access_token] = account
                saved = self._save_accounts(
                    expected_credential_generation=expected_generation,
                )
                if not saved:
                    should_verify_after_failure = False
                    return None
                access_token = self._resolve_access_token_locked(access_token)
                persisted = self._accounts.get(access_token)
                if persisted is None:
                    should_verify_after_failure = False
                    return None
                result = dict(persisted)
            finally:
                self._image_slot_condition.notify_all()
        if should_verify_after_failure:
            scheduled = self._schedule_account_refresh_after_image_failure(
                access_token,
                force=True,
            )
            if not scheduled:
                self._record_remote_check_error(
                    access_token,
                    "image_failure",
                    "Account verification could not be scheduled.",
                )
        return result

    def fetch_remote_info(
        self,
        access_token: str,
        event: str = "fetch_remote_info",
        remove_invalid: bool | None = None,
        *,
        image_scope: bool = False,
        allow_refresh_token_exchange: bool = True,
        preflight_refresh: bool = True,
    ) -> dict[str, Any] | None:
        if not access_token:
            raise ValueError("access_token is required")

        if allow_refresh_token_exchange and preflight_refresh:
            refresh_kwargs = {"event": f"{event}:preflight"}
            if image_scope:
                refresh_kwargs["image_scope"] = True
            active_token = self.ensure_access_token(access_token, **refresh_kwargs)
        else:
            active_token = self.resolve_access_token(access_token) or access_token
        from services.openai_backend_api import InvalidAccessTokenError, OpenAIBackendAPI

        def request_user_info(token: str) -> dict[str, Any]:
            with account_processing_slot():
                with OpenAIBackendAPI(token) as backend:
                    return backend.get_user_info()

        request_token, request_refresh_token, request_account = self._credential_snapshot(active_token)
        if not request_account:
            raise RefreshCredentialsChangedError()
        request_generation = self._credential_generation(request_token, request_account)
        successful_snapshot = (request_token, request_refresh_token)
        successful_remote_check_marker = self._remote_check_marker(request_account)
        try:
            result = request_user_info(request_token)
        except InvalidAccessTokenError as exc:
            rejected_error: InvalidAccessTokenError | None = exc
            rejected_snapshot = (request_token, request_refresh_token)
            rejected_remote_check_marker = successful_remote_check_marker
            current_token, current_refresh_token, current_account = self._credential_snapshot(request_token)
            current_snapshot = (current_token, current_refresh_token)
            current_remote_check_marker = self._remote_check_marker(current_account)
            current_generation = self._credential_generation(current_token, current_account)
            if current_account and current_generation != request_generation:
                try:
                    result = request_user_info(current_token)
                except InvalidAccessTokenError as current_exc:
                    rejected_error = current_exc
                    rejected_snapshot = current_snapshot
                    rejected_remote_check_marker = current_remote_check_marker
                except Exception as current_exc:
                    self._record_remote_check_error(
                        current_token,
                        event,
                        str(current_exc),
                        expected_access_token=current_token,
                        expected_refresh_token=current_refresh_token,
                        expected_remote_check_marker=current_remote_check_marker,
                    )
                    raise
                else:
                    successful_snapshot = current_snapshot
                    successful_remote_check_marker = current_remote_check_marker
                    active_token = current_token
                    rejected_error = None

            if rejected_error is not None:
                if image_scope:
                    self.schedule_auth_verification(
                        rejected_snapshot[0],
                        event,
                        expected_access_token=rejected_snapshot[0],
                        expected_refresh_token=rejected_snapshot[1],
                        expected_last_token_refresh_at=rejected_remote_check_marker[0],
                        remove_invalid=remove_invalid,
                        scope="image",
                    )
                    raise rejected_error

                if not allow_refresh_token_exchange:
                    refresh_token_can_recover = bool(rejected_snapshot[1]) and not bool(
                        (current_account or {}).get("refresh_token_invalid_at")
                    )
                    self.handle_invalid_token(
                        rejected_snapshot[0],
                        event,
                        error=str(rejected_error),
                        remove=False if refresh_token_can_recover else remove_invalid,
                        expected_access_token=rejected_snapshot[0],
                        expected_refresh_token=rejected_snapshot[1],
                        expected_remote_check_marker=rejected_remote_check_marker,
                    )
                    raise rejected_error

                before_refresh = self.get_account(rejected_snapshot[0]) or {}
                before_refresh_at = str(before_refresh.get("last_token_refresh_at") or "")
                before_error_at = str(before_refresh.get("last_token_refresh_error_at") or "")
                try:
                    active_token = self.force_refresh_access_token(
                        rejected_snapshot[0],
                        event=f"{event}:invalid_access_token",
                        expected_credentials=(
                            rejected_snapshot[0],
                            rejected_snapshot[1],
                            rejected_remote_check_marker[0],
                        ),
                    )
                except TerminalRefreshTokenError as refresh_error:
                    self.handle_invalid_token(
                        rejected_snapshot[0],
                        event,
                        error=str(rejected_error),
                        remove=remove_invalid,
                        expected_access_token=rejected_snapshot[0],
                        expected_refresh_token=rejected_snapshot[1],
                        expected_remote_check_marker=rejected_remote_check_marker,
                        token_refresh_error=str(refresh_error),
                        refresh_token_terminal=True,
                    )
                    raise
                except RefreshCredentialsChangedError:
                    raise
                except Exception as refresh_exc:
                    self._record_remote_check_error(
                        rejected_snapshot[0],
                        event,
                        str(refresh_exc),
                        expected_access_token=rejected_snapshot[0],
                        expected_refresh_token=rejected_snapshot[1],
                        expected_remote_check_marker=rejected_remote_check_marker,
                    )
                    raise

                after_refresh = self.get_account(active_token or rejected_snapshot[0]) or {}
                after_refresh_at = str(after_refresh.get("last_token_refresh_at") or "")
                after_error_at = str(after_refresh.get("last_token_refresh_error_at") or "")
                refresh_failed = bool(after_error_at and after_error_at != before_error_at)
                refresh_succeeded = bool(after_refresh_at and after_refresh_at != before_refresh_at)
                if refresh_failed and not refresh_succeeded:
                    self._record_remote_check_error(
                        rejected_snapshot[0],
                        event,
                        str(
                            after_refresh.get("last_token_refresh_error")
                            or "refresh token failed"
                        ),
                        expected_access_token=rejected_snapshot[0],
                        expected_refresh_token=rejected_snapshot[1],
                        expected_remote_check_marker=rejected_remote_check_marker,
                    )
                    raise rejected_error

                verification_token, verification_refresh_token, verification_account = (
                    self._credential_snapshot(active_token)
                )
                if not verification_account:
                    raise RefreshCredentialsChangedError()
                verification_remote_check_marker = self._remote_check_marker(verification_account)
                try:
                    result = request_user_info(verification_token)
                except InvalidAccessTokenError as retry_exc:
                    self.handle_invalid_token(
                        verification_token,
                        event,
                        error=str(retry_exc),
                        remove=remove_invalid,
                        expected_access_token=verification_token,
                        expected_refresh_token=verification_refresh_token,
                        expected_remote_check_marker=verification_remote_check_marker,
                    )
                    raise
                except Exception as retry_exc:
                    self._record_remote_check_error(
                        verification_token,
                        event,
                        str(retry_exc),
                        expected_access_token=verification_token,
                        expected_refresh_token=verification_refresh_token,
                        expected_remote_check_marker=verification_remote_check_marker,
                    )
                    raise
                active_token = verification_token
                successful_snapshot = (verification_token, verification_refresh_token)
                successful_remote_check_marker = verification_remote_check_marker
        except Exception as exc:
            self._record_remote_check_error(
                request_token,
                event,
                str(exc),
                expected_access_token=request_token,
                expected_refresh_token=request_refresh_token,
                expected_remote_check_marker=successful_remote_check_marker,
            )
            raise

        updated = self._record_refresh_success(
            active_token,
            result,
            event,
            expected_access_token=successful_snapshot[0],
            expected_refresh_token=successful_snapshot[1],
            expected_remote_check_marker=successful_remote_check_marker,
        )
        if updated is not None:
            return updated
        # update_account 可能因为“自动移除额度耗尽账号”删除了远程确认限流的账号。
        # 调用方仍需要知道本次预检的真实结果，不能把它混成普通预检失败。
        if str(result.get("status") or "") == "\u9650\u6d41" and config.auto_remove_rate_limited_accounts:
            return {**result, "access_token": active_token, "_removed_after_refresh": True}
        current_token, current_refresh_token, current_account = self._credential_snapshot(active_token)
        if (
            current_account is not None
            and current_token == successful_snapshot[0]
            and current_refresh_token == successful_snapshot[1]
        ):
            # A newer verification marker won the compare-and-swap. Preserve and
            # return that newer account state instead of reporting a credential race.
            return current_account
        # A deleted account must not leak its stale token back into the selection path.
        raise RefreshCredentialsChangedError()

    # ---- 刷新进度追踪 ----

    @classmethod
    def _prune_refresh_progress_locked(
        cls,
        now: float,
        *,
        target_id: str | None = None,
    ) -> None:
        full_scan_due = (
            now < cls._refresh_progress_last_pruned_at
            or now - cls._refresh_progress_last_pruned_at
            >= cls._REFRESH_PROGRESS_PRUNE_INTERVAL_SECONDS
        )
        if full_scan_due:
            candidates = list(cls._refresh_progress)
            cls._refresh_progress_last_pruned_at = now
        elif target_id and target_id in cls._refresh_progress:
            candidates = [target_id]
        else:
            return

        for progress_id in candidates:
            progress = cls._refresh_progress.get(progress_id)
            if progress is None:
                continue
            updated_at_value = progress.get("_updated_at_monotonic")
            if isinstance(updated_at_value, (int, float)):
                updated_at = float(updated_at_value)
            else:
                updated_at = now
                progress["_updated_at_monotonic"] = now
            ttl = (
                cls._REFRESH_PROGRESS_COMPLETED_TTL_SECONDS
                if progress.get("done")
                else cls._REFRESH_PROGRESS_ACTIVE_TTL_SECONDS
            )
            if now - updated_at >= ttl:
                cls._refresh_progress.pop(progress_id, None)

    def init_refresh_progress(self, progress_id: str, total: int) -> None:
        """初始化刷新进度记录。"""
        now = time.monotonic()
        with self._refresh_progress_lock:
            self._prune_refresh_progress_locked(now, target_id=progress_id)
            self._refresh_progress[progress_id] = {
                "total": total,
                "processed": 0,
                "done": False,
                "error": None,
                "status_counts": {"正常": 0, "限流": 0, "异常": 0, "禁用": 0},
                "total_quota": 0,
                "events": [],
                "_event_sequence": 0,
                "_updated_at_monotonic": now,
            }

    def update_refresh_progress_stage(
        self,
        progress_id: str,
        stage: str,
        stage_label: str,
    ) -> None:
        """Publish task-level progress without counting an account as completed."""
        now = time.monotonic()
        with self._refresh_progress_lock:
            self._prune_refresh_progress_locked(now, target_id=progress_id)
            progress = self._refresh_progress.get(progress_id)
            if progress is None or progress.get("done"):
                return
            progress["stage"] = str(stage or "").strip()
            progress["stage_label"] = str(stage_label or "").strip()
            progress["_updated_at_monotonic"] = now

    @staticmethod
    def _account_operation_identity(
        account: dict | None,
        *,
        fallback_id: str = "",
    ) -> tuple[str, str]:
        item = account or {}
        account_id = str(item.get("management_id") or fallback_id or "").strip()
        account_label = str(item.get("email") or account_id).strip()
        return account_id, account_label

    @classmethod
    def _append_refresh_progress_event_locked(
        cls,
        progress: dict[str, Any],
        *,
        account_id: str = "",
        account_label: str = "",
        action: str,
        status: str,
        message: str,
        sensitive_values: tuple[object, ...] = (),
        proxy_values: tuple[object, ...] = (),
    ) -> None:
        sequence = int(progress.get("_event_sequence") or 0) + 1
        event = normalize_account_operation_event(
            {
                "sequence": sequence,
                "account_id": account_id,
                "account_label": account_label,
                "action": action,
                "status": status,
                "message": message,
            },
            fallback_sequence=sequence,
            sensitive_values=sensitive_values,
            proxy_values=proxy_values,
        )
        if event is None:
            return
        events = progress.setdefault("events", [])
        events.append(event)
        if len(events) > cls._REFRESH_PROGRESS_EVENT_LIMIT:
            del events[:-cls._REFRESH_PROGRESS_EVENT_LIMIT]
        progress["_event_sequence"] = sequence

    def update_refresh_progress(
        self,
        progress_id: str,
        token: str,
        result_account: dict | None = None,
        *,
        account_id: str = "",
        account_label: str = "",
        action: str = "",
        event_status: str = "info",
        event_message: str = "",
    ) -> None:
        """刷新单个账号后，更新进度计数。"""
        account = result_account or self.get_account(token)
        status = str(account.get("status") or "正常").strip() if account else "异常"
        quota = max(0, int(account.get("quota") or 0)) if account else 0

        now = time.monotonic()
        with self._refresh_progress_lock:
            self._prune_refresh_progress_locked(now, target_id=progress_id)
            progress = self._refresh_progress.get(progress_id)
            if progress is None:
                return
            progress["processed"] += 1
            progress["status_counts"][status] = progress["status_counts"].get(status, 0) + 1
            progress["total_quota"] += quota
            if action and event_message:
                event_account_id, event_account_label = self._account_operation_identity(
                    account,
                    fallback_id=account_id,
                )
                sensitive_values = tuple(
                    value
                    for value in (
                        token,
                        (account or {}).get("access_token"),
                        (account or {}).get("refresh_token"),
                        (account or {}).get("id_token"),
                        (account or {}).get("password"),
                    )
                    if value
                )
                proxy_values = tuple(
                    value for value in ((account or {}).get("proxy"),) if value
                )
                self._append_refresh_progress_event_locked(
                    progress,
                    account_id=event_account_id,
                    account_label=account_label or event_account_label,
                    action=action,
                    status=event_status,
                    message=event_message,
                    sensitive_values=sensitive_values,
                    proxy_values=proxy_values,
                )
            progress["_updated_at_monotonic"] = now

    def finish_refresh_progress(
        self,
        progress_id: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        """标记刷新完成。"""
        now = time.monotonic()
        with self._refresh_progress_lock:
            self._prune_refresh_progress_locked(now, target_id=progress_id)
            progress = self._refresh_progress.get(progress_id)
            if progress is None:
                return
            progress["done"] = True
            progress["result"] = result
            progress["stage"] = "completed"
            progress["stage_label"] = ""
            if error:
                progress["error"] = error
            progress["_updated_at_monotonic"] = now

    def get_refresh_progress(self, progress_id: str) -> dict | None:
        """查询刷新进度。"""
        now = time.monotonic()
        with self._refresh_progress_lock:
            self._prune_refresh_progress_locked(now, target_id=progress_id)
            progress = self._refresh_progress.get(progress_id)
            return {
                key: value
                for key, value in progress.items()
                if not key.startswith("_")
            } if progress else None

    def clean_refresh_progress(self, progress_id: str) -> None:
        """清理过期进度记录。"""
        with self._refresh_progress_lock:
            self._refresh_progress.pop(progress_id, None)

    def _exchange_access_tokens(
        self,
        access_tokens: list[str],
        progress_id: str | None = None,
        *,
        force: bool,
        event: str,
        finalize_progress: bool = True,
    ) -> dict[str, Any]:
        """Exchange RT-to-AT credentials without querying account metadata."""
        requested_tokens = list(dict.fromkeys(token for token in access_tokens if token))
        if not requested_tokens:
            result = {
                "refreshed": 0,
                "skipped": 0,
                "updated_ids": [],
                "removed_ids": [],
                "errors": [],
            }
            if progress_id and finalize_progress:
                self.finish_refresh_progress(progress_id, result)
            return result

        if progress_id and self.get_refresh_progress(progress_id) is None:
            self.init_refresh_progress(progress_id, len(requested_tokens))

        targets: list[tuple[str, str]] = []
        initial_errors: list[dict[str, Any]] = []
        for requested_token in requested_tokens:
            active_token, _refresh_token, account = self._credential_snapshot(requested_token)
            account_id = str((account or {}).get("management_id") or "").strip()
            if not account or not account_id:
                error = {
                    "id": account_id,
                    "token": anonymize_token(requested_token),
                    "code": "account_not_found",
                    "error": "account not found",
                }
                initial_errors.append(error)
                if progress_id:
                    self.update_refresh_progress(
                        progress_id,
                        requested_token,
                        account_id=account_id,
                        action="refresh_access_token",
                        event_status="failed",
                        event_message=error["error"],
                    )
                continue
            targets.append((active_token, account_id))

        refreshed = 0
        skipped = 0
        refreshed_ids: list[str] = []
        errors = list(initial_errors)

        def exchange(
            token: str,
            account_id: str,
        ) -> tuple[str, dict | None, bool, dict[str, Any] | None]:
            active_token, refresh_token, account = self._credential_snapshot(token)
            if not account:
                return token, None, False, {
                    "id": account_id,
                    "token": anonymize_token(token),
                    "code": "account_not_found",
                    "error": "account not found",
                }
            if not refresh_token:
                return active_token, account, False, {
                    "id": account_id,
                    "token": anonymize_token(active_token),
                    "code": "refresh_token_missing",
                    "error": "refresh token is missing",
                }
            if account.get("refresh_token_invalid_at"):
                return active_token, account, False, {
                    "id": account_id,
                    "token": anonymize_token(active_token),
                    "code": "refresh_token_invalid",
                    "error": "refresh token is invalid",
                }
            before_refresh_at = str(account.get("last_token_refresh_at") or "")
            try:
                operation = (
                    self.force_refresh_access_token
                    if force
                    else self.ensure_access_token
                )
                refreshed_token = operation(
                    active_token,
                    raise_on_error=True,
                    event=event,
                )
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                failure = classify_image_exception(exc)
                current_token = self.resolve_access_token(active_token) or active_token
                current_account = self.get_account(current_token) or account
                return current_token, self.get_account(current_token), False, {
                    "id": account_id,
                    "token": anonymize_token(active_token),
                    "error": self._credential_error_text(
                        exc,
                        current_account,
                        access_token=active_token,
                    ),
                    **failure.diagnostic_fields(),
                }
            result_account = self.get_account(refreshed_token)
            after_refresh_at = str((result_account or {}).get("last_token_refresh_at") or "")
            exchanged = bool(
                refreshed_token != active_token
                or (after_refresh_at and after_refresh_at != before_refresh_at)
            )
            return refreshed_token, result_account, exchanged, None

        max_workers = account_processing_worker_count(len(targets))
        executor = ThreadPoolExecutor(max_workers=max_workers) if max_workers else None
        try:
            futures = {
                executor.submit(exchange, token, account_id): (token, account_id)
                for token, account_id in targets
            } if executor else {}
            for future in as_completed(futures):
                token, account_id = futures[future]
                active_token, result_account, exchanged, error = future.result()
                if error:
                    errors.append(error)
                    event_status = "failed"
                    event_message = str(
                        error.get("error")
                        or "\u8bbf\u95ee\u4ee4\u724c\u5237\u65b0\u5931\u8d25"
                    )
                elif exchanged:
                    refreshed += 1
                    refreshed_ids.append(account_id)
                    event_status = "success"
                    event_message = "\u8bbf\u95ee\u4ee4\u724c\u5df2\u5237\u65b0"
                else:
                    skipped += 1
                    event_status = "skipped"
                    event_message = "\u8bbf\u95ee\u4ee4\u724c\u65e0\u9700\u66f4\u65b0"
                if progress_id:
                    self.update_refresh_progress(
                        progress_id,
                        active_token or token,
                        result_account,
                        account_id=account_id,
                        action="refresh_access_token",
                        event_status=event_status,
                        event_message=event_message,
                    )
        except (KeyboardInterrupt, SystemExit):
            if progress_id:
                self.finish_refresh_progress(progress_id, error="cancelled")
            if executor:
                executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            if executor:
                executor.shutdown(wait=True, cancel_futures=True)

        existing_ids = {
            str(account.get("management_id") or "").strip()
            for account in self.list_accounts()
            if str(account.get("management_id") or "").strip()
        }
        target_ids = [account_id for _token, account_id in targets]
        result = {
            "refreshed": refreshed,
            "skipped": skipped,
            "updated_ids": [
                account_id for account_id in refreshed_ids if account_id in existing_ids
            ],
            "removed_ids": [account_id for account_id in target_ids if account_id not in existing_ids],
            "errors": errors,
        }
        if progress_id and finalize_progress:
            self.finish_refresh_progress(progress_id, result)
        return result

    def refresh_access_tokens(
        self,
        access_tokens: list[str],
        progress_id: str | None = None,
        *,
        finalize_progress: bool = True,
    ) -> dict[str, Any]:
        """Force RT-to-AT exchanges for an explicit administrator action."""
        return self._exchange_access_tokens(
            access_tokens,
            progress_id,
            force=True,
            event="refresh_access_tokens",
            finalize_progress=finalize_progress,
        )

    def renew_expiring_access_tokens(self, access_tokens: list[str]) -> dict[str, Any]:
        """Conditionally renew ATs selected by a periodic expiry scan."""
        return self._exchange_access_tokens(
            access_tokens,
            force=False,
            event="renew_expiring_access_tokens",
        )

    def sync_accounts_and_quota(
        self,
        access_tokens: list[str],
        progress_id: str | None = None,
        remove_invalid: bool | None = None,
        *,
        finalize_progress: bool = True,
    ) -> dict[str, Any]:
        """Synchronize remote account metadata and image quota."""
        access_tokens = list(dict.fromkeys(token for token in access_tokens if token))
        if not access_tokens:
            items = self.list_accounts()
            result = {"synced": 0, "errors": [], "items": items}
            if progress_id and finalize_progress:
                self.finish_refresh_progress(progress_id, result)
            return result

        synced = 0
        errors = []
        max_workers = account_processing_worker_count(len(access_tokens))

        if progress_id and self.get_refresh_progress(progress_id) is None:
            self.init_refresh_progress(progress_id, len(access_tokens))

        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            futures = {}
            for token in access_tokens:
                account_id, account_label = self._account_operation_identity(
                    self.get_account(token)
                )
                future = executor.submit(
                    self.fetch_remote_info,
                    token,
                    "sync_accounts_and_quota",
                    remove_invalid,
                    preflight_refresh=False,
                )
                futures[future] = (token, account_id, account_label)
            for future in as_completed(futures):
                token, account_id, account_label = futures[future]
                result_account = None
                try:
                    account = future.result()
                except (KeyboardInterrupt, SystemExit):
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise
                except Exception as exc:
                    failure = classify_image_exception(exc)
                    account = self.get_account(token)
                    errors.append({
                        "token": anonymize_token(token),
                        "account_id": account_id,
                        "account_label": account_label,
                        "error": self._credential_error_text(
                            exc,
                            account,
                            access_token=token,
                        ),
                        **failure.diagnostic_fields(),
                    })
                    event_status = "failed"
                    event_message = self._credential_error_text(
                        exc,
                        account,
                        access_token=token,
                    )
                else:
                    if account is not None:
                        synced += 1
                        result_account = account
                        event_status = "success"
                        event_message = "\u8d26\u53f7\u4e0e\u989d\u5ea6\u5df2\u540c\u6b65"
                    else:
                        event_status = "failed"
                        event_message = "\u8d26\u53f7\u4e0e\u989d\u5ea6\u540c\u6b65\u5931\u8d25"

                if progress_id:
                    self.update_refresh_progress(
                        progress_id,
                        token,
                        result_account,
                        account_id=account_id,
                        account_label=account_label,
                        action="sync_account",
                        event_status=event_status,
                        event_message=event_message,
                    )
        except (KeyboardInterrupt, SystemExit):
            if progress_id:
                self.finish_refresh_progress(progress_id, error="cancelled")
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True, cancel_futures=True)

        result = {
            "synced": synced,
            "errors": errors,
            "items": self.list_accounts(),
        }

        if progress_id and finalize_progress:
            self.finish_refresh_progress(progress_id, result)

        return result

    def refresh_accounts(
        self,
        access_tokens: list[str],
        progress_id: str | None = None,
        remove_invalid: bool | None = None,
        *,
        finalize_progress: bool = True,
    ) -> dict[str, Any]:
        """Compatibility alias for synchronize-account-and-quota callers."""
        result = self.sync_accounts_and_quota(
            access_tokens,
            progress_id,
            remove_invalid,
            finalize_progress=finalize_progress,
        )
        return {**result, "refreshed": int(result.get("synced") or 0)}

    def build_export_items(
            self,
            access_tokens: list[str] | None = None,
            *,
            full: bool = False,
    ) -> list[dict[str, Any]]:
        self._refresh_accounts_snapshot_if_stale()
        target_tokens = set(token for token in (access_tokens or []) if token)
        with self._lock:
            accounts = [
                dict(item)
                for item in self._accounts.values()
                if not target_tokens or str(item.get("access_token") or "") in target_tokens
            ]

        items: list[dict[str, Any]] = []
        for account in accounts:
            access_token = str(account.get("access_token") or "").strip()
            refresh_token = str(account.get("refresh_token") or "").strip()
            id_token = str(account.get("id_token") or "").strip()
            if not access_token:
                continue

            if full:
                item: dict[str, Any] = {"access_token": access_token}
                for key in (
                    "management_id",
                    "access_token_fingerprints",
                    "refresh_token",
                    "id_token",
                    "password",
                    "type",
                    "plan_type",
                    "export_type",
                    "source_type",
                    "status",
                    "quota",
                    "image_quota_unknown",
                    "limits_progress",
                    "default_model_slug",
                    "email",
                    "user_id",
                    "account_id",
                    "proxy",
                    "group_id",
                    "created_at",
                    "last_token_refresh_at",
                    "last_token_refresh_error",
                    "last_token_refresh_error_at",
                    "refresh_token_invalid_at",
                    "last_remote_checked_at",
                    "last_remote_check_attempt_at",
                    "last_remote_check_error",
                    "last_remote_check_error_at",
                    "last_remote_check_event",
                    "last_remote_check_result",
                ):
                    if key in account and account.get(key) not in (None, ""):
                        item[key] = account.get(key)
                items.append(item)
                continue

            access_payload = self._decode_jwt_payload(access_token)
            id_payload = self._decode_jwt_payload(id_token)
            auth_claim = access_payload.get("https://api.openai.com/auth")
            auth_claim = auth_claim if isinstance(auth_claim, dict) else {}
            profile_claim = access_payload.get("https://api.openai.com/profile")
            profile_claim = profile_claim if isinstance(profile_claim, dict) else {}

            email = (
                str(account.get("email") or "").strip()
                or str(profile_claim.get("email") or "").strip()
                or str(id_payload.get("email") or "").strip()
            )
            account_id = (
                str(account.get("account_id") or "").strip()
                or str(auth_claim.get("chatgpt_account_id") or "").strip()
                or str(account.get("user_id") or "").strip()
            )
            item: dict[str, Any] = {
                "type": str(account.get("export_type") or "codex"),
                "email": email,
                "account_id": account_id,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "id_token": id_token,
                "expired": self._timestamp_to_iso(access_payload.get("exp")),
                "last_refresh": self._timestamp_to_iso(access_payload.get("iat")),
            }
            password = str(account.get("password") or "").strip()
            if password:
                item["password"] = password
            items.append(item)
        return items

    def get_stats(self) -> dict:
        self._refresh_accounts_snapshot_if_stale()
        with self._lock:
            items = list(self._accounts.values())
        total = len(items)
        active = sum(1 for a in items if a.get("status") == "正常")
        limited = sum(1 for a in items if a.get("status") == "限流")
        abnormal = sum(1 for a in items if a.get("status") == "异常")
        disabled = sum(1 for a in items if a.get("status") == "禁用")
        normal_items = [a for a in items if a.get("status") == "正常"]
        total_quota = sum(max(0, int(a.get("quota") or 0)) for a in normal_items)
        unlimited = sum(1 for a in normal_items if self._is_unlimited_image_quota_account(a))
        unknown_quota = sum(
            1
            for a in normal_items
            if (
                bool(a.get("image_quota_unknown"))
                or (not bool(a.get("image_quota_unknown")) and max(0, int(a.get("quota") or 0)) <= 0)
            )
            and not self._is_unlimited_image_quota_account(a)
        )
        total_success = sum(int(a.get("success") or 0) for a in items)
        total_fail = sum(int(a.get("fail") or 0) for a in items)
        by_type = {}
        for a in items:
            t = a.get("type") or "unknown"
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total": total,
            "cumulative_total": self._cumulative_total,
            "active": active,
            "limited": limited,
            "abnormal": abnormal,
            "disabled": disabled,
            "total_quota": total_quota,
            "unlimited_quota_count": unlimited,
            "unknown_quota_count": unknown_quota,
            "total_success": total_success,
            "total_fail": total_fail,
            "by_type": by_type,
        }

    def account_health(self) -> dict:
        stats = self.get_stats()
        return {
            "healthy": stats["active"] > 0 or stats["unlimited_quota_count"] > 0,
            "status": "ok" if stats["active"] > 0 else "degraded",
            **stats,
        }


from services.proxy_management_service import proxy_management_service

account_service = AccountService(
    config.get_storage_backend(),
    proxy_reference_mutation=proxy_management_service.mutate_assignment_references,
)
proxy_management_service.bind_account_provider(account_service.list_accounts)
