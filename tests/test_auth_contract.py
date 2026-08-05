from __future__ import annotations

import asyncio
import base64
import json
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import FastAPI, HTTPException

from api import accounts, system
from api.app import create_app
from contracts.auth import AuthView
from services.account_credentials import project_access_token_lifecycle
from services.auth_view import build_auth_view
from services.account_view import account_row


def _user_key(key_id: str = "user-key-1") -> dict[str, object]:
    return {
        "id": key_id,
        "name": "Studio user",
        "role": "user",
        "enabled": True,
        "created_at": "2026-07-26T00:00:00+00:00",
        "last_used_at": None,
    }


def _access_token(*, issued_at: int, expires_at: int) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"iat": issued_at, "exp": expires_at}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"header.{payload}.signature"


class AuthViewTests(unittest.TestCase):
    def test_admin_identity_owns_admin_and_studio_capabilities(self) -> None:
        view = build_auth_view(
            "test-version",
            {"id": "admin", "name": "Administrator", "role": "admin"},
        )

        self.assertEqual(view.home_route, "/")
        self.assertTrue(view.capabilities.admin_console)
        self.assertTrue(view.capabilities.studio)
        self.assertEqual(view.subject.role if view.subject else None, "admin")

    def test_unknown_role_is_never_promoted_to_admin(self) -> None:
        view = build_auth_view(
            "test-version",
            {"id": "legacy", "name": "Legacy", "role": "unexpected"},
        )

        self.assertEqual(view.home_route, "/studio")
        self.assertFalse(view.capabilities.admin_console)
        self.assertTrue(view.capabilities.studio)
        self.assertEqual(view.subject.role if view.subject else None, "unknown")

    def test_anonymous_view_has_no_identity_or_capabilities(self) -> None:
        view = build_auth_view("test-version")

        self.assertFalse(view.authenticated)
        self.assertIsNone(view.subject)
        self.assertEqual(view.home_route, "/login")
        self.assertFalse(view.capabilities.admin_console)
        self.assertFalse(view.capabilities.studio)
        AuthView.model_validate(view.model_dump())

    def test_cors_exposes_account_export_summary_headers(self) -> None:
        middleware = next(
            item
            for item in create_app().user_middleware
            if item.cls.__name__ == "CORSMiddleware"
        )

        self.assertEqual(
            set(middleware.kwargs.get("expose_headers", [])),
            {"X-Export-Requested", "X-Exported", "X-Skipped"},
        )


class AuthHttpContractTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _app() -> FastAPI:
        app = FastAPI()
        app.include_router(system.create_router("test-version"))
        return app

    async def test_login_returns_complete_session_without_status_probe(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        identity = {"id": "user-key-1", "name": "Studio user", "role": "user"}
        with patch("api.system.require_identity", return_value=identity):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/auth/login")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            {
                "schema_version": 1,
                "authenticated": True,
                "version": "test-version",
                "subject": {"id": "user-key-1", "name": "Studio user", "role": "user"},
                "capabilities": {"admin_console": False, "studio": True},
                "home_route": "/studio",
            },
        )

    async def test_status_returns_the_same_anonymous_contract(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        with patch(
            "api.system.require_identity",
            side_effect=HTTPException(status_code=401, detail={"error": "invalid"}),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/auth/status")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["home_route"], "/login")
        self.assertEqual(response.json()["capabilities"], {"admin_console": False, "studio": False})
        self.assertIsNone(response.json()["subject"])


class UserKeyHttpContractTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _app() -> FastAPI:
        app = FastAPI()
        app.include_router(accounts.create_router())
        return app

    async def test_create_returns_raw_key_once_without_full_list(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        create_key = AsyncMock(return_value=(_user_key(), "sk-one-time"))
        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.run_in_threadpool", create_key),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/auth/users", json={"name": "Studio user"})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["raw_key"], "sk-one-time")
        self.assertEqual(response.json()["item"]["id"], "user-key-1")
        self.assertNotIn("items", response.json())

    async def test_update_returns_only_the_changed_item(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        updated = _user_key()
        updated["enabled"] = False
        update_key = AsyncMock(return_value=updated)
        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.run_in_threadpool", update_key),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/auth/users/user-key-1",
                    json={"enabled": False},
                )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["item"]["enabled"])
        self.assertNotIn("items", response.json())

    async def test_delete_returns_only_the_deleted_id(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        delete_key = AsyncMock(return_value=True)
        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.run_in_threadpool", delete_key),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete("/api/auth/users/user-key-1")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"deleted_id": "user-key-1"})


class AccountManagementHttpContractTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _app() -> FastAPI:
        app = FastAPI()
        app.include_router(accounts.create_router())
        return app

    def test_account_projection_exposes_credential_lifecycle(self) -> None:
        now = int(time.time())
        row = account_row(
            {
                "management_id": "acct_one",
                "access_token": _access_token(
                    issued_at=now - 60,
                    expires_at=now + 25 * 60 * 60,
                ),
                "refresh_token": "refresh-secret",
                "status": "正常",
                "last_token_refresh_at": "2026-07-30T01:02:03+00:00",
            },
            available=True,
            unlimited_quota=False,
        )

        self.assertEqual(row["access_token_status"], "valid")
        self.assertEqual(row["access_token_label"], "AT 有效")
        self.assertEqual(row["access_token_tone"], "success")
        self.assertEqual(row["access_token_issued_at"], now - 60)
        self.assertEqual(row["access_token_expires_at"], now + 25 * 60 * 60)
        self.assertEqual(row["refresh_token_status"], "valid")
        self.assertEqual(row["refresh_token_label"], "RT 有效")
        self.assertEqual(row["refresh_token_tone"], "success")
        self.assertTrue(row["can_refresh_access_token"])
        self.assertEqual(row["credential_availability"], "usable")
        self.assertEqual(row["credential_availability_label"], "可用")
        self.assertEqual(row["status_label"], "正常")
        self.assertEqual(row["status_tone"], "success")
        self.assertEqual(row["last_token_refresh_at"], 1785373323)
        self.assertIsNone(row["last_token_refresh_error"])
        self.assertIsNone(row["last_token_refresh_error_at"])
        self.assertNotIn("auth_kind", row)
        self.assertNotIn("has_refresh_token", row)
        self.assertNotIn("access_token_expires_in_seconds", row)

    def test_account_projection_owns_the_next_enabled_action(self) -> None:
        enabled = account_row(
            {
                "management_id": "acct_enabled",
                "access_token": "enabled-access-token",
                "status": "正常",
            },
            available=True,
            unlimited_quota=False,
        )
        disabled = account_row(
            {
                "management_id": "acct_disabled",
                "access_token": "disabled-access-token",
                "status": "禁用",
            },
            available=False,
            unlimited_quota=False,
        )

        self.assertTrue(enabled["enabled"])
        self.assertEqual(enabled["enabled_action"], "disable")
        self.assertEqual(enabled["enabled_action_label"], "停用账号")
        self.assertFalse(disabled["enabled"])
        self.assertEqual(disabled["enabled_action"], "enable")
        self.assertEqual(disabled["enabled_action_label"], "恢复启用")

    def test_credential_projection_uses_explicit_invalidity_without_unknown_states(self) -> None:
        now = int(time.time())
        expiring = account_row(
            {
                "management_id": "acct_expiring",
                "access_token": _access_token(issued_at=now - 60, expires_at=now + 60),
                "status": "正常",
            },
            available=True,
            unlimited_quota=False,
        )
        expired = account_row(
            {
                "management_id": "acct_expired",
                "access_token": _access_token(issued_at=now - 3600, expires_at=now - 1),
                "status": "正常",
            },
            available=False,
            unlimited_quota=False,
        )
        opaque = account_row(
            {
                "management_id": "acct_opaque",
                "access_token": "opaque-access-token",
                "refresh_token": "refresh-secret",
                "status": "正常",
                "refresh_token_invalid_at": "2026-07-30T02:03:04+00:00",
                "last_token_refresh_error": "invalid_grant for refresh-secret",
            },
            available=True,
            unlimited_quota=False,
        )
        invalid = account_row(
            {
                "management_id": "acct_invalid",
                "access_token": "another-opaque-token",
                "status": "正常",
                "last_remote_check_result": "invalid",
            },
            available=False,
            unlimited_quota=False,
        )
        manually_abnormal = account_row(
            {
                "management_id": "acct_manual_abnormal",
                "access_token": "manual-opaque-token",
                "status": "异常",
                "last_remote_check_result": "error",
            },
            available=False,
            unlimited_quota=False,
        )

        self.assertEqual(expiring["access_token_status"], "expiring")
        self.assertEqual(expiring["access_token_label"], "AT 临期")
        self.assertEqual(expiring["access_token_tone"], "warning")
        self.assertEqual(expired["access_token_status"], "invalid")
        self.assertEqual(expired["credential_availability"], "unavailable")
        self.assertEqual(expired["backend_status"], "正常")
        self.assertEqual(expired["status_category"], "abnormal")
        self.assertEqual(expired["status_label"], "异常")
        self.assertEqual(expired["status_reason_code"], "credentials_unavailable")
        self.assertEqual(expiring["refresh_token_status"], "missing")
        self.assertEqual(expiring["refresh_token_label"], "RT 缺失")
        self.assertEqual(expiring["refresh_token_tone"], "neutral")
        self.assertFalse(expiring["can_refresh_access_token"])
        self.assertEqual(opaque["access_token_status"], "valid")
        self.assertEqual(opaque["refresh_token_status"], "invalid")
        self.assertEqual(opaque["refresh_token_label"], "RT 失效")
        self.assertEqual(opaque["refresh_token_tone"], "error")
        self.assertEqual(opaque["refresh_token_invalid_at"], 1785376984)
        self.assertNotIn("refresh-secret", str(opaque["last_token_refresh_error"]))
        self.assertEqual(invalid["access_token_status"], "invalid")
        self.assertEqual(invalid["credential_availability"], "unavailable")
        self.assertEqual(invalid["backend_status"], "正常")
        self.assertEqual(invalid["status_category"], "abnormal")
        self.assertEqual(manually_abnormal["access_token_status"], "valid")

        recoverable = account_row(
            {
                "management_id": "acct_recoverable",
                "access_token": _access_token(issued_at=now - 3600, expires_at=now - 1),
                "refresh_token": "refresh-secret",
                "status": "正常",
            },
            available=True,
            unlimited_quota=False,
        )
        self.assertEqual(recoverable["credential_availability"], "recoverable")
        self.assertEqual(recoverable["status_category"], "normal")
        self.assertEqual(recoverable["status_label"], "正常")
        self.assertEqual(recoverable["status_reason_code"], "access_token_refresh_required")

    def test_primary_status_priority_is_owned_by_the_backend_projection(self) -> None:
        now = int(time.time())
        expired_access_token = _access_token(issued_at=now - 3600, expires_at=now - 1)

        disabled = account_row(
            {
                "management_id": "acct_disabled_unavailable",
                "access_token": expired_access_token,
                "status": "禁用",
            },
            available=False,
            unlimited_quota=False,
        )
        limited = account_row(
            {
                "management_id": "acct_limited_unavailable",
                "access_token": expired_access_token,
                "status": "限流",
            },
            available=False,
            unlimited_quota=False,
        )
        recoverable = account_row(
            {
                "management_id": "acct_recoverable",
                "access_token": expired_access_token,
                "refresh_token": "refresh-secret",
                "status": "正常",
            },
            available=True,
            unlimited_quota=False,
        )

        self.assertEqual(disabled["credential_availability"], "unavailable")
        self.assertEqual(disabled["status_category"], "disabled")
        self.assertEqual(disabled["status_label"], "禁用")
        self.assertFalse(disabled["enabled"])

        self.assertEqual(limited["credential_availability"], "unavailable")
        self.assertEqual(limited["status_category"], "abnormal")
        self.assertEqual(limited["status_label"], "异常")
        self.assertTrue(limited["enabled"])

        self.assertEqual(recoverable["credential_availability"], "recoverable")
        self.assertEqual(recoverable["status_category"], "normal")
        self.assertEqual(recoverable["status_label"], "正常")
        self.assertTrue(recoverable["enabled"])

    def test_missing_access_token_is_projected_as_invalid(self) -> None:
        lifecycle = project_access_token_lifecycle("")

        self.assertEqual(lifecycle.status, "invalid")
        self.assertIsNone(lifecycle.issued_at)
        self.assertIsNone(lifecycle.expires_at)

    async def test_get_account_refresh_token_returns_only_the_secret_without_caching(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        require_admin = Mock()
        account = {
            "management_id": "acct_one",
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
        }
        with (
            patch("api.accounts.require_admin", require_admin),
            patch("api.accounts._get_account_by_id", return_value=account),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/accounts/acct_one/refresh-token")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"refresh_token": "refresh-secret"})
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertNotIn("access-secret", response.text)
        self.assertNotIn("acct_one", response.text)
        require_admin.assert_called_once_with(None)

    async def test_get_account_refresh_token_returns_404_for_missing_account_or_token(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        cases = (
            (None, "account not found"),
            ({"management_id": "acct_one", "access_token": "access-secret"}, "refresh token not found"),
        )

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for account, expected_error in cases:
                with (
                    self.subTest(expected_error=expected_error),
                    patch("api.accounts.require_admin"),
                    patch("api.accounts._get_account_by_id", return_value=account),
                ):
                    response = await client.get("/api/accounts/acct_one/refresh-token")

                self.assertEqual(response.status_code, 404, response.text)
                self.assertEqual(response.json()["detail"]["error"], expected_error)

    async def test_batch_update_runs_atomic_service_method_in_threadpool(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        scheduled: list[object] = []

        def schedule(coroutine: object) -> object:
            scheduled.append(coroutine)
            return object()

        account = {
            "management_id": "acct_one",
            "access_token": "token-one",
        }
        update_accounts = Mock()
        run_in_threadpool = AsyncMock(return_value={
            "updated_ids": ["acct_one"],
            "removed_ids": [],
            "missing_tokens": [],
        })
        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.account_service.list_accounts", return_value=[account]),
            patch("api.accounts.account_service.update_accounts", update_accounts),
            patch("api.accounts.account_service.init_refresh_progress") as init_progress,
            patch("api.accounts.account_service.update_refresh_progress_stage") as update_stage,
            patch("api.accounts.account_service.update_refresh_progress") as update_progress,
            patch("api.accounts.account_service.finish_refresh_progress") as finish_progress,
            patch("api.accounts.run_in_threadpool", run_in_threadpool),
            patch("api.accounts.asyncio.create_task", side_effect=schedule),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/accounts/batch-update",
                    json={
                        "selection": {"mode": "all"},
                        "status": "\u7981\u7528",
                        "operation": "disable",
                    },
                )

            self.assertEqual(response.status_code, 200, response.text)
            progress_id = response.json()["progress_id"]
            self.assertEqual(response.json()["target_ids"], ["acct_one"])
            self.assertEqual(len(scheduled), 1)
            init_progress.assert_called_once_with(progress_id, 1)
            update_stage.assert_called_once_with(
                progress_id,
                "prepare_accounts",
                "\u6b63\u5728\u51c6\u5907 1 \u4e2a\u8d26\u53f7",
            )
            run_in_threadpool.assert_not_awaited()
            finish_progress.assert_not_called()
            await scheduled[0]

        self.assertEqual(
            run_in_threadpool.await_args.args,
            (update_accounts, ["token-one"], {"status": "\u7981\u7528"}),
        )
        self.assertTrue(run_in_threadpool.await_args.kwargs["quiet"])
        self.assertTrue(callable(run_in_threadpool.await_args.kwargs["progress_callback"]))
        update_progress.assert_called_once()
        result = finish_progress.call_args.args[1]
        self.assertEqual(result["updated_ids"], ["acct_one"])
        self.assertEqual(result["events"][0]["account_id"], "acct_one")
        self.assertEqual(result["events"][0]["action"], "disable_account")
        self.assertEqual(result["events"][0]["status"], "success")

    async def test_batch_update_reports_account_removed_during_mutation(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        scheduled: list[object] = []

        def schedule(coroutine: object) -> object:
            scheduled.append(coroutine)
            return object()

        account = {
            "management_id": "acct_one",
            "access_token": "token-one",
        }
        run_in_threadpool = AsyncMock(return_value={
            "updated_ids": [],
            "removed_ids": [],
            "missing_tokens": ["token-one"],
        })
        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.account_service.list_accounts", return_value=[account]),
            patch("api.accounts.account_service.get_account", return_value=account),
            patch("api.accounts.account_service.init_refresh_progress"),
            patch("api.accounts.account_service.update_refresh_progress"),
            patch("api.accounts.account_service.finish_refresh_progress") as finish_progress,
            patch("api.accounts.run_in_threadpool", run_in_threadpool),
            patch("api.accounts.asyncio.create_task", side_effect=schedule),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/accounts/batch-update",
                    json={
                        "selection": {"mode": "all"},
                        "status": "\u7981\u7528",
                        "operation": "disable",
                    },
                )
            await scheduled[0]

        self.assertEqual(response.status_code, 200, response.text)
        payload = finish_progress.call_args.args[1]
        self.assertEqual(payload["removed_ids"], ["acct_one"])
        self.assertEqual(
            payload["errors"],
            [{
                "id": "acct_one",
                "code": "account_not_found",
                "message": "account not found",
            }],
        )
        self.assertEqual(payload["events"][0]["account_id"], "acct_one")
        self.assertEqual(payload["events"][0]["status"], "failed")

    async def test_batch_update_counts_missing_selection_members_in_progress(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        scheduled: list[object] = []

        def schedule(coroutine: object) -> object:
            scheduled.append(coroutine)
            return object()

        account = {
            "management_id": "acct_one",
            "access_token": "token-one",
            "email": "one@example.com",
        }
        run_in_threadpool = AsyncMock(return_value={
            "updated_ids": ["acct_one"],
            "removed_ids": [],
            "missing_tokens": [],
        })
        with (
            patch("api.accounts.require_admin"),
            patch(
                "api.accounts._account_selection_targets",
                return_value=([("token-one", "acct_one")], ["acct_missing"]),
            ),
            patch("api.accounts.account_service.get_account", return_value=account),
            patch("api.accounts.account_service.init_refresh_progress") as init_progress,
            patch("api.accounts.account_service.update_refresh_progress") as update_progress,
            patch("api.accounts.account_service.finish_refresh_progress") as finish_progress,
            patch("api.accounts.run_in_threadpool", run_in_threadpool),
            patch("api.accounts.asyncio.create_task", side_effect=schedule),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/accounts/batch-update",
                    json={
                        "selection": {
                            "mode": "explicit",
                            "account_ids": ["acct_one", "acct_missing"],
                        },
                        "status": "\u6b63\u5e38",
                        "operation": "enable",
                    },
                )
            await scheduled[0]

        self.assertEqual(response.status_code, 200, response.text)
        progress_id = response.json()["progress_id"]
        init_progress.assert_called_once_with(progress_id, 2)
        update_progress.assert_any_call(
            progress_id,
            "acct_missing",
            account_id="acct_missing",
            account_label="acct_missing",
            action="enable_account",
            event_status="failed",
            event_message="account_not_found · \u8d26\u53f7\u4e0d\u5b58\u5728",
        )
        result = finish_progress.call_args.args[1]
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"][0]["id"], "acct_missing")
        self.assertEqual(
            [event["status"] for event in result["events"]],
            ["success", "failed"],
        )

    async def test_bulk_delete_returns_progress_before_atomic_service_call(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        scheduled: list[object] = []

        def schedule(coroutine: object) -> object:
            scheduled.append(coroutine)
            return object()

        account = {
            "management_id": "acct_one",
            "access_token": "token-one",
            "email": "one@example.com",
        }
        delete_accounts = Mock()
        run_in_threadpool = AsyncMock(return_value={
            "removed": 1,
            "removed_ids": ["acct_one"],
            "missing_tokens": [],
            "items": [],
        })
        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.account_service.list_accounts", return_value=[account]),
            patch("api.accounts.account_service.get_account", return_value=account),
            patch("api.accounts.account_service.delete_accounts", delete_accounts),
            patch("api.accounts.account_service.init_refresh_progress") as init_progress,
            patch("api.accounts.account_service.update_refresh_progress_stage") as update_stage,
            patch("api.accounts.account_service.update_refresh_progress") as update_progress,
            patch("api.accounts.account_service.finish_refresh_progress") as finish_progress,
            patch("api.accounts.run_in_threadpool", run_in_threadpool),
            patch("api.accounts.asyncio.create_task", side_effect=schedule),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.request(
                    "DELETE",
                    "/api/accounts",
                    json={"selection": {"mode": "all"}},
                )

            self.assertEqual(response.status_code, 200, response.text)
            progress_id = response.json()["progress_id"]
            init_progress.assert_called_once_with(progress_id, 1)
            update_stage.assert_called_once_with(
                progress_id,
                "prepare_accounts",
                "\u6b63\u5728\u51c6\u5907 1 \u4e2a\u8d26\u53f7",
            )
            run_in_threadpool.assert_not_awaited()
            await scheduled[0]

        self.assertEqual(
            run_in_threadpool.await_args.args,
            (delete_accounts, ["token-one"]),
        )
        self.assertFalse(run_in_threadpool.await_args.kwargs["return_items"])
        self.assertTrue(callable(run_in_threadpool.await_args.kwargs["progress_callback"]))
        update_progress.assert_called_once()
        result = finish_progress.call_args.args[1]
        self.assertEqual(result["removed"], 1)
        self.assertEqual(result["removed_ids"], ["acct_one"])
        self.assertEqual(result["events"][0]["action"], "delete_account")

    async def test_bulk_delete_does_not_report_an_account_removed_before_worker_runs(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        scheduled: list[object] = []

        def schedule(coroutine: object) -> object:
            scheduled.append(coroutine)
            return object()

        account = {
            "management_id": "acct_one",
            "access_token": "token-one",
            "email": "one@example.com",
        }
        run_in_threadpool = AsyncMock(return_value={
            "removed": 0,
            "removed_ids": [],
            "missing_tokens": ["token-one"],
            "items": [],
        })
        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.account_service.list_accounts", return_value=[account]),
            patch("api.accounts.account_service.get_account", return_value=None),
            patch("api.accounts.account_service.init_refresh_progress"),
            patch("api.accounts.account_service.update_refresh_progress_stage"),
            patch("api.accounts.account_service.update_refresh_progress"),
            patch("api.accounts.account_service.finish_refresh_progress") as finish_progress,
            patch("api.accounts.run_in_threadpool", run_in_threadpool),
            patch("api.accounts.asyncio.create_task", side_effect=schedule),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.request(
                    "DELETE",
                    "/api/accounts",
                    json={"selection": {"mode": "all"}},
                )
            await scheduled[0]

        self.assertEqual(response.status_code, 200, response.text)
        result = finish_progress.call_args.args[1]
        self.assertEqual(result["removed"], 0)
        self.assertEqual(result["removed_ids"], [])
        self.assertEqual(result["errors"][0]["id"], "acct_one")
        self.assertEqual(result["events"][0]["status"], "failed")

    async def test_single_edit_without_operation_returns_update_event(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        account = {
            "management_id": "acct_one",
            "access_token": "token-one",
            "email": "one@example.com",
            "status": "\u6b63\u5e38",
            "proxy": "",
        }
        updated_account = {
            **account,
            "proxy": "http://127.0.0.1:7890",
        }
        update_account = Mock(return_value=updated_account)
        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts._get_account_by_id", return_value=account),
            patch("api.accounts.account_service.get_account", return_value=account),
            patch("api.accounts.account_service.update_account", update_account),
            patch("api.accounts._account_for_api", return_value={"id": "acct_one"}),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/accounts/update",
                    json={
                        "id": "acct_one",
                        "proxy": "http://127.0.0.1:7890",
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["events"][0]["action"], "update_account")
        self.assertEqual(payload["events"][0]["message"], "\u8d26\u53f7\u5df2\u66f4\u65b0")
        update_account.assert_called_once_with(
            "token-one",
            {"proxy": "http://127.0.0.1:7890"},
        )

    async def test_single_edit_does_not_own_status_operations(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        account = {
            "management_id": "acct_one",
            "access_token": "token-one",
            "status": "\u6b63\u5e38",
        }
        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts._get_account_by_id", return_value=account),
            patch("api.accounts.account_service.get_account", return_value=account),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/accounts/update",
                    json={
                        "id": "acct_one",
                        "status": "\u7981\u7528",
                        "operation": "disable",
                    },
                )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("no updates provided", response.text)

    async def test_import_cleanup_returns_authoritative_delete_events(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        account = {
            "management_id": "acct_bad",
            "access_token": "access-secret",
            "email": "bad@example.com",
            "status": "\u5f02\u5e38",
        }
        delete_accounts = Mock(return_value={
            "removed": 1,
            "removed_ids": ["acct_bad"],
            "missing_tokens": [],
            "items": [],
        })
        with (
            patch("api.accounts.require_admin"),
            patch(
                "api.accounts._account_targets",
                return_value=([("access-secret", "acct_bad")], []),
            ),
            patch("api.accounts.account_service.get_account", return_value=account),
            patch("api.accounts.account_service.delete_accounts", delete_accounts),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/accounts/import-cleanup",
                    json={"account_ids": ["acct_bad"], "remove": True},
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["removed_ids"], ["acct_bad"])
        self.assertEqual(payload["events"][0]["account_label"], "bad@example.com")
        self.assertEqual(payload["events"][0]["action"], "delete_account")
        self.assertEqual(payload["events"][0]["status"], "success")
        self.assertNotIn("access-secret", response.text)
        delete_accounts.assert_called_once_with(["access-secret"], return_items=False)

    async def test_batch_status_operation_is_validated_before_mutation(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        run_in_threadpool = AsyncMock()
        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.run_in_threadpool", run_in_threadpool),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/accounts/batch-update",
                    json={
                        "selection": {"mode": "all"},
                        "status": "\u7981\u7528",
                        "operation": "reset",
                    },
                )

        self.assertEqual(response.status_code, 400, response.text)
        run_in_threadpool.assert_not_awaited()

    async def test_force_refresh_access_token_uses_selection_progress_without_quota_sync(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        targets = [
            ("token-one", "acct_one"),
            ("token-two", "acct_two"),
        ]
        raw_result = {
            "refreshed": 1,
            "skipped": 1,
            "updated_ids": ["acct_one", "acct_two"],
            "removed_ids": [],
            "errors": [
                {
                    "id": "acct_two",
                    "token": "token-two",
                    "code": "refresh_token_missing",
                    "error": "refresh token is missing",
                }
            ],
        }
        run_in_threadpool = AsyncMock(return_value=raw_result)
        finish_progress = Mock()
        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts._account_selection_targets", return_value=(targets, [])),
            patch(
                "api.accounts.account_service.get_account",
                side_effect=lambda token: {
                    "management_id": "acct_one" if token == "token-one" else "acct_two",
                    "access_token": token,
                    "refresh_token": "refresh-secret" if token == "token-one" else "",
                },
            ),
            patch("api.accounts.account_service.init_refresh_progress") as init_progress,
            patch("api.accounts.account_service.finish_refresh_progress", finish_progress),
            patch("api.accounts.run_in_threadpool", run_in_threadpool),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/accounts/refresh-access-token",
                    json={"selection": {"mode": "explicit", "account_ids": ["acct_one", "acct_two"]}},
                )
            await asyncio.sleep(0)

        self.assertEqual(response.status_code, 200, response.text)
        progress_id = response.json()["progress_id"]
        init_progress.assert_called_once_with(progress_id, 2)
        run_in_threadpool.assert_awaited_once_with(
            accounts.account_service.refresh_access_tokens,
            ["token-one", "token-two"],
            progress_id,
            finalize_progress=False,
        )
        result = finish_progress.call_args.args[1]
        self.assertEqual(result["refreshed"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["errors"][0]["id"], "acct_two")
        self.assertNotIn("refresh-secret", json.dumps(result))

    async def test_refresh_progress_counts_missing_selected_accounts_as_processed(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        run_in_threadpool = AsyncMock(return_value={
            "refreshed": 1,
            "skipped": 0,
            "updated_ids": ["acct_one"],
            "removed_ids": [],
            "errors": [],
        })
        finish_progress = Mock()
        with (
            patch("api.accounts.require_admin"),
            patch(
                "api.accounts._account_selection_targets",
                return_value=([("token-one", "acct_one")], ["acct_missing"]),
            ),
            patch(
                "api.accounts.account_service.get_account",
                return_value={
                    "management_id": "acct_one",
                    "access_token": "token-one",
                    "refresh_token": "refresh-secret",
                },
            ),
            patch("api.accounts.account_service.init_refresh_progress") as init_progress,
            patch("api.accounts.account_service.update_refresh_progress") as update_progress,
            patch("api.accounts.account_service.finish_refresh_progress", finish_progress),
            patch("api.accounts.run_in_threadpool", run_in_threadpool),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/accounts/refresh-access-token",
                    json={
                        "selection": {
                            "mode": "explicit",
                            "account_ids": ["acct_one", "acct_missing"],
                        },
                    },
                )
            await asyncio.sleep(0)

        self.assertEqual(response.status_code, 200, response.text)
        progress_id = response.json()["progress_id"]
        init_progress.assert_called_once_with(progress_id, 2)
        update_progress.assert_called_once_with(
            progress_id,
            "acct_missing",
            account_id="acct_missing",
            action="refresh_access_token",
            event_status="failed",
            event_message="account_not_found · \u8d26\u53f7\u4e0d\u5b58\u5728",
        )
        result = finish_progress.call_args.args[1]
        self.assertEqual(result["errors"][0]["id"], "acct_missing")

    async def test_active_remote_import_sources_return_conflict_on_delete(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        cases = (
            (
                "/api/cpa/pools/pool-one",
                "api.accounts.cpa_config.delete_pool",
                "CPA import job is active",
            ),
            (
                "/api/sub2api/servers/server-one",
                "api.accounts.sub2api_config.delete_server",
                "Sub2API import job is active",
            ),
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for path, target, expected_error in cases:
                with (
                    self.subTest(path=path),
                    patch("api.accounts.require_admin"),
                    patch(target, side_effect=ValueError("import job is active")),
                ):
                    response = await client.delete(path)

                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()["detail"]["error"], expected_error)

    async def test_active_remote_import_sources_return_conflict_on_update(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        cases = (
            (
                "/api/cpa/pools/pool-one",
                "api.accounts.cpa_config.update_pool",
                {"name": "Updated CPA"},
                "CPA import job is active",
            ),
            (
                "/api/sub2api/servers/server-one",
                "api.accounts.sub2api_config.update_server",
                {"name": "Updated Sub2API"},
                "Sub2API import job is active",
            ),
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for path, target, payload, expected_error in cases:
                with (
                    self.subTest(path=path),
                    patch("api.accounts.require_admin"),
                    patch(target, side_effect=ValueError("import job is active")),
                ):
                    response = await client.post(path, json=payload)

                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()["detail"]["error"], expected_error)

    async def test_export_rejects_a_missing_legacy_access_token(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        with (
            patch("api.accounts.require_admin"),
            patch(
                "api.accounts._account_selection_targets",
                return_value=([("valid-token", "acct_valid")], []),
            ),
            patch(
                "api.accounts._get_account_by_token_identity",
                side_effect=lambda token: {"access_token": token} if token == "valid-token" else None,
            ),
            patch("api.accounts.account_service.build_export_items") as build_export_items,
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/accounts/export",
                    json={
                        "access_tokens": ["valid-token", "missing-token"],
                        "format": "txt",
                    },
                )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["detail"]["error"], "one or more accounts were not found")
        build_export_items.assert_not_called()

    async def test_export_reports_actual_requested_exported_and_skipped_counts(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        with (
            patch("api.accounts.require_admin"),
            patch(
                "api.accounts._account_selection_targets",
                return_value=(
                    [
                        ("token-one", "acct_one"),
                        ("token-two", "acct_two"),
                        ("token-three", "acct_three"),
                    ],
                    [],
                ),
            ),
            patch(
                "api.accounts.account_service.build_export_items",
                return_value=[
                    {"access_token": "token-one"},
                    {"access_token": "token-two"},
                ],
            ),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/accounts/export",
                    json={"selection": {"mode": "all"}, "format": "txt"},
                )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["x-export-requested"], "3")
        self.assertEqual(response.headers["x-exported"], "2")
        self.assertEqual(response.headers["x-skipped"], "1")
        self.assertEqual(response.text, "token-one\ntoken-two\n")

    async def test_selection_preview_requires_admin_access(self) -> None:
        transport = httpx.ASGITransport(app=self._app())
        with patch(
            "api.accounts.require_admin",
            side_effect=HTTPException(status_code=403, detail={"error": "admin required"}),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/accounts/selection-preview",
                    json={"selection": {"mode": "all"}},
                )

        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()
