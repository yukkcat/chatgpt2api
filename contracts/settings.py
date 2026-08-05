from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from contracts.settings_specification import numeric_setting_spec


LogLevel = Literal["debug", "info", "warning", "error"]
ImageUpscaleEngine = Literal["sharp_lanczos3", "pillow_lanczos"]
ImageStorageMode = Literal["local", "webdav", "both"]
ProxyRuntimeClearanceMode = Literal["none", "manual", "flaresolverr"]
SettingsFieldSource = Literal["default", "configured", "environment"]


def _numeric_field(name: str):
    spec = numeric_setting_spec(name)
    return Field(default=spec.default, ge=spec.minimum, le=spec.maximum)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("by_alias", True)
        return super().model_dump(*args, **kwargs)


class SettingsFieldMetadata(_StrictModel):
    source: SettingsFieldSource
    default: Any = None
    min: int | float | None = None
    max: int | float | None = None
    options: list[str] = Field(default_factory=list)
    unit: str | None = None
    read_only: bool = False
    restart_required: bool = False
    sensitive: bool = False


class _AIReviewFields(_StrictModel):
    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    prompt: str = ""


class AIReviewSettings(_AIReviewFields):
    has_api_key: bool = False


class AIReviewPatch(_AIReviewFields):
    pass


class _ImageStorageFields(_StrictModel):
    enabled: bool = False
    mode: ImageStorageMode = "local"
    webdav_url: str = ""
    webdav_username: str = ""
    webdav_password: str = ""
    webdav_root_path: str = "chatgpt2api/images"
    public_base_url: str = ""


class ImageStorageSettings(_ImageStorageFields):
    has_webdav_password: bool = False


class ImageStoragePatch(_ImageStorageFields):
    pass


class _GenBoxPushFields(_StrictModel):
    enabled: bool = False
    base_url: str = ""
    source_id: str = ""
    push_key: str = ""
    timeout_secs: int = Field(default=20, ge=5, le=120)
    auto_push_after_studio: bool = False


class GenBoxPushSettings(_GenBoxPushFields):
    has_push_key: bool = False


class GenBoxPushPatch(_GenBoxPushFields):
    clear_push_key: bool = False


class BackupIncludeSettings(_StrictModel):
    image_tasks: bool = True
    editable_files: bool = True
    images: bool = False


class _BackupFields(_StrictModel):
    enabled: bool = False
    account_id: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    bucket: str = ""
    prefix: str = "backups"
    interval_minutes: int = _numeric_field("backup.interval_minutes")
    rotation_keep: int = _numeric_field("backup.rotation_keep")
    encrypt: bool = False
    passphrase: str = ""
    include: BackupIncludeSettings = Field(default_factory=BackupIncludeSettings)


class BackupSettings(_BackupFields):
    provider: Literal["cloudflare_r2"] = "cloudflare_r2"
    has_secret_access_key: bool = False
    has_passphrase: bool = False


class BackupPatch(_BackupFields):
    pass


class _ProxyRuntimeClearanceFields(_StrictModel):
    enabled: bool = False
    mode: ProxyRuntimeClearanceMode = "none"
    cf_cookies: str = ""
    cf_clearance: str = ""
    user_agent: str = ""
    flaresolverr_url: str = ""
    timeout_sec: int = _numeric_field("proxy_runtime.clearance.timeout_sec")
    refresh_interval: int = _numeric_field("proxy_runtime.clearance.refresh_interval")
    warm_up_on_start: bool = False


class ProxyRuntimeClearanceSettings(_ProxyRuntimeClearanceFields):
    has_cf_cookies: bool = False
    has_cf_clearance: bool = False


class ProxyRuntimeClearancePatch(_ProxyRuntimeClearanceFields):
    pass


class ProxyRuntimeSettings(_StrictModel):
    enabled: bool = False
    resource_proxy_url: str = ""
    skip_ssl_verify: bool = False
    clearance: ProxyRuntimeClearanceSettings = Field(default_factory=ProxyRuntimeClearanceSettings)


class InfiniteCanvasSettings(_StrictModel):
    enabled: bool = False
    url: str = "https://canvas.best"


