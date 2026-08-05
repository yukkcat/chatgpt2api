from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal


NumericKind = Literal["integer", "float"]


@dataclass(frozen=True)
class NumericSettingSpec:
    default: int | float
    minimum: int | float
    maximum: int | float | None = None
    unit: str | None = None
    kind: NumericKind = "integer"


NUMERIC_SETTING_SPECS = MappingProxyType({
    "proxy_runtime.clearance.timeout_sec": NumericSettingSpec(60, 1, unit="seconds"),
    "proxy_runtime.clearance.refresh_interval": NumericSettingSpec(3600, 60, unit="seconds"),
    "refresh_account_interval_minute": NumericSettingSpec(5, 1, unit="minutes"),
    "image_retention_days": NumericSettingSpec(30, 1, unit="days"),
    "log_retention_days": NumericSettingSpec(30, 1, unit="days"),
    "image_poll_timeout_secs": NumericSettingSpec(60, 1, unit="seconds"),
    "image_stream_timeout_secs": NumericSettingSpec(80, 1, unit="seconds"),
    "image_account_concurrency": NumericSettingSpec(1, 1, 3),
    "account_processing_concurrency": NumericSettingSpec(30, 1, 100),
    "image_max_account_attempts": NumericSettingSpec(4, 2),
    "image_settle_secs": NumericSettingSpec(5.0, 0.5, unit="seconds", kind="float"),
    "backup.interval_minutes": NumericSettingSpec(360, 1, unit="minutes"),
    "backup.rotation_keep": NumericSettingSpec(10, 0),
})


def numeric_setting_spec(name: str) -> NumericSettingSpec:
    try:
        return NUMERIC_SETTING_SPECS[name]
    except KeyError as exc:
        raise KeyError(f"unknown numeric setting: {name}") from exc


def normalize_integer_setting(name: str, value: object) -> int:
    spec = numeric_setting_spec(name)
    if spec.kind != "integer":
        raise TypeError(f"setting is not an integer: {name}")
    try:
        normalized = int(value)
    except (OverflowError, TypeError, ValueError):
        normalized = int(spec.default)
    normalized = max(int(spec.minimum), normalized)
    if spec.maximum is not None:
        normalized = min(int(spec.maximum), normalized)
    return normalized


def normalize_float_setting(name: str, value: object) -> float:
    spec = numeric_setting_spec(name)
    if spec.kind != "float":
        raise TypeError(f"setting is not a float: {name}")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError):
        normalized = float(spec.default)
    normalized = max(float(spec.minimum), normalized)
    if spec.maximum is not None:
        normalized = min(float(spec.maximum), normalized)
    return normalized
