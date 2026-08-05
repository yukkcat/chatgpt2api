from __future__ import annotations

import copy
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
import threading
from typing import Any, Iterable, Mapping

from contracts.settings import (
    AIReviewSettings,
    BackupIncludeSettings,
    BackupSettings,
    GenBoxPushSettings,
    ImageStorageSettings,
    InfiniteCanvasSettings,
    PublicInfiniteCanvasSettings,
    PublicThirdPartyAppsView,
    PublicThirdPartyAppsSettings,
    ProxyRuntimeClearanceSettings,
    ProxyRuntimeSettings,
    SettingsFieldMetadata,
    SettingsMutationResult,
    SettingsPatch,
    SettingsValues,
    SettingsView,
    ThirdPartyAppsSettings,
)
from contracts.settings_specification import (
    normalize_float_setting,
    normalize_integer_setting,
    numeric_setting_spec,
)
from services.config import (
    DEFAULT_BACKUP_INCLUDE,
    DEFAULT_GENBOX_PUSH,
    DEFAULT_IMAGE_STORAGE,
    DEFAULT_PROXY_RUNTIME,
    DEFAULT_PROXY_RUNTIME_USER_AGENT,
    DEFAULT_THIRD_PARTY_APPS,
    config,
)


SETTINGS_SCHEMA_VERSION = 1

_MANAGED_TOP_LEVEL_FIELDS = (
    "proxy_runtime",
    "base_url",
    "refresh_account_interval_minute",
    "image_retention_days",
    "log_retention_days",
    "image_poll_timeout_secs",
    "image_stream_timeout_secs",
    "image_account_concurrency",
    "account_processing_concurrency",
    "image_account_retry_enabled",
    "image_upscale_enabled",
    "image_upscale_engine",
    "image_max_account_attempts",
    "image_remove_conversation_after_result",
    "image_settle_enabled",
    "image_settle_secs",
    "auto_remove_invalid_accounts",
    "auto_remove_rate_limited_accounts",
    "log_levels",
    "global_system_prompt",
    "sensitive_words",
    "ai_review",
    "image_storage",
    "genbox_push",
    "backup",
    "third_party_apps",
)

_SENSITIVE_PATHS = (
    ("ai_review", "api_key"),
    ("image_storage", "webdav_password"),
    ("genbox_push", "push_key"),
    ("backup", "secret_access_key"),
    ("backup", "passphrase"),
    ("proxy_runtime", "clearance", "cf_cookies"),
    ("proxy_runtime", "clearance", "cf_clearance"),
)


class SettingsRevisionConflictError(ValueError):
    pass


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _url(value: object, default: str = "") -> str:
    return _text(value, default).rstrip("/")


def _bool(value: object, default: bool) -> bool:
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


def _dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for raw in value if (item := _text(raw))]


def _enum(value: object, default: str, options: set[str]) -> str:
    normalized = _text(value).lower()
    return normalized if normalized in options else default


