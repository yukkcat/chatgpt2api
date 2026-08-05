from __future__ import annotations

from typing import Any, Callable

from services.account_service import account_service
from services.image_failure import classify_image_exception
from utils.log import logger


def _account_snapshot(access_token: str) -> dict[str, Any]:
    account = account_service.get_account(access_token) or {}
    return dict(account) if isinstance(account, dict) else {}


def _is_account_auth_failure(exc: BaseException) -> bool:
    return classify_image_exception(exc).capability == "auth"


def _schedule_auth_verification(
    access_token: str,
    account: dict[str, Any],
    event: str,
) -> None:
    try:
        account_service.schedule_auth_verification(
            access_token,
            event,
            expected_access_token=access_token,
            expected_refresh_token=str(account.get("refresh_token") or ""),
            expected_last_token_refresh_at=account.get("last_token_refresh_at"),
        )
    except Exception as schedule_error:
        logger.warning({
            "event": "auth_verification_schedule_failed",
            "source": event,
            "error": repr(schedule_error)[:300],
        })


def execute_search(
    query: str,
    *,
    backend_factory: Callable[[str], Any],
    decorate: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Execute one search and switch Upstream Account once on auth rejection."""
    attempted_tokens: set[str] = set()
    auth_failures = 0
    last_auth_error: Exception | None = None

    while True:
        access_token = account_service.get_text_access_token(attempted_tokens)
        if not access_token or access_token in attempted_tokens:
            if last_auth_error is not None:
                raise last_auth_error
            raise RuntimeError("no available text account")
        attempted_tokens.add(access_token)
        account = _account_snapshot(access_token)

        try:
            with backend_factory(access_token) as backend:
                result = backend.search(query)
        except Exception as exc:
            if not _is_account_auth_failure(exc):
                raise
            last_auth_error = exc
            _schedule_auth_verification(access_token, account, "search")
            auth_failures += 1
            if auth_failures < 2:
                continue
            raise

        account_service.mark_text_used(access_token)
        output = dict(result)
        if decorate is not None:
            decorate(output, account)
        return output
