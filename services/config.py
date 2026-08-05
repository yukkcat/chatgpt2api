from __future__ import annotations

import copy
import os
import threading
from time import monotonic
from pathlib import Path

from contracts.settings_specification import (
    normalize_float_setting,
    normalize_integer_setting,
    numeric_setting_spec,
)
from services.json_file import read_json_object, write_json_file
from services.storage.base import StorageBackend
from services.storage.configuration_repository import (
    AccountGroupRepository,
    SystemSettingsRepository,
    account_group_repository,
    system_settings_repository,
)

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config.json"
VERSION_FILE = BASE_DIR / "VERSION"

_REMOVED_TOP_LEVEL_SETTINGS = (
    "auto_relogin_after_refresh",
    "image_auth_refresh_concurrency",
    "image_preflight_token_refresh_enabled",
)

DEFAULT_BACKUP_INCLUDE = {
    "image_tasks": True,
    "editable_files": True,
    "images": False,
}

_DATABASE_SETTINGS_REFRESH_INTERVAL_SECONDS = 1.0

DEFAULT_IMAGE_STORAGE = {
    "enabled": False,
    "mode": "local",
    "webdav_url": "",
    "webdav_username": "",
    "webdav_password": "",
    "webdav_root_path": "chatgpt2api/images",
    "public_base_url": "",
}

DEFAULT_CHAT_COMPLETION_CACHE = {
    "enabled": True,
    "ttl_seconds": 60,
    "max_entries": 256,
    "dedupe_inflight": True,
    "stream_cache": True,
    "normalize_messages": True,
    "drop_adjacent_duplicates": True,
    "drop_assistant_history": False,
}

DEFAULT_PROXY_RUNTIME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)

DEFAULT_PROXY_RUNTIME = {
    "enabled": False,
    "resource_proxy_url": "",
    "skip_ssl_verify": False,
    "reset_session_status_codes": [403],
    "clearance": {
        "enabled": False,
        "mode": "none",
        "cf_cookies": "",
        "cf_clearance": "",
        "user_agent": DEFAULT_PROXY_RUNTIME_USER_AGENT,
        "browser": "chrome",
        "flaresolverr_url": "",
        "timeout_sec": int(numeric_setting_spec("proxy_runtime.clearance.timeout_sec").default),
        "refresh_interval": int(
            numeric_setting_spec("proxy_runtime.clearance.refresh_interval").default
        ),
        "warm_up_on_start": False,
    },
}

DEFAULT_THIRD_PARTY_APPS = {
    "infinite_canvas": {
        "enabled": False,
        "url": "https://canvas.best",
    },
}


def _normalize_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return default
    if value is None:
        return default
    return bool(value)


def _normalize_positive_int(value: object, default: int, minimum: int = 0) -> int:
    try:
        normalized = int(value)
    except (OverflowError, TypeError, ValueError):
        normalized = default
    return max(minimum, normalized)


