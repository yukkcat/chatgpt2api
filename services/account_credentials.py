from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Literal


ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 24 * 60 * 60
AccessTokenStatus = Literal["valid", "expiring", "invalid"]
RefreshTokenStatus = Literal["valid", "missing", "invalid"]
CredentialAvailabilityStatus = Literal["usable", "recoverable", "unavailable"]


@dataclass(frozen=True)
class AccessTokenLifecycle:
    status: AccessTokenStatus
    issued_at: int | None
    expires_at: int | None


@dataclass(frozen=True)
class UpstreamCredentialAvailability:
    status: CredentialAvailabilityStatus
    access: AccessTokenLifecycle
    refresh_status: RefreshTokenStatus


def decode_access_token_payload(access_token: str) -> dict[str, object]:
    try:
        payload = str(access_token or "").split(".")[1]
        payload += "=" * ((4 - len(payload) % 4) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        return claims if isinstance(claims, dict) else {}
    except Exception:
        return {}


def _positive_timestamp(claims: dict[str, object], name: str) -> int | None:
    try:
        value = int(claims.get(name) or 0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def access_token_timestamps(access_token: str) -> tuple[int | None, int | None]:
    claims = decode_access_token_payload(access_token)
    return _positive_timestamp(claims, "iat"), _positive_timestamp(claims, "exp")


def access_token_expires_in_seconds(
    access_token: str,
    *,
    now_seconds: int | None = None,
) -> int | None:
    _issued_at, expires_at = access_token_timestamps(access_token)
    if expires_at is None:
        return None
    now = int(time.time()) if now_seconds is None else int(now_seconds)
    return expires_at - now


def access_token_issued_at(access_token: str) -> int | None:
    issued_at, _expires_at = access_token_timestamps(access_token)
    return issued_at


def project_access_token_lifecycle(
    access_token: str,
    *,
    confirmed_invalid: bool = False,
    now_seconds: int | None = None,
) -> AccessTokenLifecycle:
    normalized_token = str(access_token or "").strip()
    if not normalized_token:
        return AccessTokenLifecycle(
            status="invalid",
            issued_at=None,
            expires_at=None,
        )
    issued_at, expires_at = access_token_timestamps(normalized_token)
    now = int(time.time()) if now_seconds is None else int(now_seconds)
    expires_in = expires_at - now if expires_at is not None else None
    if confirmed_invalid or (expires_in is not None and expires_in <= 0):
        status: AccessTokenStatus = "invalid"
    elif expires_in is not None and expires_in <= ACCESS_TOKEN_REFRESH_SKEW_SECONDS:
        status = "expiring"
    else:
        status = "valid"
    return AccessTokenLifecycle(
        status=status,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def project_upstream_credential_availability(
    access_token: str,
    refresh_token: str = "",
    *,
    access_confirmed_invalid: bool = False,
    refresh_confirmed_invalid: bool = False,
    now_seconds: int | None = None,
) -> UpstreamCredentialAvailability:
    """Project whether one Upstream Account can execute or recover a request."""
    access = project_access_token_lifecycle(
        access_token,
        confirmed_invalid=access_confirmed_invalid,
        now_seconds=now_seconds,
    )
    normalized_refresh_token = str(refresh_token or "").strip()
    refresh_status: RefreshTokenStatus = (
        "missing"
        if not normalized_refresh_token
        else "invalid"
        if refresh_confirmed_invalid
        else "valid"
    )
    if access.status != "invalid":
        status: CredentialAvailabilityStatus = "usable"
    elif refresh_status == "valid":
        status = "recoverable"
    else:
        status = "unavailable"
    return UpstreamCredentialAvailability(
        status=status,
        access=access,
        refresh_status=refresh_status,
    )