class ThirdPartyAppsSettings(_StrictModel):
    infinite_canvas: InfiniteCanvasSettings = Field(default_factory=InfiniteCanvasSettings)


class PublicInfiniteCanvasSettings(_StrictModel):
    enabled: bool = False
    url: str = "https://canvas.best"


class PublicThirdPartyAppsSettings(_StrictModel):
    infinite_canvas: PublicInfiniteCanvasSettings = Field(default_factory=PublicInfiniteCanvasSettings)


class PublicThirdPartyAppsView(_StrictModel):
    api_base_url: str = ""
    third_party_apps: PublicThirdPartyAppsSettings = Field(default_factory=PublicThirdPartyAppsSettings)


class ProxyRuntimePatch(_StrictModel):
    enabled: bool = False
    resource_proxy_url: str = ""
    skip_ssl_verify: bool = False
    clearance: ProxyRuntimeClearancePatch = Field(default_factory=ProxyRuntimeClearancePatch)


class _SettingsEditableFields(_StrictModel):
    proxy_runtime: ProxyRuntimePatch = Field(default_factory=ProxyRuntimePatch)
    base_url: str = ""
    refresh_account_interval_minute: int = _numeric_field("refresh_account_interval_minute")
    image_retention_days: int = _numeric_field("image_retention_days")
    log_retention_days: int = _numeric_field("log_retention_days")
    image_poll_timeout_secs: int = _numeric_field("image_poll_timeout_secs")
    image_stream_timeout_secs: int = _numeric_field("image_stream_timeout_secs")
    image_account_concurrency: int = _numeric_field("image_account_concurrency")
    account_processing_concurrency: int = _numeric_field("account_processing_concurrency")
    image_account_retry_enabled: bool = True
    image_upscale_enabled: bool = False
    image_upscale_engine: ImageUpscaleEngine = "sharp_lanczos3"
    image_max_account_attempts: int = _numeric_field("image_max_account_attempts")
    image_remove_conversation_after_result: bool = False
    image_settle_enabled: bool = True
    image_settle_secs: float = _numeric_field("image_settle_secs")
    auto_remove_invalid_accounts: bool = True
    auto_remove_rate_limited_accounts: bool = False
    log_levels: list[LogLevel] = Field(default_factory=list)
    global_system_prompt: str = ""
    sensitive_words: list[str] = Field(default_factory=list)
    ai_review: AIReviewPatch = Field(default_factory=AIReviewPatch)
    image_storage: ImageStoragePatch = Field(default_factory=ImageStoragePatch)
    genbox_push: GenBoxPushPatch = Field(default_factory=GenBoxPushPatch)
    backup: BackupPatch = Field(default_factory=BackupPatch)
    third_party_apps: ThirdPartyAppsSettings = Field(default_factory=ThirdPartyAppsSettings)

    @field_validator("log_levels")
    @classmethod
    def deduplicate_log_levels(cls, value: list[LogLevel]) -> list[LogLevel]:
        return list(dict.fromkeys(value))


class SettingsValues(_SettingsEditableFields):
    proxy_runtime: ProxyRuntimeSettings = Field(default_factory=ProxyRuntimeSettings)
    ai_review: AIReviewSettings = Field(default_factory=AIReviewSettings)
    image_storage: ImageStorageSettings = Field(default_factory=ImageStorageSettings)
    genbox_push: GenBoxPushSettings = Field(default_factory=GenBoxPushSettings)
    backup: BackupSettings = Field(default_factory=BackupSettings)


class SettingsPatch(_SettingsEditableFields):
    revision: str = Field(min_length=1, max_length=64)

    @field_validator("revision")
    @classmethod
    def normalize_revision(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("revision must not be blank")
        return normalized


class SettingsView(_StrictModel):
    schema_version: int = Field(ge=1)
    generated_at: str
    revision: str
    settings: SettingsValues
    fields: dict[str, SettingsFieldMetadata]


class SettingsMutationResult(_StrictModel):
    schema_version: int = Field(ge=1)
    generated_at: str
    revision: str
    settings: SettingsValues
    fields: dict[str, SettingsFieldMetadata]
    changed_fields: list[str] = Field(default_factory=list)
    restart_required: bool = False
