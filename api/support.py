from __future__ import annotations

from pathlib import Path
from threading import Event, Thread

from fastapi import HTTPException, Request

from services.account_service import account_service
from services.auth_service import auth_service
from services.config import config

BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIST_DIR = BASE_DIR / "web_dist"


def extract_bearer_token(authorization: str | None) -> str:
    scheme, _, value = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return ""
    return value.strip()


def _legacy_admin_identity(token: str) -> dict[str, object] | None:
    auth_key = str(config.auth_key or "").strip()
    if auth_key and token == auth_key:
        return {"id": "admin", "name": "管理员", "role": "admin"}
    return None


def require_identity(authorization: str | None) -> dict[str, object]:
    token = extract_bearer_token(authorization)
    identity = _legacy_admin_identity(token) or auth_service.authenticate(token)
    if identity is None:
        raise HTTPException(status_code=401, detail={"error": "密钥无效或已失效，请重新登录"})
    return identity


def require_auth_key(authorization: str | None) -> None:
    require_identity(authorization)


def require_admin(authorization: str | None) -> dict[str, object]:
    identity = require_identity(authorization)
    if identity.get("role") != "admin":
        raise HTTPException(status_code=403, detail={"error": "需要管理员权限才能执行这个操作"})
    return identity


def resolve_image_base_url(request: Request) -> str:
    return config.base_url or f"{request.url.scheme}://{request.headers.get('host', request.url.netloc)}"


def sanitize_cpa_pool(pool: dict | None) -> dict | None:
    if not isinstance(pool, dict):
        return None
    return {key: value for key, value in pool.items() if key != "secret_key"}


def sanitize_cpa_pools(pools: list[dict]) -> list[dict]:
    return [sanitized for pool in pools if (sanitized := sanitize_cpa_pool(pool)) is not None]


def sanitize_sub2api_server(server: dict | None) -> dict | None:
    if not isinstance(server, dict):
        return None
    sanitized = {key: value for key, value in server.items() if key not in {"password", "api_key"}}
    sanitized["has_api_key"] = bool(str(server.get("api_key") or "").strip())
    return sanitized


def sanitize_sub2api_servers(servers: list[dict]) -> list[dict]:
    return [sanitized for server in servers if (sanitized := sanitize_sub2api_server(server)) is not None]


def start_account_lifecycle_watcher(stop_event: Event) -> Thread:
    def worker() -> None:
        while not stop_event.is_set():
            try:
                pending_auth = account_service.list_pending_auth_verification_tokens()
                if pending_auth:
                    account_service.resume_pending_auth_verifications()
                expiring_tokens = account_service.list_expiring_access_tokens()
                if expiring_tokens:
                    print(
                        "[account-watcher] renewing "
                        f"{len(expiring_tokens)} expiring access tokens"
                    )
                    result = account_service.renew_expiring_access_tokens(expiring_tokens)
                    if result.get("errors"):
                        print(f"[account-watcher] renewal errors: {result['errors']}")

                limited_tokens = account_service.list_limited_tokens()
                normal_tokens = account_service.list_normal_tokens()
                if limited_tokens:
                    print(
                        "[account-watcher] syncing "
                        f"{len(limited_tokens)} limited accounts "
                        f"(skipping {len(normal_tokens)} healthy accounts, "
                        f"recovering {len(pending_auth)} pending auth accounts)"
                    )
                    account_service.sync_accounts_and_quota(limited_tokens)
            except Exception as exc:
                print(f"[account-watcher] fail {exc}")
            stop_event.wait(config.refresh_account_interval_minute * 60)

    thread = Thread(target=worker, name="account-lifecycle-watcher", daemon=True)
    thread.start()
    return thread


def start_limited_account_watcher(stop_event: Event) -> Thread:
    """Compatibility alias for integrations importing the old watcher name."""
    return start_account_lifecycle_watcher(stop_event)


def resolve_web_asset(requested_path: str) -> Path | None:
    if not WEB_DIST_DIR.exists():
        return None
    clean_path = requested_path.strip("/")
    base_dir = WEB_DIST_DIR.resolve()
    candidates = [base_dir / "index.html"] if not clean_path else [
        base_dir / Path(clean_path),
        base_dir / clean_path / "index.html",
        base_dir / f"{clean_path}.html",
    ]
    for candidate in candidates:
        try:
            candidate.resolve().relative_to(base_dir)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None
