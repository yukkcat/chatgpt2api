from __future__ import annotations

from collections.abc import Mapping

from contracts.auth import AuthCapabilities, AuthSubject, AuthView


def _clean(value: object) -> str:
    return str(value or "").strip()


def build_auth_view(app_version: str, identity: Mapping[str, object] | None = None) -> AuthView:
    if identity is None:
        return AuthView(
            authenticated=False,
            version=app_version,
            subject=None,
            capabilities=AuthCapabilities(),
            home_route="/login",
        )

    raw_role = _clean(identity.get("role")).lower()
    role = raw_role if raw_role in {"admin", "user"} else "unknown"
    is_admin = role == "admin"
    subject_id = _clean(identity.get("id")) or "authenticated"
    subject_name = _clean(identity.get("name")) or subject_id

    return AuthView(
        authenticated=True,
        version=app_version,
        subject=AuthSubject(id=subject_id, name=subject_name, role=role),
        capabilities=AuthCapabilities(admin_console=is_admin, studio=True),
        home_route="/" if is_admin else "/studio",
    )
