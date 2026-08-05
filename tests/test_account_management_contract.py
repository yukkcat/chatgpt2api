from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.accounts as accounts_module
import services.account_test_service as account_test_service_module
import services.account_service as account_service_module
from services.account_service import AccountService
from services.cpa_service import _normalize_import_job as normalize_cpa_import_job
from services.log_service import LOG_TYPE_ACCOUNT, LogService
from tests.support.account_repository import TestAccountRepository
from services.sub2api_service import _normalize_import_job as normalize_sub2api_import_job
from utils.diagnostics import sanitize_diagnostic_text


class AccountManagementContractTests(unittest.TestCase):
    ACCESS_TOKEN = "access-secret-token-a"
    REFRESH_TOKEN = "refresh-secret-token-a"
    ID_TOKEN = "id-secret-token-a"
    OTHER_ACCESS_TOKEN = "access-secret-token-b"
    OTHER_REFRESH_TOKEN = "refresh-secret-token-b"
    OTHER_ID_TOKEN = "id-secret-token-b"
    PROXY_USER = "proxy-user"
    PROXY_PASSWORD = "proxy-password"

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.service = AccountService(
            TestAccountRepository(Path(self.tmp_dir.name) / "accounts.json")
        )
        self.service.add_account_items([
            {
                "access_token": self.ACCESS_TOKEN,
                "refresh_token": self.REFRESH_TOKEN,
                "id_token": self.ID_TOKEN,
                "email": "first@example.test",
                "proxy": (
                    f"http://{self.PROXY_USER}:{self.PROXY_PASSWORD}"
                    "@proxy.example.test:8080"
                ),
                "last_remote_check_result": "error",
                "last_remote_check_error": (
                    f"request with {self.ACCESS_TOKEN} failed through "
                    f"http://{self.PROXY_USER}:{self.PROXY_PASSWORD}@proxy.example.test"
                ),
            },
            {
                "access_token": self.OTHER_ACCESS_TOKEN,
                "refresh_token": self.OTHER_REFRESH_TOKEN,
                "id_token": self.OTHER_ID_TOKEN,
                "email": "second@example.test",
            },
        ])
        self.account_id = str(
            (self.service.get_account(self.ACCESS_TOKEN) or {}).get("management_id") or ""
        )
        self.other_account_id = str(
            (self.service.get_account(self.OTHER_ACCESS_TOKEN) or {}).get("management_id") or ""
        )

        self.service_patcher = mock.patch.object(
            accounts_module,
            "account_service",
            self.service,
        )
        self.auth_patcher = mock.patch.object(
            accounts_module,
            "require_admin",
            lambda _authorization: {"id": "admin", "role": "admin"},
        )
        self.service_patcher.start()
        self.auth_patcher.start()
        self.addCleanup(self.service_patcher.stop)
        self.addCleanup(self.auth_patcher.stop)

        app = FastAPI()
        app.include_router(accounts_module.create_router())
        self.client = TestClient(app)

    def _assert_secret_free(self, payload: object) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        for secret in (
            self.ACCESS_TOKEN,
            self.REFRESH_TOKEN,
            self.ID_TOKEN,
            self.OTHER_ACCESS_TOKEN,
            self.OTHER_REFRESH_TOKEN,
            self.OTHER_ID_TOKEN,
            self.PROXY_PASSWORD,
        ):
            self.assertNotIn(secret, serialized)

    def _assert_proxy_credentials_absent(self, payload: object) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(self.PROXY_USER, serialized)
        self.assertNotIn(self.PROXY_PASSWORD, serialized)

    def _assert_no_credential_keys(self, value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                self.assertNotIn(
                    key,
                    {"access_token", "accessToken", "refresh_token", "id_token"},
                )
                self._assert_no_credential_keys(child)
        elif isinstance(value, list):
            for child in value:
                self._assert_no_credential_keys(child)

    def test_list_is_projected_and_masks_custom_proxy_credentials(self) -> None:
        response = self.client.get("/api/accounts", params={"page_size": 20})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(
            {item.get("id") for item in payload.get("items", [])},
            {self.account_id, self.other_account_id},
        )
        self._assert_secret_free(payload)
        self._assert_no_credential_keys(payload)
        self._assert_proxy_credentials_absent(payload)

    def test_detail_uses_stable_id_without_exposing_credentials(self) -> None:
        response = self.client.get(f"/api/accounts/{self.account_id}")

        self.assertEqual(response.status_code, 200, response.text)
        item = response.json().get("item", {})
        self.assertEqual(item.get("id"), self.account_id)
        self.assertEqual(
            item.get("configuration", {}).get("proxy"),
            f"http://{self.PROXY_USER}:{self.PROXY_PASSWORD}@proxy.example.test:8080",
        )
        self._assert_no_credential_keys(item)
        serialized = json.dumps(item, ensure_ascii=False)
        self.assertNotIn(self.ACCESS_TOKEN, serialized)
        self.assertNotIn(self.REFRESH_TOKEN, serialized)
        self.assertNotIn(self.ID_TOKEN, serialized)

    def test_access_token_is_only_returned_by_explicit_no_store_endpoint(self) -> None:
        response = self.client.get(f"/api/accounts/{self.account_id}/access-token")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"access_token": self.ACCESS_TOKEN})
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertNotIn(self.REFRESH_TOKEN, response.text)
        self.assertNotIn(self.ID_TOKEN, response.text)

    def test_refresh_token_is_only_returned_by_explicit_no_store_endpoint(self) -> None:
        response = self.client.get(f"/api/accounts/{self.account_id}/refresh-token")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"refresh_token": self.REFRESH_TOKEN})
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertNotIn(self.ACCESS_TOKEN, response.text)
        self.assertNotIn(self.ID_TOKEN, response.text)

    def test_refresh_token_endpoint_returns_404_for_missing_account_or_token(self) -> None:
        missing_account = self.client.get(
            "/api/accounts/acct_000000000000000000000000/refresh-token"
        )

        self.assertEqual(missing_account.status_code, 404, missing_account.text)
        self.assertEqual(
            missing_account.json().get("detail", {}).get("error"),
            "account not found",
        )

        updated = self.service.update_account(
            self.OTHER_ACCESS_TOKEN,
            {"refresh_token": ""},
            quiet=True,
        )
        self.assertIsNotNone(updated)

        missing_token = self.client.get(
            f"/api/accounts/{self.other_account_id}/refresh-token"
        )

        self.assertEqual(missing_token.status_code, 404, missing_token.text)
        self.assertEqual(
            missing_token.json().get("detail", {}).get("error"),
            "refresh token not found",
        )
        self.assertNotIn(self.OTHER_ACCESS_TOKEN, missing_token.text)
        self.assertNotIn(self.OTHER_ID_TOKEN, missing_token.text)

    def test_account_chat_test_returns_projected_result_without_credentials(self) -> None:
        expected = {
            "status": "success",
            "status_label": "测试通过",
            "tone": "success",
            "account_id": self.account_id,
            "account_label": "first@example.test",
            "mode": "chat",
            "mode_label": "对话",
            "model": "auto",
            "duration_ms": 42,
            "content": "OK",
            "quota_before_label": "5",
            "quota_after_label": "5",
            "quota_deducted": False,
            "error_code": "",
            "error_message": "",
        }
        with (
            mock.patch.object(
                accounts_module.account_test_service,
                "execute",
                return_value=expected,
            ) as execute,
            mock.patch("services.log_service.log_service.add") as add_log,
        ):
            response = self.client.post(
                f"/api/accounts/{self.account_id}/test",
                json={
                    "mode": "chat",
                    "model": "auto",
                    "prompt": "请仅回复 OK",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), expected)
        execute.assert_called_once_with({
            "account_id": self.account_id,
            "mode": "chat",
            "model": "auto",
            "prompt": "请仅回复 OK",
        })
        self.assertEqual(add_log.call_args.args[2]["status"], "success")
        self._assert_secret_free(response.json())
        self._assert_no_credential_keys(response.json())

    def test_account_chat_test_renews_at_and_executes_only_with_that_account(self) -> None:
        observed: dict[str, object] = {}

        class Backend:
            def __init__(self, *, access_token: str) -> None:
                observed["backend_token"] = access_token

            def close(self) -> None:
                observed["closed"] = True

        def conversation_events(_backend: object, **kwargs: object):
            observed["conversation"] = kwargs
            yield {"type": "conversation.delta", "delta": "O"}
            yield {"type": "conversation.delta", "delta": "K"}

        with (
            mock.patch.object(account_test_service_module, "account_service", self.service),
            mock.patch.object(
                self.service,
                "ensure_access_token",
                return_value="rotated-access-token",
            ) as ensure_access_token,
            mock.patch.object(account_test_service_module, "OpenAIBackendAPI", Backend),
            mock.patch.object(
                account_test_service_module,
                "conversation_events",
                side_effect=conversation_events,
            ),
            mock.patch("services.log_service.log_service.add") as add_log,
        ):
            response = self.client.post(
                f"/api/accounts/{self.account_id}/test",
                json={
                    "mode": "chat",
                    "model": "auto",
                    "prompt": "请仅回复 OK",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["content"], "OK")
        self.assertEqual(payload["account_id"], self.account_id)
        self.assertEqual(payload["account_label"], "first@example.test")
        self.assertEqual(observed.get("backend_token"), "rotated-access-token")
        self.assertEqual(
            observed.get("conversation"),
            {
                "model": "auto",
                "prompt": "请仅回复 OK",
            },
        )
        self.assertTrue(observed.get("closed"))
        self.assertEqual(add_log.call_args.args[2]["account_email"], "first@example.test")
        ensure_access_token.assert_called_once_with(
            self.ACCESS_TOKEN,
            event="account_test_chat",
            raise_on_error=True,
        )
        self._assert_secret_free(payload)

    def test_account_image_test_uses_selected_account_and_deducts_quota(self) -> None:
        image_token = "image-account-token"
        self.service.add_account_items([{
            "access_token": image_token,
            "email": "image@example.test",
            "type": "Plus",
            "quota": 5,
            "image_quota_unknown": False,
            "last_remote_check_result": "success",
            "last_remote_checked_at": datetime.now(timezone.utc).isoformat(),
        }])
        image_account = self.service.get_account(image_token) or {}
        image_account_id = str(image_account.get("management_id") or "")
        self.assertTrue(image_account_id)
        observed: dict[str, object] = {}

        class Backend:
            def __init__(self, *, access_token: str) -> None:
                observed["backend_token"] = access_token

            def close(self) -> None:
                observed["closed"] = True

        output_marker = object()

        def stream_image_outputs(_backend: object, request: object):
            observed["request"] = request
            return iter([output_marker])

        def collect_image_outputs(outputs: object):
            observed["outputs"] = list(outputs)
            return {
                "data": [{"url": "/images/account-test.png"}],
                "_image_urls": ["/images/account-test.png"],
            }

        with (
            mock.patch.object(account_test_service_module, "account_service", self.service),
            mock.patch.object(
                self.service,
                "ensure_access_token",
                return_value=image_token,
            ) as ensure_access_token,
            mock.patch.object(account_test_service_module, "OpenAIBackendAPI", Backend),
            mock.patch.object(
                account_test_service_module,
                "stream_image_outputs",
                side_effect=stream_image_outputs,
            ),
            mock.patch.object(
                account_test_service_module,
                "collect_image_outputs",
                side_effect=collect_image_outputs,
            ),
            mock.patch("services.log_service.log_service.add") as add_log,
            mock.patch("services.log_service.realtime_monitor_service.start") as monitor_start,
            mock.patch("services.log_service.realtime_monitor_service.finish") as monitor_finish,
        ):
            response = self.client.post(
                f"/api/accounts/{image_account_id}/test",
                json={
                    "mode": "image",
                    "model": "gpt-image-2",
                    "prompt": "一枚蓝色圆形图标",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["content"], "![image_1](/images/account-test.png)")
        self.assertEqual(payload["quota_before_label"], "5")
        self.assertEqual(payload["quota_after_label"], "4")
        self.assertTrue(payload["quota_deducted"])
        self.assertEqual(observed.get("backend_token"), image_token)
        self.assertEqual(observed.get("outputs"), [output_marker])
        self.assertTrue(observed.get("closed"))
        ensure_access_token.assert_called_once_with(
            image_token,
            event="account_test_image",
            raise_on_error=True,
            image_scope=True,
        )
        request = observed.get("request")
        self.assertEqual(getattr(request, "model", ""), "gpt-image-2")
        self.assertEqual(getattr(request, "prompt", ""), "一枚蓝色圆形图标")
        self.assertTrue(getattr(request, "trace_image_perf", False))
        self.assertTrue(getattr(request, "call_id", ""))
        monitor_start.assert_called_once()
        monitor_finish.assert_called_once()
        log_detail = add_log.call_args.args[2]
        self.assertEqual(log_detail["account_email"], "image@example.test")
        self.assertEqual(log_detail["urls"], ["/images/account-test.png"])
        current = self.service.get_account_by_id(image_account_id) or {}
        self.assertEqual(current.get("quota"), 4)
        self.assertEqual(current.get("success"), 1)
        self._assert_secret_free(payload)
        self.assertNotIn(image_token, response.text)

    def test_account_image_test_does_not_deduct_quota_for_empty_result(self) -> None:
        image_token = "empty-image-account-token"
        self.service.add_account_items([{
            "access_token": image_token,
            "email": "empty-image@example.test",
            "type": "Plus",
            "quota": 5,
            "image_quota_unknown": False,
            "last_remote_check_result": "success",
            "last_remote_checked_at": datetime.now(timezone.utc).isoformat(),
        }])
        image_account = self.service.get_account(image_token) or {}
        image_account_id = str(image_account.get("management_id") or "")

        class Backend:
            def __init__(self, *, access_token: str) -> None:
                self.access_token = access_token

            def close(self) -> None:
                pass

        with (
            mock.patch.object(account_test_service_module, "account_service", self.service),
            mock.patch.object(
                self.service,
                "ensure_access_token",
                return_value=image_token,
            ),
            mock.patch.object(account_test_service_module, "OpenAIBackendAPI", Backend),
            mock.patch.object(
                account_test_service_module,
                "stream_image_outputs",
                return_value=iter([object()]),
            ),
            mock.patch.object(
                account_test_service_module,
                "collect_image_outputs",
                return_value={"data": [], "_image_urls": []},
            ),
            mock.patch("services.log_service.log_service.add") as add_log,
            mock.patch("services.log_service.realtime_monitor_service.start"),
            mock.patch("services.log_service.realtime_monitor_service.finish") as monitor_finish,
        ):
            response = self.client.post(
                f"/api/accounts/{image_account_id}/test",
                json={
                    "mode": "image",
                    "model": "gpt-image-2",
                    "prompt": "生成一张测试图片",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["quota_before_label"], "5")
        self.assertEqual(payload["quota_after_label"], "5")
        self.assertFalse(payload["quota_deducted"])
        self.assertEqual(payload["content"], "")
        self.assertEqual(add_log.call_args.args[2]["status"], "failed")
        self.assertEqual(add_log.call_args.args[2]["account_email"], "empty-image@example.test")
        monitor_finish.assert_called_once()
        current = self.service.get_account_by_id(image_account_id) or {}
        self.assertEqual(current.get("quota"), 5)
        self.assertEqual(current.get("success") or 0, 0)
        self._assert_secret_free(payload)

    def test_proxy_change_scrubs_historical_colon_proxy_credentials(self) -> None:
        old_proxy = "old.example.test:8080:old-user:old-password"
        self.service.update_account(
            self.ACCESS_TOKEN,
            {
                "proxy": old_proxy,
                "last_remote_check_result": "error",
                "last_remote_check_error": f"request through {old_proxy} failed",
            },
            quiet=True,
        )
        updated = self.service.update_account(
            self.ACCESS_TOKEN,
            {"proxy": "direct"},
            quiet=True,
        )

        serialized_account = json.dumps(updated, ensure_ascii=False)
        self.assertNotIn("old-user", serialized_account)
        self.assertNotIn("old-password", serialized_account)

        response = self.client.get("/api/accounts", params={"page_size": 20})
        self.assertEqual(response.status_code, 200, response.text)
        serialized_response = json.dumps(response.json(), ensure_ascii=False)
        self.assertNotIn("old-user", serialized_response)
        self.assertNotIn("old-password", serialized_response)

    def test_diagnostic_sanitizer_handles_ipv6_basic_and_query_credentials(self) -> None:
        diagnostic = (
            "http://url-user:url-password@[2001:db8::1]:8080 "
            "[2001:db8::1]:8080:colon-user:colon-password "
            "Proxy-Authorization: Basic dXNlcjpwYXNzd29yZA== "
            "https://example.test/check?proxy_username=query-user"
            "&proxy_password=query-password&access_token=query-token"
        )

        sanitized = sanitize_diagnostic_text(diagnostic)

        for secret in (
            "url-user",
            "url-password",
            "colon-user",
            "colon-password",
            "dXNlcjpwYXNzd29yZA==",
            "query-user",
            "query-password",
            "query-token",
        ):
            self.assertNotIn(secret, sanitized)
        self.assertIn("[2001:db8::1]:8080:***:***", sanitized)
        self.assertIn("Proxy-Authorization: Basic [credential]", sanitized)

        ordinary_text = sanitize_diagnostic_text(
            "2026-07-25:12:34:56 redirect Bearer bare-secret",
            proxy_values=("direct",),
        )
        self.assertIn("2026-07-25:12:34:56", ordinary_text)
        self.assertIn("redirect", ordinary_text)
        self.assertNotIn("bare-secret", ordinary_text)

        json_text = sanitize_diagnostic_text(
            '{"accessToken":"camel-access","refreshToken":"camel-refresh"}'
        )
        self.assertNotIn("camel-access", json_text)
        self.assertNotIn("camel-refresh", json_text)

    def test_ipv6_proxy_label_preserves_brackets_without_credentials(self) -> None:
        self.service.update_account(
            self.ACCESS_TOKEN,
            {"proxy": "http://ipv6-user:ipv6-password@[2001:db8::1]:8080"},
            quiet=True,
        )

        response = self.client.get("/api/accounts", params={"page_size": 20})

        self.assertEqual(response.status_code, 200, response.text)
        item = next(
            account
            for account in response.json().get("items", [])
            if account.get("id") == self.account_id
        )
        self.assertEqual(item.get("proxy_label"), "http://[2001:db8::1]:8080")
        self.assertNotIn("ipv6-user", response.text)
        self.assertNotIn("ipv6-password", response.text)

    def test_image_last_used_at_is_utc_in_storage_and_projection(self) -> None:
        self.service.mark_image_result(
            self.ACCESS_TOKEN,
            True,
            quota_consumed=False,
        )

        raw_value = str(
            (self.service.get_account(self.ACCESS_TOKEN) or {}).get("last_used_at") or ""
        )
        parsed = datetime.fromisoformat(raw_value)
        self.assertEqual(parsed.utcoffset(), timezone.utc.utcoffset(parsed))

        response = self.client.get(f"/api/accounts/{self.account_id}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json().get("item", {}).get("last_used_at"),
            int(parsed.timestamp()),
        )

    def test_mutation_projection_uses_one_pool_snapshot_for_multiple_ids(self) -> None:
        with mock.patch.object(
            self.service,
            "list_accounts",
            wraps=self.service.list_accounts,
        ) as list_accounts:
            payload = accounts_module._account_mutation_payload(
                updated_ids=[self.account_id, self.other_account_id],
            )

        self.assertEqual(list_accounts.call_count, 1)
        self.assertEqual(
            [item.get("id") for item in payload.get("items", [])],
            [self.account_id, self.other_account_id],
        )

    def test_mutation_payload_keeps_updated_and_removed_results_exclusive(self) -> None:
        payload = accounts_module._account_mutation_response(
            updated=2,
            removed=1,
            updated_ids=[self.account_id, self.other_account_id],
            removed_ids=[self.account_id],
            include_items=False,
        )

        self.assertEqual(payload.get("updated"), 1)
        self.assertEqual(payload.get("removed"), 1)
        self.assertEqual(payload.get("updated_ids"), [self.other_account_id])
        self.assertEqual(payload.get("removed_ids"), [self.account_id])
        self.assertEqual(payload.get("status_label"), "已完成")
        self.assertEqual(payload.get("tone"), "success")
        self.assertIsInstance(payload.get("message"), str)
        self.assertIsInstance(payload.get("summary_items"), list)
        self.assertIsInstance(payload.get("events"), list)

    def test_account_logs_are_sanitized_before_persistence(self) -> None:
        database_url = f"sqlite:///{(Path(self.tmp_dir.name) / 'app.db').as_posix()}"
        service = LogService(database_url=database_url)
        service.add(
            LOG_TYPE_ACCOUNT,
            "account refresh failed for access-secret",
            {
                "access_token": "access-secret",
                "nested": {
                    "authorization": "Basic dXNlcjpwYXNzd29yZA==",
                    "message": (
                        "request through proxy.example.test:8080:proxy-user:proxy-password "
                        "with refresh_token=refresh-secret and access-secret"
                    ),
                },
            },
        )

        persisted = json.dumps(service.list(type=LOG_TYPE_ACCOUNT), ensure_ascii=False)
        for secret in (
            "access-secret",
            "dXNlcjpwYXNzd29yZA==",
            "proxy-user",
            "proxy-password",
            "refresh-secret",
        ):
            self.assertNotIn(secret, persisted)

    def test_single_id_batch_update_auto_removal_is_not_counted_as_updated(self) -> None:
        scheduled: list[object] = []

        def schedule(coroutine: object) -> object:
            scheduled.append(coroutine)
            return object()

        with (
            mock.patch.object(
                account_service_module.config.__class__,
                "auto_remove_invalid_accounts",
                new_callable=mock.PropertyMock,
                return_value=True,
            ),
            mock.patch.object(accounts_module.asyncio, "create_task", side_effect=schedule),
        ):
            response = self.client.post(
                "/api/accounts/batch-update",
                json={"account_ids": [self.account_id], "status": "\u5f02\u5e38"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            progress_id = str(response.json().get("progress_id") or "")
            asyncio.run(scheduled[0])

        self.addCleanup(self.service.clean_refresh_progress, progress_id)
        progress_response = self.client.get(
            f"/api/accounts/operations/{progress_id}"
        )
        self.assertEqual(progress_response.status_code, 200, progress_response.text)
        result = progress_response.json().get("result", {})
        self.assertEqual(result.get("updated"), 0)
        self.assertEqual(result.get("removed"), 1)
        self.assertEqual(result.get("updated_ids"), [])
        self.assertEqual(result.get("removed_ids"), [self.account_id])

    def test_sync_progress_uses_proxy_snapshot_after_account_removal(self) -> None:
        scheduled: list[object] = []
        proxy = (
            f"http://{self.PROXY_USER}:{self.PROXY_PASSWORD}"
            "@proxy.example.test:8080"
        )

        def schedule(coroutine: object) -> object:
            scheduled.append(coroutine)
            return object()

        def sync_and_remove(
            _tokens: list[str],
            _progress_id: str,
            *,
            finalize_progress: bool = True,
        ) -> dict[str, object]:
            self.assertFalse(finalize_progress)
            self.service.delete_accounts([self.ACCESS_TOKEN], return_items=False)
            return {
                "synced": 0,
                "errors": [{
                    "token": self.ACCESS_TOKEN,
                    "error": (
                        f"refresh through {proxy} failed with "
                        f"{self.REFRESH_TOKEN} and {self.ID_TOKEN}"
                    ),
                }],
                "items": [],
            }

        with (
            mock.patch.object(accounts_module.asyncio, "create_task", side_effect=schedule),
            mock.patch.object(
                self.service,
                "sync_accounts_and_quota",
                side_effect=sync_and_remove,
            ),
        ):
            response = self.client.post(
                "/api/accounts/sync",
                json={"account_ids": [self.account_id]},
            )
            self.assertEqual(response.status_code, 200, response.text)
            progress_id = str(response.json().get("progress_id") or "")
            asyncio.run(scheduled[0])

        self.addCleanup(self.service.clean_refresh_progress, progress_id)
        progress_response = self.client.get(
            f"/api/accounts/operations/{progress_id}"
        )
        self.assertEqual(progress_response.status_code, 200, progress_response.text)
        payload = progress_response.json()
        self._assert_secret_free(payload)
        self._assert_proxy_credentials_absent(payload)
        self.assertEqual(payload.get("result", {}).get("removed_ids"), [self.account_id])
        self.assertEqual(
            payload.get("result", {}).get("errors", [{}])[0].get("id"),
            self.account_id,
        )

    def test_unknown_detail_id_returns_404(self) -> None:
        response = self.client.get(
            "/api/accounts/acct_000000000000000000000000"
        )

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json().get("detail", {}).get("error"), "account not found")

    def test_unknown_nonempty_ids_do_not_expand_sync_to_all_accounts(self) -> None:
        with mock.patch.object(self.service, "sync_accounts_and_quota") as sync:
            for path in ("/api/accounts/sync", "/api/accounts/refresh"):
                response = self.client.post(
                    path,
                    json={"account_ids": ["acct_000000000000000000000000"]},
                )
                self.assertEqual(response.status_code, 400, response.text)

        sync.assert_not_called()

    def test_unknown_nonempty_ids_do_not_expand_export_to_all_accounts(self) -> None:
        with mock.patch.object(self.service, "build_export_items") as export:
            response = self.client.post(
                "/api/accounts/export",
                json={
                    "account_ids": ["acct_000000000000000000000000"],
                    "format": "json",
                },
            )

        self.assertEqual(response.status_code, 400, response.text)
        export.assert_not_called()

    def test_update_response_is_delta_only_and_secret_free(self) -> None:
        response = self.client.post(
            "/api/accounts/update",
            json={"id": self.account_id, "quota": 7},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload.get("item", {}).get("id"), self.account_id)
        self.assertNotIn(self.other_account_id, json.dumps(payload))
        self._assert_secret_free(payload)
        self._assert_no_credential_keys(payload)

    def test_create_response_contains_projected_affected_rows_only(self) -> None:
        new_token = "new-account-secret-token"
        response = self.client.post(
            "/api/accounts",
            json={
                "accounts": [{"access_token": new_token, "email": "new@example.test"}],
                "refresh": False,
                "return_items": True,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(new_token, serialized)
        self.assertNotIn(self.account_id, serialized)
        self.assertNotIn(self.other_account_id, serialized)
        self._assert_no_credential_keys(payload)

    def test_reimported_rotated_token_refreshes_current_account_after_restart(self) -> None:
        rotated_token = "rotated-access-secret-token-a"
        self.service._apply_refreshed_tokens(
            self.ACCESS_TOKEN,
            {
                "access_token": rotated_token,
                "refresh_token": self.REFRESH_TOKEN,
                "id_token": self.ID_TOKEN,
            },
            "test",
            expected_access_token=self.ACCESS_TOKEN,
            expected_refresh_token=self.REFRESH_TOKEN,
        )
        reloaded = AccountService(
            TestAccountRepository(Path(self.tmp_dir.name) / "accounts.json")
        )

        with (
            mock.patch.object(accounts_module, "account_service", reloaded),
            mock.patch.object(
                reloaded,
                "sync_accounts_and_quota",
                return_value={"synced": 1, "errors": []},
            ) as sync,
        ):
            response = self.client.post(
                "/api/accounts",
                json={
                    "accounts": [{"access_token": self.ACCESS_TOKEN}],
                    "sync_after_import": True,
                    "return_items": True,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload.get("added"), 0)
        self.assertEqual(payload.get("skipped"), 1)
        self.assertEqual(payload.get("synced"), 1)
        self.assertEqual(payload.get("updated_ids"), [self.account_id])
        self.assertEqual(payload.get("items", [{}])[0].get("id"), self.account_id)
        sync.assert_called_once_with([rotated_token])
        self._assert_secret_free(payload)
        self._assert_no_credential_keys(payload)

    def test_delete_response_does_not_return_remaining_account_pool(self) -> None:
        scheduled: list[object] = []

        def schedule(coroutine: object) -> object:
            scheduled.append(coroutine)
            return object()

        with mock.patch.object(accounts_module.asyncio, "create_task", side_effect=schedule):
            response = self.client.request(
                "DELETE",
                "/api/accounts",
                json={"account_ids": [self.account_id]},
            )
            self.assertEqual(response.status_code, 200, response.text)
            progress_id = str(response.json().get("progress_id") or "")
            self.assertTrue(progress_id)
            asyncio.run(scheduled[0])

        self.assertEqual(response.status_code, 200, response.text)
        progress = self.client.get(f"/api/accounts/operations/{progress_id}")
        self.assertEqual(progress.status_code, 200, progress.text)
        payload = progress.json().get("result") or {}
        self.assertEqual(payload.get("removed_ids"), [self.account_id])
        self.assertNotIn(self.other_account_id, json.dumps(progress.json()))
        self._assert_secret_free(progress.json())
        self._assert_no_credential_keys(progress.json())
        self.addCleanup(self.service.clean_refresh_progress, progress_id)

    def test_operation_progress_sanitizes_sync_result_and_keeps_legacy_alias(self) -> None:
        progress_id = "account-contract-progress"
        self.service.init_refresh_progress(progress_id, 1)
        self.service.finish_refresh_progress(
            progress_id,
            {
                "synced": 1,
                "updated_ids": [self.account_id],
                "removed_ids": [],
                "errors": [{
                    "token": self.ACCESS_TOKEN,
                    "error": (
                        f"failed with {self.ACCESS_TOKEN} through "
                        f"http://{self.PROXY_USER}:{self.PROXY_PASSWORD}@proxy.example.test"
                    ),
                }],
                "items": self.service.list_accounts(),
            },
        )
        self.addCleanup(self.service.clean_refresh_progress, progress_id)

        response = self.client.get(f"/api/accounts/operations/{progress_id}")
        legacy_response = self.client.get(
            f"/api/accounts/refresh/progress/{progress_id}"
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(legacy_response.status_code, 200, legacy_response.text)
        payload = response.json()
        self._assert_secret_free(payload)
        self._assert_proxy_credentials_absent(payload)
        self._assert_no_credential_keys(payload)
        result_items = payload.get("result", {}).get("items", [])
        self.assertEqual(
            [item.get("id") for item in result_items],
            [self.account_id],
        )
        self.assertEqual(payload.get("result", {}).get("errors", [{}])[0].get("id"), self.account_id)
        self.assertEqual(payload.get("result", {}).get("synced"), 1)
        self.assertNotIn("refreshed", payload.get("result", {}))
        self.assertEqual(
            set(payload.get("result", {})),
            {"synced", "skipped", "updated_ids", "removed_ids", "errors", "events", "items"},
        )
        legacy_result = legacy_response.json().get("result", {})
        self.assertEqual(legacy_result.get("refreshed"), 1)
        self.assertNotIn("synced", legacy_result)

    def test_management_id_survives_token_rotation_for_detail_update_export_and_delete(self) -> None:
        rotated_token = "rotated-access-secret-token-a"
        self.service._apply_refreshed_tokens(
            self.ACCESS_TOKEN,
            {
                "access_token": rotated_token,
                "refresh_token": self.REFRESH_TOKEN,
                "id_token": self.ID_TOKEN,
            },
            "test",
            expected_access_token=self.ACCESS_TOKEN,
            expected_refresh_token=self.REFRESH_TOKEN,
        )

        detail = self.client.get(f"/api/accounts/{self.account_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json().get("item", {}).get("id"), self.account_id)
        self.assertNotIn(rotated_token, detail.text)
        self._assert_no_credential_keys(detail.json())

        update = self.client.post(
            "/api/accounts/update",
            json={"id": self.account_id, "quota": 9},
        )
        self.assertEqual(update.status_code, 200, update.text)
        self.assertEqual(update.json().get("item", {}).get("id"), self.account_id)
        self.assertEqual((self.service.get_account(rotated_token) or {}).get("quota"), 9)

        exported = self.client.post(
            "/api/accounts/export",
            json={"account_ids": [self.account_id], "format": "json"},
        )
        self.assertEqual(exported.status_code, 200, exported.text)
        export_payload = json.loads(exported.content)
        self.assertEqual(export_payload.get("access_token"), rotated_token)

        scheduled: list[object] = []

        def schedule(coroutine: object) -> object:
            scheduled.append(coroutine)
            return object()

        with mock.patch.object(accounts_module.asyncio, "create_task", side_effect=schedule):
            deleted = self.client.request(
                "DELETE",
                "/api/accounts",
                json={"account_ids": [self.account_id]},
            )
            progress_id = str(deleted.json().get("progress_id") or "")
            self.assertTrue(progress_id)
            asyncio.run(scheduled[0])
        self.assertEqual(deleted.status_code, 200, deleted.text)
        progress = self.client.get(f"/api/accounts/operations/{progress_id}")
        self.assertEqual(progress.status_code, 200, progress.text)
        self.assertEqual(
            progress.json().get("result", {}).get("removed_ids"),
            [self.account_id],
        )
        self.assertIsNone(self.service.get_account(rotated_token))
        self.addCleanup(self.service.clean_refresh_progress, progress_id)

    def test_sync_initializes_progress_before_background_operation(self) -> None:
        scheduled: list[object] = []

        def schedule(coroutine: object) -> object:
            scheduled.append(coroutine)
            return object()

        with mock.patch.object(accounts_module.asyncio, "create_task", side_effect=schedule):
            response = self.client.post(
                "/api/accounts/sync",
                json={"account_ids": [self.account_id]},
            )

        self.assertEqual(response.status_code, 200, response.text)
        progress_id = response.json().get("progress_id")
        self.assertTrue(progress_id)
        self.assertEqual(len(scheduled), 1)
        try:
            progress = self.service.get_refresh_progress(progress_id)
            self.assertIsNotNone(progress)
            self.assertEqual(progress.get("total"), 1)
            self.assertEqual(progress.get("processed"), 0)
            self.assertFalse(progress.get("done"))
        finally:
            scheduled[0].close()

    def test_sync_progress_is_finalized_by_api_after_service_sync(self) -> None:
        service_progress_id = "service-refresh-progress"
        self.service.init_refresh_progress(service_progress_id, 1)
        account = self.service.get_account(self.ACCESS_TOKEN) or {}
        with mock.patch.object(self.service, "fetch_remote_info", return_value=account):
            result = self.service.sync_accounts_and_quota(
                [self.ACCESS_TOKEN],
                service_progress_id,
                finalize_progress=False,
            )
        self.addCleanup(self.service.clean_refresh_progress, service_progress_id)
        service_progress = self.service.get_refresh_progress(service_progress_id) or {}
        self.assertFalse(service_progress.get("done"))
        self.assertEqual(service_progress.get("processed"), 1)

        scheduled: list[object] = []
        observed: dict[str, object] = {}

        def schedule(coroutine: object) -> object:
            scheduled.append(coroutine)
            return object()

        def refresh_for_api(
            _tokens: list[str],
            progress_id: str,
            *,
            finalize_progress: bool = True,
        ) -> dict[str, object]:
            observed["progress_id"] = progress_id
            observed["finalize_progress"] = finalize_progress
            observed["done_during_service_refresh"] = bool(
                (self.service.get_refresh_progress(progress_id) or {}).get("done")
            )
            return result

        with (
            mock.patch.object(accounts_module.asyncio, "create_task", side_effect=schedule),
            mock.patch.object(
                self.service,
                "sync_accounts_and_quota",
                side_effect=refresh_for_api,
            ),
        ):
            response = self.client.post(
                "/api/accounts/sync",
                json={"account_ids": [self.account_id]},
            )
            self.assertEqual(response.status_code, 200, response.text)
            api_progress_id = str(response.json().get("progress_id") or "")
            self.assertTrue(api_progress_id)
            self.assertFalse((self.service.get_refresh_progress(api_progress_id) or {}).get("done"))
            asyncio.run(scheduled[0])

        self.addCleanup(self.service.clean_refresh_progress, api_progress_id)
        self.assertEqual(observed.get("progress_id"), api_progress_id)
        self.assertFalse(observed.get("finalize_progress"))
        self.assertFalse(observed.get("done_during_service_refresh"))
        self.assertTrue((self.service.get_refresh_progress(api_progress_id) or {}).get("done"))

    def test_oauth_finish_does_not_log_callback_or_code(self) -> None:
        callback = (
            "http://localhost/callback?"
            "code=oauth-super-secret-code&state=oauth-state"
        )
        tokens = {
            "access_token": "oauth-access-secret",
            "refresh_token": "oauth-refresh-secret",
            "id_token": "oauth-id-secret",
        }
        refresh_result = {
            "synced": 1,
            "errors": [],
            "items": self.service.list_accounts(),
        }
        with (
            mock.patch.object(
                accounts_module.oauth_login_service,
                "finish",
                return_value=tokens,
            ),
            mock.patch.object(
                self.service,
                "sync_accounts_and_quota",
                return_value=refresh_result,
            ),
            mock.patch("builtins.print") as printed,
        ):
            response = self.client.post(
                "/api/accounts/oauth/finish",
                json={"session_id": "oauth-session", "callback": callback},
            )

        self.assertEqual(response.status_code, 200, response.text)
        logged = " ".join(
            " ".join(str(arg) for arg in call.args)
            for call in printed.call_args_list
        )
        self.assertNotIn(callback, logged)
        self.assertNotIn("oauth-super-secret-code", logged)
        response_text = response.text
        self.assertNotIn(tokens["refresh_token"], response_text)
        self.assertNotIn(tokens["id_token"], response_text)
        self.assertNotIn(tokens["access_token"], response_text)

    def test_oauth_start_route_remains_available(self) -> None:
        result = {
            "session_id": "oauth-session",
            "authorize_url": "https://auth.openai.com/authorize?state=oauth-state",
        }
        with mock.patch.object(
            accounts_module.oauth_login_service,
            "start",
            return_value=result,
        ):
            response = self.client.post(
                "/api/accounts/oauth/start",
                json={"email_hint": "user@example.test"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), result)


class RemoteAccountImportContractTests(unittest.TestCase):
    NORMALIZERS = (normalize_cpa_import_job, normalize_sub2api_import_job)

    def test_synced_is_the_canonical_job_count(self) -> None:
        for normalize in self.NORMALIZERS:
            with self.subTest(normalize=normalize.__module__):
                job = normalize(
                    {"status": "completed", "synced": 2, "refreshed": 9},
                    fail_unfinished=False,
                )
                self.assertEqual(job["synced"], 2)
                self.assertNotIn("refreshed", job)

    def test_legacy_refreshed_count_is_translated_at_the_storage_boundary(self) -> None:
        for normalize in self.NORMALIZERS:
            with self.subTest(normalize=normalize.__module__):
                job = normalize(
                    {"status": "completed", "refreshed": 3},
                    fail_unfinished=False,
                )
                self.assertEqual(job["synced"], 3)
                self.assertNotIn("refreshed", job)


if __name__ == "__main__":
    unittest.main()