def _deep_merge(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in patch.items():
        previous = merged.get(key)
        if isinstance(previous, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(previous, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _path_exists(source: Mapping[str, Any], path: Iterable[str]) -> bool:
    current: object = source
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def _path_value(source: Mapping[str, Any], path: Iterable[str]) -> object:
    current: object = source
    for part in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _delete_path(source: dict[str, Any], path: tuple[str, ...]) -> None:
    current: object = source
    parents: list[tuple[dict[str, Any], str]] = []
    for part in path[:-1]:
        if not isinstance(current, dict) or not isinstance(current.get(part), dict):
            return
        parents.append((current, part))
        current = current[part]
    if isinstance(current, dict):
        current.pop(path[-1], None)
    for parent, key in reversed(parents):
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            parent.pop(key, None)


def _leaf_paths(value: Mapping[str, Any], prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    paths: list[tuple[str, ...]] = []
    for key, item in value.items():
        path = (*prefix, key)
        if isinstance(item, Mapping):
            paths.extend(_leaf_paths(item, path))
        else:
            paths.append(path)
    return paths


def _field_metadata(
    default: object,
    *,
    min: int | float | None = None,
    max: int | float | None = None,
    options: Iterable[str] = (),
    unit: str | None = None,
    read_only: bool = False,
    restart_required: bool = False,
    sensitive: bool = False,
) -> dict[str, Any]:
    return {
        "default": default,
        "min": min,
        "max": max,
        "options": list(options),
        "unit": unit,
        "read_only": read_only,
        "restart_required": restart_required,
        "sensitive": sensitive,
    }


def _numeric_field_metadata(name: str) -> dict[str, Any]:
    spec = numeric_setting_spec(name)
    return _field_metadata(
        spec.default,
        min=spec.minimum,
        max=spec.maximum,
        unit=spec.unit,
    )


_FIELD_SPECS: dict[str, dict[str, Any]] = {
    "proxy_runtime.enabled": _field_metadata(False),
    "proxy_runtime.resource_proxy_url": _field_metadata(""),
    "proxy_runtime.skip_ssl_verify": _field_metadata(False),
    "proxy_runtime.clearance.enabled": _field_metadata(False),
    "proxy_runtime.clearance.mode": _field_metadata("none", options=("none", "manual", "flaresolverr")),
    "proxy_runtime.clearance.cf_cookies": _field_metadata("", sensitive=True),
    "proxy_runtime.clearance.cf_clearance": _field_metadata("", sensitive=True),
    "proxy_runtime.clearance.user_agent": _field_metadata(DEFAULT_PROXY_RUNTIME_USER_AGENT),
    "proxy_runtime.clearance.flaresolverr_url": _field_metadata(""),
    "proxy_runtime.clearance.timeout_sec": _numeric_field_metadata("proxy_runtime.clearance.timeout_sec"),
    "proxy_runtime.clearance.refresh_interval": _numeric_field_metadata("proxy_runtime.clearance.refresh_interval"),
    "proxy_runtime.clearance.warm_up_on_start": _field_metadata(False),
    "base_url": _field_metadata(""),
    "refresh_account_interval_minute": _numeric_field_metadata("refresh_account_interval_minute"),
    "image_retention_days": _numeric_field_metadata("image_retention_days"),
    "log_retention_days": _numeric_field_metadata("log_retention_days"),
    "image_poll_timeout_secs": _numeric_field_metadata("image_poll_timeout_secs"),
    "image_stream_timeout_secs": _numeric_field_metadata("image_stream_timeout_secs"),
    "image_account_concurrency": _numeric_field_metadata("image_account_concurrency"),
    "account_processing_concurrency": _numeric_field_metadata("account_processing_concurrency"),
    "image_account_retry_enabled": _field_metadata(True),
    "image_upscale_enabled": _field_metadata(False),
    "image_upscale_engine": _field_metadata("sharp_lanczos3", options=("sharp_lanczos3", "pillow_lanczos")),
    "image_max_account_attempts": _numeric_field_metadata("image_max_account_attempts"),
    "image_remove_conversation_after_result": _field_metadata(False),
    "image_settle_enabled": _field_metadata(True),
    "image_settle_secs": _numeric_field_metadata("image_settle_secs"),
    "auto_remove_invalid_accounts": _field_metadata(True),
    "auto_remove_rate_limited_accounts": _field_metadata(False),
    "log_levels": _field_metadata([], options=("debug", "info", "warning", "error")),
    "global_system_prompt": _field_metadata(""),
    "sensitive_words": _field_metadata([]),
    "ai_review.enabled": _field_metadata(False),
    "ai_review.base_url": _field_metadata(""),
    "ai_review.api_key": _field_metadata("", sensitive=True),
    "ai_review.model": _field_metadata(""),
    "ai_review.prompt": _field_metadata(""),
    "image_storage.enabled": _field_metadata(False),
    "image_storage.mode": _field_metadata("local", options=("local", "webdav", "both")),
    "image_storage.webdav_url": _field_metadata(""),
    "image_storage.webdav_username": _field_metadata(""),
    "image_storage.webdav_password": _field_metadata("", sensitive=True),
    "image_storage.webdav_root_path": _field_metadata(DEFAULT_IMAGE_STORAGE["webdav_root_path"]),
    "image_storage.public_base_url": _field_metadata(""),
    "genbox_push.enabled": _field_metadata(False),
    "genbox_push.base_url": _field_metadata(""),
    "genbox_push.source_id": _field_metadata(""),
    "genbox_push.push_key": _field_metadata("", sensitive=True),
    "genbox_push.timeout_secs": _field_metadata(20, min=5, max=120, unit="seconds"),
    "genbox_push.auto_push_after_studio": _field_metadata(False),
    "backup.enabled": _field_metadata(False),
    "backup.provider": _field_metadata("cloudflare_r2", options=("cloudflare_r2",), read_only=True),
    "backup.account_id": _field_metadata(""),
    "backup.access_key_id": _field_metadata(""),
    "backup.secret_access_key": _field_metadata("", sensitive=True),
    "backup.bucket": _field_metadata(""),
    "backup.prefix": _field_metadata("backups"),
    "backup.interval_minutes": _numeric_field_metadata("backup.interval_minutes"),
    "backup.rotation_keep": _numeric_field_metadata("backup.rotation_keep"),
    "backup.encrypt": _field_metadata(False),
    "backup.passphrase": _field_metadata("", sensitive=True),
    **{
        f"backup.include.{key}": _field_metadata(value)
        for key, value in DEFAULT_BACKUP_INCLUDE.items()
    },
    "third_party_apps.infinite_canvas.enabled": _field_metadata(False),
    "third_party_apps.infinite_canvas.url": _field_metadata("https://canvas.best"),
}


class SettingsManagementService:
    """Projects and mutates only the admin settings-page contract."""

    def __init__(self, config_store: Any = None) -> None:
        self._config = config_store or config
        self._mutation_lock = threading.RLock()

    def view(self) -> SettingsView:
        with self._mutation_lock, self._config_lock():
            effective, stored = self._snapshots()
            return self._build_view(effective, stored)

    def public_third_party_apps_view(self) -> PublicThirdPartyAppsView:
        with self._mutation_lock, self._config_lock():
            effective, stored = self._snapshots()
            settings = self._project_settings(effective, stored)
            canvas = settings.third_party_apps.infinite_canvas
            return PublicThirdPartyAppsView(
                api_base_url=settings.base_url,
                third_party_apps=PublicThirdPartyAppsSettings(
                    infinite_canvas=PublicInfiniteCanvasSettings(
                        enabled=canvas.enabled,
                        url=canvas.url,
                    ),
                ),
            )

    def update(self, patch: SettingsPatch) -> SettingsMutationResult:
        values = patch.model_dump(mode="python", exclude_unset=True)
        expected_revision = _text(values.pop("revision"))
        clear_genbox_push = bool(_path_value(values, ("genbox_push", "clear_push_key")))
        self._drop_blank_sensitive_values(values)

        with self._mutation_lock, self._config_lock():
            effective, stored = self._snapshots()
            current_revision = self._revision(effective, stored)
            if expected_revision != current_revision:
                raise SettingsRevisionConflictError("settings revision does not match current configuration")

            if "base_url" in values and self._environment_base_url():
                raise ValueError("base_url is read-only while CHATGPT2API_BASE_URL is configured")

            updates = self._storage_updates(values, effective, stored)
            if clear_genbox_push:
                genbox_updates = updates.get("genbox_push")
                if isinstance(genbox_updates, dict):
                    genbox_updates.pop("clear_push_key", None)
                    incoming_genbox = values.get("genbox_push")
                    incoming_push_key = incoming_genbox.get("push_key") if isinstance(incoming_genbox, Mapping) else None
                    if not _text(incoming_push_key):
                        genbox_updates.pop("push_key", None)
            requested_paths = _leaf_paths(values)
            current_values = self._project_settings(effective, stored).model_dump(mode="python")
            candidate_paths = [
                path
                for path in requested_paths
                if self._comparison_value(current_values, stored, path) != self._comparison_value(updates, updates, path)
            ]
            changed_roots = {path[0] for path in candidate_paths}
            if clear_genbox_push:
                changed_roots.add("genbox_push")
            changed_updates = {
                key: value for key, value in updates.items()
                if key in changed_roots
            }
            if changed_updates:
                self._config.update(changed_updates)

            next_effective, next_stored = self._snapshots()
            view = self._build_view(next_effective, next_stored)
            next_values = view.settings.model_dump(mode="python")
            changed_paths = [
                path
                for path in requested_paths
                if self._comparison_value(current_values, stored, path)
                != self._comparison_value(next_values, next_stored, path)
            ]
            changed_fields = sorted(".".join(path) for path in changed_paths)
            if clear_genbox_push:
                changed_fields.append("genbox_push.push_key")
                changed_fields = sorted(set(changed_fields))
            restart_required = any(
                view.fields.get(path, SettingsFieldMetadata(source="configured")).restart_required
                for path in changed_fields
            )
            return SettingsMutationResult(
                schema_version=view.schema_version,
                generated_at=view.generated_at,
                revision=view.revision,
                settings=view.settings,
                fields=view.fields,
                changed_fields=changed_fields,
                restart_required=restart_required,
            )

    def _config_lock(self):
        lock = getattr(self._config, "mutation_lock", None)
        if lock is None:
            lock = getattr(self._config, "_lock", None)
        return lock if lock is not None else nullcontext()

    @staticmethod
    def _comparison_value(
        projected: Mapping[str, Any],
        stored: Mapping[str, Any],
        path: tuple[str, ...],
    ) -> object:
        if path in _SENSITIVE_PATHS:
            return _text(_path_value(stored, path))
        return _path_value(projected, path)

    def _snapshots(self) -> tuple[dict[str, Any], dict[str, Any]]:
        value = self._config.get()
        effective = copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}
        raw = getattr(self._config, "data", None)
        stored = copy.deepcopy(dict(raw)) if isinstance(raw, Mapping) else copy.deepcopy(effective)

        environment_base_url = self._environment_base_url()
        effective_base_url = _url(getattr(self._config, "base_url", ""))
        stored_base_url = _url(stored.get("base_url", effective.get("base_url")))
        effective["base_url"] = environment_base_url or effective_base_url or stored_base_url
        return effective, stored

    def _build_view(self, effective: dict[str, Any], stored: dict[str, Any]) -> SettingsView:
        settings = self._project_settings(effective, stored)
        return SettingsView(
            schema_version=SETTINGS_SCHEMA_VERSION,
            generated_at=_generated_at(),
            revision=self._revision(effective, stored),
            settings=settings,
            fields=self._metadata(stored),
        )

    def _project_settings(self, effective: dict[str, Any], stored: dict[str, Any]) -> SettingsValues:
        proxy_runtime = _dict(effective.get("proxy_runtime"))
        stored_proxy_runtime = _dict(stored.get("proxy_runtime"))
        if stored_proxy_runtime:
            proxy_runtime = _deep_merge(proxy_runtime, stored_proxy_runtime)
        clearance = _dict(proxy_runtime.get("clearance"))

        ai_review = _dict(effective.get("ai_review"))
        stored_ai_review = _dict(stored.get("ai_review"))
        image_storage = _dict(effective.get("image_storage"))
        stored_image_storage = _dict(stored.get("image_storage"))
        genbox_push = _dict(effective.get("genbox_push"))
        stored_genbox_push = _dict(stored.get("genbox_push"))
        backup = _dict(effective.get("backup"))
        stored_backup = _dict(stored.get("backup"))
        backup_include = _dict(backup.get("include"))
        third_party_apps = _dict(effective.get("third_party_apps"))
        infinite_canvas = _dict(third_party_apps.get("infinite_canvas"))

        log_levels = [
            level
            for level in dict.fromkeys(item.lower() for item in _string_list(effective.get("log_levels")))
            if level in {"debug", "info", "warning", "error"}
        ]
        sensitive_words = list(dict.fromkeys(_string_list(effective.get("sensitive_words"))))

        return SettingsValues(
            proxy_runtime=ProxyRuntimeSettings(
                enabled=_bool(proxy_runtime.get("enabled"), bool(DEFAULT_PROXY_RUNTIME["enabled"])),
                resource_proxy_url=_text(proxy_runtime.get("resource_proxy_url")),
                skip_ssl_verify=_bool(proxy_runtime.get("skip_ssl_verify"), False),
                clearance=ProxyRuntimeClearanceSettings(
                    enabled=_bool(clearance.get("enabled"), False),
                    mode=_enum(clearance.get("mode"), "none", {"none", "manual", "flaresolverr"}),
                    cf_cookies="",
                    has_cf_cookies=bool(_text(_path_value(stored_proxy_runtime, ("clearance", "cf_cookies")))),
                    cf_clearance="",
                    has_cf_clearance=bool(_text(_path_value(stored_proxy_runtime, ("clearance", "cf_clearance")))),
                    user_agent=_text(clearance.get("user_agent"), DEFAULT_PROXY_RUNTIME_USER_AGENT) or DEFAULT_PROXY_RUNTIME_USER_AGENT,
                    flaresolverr_url=_url(clearance.get("flaresolverr_url")),
                    timeout_sec=normalize_integer_setting(
                        "proxy_runtime.clearance.timeout_sec",
                        clearance.get("timeout_sec"),
                    ),
                    refresh_interval=normalize_integer_setting(
                        "proxy_runtime.clearance.refresh_interval",
                        clearance.get("refresh_interval"),
                    ),
                    warm_up_on_start=_bool(clearance.get("warm_up_on_start"), False),
                ),
            ),
            base_url=_url(effective.get("base_url")),
            refresh_account_interval_minute=normalize_integer_setting(
                "refresh_account_interval_minute",
                effective.get("refresh_account_interval_minute"),
            ),
            image_retention_days=normalize_integer_setting(
                "image_retention_days",
                effective.get("image_retention_days"),
            ),
            log_retention_days=normalize_integer_setting(
                "log_retention_days",
                effective.get("log_retention_days"),
            ),
            image_poll_timeout_secs=normalize_integer_setting(
                "image_poll_timeout_secs",
                effective.get("image_poll_timeout_secs"),
            ),
            image_stream_timeout_secs=normalize_integer_setting(
                "image_stream_timeout_secs",
                effective.get("image_stream_timeout_secs"),
            ),
            image_account_concurrency=normalize_integer_setting(
                "image_account_concurrency",
                effective.get("image_account_concurrency"),
            ),
            account_processing_concurrency=normalize_integer_setting(
                "account_processing_concurrency",
                effective.get("account_processing_concurrency"),
            ),
            image_account_retry_enabled=_bool(effective.get("image_account_retry_enabled"), True),
            image_upscale_enabled=_bool(effective.get("image_upscale_enabled"), False),
            image_upscale_engine=_enum(
                effective.get("image_upscale_engine"),
                "sharp_lanczos3",
                {"sharp_lanczos3", "pillow_lanczos"},
            ),
            image_max_account_attempts=normalize_integer_setting(
                "image_max_account_attempts",
                effective.get("image_max_account_attempts"),
            ),
            image_remove_conversation_after_result=_bool(
                effective.get("image_remove_conversation_after_result"),
                False,
            ),
            image_settle_enabled=_bool(effective.get("image_settle_enabled"), True),
            image_settle_secs=normalize_float_setting(
                "image_settle_secs",
                effective.get("image_settle_secs"),
            ),
            auto_remove_invalid_accounts=_bool(effective.get("auto_remove_invalid_accounts"), True),
            auto_remove_rate_limited_accounts=_bool(
                effective.get("auto_remove_rate_limited_accounts"),
                False,
            ),
            log_levels=log_levels,
            global_system_prompt=_text(effective.get("global_system_prompt")),
            sensitive_words=sensitive_words,
            ai_review=AIReviewSettings(
                enabled=_bool(ai_review.get("enabled"), False),
                base_url=_url(ai_review.get("base_url")),
                api_key="",
                has_api_key=bool(_text(stored_ai_review.get("api_key"))),
                model=_text(ai_review.get("model")),
                prompt=_text(ai_review.get("prompt")),
            ),
            image_storage=ImageStorageSettings(
                enabled=_bool(image_storage.get("enabled"), False),
                mode=_enum(image_storage.get("mode"), "local", {"local", "webdav", "both"}),
                webdav_url=_url(image_storage.get("webdav_url")),
                webdav_username=_text(image_storage.get("webdav_username")),
                webdav_password="",
                has_webdav_password=bool(_text(stored_image_storage.get("webdav_password"))),
                webdav_root_path=(
                    _text(image_storage.get("webdav_root_path"), str(DEFAULT_IMAGE_STORAGE["webdav_root_path"]))
                    or str(DEFAULT_IMAGE_STORAGE["webdav_root_path"])
                ),
                public_base_url=_url(image_storage.get("public_base_url")),
            ),
            genbox_push=GenBoxPushSettings(
                enabled=_bool(genbox_push.get("enabled"), False),
                base_url=_url(genbox_push.get("base_url")),
                source_id=_text(genbox_push.get("source_id")),
                push_key="",
                has_push_key=bool(_text(stored_genbox_push.get("push_key"))),
                timeout_secs=max(5, min(120, int(genbox_push.get("timeout_secs") or DEFAULT_GENBOX_PUSH["timeout_secs"]))),
                auto_push_after_studio=_bool(genbox_push.get("auto_push_after_studio"), False),
            ),
            backup=BackupSettings(
                enabled=_bool(backup.get("enabled"), False),
                provider="cloudflare_r2",
                account_id=_text(backup.get("account_id")),
                access_key_id=_text(backup.get("access_key_id")),
                secret_access_key="",
                has_secret_access_key=bool(_text(stored_backup.get("secret_access_key"))),
                bucket=_text(backup.get("bucket")),
                prefix=_text(backup.get("prefix"), "backups").strip("/") or "backups",
                interval_minutes=normalize_integer_setting(
                    "backup.interval_minutes",
                    backup.get("interval_minutes"),
                ),
                rotation_keep=normalize_integer_setting(
                    "backup.rotation_keep",
                    backup.get("rotation_keep"),
                ),
                encrypt=_bool(backup.get("encrypt"), False),
                passphrase="",
                has_passphrase=bool(_text(stored_backup.get("passphrase"))),
                include=BackupIncludeSettings(**{
                    key: _bool(backup_include.get(key), bool(default))
                    for key, default in DEFAULT_BACKUP_INCLUDE.items()
                }),
            ),
            third_party_apps=ThirdPartyAppsSettings(
                infinite_canvas=InfiniteCanvasSettings(
                    enabled=_bool(infinite_canvas.get("enabled"), False),
                    url=(
                        _url(
                            infinite_canvas.get("url"),
                            str(DEFAULT_THIRD_PARTY_APPS["infinite_canvas"]["url"]),
                        )
                        or str(DEFAULT_THIRD_PARTY_APPS["infinite_canvas"]["url"])
                    ),
                ),
            ),
        )

    def _metadata(self, stored: dict[str, Any]) -> dict[str, SettingsFieldMetadata]:
        environment_base_url = self._environment_base_url()
        fields: dict[str, SettingsFieldMetadata] = {}
        for dotted_path, spec in _FIELD_SPECS.items():
            path = tuple(dotted_path.split("."))
            source = "configured" if _path_exists(stored, path) else "default"
            values = dict(spec)
            if dotted_path == "base_url" and environment_base_url:
                source = "environment"
                values["read_only"] = True
            fields[dotted_path] = SettingsFieldMetadata(source=source, **values)
        return fields

    def _storage_updates(
        self,
        values: dict[str, Any],
        effective: dict[str, Any],
        stored: dict[str, Any],
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        for key, value in values.items():
            if key not in _MANAGED_TOP_LEVEL_FIELDS:
                continue
            if isinstance(value, Mapping):
                base = stored.get(key)
                if not isinstance(base, Mapping):
                    base = effective.get(key)
                updates[key] = _deep_merge(_dict(base), value)
            else:
                updates[key] = copy.deepcopy(value)
        return updates

    @staticmethod
    def _drop_blank_sensitive_values(values: dict[str, Any]) -> None:
        for path in _SENSITIVE_PATHS:
            if _path_exists(values, path) and not _text(_path_value(values, path)):
                _delete_path(values, path)

    def _revision(self, effective: dict[str, Any], stored: dict[str, Any]) -> str:
        relevant: dict[str, Any] = {}
        for key in _MANAGED_TOP_LEVEL_FIELDS:
            if key == "base_url":
                relevant[key] = _url(effective.get(key))
            elif key in stored:
                relevant[key] = stored.get(key)
            else:
                relevant[key] = effective.get(key)
        encoded = json.dumps(
            relevant,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    @staticmethod
    def _environment_base_url() -> str:
        return _url(os.getenv("CHATGPT2API_BASE_URL"))


settings_management_service = SettingsManagementService()
