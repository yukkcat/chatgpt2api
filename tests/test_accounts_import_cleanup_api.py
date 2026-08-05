from __future__ import annotations

import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.accounts as accounts_module


class FakeAccountService:
    def __init__(self):
        self.accounts = {
            "normal-token": {
                "management_id": "acct-normal",
                "access_token": "normal-token",
                "status": "\u6b63\u5e38",
            },
            "normal-token-with-error": {
                "management_id": "acct-normal-error",
                "access_token": "normal-token-with-error",
                "status": "\u6b63\u5e38",
                "last_refresh_error": "token invalidated (/backend-api/me)",
            },
            "limited-token": {
                "management_id": "acct-limited",
                "access_token": "limited-token",
                "status": "\u9650\u6d41",
            },
            "bad-token": {
                "management_id": "acct-bad",
                "access_token": "bad-token",
                "status": "\u5f02\u5e38",
            },
        }
        self.refresh_calls = []

    def list_accounts(self):
        return [dict(item) for item in self.accounts.values()]

    def get_account(self, access_token: str):
        item = self.accounts.get(access_token)
        return dict(item) if item else None

    def add_account_items(
        self,
        items: list[dict],
        return_items: bool = True,
        *,
        restore: bool = False,
    ):
        added = 0
        skipped = 0
        for item in items:
            token = str(item.get("access_token") or "").strip()
            if not token:
                continue
            if token in self.accounts:
                skipped += 1
            else:
                added += 1
            self.accounts[token] = {
                "management_id": f"acct-{token}",
                "access_token": token,
                "status": item.get("status") or "\u6b63\u5e38",
            }
        return {"added": added, "skipped": skipped, "items": list(self.accounts.values()) if return_items else []}

    def add_accounts(self, tokens: list[str], return_items: bool = True):
        return self.add_account_items([{"access_token": token} for token in tokens], return_items=return_items)

    def sync_accounts_and_quota(self, tokens: list[str], **kwargs):
        self.refresh_calls.append({"tokens": list(tokens), **kwargs})
        return {
            "synced": 0,
            "errors": [{"token": token, "error": "token invalidated (/backend-api/me)"} for token in tokens],
            "items": [],
        }

    def delete_accounts(self, tokens: list[str], return_items: bool = True):
        removed_ids = []
        missing_tokens = []
        for token in tokens:
            account = self.accounts.pop(token, None)
            if account is None:
                missing_tokens.append(token)
                continue
            account_id = str(account.get("management_id") or "").strip().lower()
            if account_id:
                removed_ids.append(account_id)
        items = list(self.accounts.values()) if return_items else []
        return {
            "removed": len(removed_ids),
            "removed_ids": list(dict.fromkeys(removed_ids)),
            "missing_tokens": missing_tokens,
            "items": items,
        }


class AccountImportCleanupApiTests(unittest.TestCase):
    def setUp(self):
        self.fake_service = FakeAccountService()
        self.service_patcher = mock.patch.object(accounts_module, "account_service", self.fake_service)
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

    def test_preview_counts_only_current_abnormal_import_tokens(self):
        response = self.client.post(
            "/api/accounts/import-cleanup",
            json={
                "access_tokens": ["normal-token", "limited-token", "bad-token", "missing-token"],
                "remove": False,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            "checked": 3,
            "abnormal": 1,
            "removed": 0,
            "updated_ids": [],
            "removed_ids": [],
            "errors": [],
            "events": [],
            "items": [],
        })
        self.assertIn("bad-token", self.fake_service.accounts)

    def test_remove_deletes_only_current_abnormal_import_tokens(self):
        response = self.client.post(
            "/api/accounts/import-cleanup",
            json={
                "access_tokens": ["normal-token", "limited-token", "bad-token", "missing-token"],
                "remove": True,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        events = payload.pop("events")
        self.assertEqual(payload, {
            "checked": 3,
            "abnormal": 1,
            "removed": 1,
            "updated_ids": [],
            "removed_ids": ["acct-bad"],
            "errors": [],
            "items": [],
        })
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].get("sequence"), 1)
        self.assertTrue(events[0].get("timestamp"))
        self.assertEqual(events[0].get("account_id"), "acct-bad")
        self.assertEqual(events[0].get("account_label"), "acct-bad")
        self.assertEqual(events[0].get("action"), "delete_account")
        self.assertEqual(events[0].get("status"), "success")
        self.assertEqual(events[0].get("message"), "导入后异常账号已删除")
        self.assertIn("normal-token", self.fake_service.accounts)
        self.assertIn("limited-token", self.fake_service.accounts)
        self.assertNotIn("bad-token", self.fake_service.accounts)

    def test_account_id_cleanup_reports_missing_ids_and_removed_ids(self):
        response = self.client.post(
            "/api/accounts/import-cleanup",
            json={
                "account_ids": ["acct-bad", "acct-missing"],
                "remove": True,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload.get("checked"), 1)
        self.assertEqual(payload.get("abnormal"), 1)
        self.assertEqual(payload.get("removed_ids"), ["acct-bad"])
        self.assertEqual(payload.get("errors"), [{
            "id": "acct-missing",
            "code": "account_not_found",
            "message": "account not found",
        }])

    def test_accounts_status_filter_uses_only_canonical_status(self):
        response = self.client.get("/api/accounts", params={"status": "abnormal", "page_size": 20})

        self.assertEqual(response.status_code, 200, response.text)
        account_ids = [item["id"] for item in response.json()["items"]]
        self.assertEqual(account_ids, ["acct-bad"])

    def test_create_accounts_uses_sync_after_import_policy(self):
        response = self.client.post(
            "/api/accounts",
            json={
                "accounts": [{"access_token": "new-token", "status": "\u6b63\u5e38"}],
                "sync_after_import": True,
                "return_items": False,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json().get("synced"), 0)
        self.assertNotIn("refreshed", response.json())
        self.assertEqual(len(self.fake_service.refresh_calls), 1)
        self.assertEqual(self.fake_service.refresh_calls[0]["tokens"], ["new-token"])
        self.assertNotIn("remove_invalid", self.fake_service.refresh_calls[0])

    def test_create_accounts_keeps_legacy_refresh_request_alias(self):
        response = self.client.post(
            "/api/accounts",
            json={
                "accounts": [{"access_token": "legacy-token", "status": "\u6b63\u5e38"}],
                "refresh": False,
                "return_items": False,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json().get("synced"), 0)
        self.assertEqual(response.json().get("refreshed"), 0)
        self.assertEqual(self.fake_service.refresh_calls, [])


if __name__ == "__main__":
    unittest.main()
