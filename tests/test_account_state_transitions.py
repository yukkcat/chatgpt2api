from __future__ import annotations

import os
import base64
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("CHATGPT2API_AUTH_KEY", "test-auth")

import api.accounts as accounts_api
import services.account_service as account_service_module
import services.editable_file_task_service as editable_file_task_module
from services.account_service import (
    AccountService,
    RefreshCredentialsChangedError,
    TerminalRefreshTokenError,
)
from services.image_failure import image_failure
from services.openai_backend_api import InvalidAccessTokenError, OpenAIBackendAPI
from tests.support.account_repository import TestAccountRepository


class _Backend:
    def __init__(self, result_or_error):
        self.result_or_error = result_or_error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get_user_info(self):
        if isinstance(self.result_or_error, Exception):
            raise self.result_or_error
        return dict(self.result_or_error)


def _oauth_session(status_code: int, payload: dict) -> mock.Mock:
    response = mock.Mock(status_code=status_code, text=json.dumps(payload))
    response.json.return_value = payload
    session = mock.Mock()
    session.post.return_value = response
    return session


def _access_token(*, expires_at: int) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"iat": expires_at - 3600, "exp": expires_at}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"header.{payload}.signature"


class AccountStateTransitionTests(unittest.TestCase):
    def _service(self, tmp_dir: str, initial: list[dict] | None = None) -> AccountService:
        storage = TestAccountRepository(Path(tmp_dir) / "accounts.json")
        if initial is not None:
            storage.save_accounts(initial)
        return AccountService(storage)

    def test_unchecked_quota_is_unknown_for_every_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([
                {"access_token": "web", "source_type": "web", "quota": 0},
                {"access_token": "microsoft", "source_type": "microsoft", "quota": 0},
                {"access_token": "codex", "source_type": "codex", "quota": 0},
            ])

            for token in ("web", "microsoft", "codex"):
                with self.subTest(token=token):
                    account = service.get_account(token) or {}
                    self.assertEqual(account.get("status"), "正常")
                    self.assertEqual(account.get("quota"), 0)
                    self.assertIs(account.get("image_quota_unknown"), True)

    def test_only_canonical_status_controls_api_category(self) -> None:
        transient_metadata = {
            "last_refresh_error": "old diagnostic",
            "last_token_refresh_error": "temporary oauth failure",
            "last_remote_check_result": "error",
            "invalid_count": 2,
            "status_reason_code": "upstream_error",
            "last_error_kind": "parse_failure",
        }

        self.assertEqual(
            accounts_api._account_status_category({
                "access_token": "opaque-usable-token",
                "status": "正常",
                **transient_metadata,
            }),
            "normal",
        )
        self.assertEqual(
            accounts_api._account_status_category({
                "access_token": "opaque-limited-token",
                "status": "限流",
            }),
            "limited",
        )
        self.assertEqual(accounts_api._account_status_category({"status": "异常"}), "abnormal")
        self.assertEqual(accounts_api._account_status_category({"status": "禁用"}), "disabled")

    def test_effective_api_category_marks_unrecoverable_credentials_abnormal(self) -> None:
        expired_token = _access_token(expires_at=int(time.time()) - 1)

        self.assertEqual(
            accounts_api._account_status_category({
                "access_token": expired_token,
                "status": "正常",
            }),
            "abnormal",
        )
        self.assertEqual(
            accounts_api._account_status_category({
                "access_token": expired_token,
                "refresh_token": "refresh-secret",
                "status": "正常",
            }),
            "normal",
        )

    def test_auth_failure_stays_normal_when_background_verification_is_transient(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["token-a"])
            service.update_account("token-a", {"quota": 5}, quiet=True)

            with mock.patch.object(service, "_schedule_account_refresh_after_image_failure"):
                service.mark_image_result(
                    "token-a",
                    False,
                    failure=image_failure("auth_invalid"),
                )

            with mock.patch(
                "services.openai_backend_api.OpenAIBackendAPI",
                return_value=_Backend(RuntimeError("upstream unavailable")),
            ):
                service._refresh_account_after_image_failure("token-a")

            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("status"), "正常")
            self.assertEqual(account.get("last_remote_check_result"), "error")
            self.assertEqual(account.get("fail"), 1)

    def test_oauth_refresh_transport_error_does_not_confirm_invalid_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "quota": 5,
            }])

            def refresh(
                token: str,
                *,
                force: bool = False,
                event: str = "",
                remove_invalid: bool | None = None,
            ) -> str:
                if force:
                    service._record_token_refresh_error(token, event, "oauth unavailable")
                return token

            with (
                mock.patch.object(
                    account_service_module.config.__class__,
                    "auto_remove_invalid_accounts",
                    new_callable=mock.PropertyMock,
                    return_value=True,
                ),
                mock.patch.object(service, "refresh_access_token", side_effect=refresh),
                mock.patch(
                    "services.openai_backend_api.OpenAIBackendAPI",
                    return_value=_Backend(InvalidAccessTokenError("invalid access token")),
                ),
            ):
                with self.assertRaises(InvalidAccessTokenError):
                    service.fetch_remote_info("token-a", "test")

            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("status"), "正常")
            self.assertEqual(account.get("last_remote_check_result"), "error")

    def test_terminal_oauth_refresh_errors_confirm_invalid_account(self) -> None:
        scenarios = (
            (
                "nested_code",
                {"error": {"code": "refresh_token_invalidated", "message": "Your session has ended."}},
                "refresh_token_invalidated",
            ),
            (
                "invalid_refresh_token",
                {"error": {"code": "invalid_refresh_token", "message": "Invalid refresh token."}},
                "invalid_refresh_token",
            ),
            (
                "standard_oauth",
                {"error": "invalid_grant", "error_description": "The refresh token is invalid."},
                "invalid_grant",
            ),
            (
                "top_level_code_precedence",
                {
                    "error": "invalid_request_error",
                    "code": "refresh_token_invalidated",
                    "error_description": "Your session has ended.",
                },
                "refresh_token_invalidated",
            ),
            (
                "nested_type_does_not_hide_message_fallback",
                {
                    "error": {
                        "type": "invalid_request_error",
                        "message": "Your session has ended. Please sign in again.",
                    },
                },
                "",
            ),
            (
                "message_fallback",
                {"message": "Your session has ended. Please sign in again."},
                "",
            ),
        )
        for name, payload, expected_code in scenarios:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp_dir:
                service = self._service(tmp_dir)
                service.add_account_items([{
                    "access_token": "token-a",
                    "refresh_token": "refresh-a",
                    "quota": 5,
                }])
                session = _oauth_session(401, payload)

                with (
                    mock.patch("curl_cffi.requests.Session", return_value=session),
                    mock.patch.object(service, "handle_invalid_token", wraps=service.handle_invalid_token) as handle_invalid,
                    mock.patch(
                        "services.openai_backend_api.OpenAIBackendAPI",
                        return_value=_Backend(InvalidAccessTokenError("invalid access token")),
                    ) as backend_factory,
                ):
                    with self.assertRaises(TerminalRefreshTokenError) as raised:
                        service.fetch_remote_info("token-a", "test", remove_invalid=False)

                self.assertEqual(raised.exception.error_code, expected_code)
                handle_invalid.assert_called_once()
                self.assertEqual(backend_factory.call_count, 1)
                account = service.get_account("token-a") or {}
                self.assertEqual(account.get("status"), "异常")
                self.assertEqual(account.get("last_remote_check_result"), "invalid")
                self.assertEqual(account.get("last_token_refresh_error"), str(raised.exception))

    def test_terminal_oauth_refresh_error_obeys_removal_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "quota": 5,
            }])
            session = _oauth_session(401, {
                "error": {"code": "refresh_token_invalidated", "message": "Your session has ended."},
            })

            with (
                mock.patch("curl_cffi.requests.Session", return_value=session),
                mock.patch(
                    "services.openai_backend_api.OpenAIBackendAPI",
                    return_value=_Backend(InvalidAccessTokenError("invalid access token")),
                ),
            ):
                with self.assertRaises(TerminalRefreshTokenError):
                    service.fetch_remote_info("token-a", "test", remove_invalid=True)

            self.assertIsNone(service.get_account("token-a"))

    def test_transient_oauth_refresh_failures_do_not_confirm_invalid_account(self) -> None:
        scenarios = (
            ("timeout", TimeoutError("oauth timeout"), None),
            (
                "request_timeout_with_terminal_code",
                None,
                _oauth_session(408, {
                    "error": {"code": "invalid_refresh_token", "message": "Invalid refresh token."},
                }),
            ),
            (
                "rate_limited_with_terminal_code",
                None,
                _oauth_session(429, {
                    "error": {"code": "refresh_token_invalidated", "message": "Your session has ended."},
                }),
            ),
            (
                "server_error",
                None,
                _oauth_session(503, {
                    "error": {"code": "refresh_token_invalidated", "message": "Your session has ended."},
                }),
            ),
            (
                "unknown_client_error",
                None,
                _oauth_session(400, {
                    "error": {"code": "invalid_request", "message": "Malformed OAuth request."},
                }),
            ),
        )
        for name, post_error, session in scenarios:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp_dir:
                service = self._service(tmp_dir)
                service.add_account_items([{
                    "access_token": "token-a",
                    "refresh_token": "refresh-a",
                    "quota": 5,
                }])
                active_session = session or mock.Mock()
                if post_error is not None:
                    active_session.post.side_effect = post_error

                with (
                    mock.patch("curl_cffi.requests.Session", return_value=active_session),
                    mock.patch(
                        "services.openai_backend_api.OpenAIBackendAPI",
                        return_value=_Backend(InvalidAccessTokenError("invalid access token")),
                    ),
                ):
                    with self.assertRaises(InvalidAccessTokenError):
                        service.fetch_remote_info("token-a", "test", remove_invalid=True)

                account = service.get_account("token-a") or {}
                self.assertEqual(account.get("status"), "正常")
                self.assertEqual(account.get("last_remote_check_result"), "error")
                self.assertTrue(str(account.get("last_token_refresh_error") or ""))

    def test_direct_terminal_refresh_does_not_return_old_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "quota": 5,
            }])
            session = _oauth_session(400, {"error": "invalid_grant"})

            with mock.patch("curl_cffi.requests.Session", return_value=session):
                with self.assertRaises(TerminalRefreshTokenError):
                    service.refresh_access_token(
                        "token-a",
                        force=True,
                        event="test",
                        remove_invalid=False,
                    )

            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("status"), "正常")
            self.assertTrue(account.get("refresh_token_invalid_at"))

    def test_stale_terminal_refresh_does_not_invalidate_replaced_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "quota": 5,
            }])
            attempts: list[str] = []

            def refresh(refresh_token: str, _account: dict) -> dict[str, str]:
                attempts.append(refresh_token)
                if refresh_token == "refresh-a":
                    service.update_account("token-a", {"refresh_token": "refresh-b"})
                    raise TerminalRefreshTokenError(401, "invalid_grant")
                return {
                    "access_token": "token-b",
                    "refresh_token": "refresh-b",
                    "id_token": "",
                }

            with (
                mock.patch.object(service, "_request_access_token_refresh", side_effect=refresh),
                mock.patch.object(service, "handle_invalid_token", wraps=service.handle_invalid_token) as handle_invalid,
            ):
                result = service.refresh_access_token(
                    "token-a",
                    force=True,
                    event="test",
                    remove_invalid=True,
                )

            self.assertEqual(result, "token-b")
            self.assertEqual(attempts, ["refresh-a", "refresh-b"])
            handle_invalid.assert_not_called()
            self.assertEqual((service.get_account("token-b") or {}).get("status"), "正常")

    def test_stale_terminal_result_does_not_mutate_replaced_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-b",
                "quota": 5,
            }])

            removed = service.handle_invalid_token(
                "token-a",
                "test",
                error="oauth_refresh_http_401: invalid_grant",
                remove=True,
                expected_refresh_token="refresh-a",
                token_refresh_error="oauth_refresh_http_401: invalid_grant",
            )

            account = service.get_account("token-a") or {}
            self.assertFalse(removed)
            self.assertEqual(account.get("status"), "正常")
            self.assertEqual(account.get("refresh_token"), "refresh-b")
            self.assertIsNone(account.get("last_token_refresh_error"))

    def test_refresh_does_not_return_old_token_after_second_credentials_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "quota": 5,
            }])
            attempts: list[str] = []

            def refresh(refresh_token: str, _account: dict) -> dict[str, str]:
                attempts.append(refresh_token)
                replacement = "refresh-b" if refresh_token == "refresh-a" else "refresh-c"
                service.update_account("token-a", {"refresh_token": replacement})
                raise TerminalRefreshTokenError(401, "invalid_grant")

            with mock.patch.object(service, "_request_access_token_refresh", side_effect=refresh):
                with self.assertRaisesRegex(RuntimeError, "credentials changed"):
                    service.refresh_access_token(
                        "token-a",
                        force=True,
                        event="test",
                        remove_invalid=True,
                    )

            account = service.get_account("token-a") or {}
            self.assertEqual(attempts, ["refresh-a", "refresh-b"])
            self.assertEqual(account.get("status"), "正常")
            self.assertEqual(account.get("refresh_token"), "refresh-c")
            self.assertIsNone(account.get("last_token_refresh_error"))

    def test_stale_successful_refresh_does_not_overwrite_replaced_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "quota": 5,
            }])
            attempts: list[str] = []

            def refresh(refresh_token: str, _account: dict) -> dict[str, str]:
                attempts.append(refresh_token)
                if refresh_token == "refresh-a":
                    service.update_account("token-a", {"refresh_token": "refresh-b"})
                    return {
                        "access_token": "stale-token",
                        "refresh_token": "refresh-a",
                        "id_token": "",
                    }
                return {
                    "access_token": "fresh-token",
                    "refresh_token": "refresh-b",
                    "id_token": "",
                }

            with mock.patch.object(service, "_request_access_token_refresh", side_effect=refresh):
                result = service.refresh_access_token(
                    "token-a",
                    force=True,
                    event="test",
                    remove_invalid=True,
                )

            account = service.get_account("fresh-token") or {}
            self.assertEqual(result, "fresh-token")
            self.assertEqual(attempts, ["refresh-a", "refresh-b"])
            self.assertEqual(account.get("refresh_token"), "refresh-b")
            self.assertIsNone(service.get_account("stale-token"))

    def test_stale_transient_refresh_error_does_not_back_off_replaced_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "quota": 5,
            }])
            attempts: list[str] = []

            def refresh(refresh_token: str, _account: dict) -> dict[str, str]:
                attempts.append(refresh_token)
                if refresh_token == "refresh-a":
                    service.update_account("token-a", {"refresh_token": "refresh-b"})
                    raise TimeoutError("old refresh timed out")
                return {
                    "access_token": "fresh-token",
                    "refresh_token": "refresh-b",
                    "id_token": "",
                }

            with mock.patch.object(service, "_request_access_token_refresh", side_effect=refresh):
                result = service.refresh_access_token(
                    "token-a",
                    force=True,
                    event="test",
                    remove_invalid=True,
                )

            account = service.get_account("fresh-token") or {}
            self.assertEqual(result, "fresh-token")
            self.assertEqual(attempts, ["refresh-a", "refresh-b"])
            self.assertEqual(account.get("refresh_token"), "refresh-b")
            self.assertIsNone(account.get("last_token_refresh_error"))

    def test_refresh_does_not_recreate_account_deleted_during_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "quota": 5,
            }])

            def refresh(_refresh_token: str, _account: dict) -> dict[str, str]:
                service.delete_accounts(["token-a"])
                return {
                    "access_token": "stale-token",
                    "refresh_token": "refresh-a",
                    "id_token": "",
                }

            with mock.patch.object(service, "_request_access_token_refresh", side_effect=refresh):
                with self.assertRaises(RefreshCredentialsChangedError):
                    service.refresh_access_token("token-a", force=True, event="test")

            self.assertIsNone(service.get_account("token-a"))
            self.assertIsNone(service.get_account("stale-token"))

    def test_refresh_stops_after_two_stale_successful_responses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "quota": 5,
            }])
            attempts: list[str] = []

            def refresh(refresh_token: str, _account: dict) -> dict[str, str]:
                attempts.append(refresh_token)
                replacement = "refresh-b" if refresh_token == "refresh-a" else "refresh-c"
                service.update_account("token-a", {"refresh_token": replacement})
                return {
                    "access_token": f"stale-token-{len(attempts)}",
                    "refresh_token": refresh_token,
                    "id_token": "",
                }

            with mock.patch.object(service, "_request_access_token_refresh", side_effect=refresh):
                with self.assertRaises(RefreshCredentialsChangedError):
                    service.refresh_access_token("token-a", force=True, event="test")

            account = service.get_account("token-a") or {}
            self.assertEqual(attempts, ["refresh-a", "refresh-b"])
            self.assertEqual(account.get("refresh_token"), "refresh-c")
            self.assertIsNone(service.get_account("stale-token-1"))
            self.assertIsNone(service.get_account("stale-token-2"))

    def test_refresh_does_not_overwrite_occupied_target_access_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "email": "source@example.test",
                "quota": 5,
            }])

            def refresh(_refresh_token: str, _account: dict) -> dict[str, str]:
                service.add_account_items([{
                    "access_token": "token-b",
                    "refresh_token": "refresh-b",
                    "email": "concurrent@example.test",
                    "quota": 9,
                }])
                return {
                    "access_token": "token-b",
                    "refresh_token": "refresh-a",
                    "id_token": "",
                }

            with mock.patch.object(service, "_request_access_token_refresh", side_effect=refresh):
                with self.assertRaises(RefreshCredentialsChangedError):
                    service.refresh_access_token("token-a", force=True, event="test")

            source = service.get_account("token-a") or {}
            concurrent = service.get_account("token-b") or {}
            self.assertEqual(source.get("refresh_token"), "refresh-a")
            self.assertEqual(concurrent.get("refresh_token"), "refresh-b")
            self.assertEqual(concurrent.get("email"), "concurrent@example.test")
            self.assertEqual(concurrent.get("quota"), 9)
            self.assertEqual(service.resolve_access_token("token-a"), "token-a")

    def test_late_old_access_token_rejection_retries_current_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "email": "account@example.test",
                "quota": 5,
            }])
            backend_tokens: list[str] = []

            class Backend:
                def __init__(self, token: str):
                    self.token = token

                def __enter__(self):
                    backend_tokens.append(self.token)
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def get_user_info(self):
                    if self.token == "token-a":
                        service._apply_refreshed_tokens(
                            "token-a",
                            {
                                "access_token": "token-b",
                                "refresh_token": "refresh-a",
                                "id_token": "",
                            },
                            "concurrent_refresh",
                            expected_refresh_token="refresh-a",
                        )
                        raise InvalidAccessTokenError("old token rejected")
                    return {
                        "email": "account@example.test",
                        "quota": 5,
                        "status": "正常",
                    }

            with (
                mock.patch.object(service, "refresh_access_token", side_effect=lambda token, **_: token),
                mock.patch(
                    "services.openai_backend_api.OpenAIBackendAPI",
                    side_effect=lambda token: Backend(token),
                ),
            ):
                result = service.fetch_remote_info("token-a", "test", remove_invalid=True)

            self.assertEqual(backend_tokens, ["token-a", "token-b"])
            self.assertEqual((result or {}).get("access_token"), "token-b")
            self.assertEqual((service.get_account("token-b") or {}).get("status"), "正常")

    def test_stale_access_token_result_does_not_delete_rotated_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "refresh_token": "refresh-a",
                "quota": 5,
            }])
            service._apply_refreshed_tokens(
                "token-a",
                {
                    "access_token": "token-b",
                    "refresh_token": "refresh-a",
                    "id_token": "",
                },
                "concurrent_refresh",
                expected_refresh_token="refresh-a",
            )

            removed = service.handle_invalid_token(
                "token-a",
                "test",
                error="old token rejected",
                remove=True,
                expected_access_token="token-a",
            )

            account = service.get_account("token-b") or {}
            self.assertFalse(removed)
            self.assertEqual(account.get("status"), "正常")
            self.assertEqual(account.get("refresh_token"), "refresh-a")

    def test_text_selection_skips_terminal_refresh_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["token-a", "token-b"])
            terminal = TerminalRefreshTokenError(401, "invalid_grant")

            with mock.patch.object(
                service,
                "ensure_access_token",
                side_effect=[terminal, "token-b"],
            ) as refresh:
                selected = service.get_text_access_token()

            self.assertEqual(selected, "token-b")
            self.assertEqual([call.args[0] for call in refresh.call_args_list], ["token-a", "token-b"])

    def test_text_selection_excludes_expired_access_token_without_refresh_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            expired_token = _access_token(expires_at=int(time.time()) - 1)
            service = self._service(tmp_dir, [
                {"access_token": expired_token, "status": "正常"},
                {"access_token": "opaque-usable-token", "status": "正常"},
            ])

            selected = service.get_text_access_token()

            self.assertEqual(selected, "opaque-usable-token")
            expired_account = service.get_account(expired_token) or {}
            self.assertFalse(service._is_account_selectable(expired_account, allow_limited=True))

    def test_expired_access_token_with_refresh_token_remains_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            expired_token = _access_token(expires_at=int(time.time()) - 1)
            service = self._service(tmp_dir, [{
                "access_token": expired_token,
                "refresh_token": "refresh-secret",
                "status": "正常",
            }])

            account = service.get_account(expired_token) or {}

            self.assertTrue(service._is_account_selectable(account, allow_limited=True))

    def test_text_selection_skips_concurrently_changed_refresh_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["token-a", "token-b"])

            with mock.patch.object(
                service,
                "ensure_access_token",
                side_effect=[RefreshCredentialsChangedError(), "token-b"],
            ) as refresh:
                selected = service.get_text_access_token()

            self.assertEqual(selected, "token-b")
            self.assertEqual([call.args[0] for call in refresh.call_args_list], ["token-a", "token-b"])

    def test_text_selection_skips_account_deleted_before_refresh_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["token-a", "token-b"])
            original_lookup = service._get_account_for_token
            removed = False

            def lookup(token: str) -> tuple[str, dict | None]:
                nonlocal removed
                if token == "token-a" and not removed:
                    removed = True
                    service.delete_accounts([token])
                return original_lookup(token)

            with mock.patch.object(service, "_get_account_for_token", side_effect=lookup):
                selected = service.get_text_access_token()

            self.assertEqual(selected, "token-b")
            self.assertIsNone(service.get_account("token-a"))

    def test_editable_file_selection_skips_terminal_refresh_account(self) -> None:
        accounts = [
            {"access_token": "token-a", "status": "正常", "type": "Plus", "last_used_at": "1"},
            {"access_token": "token-b", "status": "正常", "type": "Plus", "last_used_at": "2"},
        ]
        terminal = TerminalRefreshTokenError(401, "invalid_grant")

        with (
            mock.patch.object(editable_file_task_module.account_service, "list_accounts", return_value=accounts),
            mock.patch.object(
                editable_file_task_module.account_service,
                "ensure_access_token",
                side_effect=[terminal, "token-b"],
            ),
        ):
            selected = editable_file_task_module._editable_access_token()

        self.assertEqual(selected, "token-b")

    def test_editable_file_selection_skips_concurrently_changed_refresh_account(self) -> None:
        accounts = [
            {"access_token": "token-a", "status": "正常", "type": "Plus", "last_used_at": "1"},
            {"access_token": "token-b", "status": "正常", "type": "Plus", "last_used_at": "2"},
        ]

        with (
            mock.patch.object(editable_file_task_module.account_service, "list_accounts", return_value=accounts),
            mock.patch.object(
                editable_file_task_module.account_service,
                "ensure_access_token",
                side_effect=[RefreshCredentialsChangedError(), "token-b"],
            ),
        ):
            selected = editable_file_task_module._editable_access_token()

        self.assertEqual(selected, "token-b")

    def test_terminal_refresh_is_reported_as_auth_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["token-a"])

            with mock.patch.object(
                service,
                "fetch_remote_info",
                side_effect=TerminalRefreshTokenError(401, "invalid_grant"),
            ):
                result = service.refresh_accounts(["token-a"])

            self.assertEqual(result.get("refreshed"), 0)
            self.assertEqual((result.get("errors") or [{}])[0].get("failure_code"), "auth_invalid")

    def test_confirmed_invalid_account_obeys_global_removal_setting(self) -> None:
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as tmp_dir:
                service = self._service(tmp_dir)
                service.add_accounts(["token-a"])
                with (
                    mock.patch.object(
                        account_service_module.config.__class__,
                        "auto_remove_invalid_accounts",
                        new_callable=mock.PropertyMock,
                        return_value=enabled,
                    ),
                    mock.patch.object(service, "refresh_access_token", return_value="token-a"),
                    mock.patch(
                        "services.openai_backend_api.OpenAIBackendAPI",
                        return_value=_Backend(InvalidAccessTokenError("invalid access token")),
                    ),
                ):
                    with self.assertRaises(InvalidAccessTokenError):
                        service.fetch_remote_info("token-a", "test")

                account = service.get_account("token-a")
                if enabled:
                    self.assertIsNone(account)
                else:
                    self.assertEqual((account or {}).get("status"), "异常")
                    self.assertEqual((account or {}).get("last_remote_check_result"), "invalid")

    def test_disabled_account_stays_disabled_after_remote_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["token-a"])
            service.update_account("token-a", {"status": "禁用"}, quiet=True)

            with (
                mock.patch.object(service, "refresh_access_token", return_value="token-a"),
                mock.patch(
                    "services.openai_backend_api.OpenAIBackendAPI",
                    return_value=_Backend({
                        "status": "正常",
                        "quota": 3,
                        "image_quota_unknown": False,
                        "restore_at": None,
                    }),
                ),
            ):
                refreshed = service.fetch_remote_info("token-a", "test")

            self.assertEqual((refreshed or {}).get("status"), "禁用")
            self.assertEqual((service.get_account("token-a") or {}).get("status"), "禁用")

    def test_auth_failure_forces_verification_past_recent_dedup_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["token-a"])
            service._image_failure_refresh_started_at["token-a"] = time.monotonic()

            with mock.patch.object(service, "_start_pending_image_failure_refreshes"):
                account = service.mark_image_result(
                    "token-a",
                    False,
                    failure=image_failure("auth_invalid"),
                )

            self.assertEqual((account or {}).get("last_remote_check_result"), "pending")
            self.assertIn("token-a", service._image_failure_refresh_pending_set)

    def test_text_auth_failure_is_queued_without_marking_account_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["token-a"])

            with mock.patch.object(service, "_start_pending_image_failure_refreshes"):
                scheduled = service.schedule_auth_verification("token-a", "text_stream")

            account = service.get_account("token-a") or {}
            self.assertTrue(scheduled)
            self.assertEqual(account.get("status"), "正常")
            self.assertEqual(account.get("last_remote_check_result"), "pending")
            self.assertEqual(account.get("last_remote_check_event"), "text_stream")
            self.assertIn("token-a", service._image_failure_refresh_pending_set)

    def test_transient_refresh_error_is_reported_without_changing_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_accounts(["token-a"])

            with (
                mock.patch.object(service, "refresh_access_token", return_value="token-a"),
                mock.patch(
                    "services.openai_backend_api.OpenAIBackendAPI",
                    return_value=_Backend(TimeoutError("upstream timeout")),
                ),
            ):
                result = service.refresh_accounts(["token-a"])

            self.assertEqual(result.get("refreshed"), 0)
            self.assertEqual(len(result.get("errors") or []), 1)
            self.assertEqual((result["errors"][0]).get("failure_code"), "upstream_connection_timeout")
            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("status"), "正常")
            self.assertEqual(account.get("last_remote_check_result"), "error")

    def test_manual_limited_recovery_clears_stale_restore_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            service.add_account_items([{
                "access_token": "token-a",
                "status": "限流",
                "quota": 0,
                "restore_at": "2030-01-01T00:00:00+00:00",
            }])

            account = service.update_account("token-a", {"status": "正常"}, quiet=True) or {}

            self.assertEqual(account.get("status"), "正常")
            self.assertIsNone(account.get("restore_at"))
            self.assertIs(account.get("image_quota_unknown"), True)

    def test_openai_remote_quota_has_three_unambiguous_states(self) -> None:
        scenarios = (
            ([], "正常", 0, True),
            ([{"feature_name": "image_gen", "remaining": 0}], "限流", 0, False),
            ([{"feature_name": "image_gen", "remaining": 3}], "正常", 3, False),
        )
        for limits, expected_status, expected_quota, expected_unknown in scenarios:
            with self.subTest(limits=limits):
                backend = object.__new__(OpenAIBackendAPI)
                backend.access_token = "token-a"
                with (
                    mock.patch.object(backend, "_get_me", return_value={"email": "a@example.test", "id": "user-a"}),
                    mock.patch.object(backend, "_get_conversation_init", return_value={"limits_progress": limits}),
                    mock.patch.object(backend, "_get_default_account", return_value={"plan_type": "free"}),
                ):
                    result = backend.get_user_info()

                self.assertEqual(result["status"], expected_status)
                self.assertEqual(result["quota"], expected_quota)
                self.assertIs(result["image_quota_unknown"], expected_unknown)


if __name__ == "__main__":
    unittest.main()