def _normalize_backup_include(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    normalized = copy.deepcopy(source)
    normalized.pop("register", None)
    for key, default in DEFAULT_BACKUP_INCLUDE.items():
        normalized[key] = _normalize_bool(source.get(key), default)
    return normalized


def _normalize_backup_settings(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    normalized = copy.deepcopy(source)
    normalized.pop("has_secret_access_key", None)
    normalized.pop("has_passphrase", None)
    normalized.update({
        "enabled": _normalize_bool(source.get("enabled"), False),
        "provider": "cloudflare_r2",
        "account_id": str(source.get("account_id") or "").strip(),
        "access_key_id": str(source.get("access_key_id") or "").strip(),
        "secret_access_key": str(source.get("secret_access_key") or "").strip(),
        "bucket": str(source.get("bucket") or "").strip(),
        "prefix": str(source.get("prefix") or "backups").strip().strip("/") or "backups",
        "interval_minutes": normalize_integer_setting(
            "backup.interval_minutes",
            source.get("interval_minutes"),
        ),
        "rotation_keep": normalize_integer_setting(
            "backup.rotation_keep",
            source.get("rotation_keep"),
        ),
        "encrypt": _normalize_bool(source.get("encrypt"), False),
        "passphrase": str(source.get("passphrase") or "").strip(),
        "include": _normalize_backup_include(source.get("include")),
    })
    return normalized


def _normalize_image_storage_settings(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    mode = str(source.get("mode") or "local").strip().lower()
    if mode not in {"local", "webdav", "both"}:
        mode = "local"
    enabled = _normalize_bool(source.get("enabled"), False)
    if not enabled:
        mode = "local"
    root_path = str(source.get("webdav_root_path") or DEFAULT_IMAGE_STORAGE["webdav_root_path"]).strip().strip("/")
    normalized = copy.deepcopy(source)
    normalized.pop("has_webdav_password", None)
    normalized.update({
        "enabled": enabled,
        "mode": mode,
        "webdav_url": str(source.get("webdav_url") or "").strip().rstrip("/"),
        "webdav_username": str(source.get("webdav_username") or "").strip(),
        "webdav_password": str(source.get("webdav_password") or "").strip(),
        "webdav_root_path": root_path or str(DEFAULT_IMAGE_STORAGE["webdav_root_path"]),
        "public_base_url": str(source.get("public_base_url") or "").strip().rstrip("/"),
    })
    return normalized


def _normalize_chat_completion_cache_settings(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    return {
        "enabled": _normalize_bool(source.get("enabled"), DEFAULT_CHAT_COMPLETION_CACHE["enabled"]),
        "ttl_seconds": _normalize_positive_int(
            source.get("ttl_seconds"),
            int(DEFAULT_CHAT_COMPLETION_CACHE["ttl_seconds"]),
            0,
        ),
        "max_entries": _normalize_positive_int(
            source.get("max_entries"),
            int(DEFAULT_CHAT_COMPLETION_CACHE["max_entries"]),
            1,
        ),
        "dedupe_inflight": _normalize_bool(
            source.get("dedupe_inflight"),
            bool(DEFAULT_CHAT_COMPLETION_CACHE["dedupe_inflight"]),
        ),
        "stream_cache": _normalize_bool(
            source.get("stream_cache"),
            bool(DEFAULT_CHAT_COMPLETION_CACHE["stream_cache"]),
        ),
        "normalize_messages": _normalize_bool(
            source.get("normalize_messages"),
            bool(DEFAULT_CHAT_COMPLETION_CACHE["normalize_messages"]),
        ),
        "drop_adjacent_duplicates": _normalize_bool(
            source.get("drop_adjacent_duplicates"),
            bool(DEFAULT_CHAT_COMPLETION_CACHE["drop_adjacent_duplicates"]),
        ),
        "drop_assistant_history": _normalize_bool(
            source.get("drop_assistant_history"),
            bool(DEFAULT_CHAT_COMPLETION_CACHE["drop_assistant_history"]),
        ),
    }


def _normalize_status_codes(value: object) -> list[int]:
    items = value if isinstance(value, list) else DEFAULT_PROXY_RUNTIME["reset_session_status_codes"]
    normalized: list[int] = []
    for item in items:
        if isinstance(item, bool):
            continue
        try:
            status = int(item)
        except (OverflowError, TypeError, ValueError):
            continue
        if 100 <= status <= 599 and status not in normalized:
            normalized.append(status)
    if not normalized:
        return list(DEFAULT_PROXY_RUNTIME["reset_session_status_codes"])
    return normalized


def _normalize_proxy_runtime_settings(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    default_clearance = DEFAULT_PROXY_RUNTIME["clearance"]
    clearance_source = source.get("clearance") if isinstance(source.get("clearance"), dict) else {}

    clearance_mode = str(clearance_source.get("mode") or default_clearance["mode"]).strip().lower()
    if clearance_mode not in {"none", "manual", "flaresolverr"}:
        clearance_mode = str(default_clearance["mode"])

    user_agent = str(clearance_source.get("user_agent") or default_clearance["user_agent"]).strip()
    browser = str(clearance_source.get("browser") or default_clearance["browser"]).strip()

    existing_clearance_cookies = str(source.get("_existing_cf_cookies") or "").strip()
    existing_cf_clearance = str(source.get("_existing_cf_clearance") or "").strip()
    cf_cookies = str(clearance_source.get("cf_cookies") or "").strip()
    cf_clearance = str(clearance_source.get("cf_clearance") or "").strip()
    if not cf_cookies and _normalize_bool(clearance_source.get("has_cf_cookies"), False):
        cf_cookies = existing_clearance_cookies
    if not cf_clearance and _normalize_bool(clearance_source.get("has_cf_clearance"), False):
        cf_clearance = existing_cf_clearance

    normalized_clearance = copy.deepcopy(clearance_source)
    normalized_clearance.pop("has_cf_cookies", None)
    normalized_clearance.pop("has_cf_clearance", None)
    normalized_clearance.update({
        "enabled": _normalize_bool(clearance_source.get("enabled"), bool(default_clearance["enabled"])),
        "mode": clearance_mode,
        "cf_cookies": cf_cookies,
        "cf_clearance": cf_clearance,
        "user_agent": user_agent or str(default_clearance["user_agent"]),
        "browser": browser or str(default_clearance["browser"]),
        "flaresolverr_url": str(clearance_source.get("flaresolverr_url") or "").strip(),
        "timeout_sec": normalize_integer_setting(
            "proxy_runtime.clearance.timeout_sec",
            clearance_source.get("timeout_sec"),
        ),
        "refresh_interval": normalize_integer_setting(
            "proxy_runtime.clearance.refresh_interval",
            clearance_source.get("refresh_interval"),
        ),
        "warm_up_on_start": _normalize_bool(
            clearance_source.get("warm_up_on_start"),
            bool(default_clearance["warm_up_on_start"]),
        ),
    })

    normalized = copy.deepcopy(source)
    normalized.pop("_existing_cf_cookies", None)
    normalized.pop("_existing_cf_clearance", None)
    normalized.pop("egress_mode", None)
    normalized.pop("proxy_url", None)
    normalized.update({
        "enabled": _normalize_bool(source.get("enabled"), bool(DEFAULT_PROXY_RUNTIME["enabled"])),
        "resource_proxy_url": str(source.get("resource_proxy_url") or "").strip(),
        "skip_ssl_verify": _normalize_bool(
            source.get("skip_ssl_verify"),
            bool(DEFAULT_PROXY_RUNTIME["skip_ssl_verify"]),
        ),
        "reset_session_status_codes": _normalize_status_codes(source.get("reset_session_status_codes")),
        "clearance": normalized_clearance,
    })
    return normalized


def _normalize_third_party_apps_settings(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    canvas_source = source.get("infinite_canvas") if isinstance(source.get("infinite_canvas"), dict) else {}
    normalized_canvas = copy.deepcopy(canvas_source)
    normalized_canvas.update({
        "enabled": _normalize_bool(canvas_source.get("enabled"), False),
        "url": str(canvas_source.get("url") or DEFAULT_THIRD_PARTY_APPS["infinite_canvas"]["url"]).strip(),
    })
    normalized = copy.deepcopy(source)
    normalized["infinite_canvas"] = normalized_canvas
    return normalized


def _legacy_basic_from_settings(value: object, settings: dict[str, object]) -> dict[str, object]:
    source = dict(value) if isinstance(value, dict) else {}
    source["proxy"] = str(settings.get("proxy") or "").strip()
    source["base_url"] = str(settings.get("base_url") or "").strip().rstrip("/")
    retention_days = normalize_integer_setting(
        "image_retention_days",
        settings.get("image_retention_days"),
    )
    source["image_expire_hours"] = retention_days * 24
    return source


def _promote_legacy_basic_settings(data: dict[str, object]) -> dict[str, object]:
    next_data = dict(data or {})
    for key in _REMOVED_TOP_LEVEL_SETTINGS:
        next_data.pop(key, None)
    basic = next_data.get("basic")
    if not isinstance(basic, dict):
        return next_data
    if "proxy" not in next_data and "proxy" in basic:
        next_data["proxy"] = str(basic.get("proxy") or "").strip()
    if "base_url" not in next_data and "base_url" in basic:
        next_data["base_url"] = str(basic.get("base_url") or "").strip().rstrip("/")
    if "image_retention_days" not in next_data and "image_expire_hours" in basic:
        try:
            legacy_hours = max(1, int(basic.get("image_expire_hours") or 24))
            next_data["image_retention_days"] = (legacy_hours + 23) // 24
        except (TypeError, ValueError):
            next_data["image_retention_days"] = int(
                numeric_setting_spec("image_retention_days").default
            )
    return next_data


def _validate_image_storage_settings(settings: dict[str, object]) -> None:
    if not _normalize_bool(settings.get("enabled"), False):
        return
    if not str(settings.get("webdav_url") or "").strip():
        raise ValueError("启用 WebDAV 图片存储后必须填写 WebDAV URL")
    if not str(settings.get("webdav_password") or "").strip():
        raise ValueError("启用 WebDAV 图片存储后必须填写 WebDAV 密码")


def _normalize_auth_key(value: object) -> str:
    return str(value or "").strip()


def _is_invalid_auth_key(value: object) -> bool:
    return _normalize_auth_key(value) == ""


class ConfigStore:
    def __init__(
        self,
        path: Path,
        *,
        settings_repository: SystemSettingsRepository | None = None,
        groups_repository: AccountGroupRepository | None = None,
    ):
        self.path = path
        self._lock = threading.RLock()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._settings_repository = settings_repository or system_settings_repository
        self._groups_repository = groups_repository or account_group_repository
        self.data = self._load()
        self._last_repository_refresh_at = monotonic()
        self._storage_backend: StorageBackend | None = None
        if _is_invalid_auth_key(self.auth_key):
            raise ValueError(
                "❌ auth-key 未设置！\n"
                "请按以下任意一种方式解决：\n"
                "1. 在 Render 的 Environment 变量中添加：\n"
                "   CHATGPT2API_AUTH_KEY = your_real_auth_key\n"
                "2. 或者在 config.json 中填写：\n"
                '   "auth-key": "your_real_auth_key"'
            )

    @property
    def mutation_lock(self) -> threading.RLock:
        return self._lock

    def _load(self) -> dict[str, object]:
        settings = _promote_legacy_basic_settings(self._settings_repository.get())
        groups = self._groups_repository.get().get("items")
        settings["account_groups"] = (
            copy.deepcopy(groups) if isinstance(groups, list) else []
        )
        return settings

    def reload_if_changed(self) -> None:
        with self._lock:
            now = monotonic()
            if (
                now - self._last_repository_refresh_at
                < _DATABASE_SETTINGS_REFRESH_INTERVAL_SECONDS
            ):
                return
            self.data = self._load()
            self._last_repository_refresh_at = now

    @property
    def auth_key(self) -> str:
        bootstrap = read_json_object(self.path, name="config.json")
        return _normalize_auth_key(
            os.getenv("CHATGPT2API_AUTH_KEY") or bootstrap.get("auth-key")
        )

    @property
    def refresh_account_interval_minute(self) -> int:
        self.reload_if_changed()
        return normalize_integer_setting(
            "refresh_account_interval_minute",
            self.data.get("refresh_account_interval_minute"),
        )

    @property
    def image_retention_days(self) -> int:
        return normalize_integer_setting(
            "image_retention_days",
            self.data.get("image_retention_days"),
        )

    @property
    def log_retention_days(self) -> int:
        return normalize_integer_setting(
            "log_retention_days",
            self.data.get("log_retention_days"),
        )

    @property
    def image_min_free_mb(self) -> int:
        self.reload_if_changed()
        return _normalize_positive_int(
            self.data.get("image_min_free_mb") or 500,
            500,
            1,
        )

    @property
    def image_poll_timeout_secs(self) -> int:
        self.reload_if_changed()
        return normalize_integer_setting(
            "image_poll_timeout_secs",
            self.data.get("image_poll_timeout_secs"),
        )

    @property
    def image_stream_timeout_secs(self) -> int:
        self.reload_if_changed()
        return normalize_integer_setting(
            "image_stream_timeout_secs",
            self.data.get("image_stream_timeout_secs"),
        )

    @property
    def image_request_timeout_secs(self) -> int:
        """Hard lifecycle deadline derived from the two user-facing image timeouts."""
        return self.image_stream_timeout_secs + self.image_poll_timeout_secs + 30

    @property
    def image_poll_interval_secs(self) -> float:
        try:
            return max(0.5, float(self.data.get("image_poll_interval_secs", 10.0)))
        except (TypeError, ValueError):
            return 10.0

    @property
    def image_poll_initial_wait_secs(self) -> float:
        """Image generation upstream takes ~30s; polling immediately wastes requests
        and trips a transient 429. Default 10s gives the conversation document time
        to commit before the first poll."""
        try:
            return max(0.0, float(self.data.get("image_poll_initial_wait_secs", 10.0)))
        except (TypeError, ValueError):
            return 10.0

    @property
    def image_account_concurrency(self) -> int:
        return normalize_integer_setting(
            "image_account_concurrency",
            self.data.get("image_account_concurrency"),
        )

    @property
    def image_account_retry_enabled(self) -> bool:
        self.reload_if_changed()
        return _normalize_bool(self.data.get("image_account_retry_enabled"), True)

    @property
    def image_upscale_enabled(self) -> bool:
        self.reload_if_changed()
        return _normalize_bool(self.data.get("image_upscale_enabled"), False)

    @property
    def image_upscale_engine(self) -> str:
        self.reload_if_changed()
        value = str(self.data.get("image_upscale_engine") or "sharp_lanczos3").strip().lower()
        return value if value in {"sharp_lanczos3", "pillow_lanczos"} else "sharp_lanczos3"

    @property
    def account_processing_concurrency(self) -> int:
        self.reload_if_changed()
        return normalize_integer_setting(
            "account_processing_concurrency",
            self.data.get("account_processing_concurrency"),
        )

    @property
    def image_max_account_attempts(self) -> int:
        self.reload_if_changed()
        return normalize_integer_setting(
            "image_max_account_attempts",
            self.data.get("image_max_account_attempts"),
        )

    @property
    def image_parallel_generation(self) -> bool:
        value = self.data.get("image_parallel_generation", True)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @property
    def image_remove_conversation_after_result(self) -> bool:
        self.reload_if_changed()
        return _normalize_bool(self.data.get("image_remove_conversation_after_result"), False)

    @property
    def image_settle_enabled(self) -> bool:
        """图片二次确认机制：找到 file_ids 后等待一段时间再次确认。"""
        value = self.data.get("image_settle_enabled", True)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @property
    def image_check_before_hit_enabled(self) -> bool:
        """先check再hit：通过轮询确认 file_ids 存在后再返回，而非仅依赖 SSE 事件。"""
        value = self.data.get("image_check_before_hit_enabled", True)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @property
    def image_settle_secs(self) -> float:
        """二次确认等待时间（秒）。"""
        return normalize_float_setting(
            "image_settle_secs",
            self.data.get("image_settle_secs"),
        )

    @property
    def auto_remove_invalid_accounts(self) -> bool:
        value = self.data.get("auto_remove_invalid_accounts", True)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @property
    def auto_remove_rate_limited_accounts(self) -> bool:
        value = self.data.get("auto_remove_rate_limited_accounts", False)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @property
    def log_levels(self) -> list[str]:
        levels = self.data.get("log_levels")
        if not isinstance(levels, list):
            return []
        allowed = {"debug", "info", "warning", "error"}
        return [level for item in levels if (level := str(item or "").strip().lower()) in allowed]

    @property
    def sensitive_words(self) -> list[str]:
        words = self.data.get("sensitive_words")
        return [word for item in words if (word := str(item or "").strip())] if isinstance(words, list) else []

    @property
    def ai_review(self) -> dict[str, object]:
        value = self.data.get("ai_review")
        return value if isinstance(value, dict) else {}

    @property
    def global_system_prompt(self) -> str:
        return str(self.data.get("global_system_prompt") or "").strip()

    @property
    def images_dir(self) -> Path:
        path = DATA_DIR / "images"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def image_thumbnails_dir(self) -> Path:
        path = DATA_DIR / "image_thumbnails"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def base_url(self) -> str:
        return str(
            os.getenv("CHATGPT2API_BASE_URL")
            or self.data.get("base_url")
            or ""
        ).strip().rstrip("/")

    @property
    def app_version(self) -> str:
        try:
            value = VERSION_FILE.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return "0.0.0"
        return value or "0.0.0"

    def get(self) -> dict[str, object]:
        with self._lock:
            self.reload_if_changed()
            data = dict(self.data)
            data["refresh_account_interval_minute"] = self.refresh_account_interval_minute
            data["image_retention_days"] = self.image_retention_days
            data["log_retention_days"] = self.log_retention_days
            data["image_min_free_mb"] = self.image_min_free_mb
            data["image_poll_timeout_secs"] = self.image_poll_timeout_secs
            data["image_stream_timeout_secs"] = self.image_stream_timeout_secs
            data["image_poll_interval_secs"] = self.image_poll_interval_secs
            data["image_poll_initial_wait_secs"] = self.image_poll_initial_wait_secs
            data["image_account_concurrency"] = self.image_account_concurrency
            data["account_processing_concurrency"] = self.account_processing_concurrency
            data["image_account_retry_enabled"] = self.image_account_retry_enabled
            data["image_upscale_enabled"] = self.image_upscale_enabled
            data["image_upscale_engine"] = self.image_upscale_engine
            data["image_max_account_attempts"] = self.image_max_account_attempts
            data["image_parallel_generation"] = self.image_parallel_generation
            data["image_remove_conversation_after_result"] = self.image_remove_conversation_after_result
            data["auto_remove_invalid_accounts"] = self.auto_remove_invalid_accounts
            data["auto_remove_rate_limited_accounts"] = self.auto_remove_rate_limited_accounts
            data["log_levels"] = self.log_levels
            data["sensitive_words"] = self.sensitive_words
            data["ai_review"] = self.ai_review
            data["global_system_prompt"] = self.global_system_prompt
            data["backup"] = self.get_backup_settings()
            data["image_storage"] = self.get_image_storage_settings()
            data["chat_completion_cache"] = self.get_chat_completion_cache_settings()
            data["proxy_runtime"] = self.get_public_proxy_runtime_settings()
            data["fallback_proxy"] = self.get_proxy_fallback_settings()
            data["third_party_apps"] = self.get_third_party_apps_settings()
            data.pop("basic", None)
            return data

    def get_proxy_settings(self) -> str:
        return ""

    def get_proxy_fallback_settings(self) -> str:
        return ""

    def get_proxy_runtime_settings(self) -> dict[str, object]:
        return _normalize_proxy_runtime_settings(self.data.get("proxy_runtime"))

    def get_public_proxy_runtime_settings(self) -> dict[str, object]:
        runtime = self.get_proxy_runtime_settings()
        clearance = runtime.get("clearance") if isinstance(runtime.get("clearance"), dict) else {}
        cf_cookies = str(clearance.get("cf_cookies") or "").strip()
        cf_clearance = str(clearance.get("cf_clearance") or "").strip()
        public_clearance = {
            key: copy.deepcopy(clearance.get(key))
            for key in (
                "enabled",
                "mode",
                "user_agent",
                "browser",
                "flaresolverr_url",
                "timeout_sec",
                "refresh_interval",
                "warm_up_on_start",
            )
        }
        public_clearance.update({
            "cf_cookies": "",
            "cf_clearance": "",
            "has_cf_cookies": bool(cf_cookies),
            "has_cf_clearance": bool(cf_clearance),
        })
        public_runtime = {
            key: copy.deepcopy(runtime.get(key))
            for key in (
                "enabled",
                "resource_proxy_url",
                "skip_ssl_verify",
                "reset_session_status_codes",
            )
        }
        public_runtime["clearance"] = public_clearance
        return public_runtime

    def get_third_party_apps_settings(self) -> dict[str, object]:
        return _normalize_third_party_apps_settings(self.data.get("third_party_apps"))

    def update(self, data: dict[str, object]) -> dict[str, object]:
        with self._lock:
            self.reload_if_changed()
            updates = dict(data or {})
            updates.pop("auth-key", None)
            updates.pop("basic", None)
            proxy_keys = {"proxy", "fallback_proxy", "proxy_profiles", "proxy_groups"}
            if proxy_keys.intersection(updates):
                raise ValueError("proxy configuration must be updated through ProxyManagementService")

            group_update = updates.pop("account_groups", None)
            if group_update is not None and updates:
                raise ValueError("account groups and system settings have separate transaction boundaries")

            if group_update is not None:
                if not isinstance(group_update, list):
                    raise ValueError("account_groups must be a list")
                self._groups_repository.update({"items": copy.deepcopy(group_update)})
                self.data = self._load()
                self._last_repository_refresh_at = monotonic()
                return self.get()

            for key in _REMOVED_TOP_LEVEL_SETTINGS:
                updates.pop(key, None)
            if "backup" in updates:
                updates["backup"] = _normalize_backup_settings(updates.get("backup"))
            if "image_storage" in updates:
                updates["image_storage"] = _normalize_image_storage_settings(updates.get("image_storage"))
                _validate_image_storage_settings(updates["image_storage"])
            if "chat_completion_cache" in updates:
                updates["chat_completion_cache"] = _normalize_chat_completion_cache_settings(
                    updates.get("chat_completion_cache")
                )
            if "third_party_apps" in updates:
                updates["third_party_apps"] = _normalize_third_party_apps_settings(updates.get("third_party_apps"))
            if "proxy_runtime" in updates:
                incoming_runtime = updates.get("proxy_runtime")
                if isinstance(incoming_runtime, dict):
                    previous_clearance = self.get_proxy_runtime_settings().get("clearance")
                    if isinstance(previous_clearance, dict):
                        incoming_runtime = dict(incoming_runtime)
                        incoming_runtime["_existing_cf_cookies"] = previous_clearance.get("cf_cookies")
                        incoming_runtime["_existing_cf_clearance"] = previous_clearance.get("cf_clearance")
                updates["proxy_runtime"] = _normalize_proxy_runtime_settings(incoming_runtime)
            updates.pop("backup_state", None)
            if updates:
                self._settings_repository.update(updates)
            self.data = self._load()
            self._last_repository_refresh_at = monotonic()
        return self.get()

    def get_backup_settings(self) -> dict[str, object]:
        return _normalize_backup_settings(self.data.get("backup"))

    def get_image_storage_settings(self) -> dict[str, object]:
        return _normalize_image_storage_settings(self.data.get("image_storage"))

    def get_chat_completion_cache_settings(self) -> dict[str, object]:
        return _normalize_chat_completion_cache_settings(self.data.get("chat_completion_cache"))

    def get_storage_backend(self) -> StorageBackend:
        """获取存储后端实例（单例）"""
        if self._storage_backend is None:
            from services.storage.factory import create_storage_backend
            self._storage_backend = create_storage_backend(DATA_DIR)
        return self._storage_backend


config = ConfigStore(CONFIG_FILE)
