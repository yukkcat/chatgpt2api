"""Normalize credential fields supplied by external account import adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping


_CREDENTIAL_CONTAINERS = ("credentials", "credential", "tokens", "auth")
_NORMALIZED_CREDENTIAL_CONTAINERS = {
    value.casefold().replace("_", "").replace("-", "")
    for value in _CREDENTIAL_CONTAINERS
}
_CREDENTIAL_ALIASES = {
    "access_token": ("access_token", "accessToken", "token"),
    "refresh_token": ("refresh_token", "refreshToken"),
    "id_token": ("id_token", "idToken"),
}

_IMPORT_SECRET_KEYS = {
    "accesstoken",
    "apikey",
    "authorization",
    "idtoken",
    "password",
    "proxyauthorization",
    "proxypassword",
    "proxyuser",
    "proxyusername",
    "refreshtoken",
    "secretkey",
    "token",
}
_IMPORT_PROXY_KEYS = {"proxy", "proxyurl"}


def _normalized_key(value: object) -> str:
    return str(value or "").strip().casefold().replace("_", "").replace("-", "")


def _append_text(values: list[str], value: object) -> None:
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _append_text(values, item)
        return
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def _collect_import_diagnostic_values(
    value: object,
    sensitive_values: list[str],
    proxy_values: list[str],
) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = _normalized_key(key)
            if normalized_key in _IMPORT_SECRET_KEYS:
                _append_text(sensitive_values, item)
            elif normalized_key in _IMPORT_PROXY_KEYS:
                _append_text(proxy_values, item)
            if isinstance(item, (Mapping, list, tuple)):
                _collect_import_diagnostic_values(
                    item,
                    sensitive_values,
                    proxy_values,
                )
            elif (
                normalized_key in _NORMALIZED_CREDENTIAL_CONTAINERS
                and isinstance(item, str)
            ):
                try:
                    decoded = json.loads(item)
                except (TypeError, ValueError):
                    continue
                _collect_import_diagnostic_values(
                    decoded,
                    sensitive_values,
                    proxy_values,
                )
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_import_diagnostic_values(
                item,
                sensitive_values,
                proxy_values,
            )


def collect_import_diagnostic_values(
    *sources: object,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Collect credentials and proxies known to a remote-import operation."""

    sensitive_values: list[str] = []
    proxy_values: list[str] = []
    for source in sources:
        _collect_import_diagnostic_values(
            source,
            sensitive_values,
            proxy_values,
        )
    return tuple(sensitive_values), tuple(proxy_values)


def extract_import_credentials(raw: object) -> dict[str, str]:
    """Return the supported AT/RT/ID Token fields from an import record.

    External systems expose credentials either at the record root or in a
    nested credential object. Only credential fields owned by the Upstream
    Account are copied; unrelated remote configuration stays in its adapter.
    """

    if not isinstance(raw, Mapping):
        return {}

    sources: list[Mapping] = []
    for key in _CREDENTIAL_CONTAINERS:
        nested = raw.get(key)
        if isinstance(nested, Mapping):
            sources.append(nested)
    sources.append(raw)

    result: dict[str, str] = {}
    for target, aliases in _CREDENTIAL_ALIASES.items():
        for source in sources:
            value = next(
                (
                    str(source.get(alias) or "").strip()
                    for alias in aliases
                    if str(source.get(alias) or "").strip()
                ),
                "",
            )
            if value:
                result[target] = value
                break
    return result
