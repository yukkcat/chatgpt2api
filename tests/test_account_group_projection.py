from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from api import accounts
from services.proxy_management_service import ProxyManagementService


class _MemoryConfig:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = deepcopy(data)

    def get(self) -> dict[str, object]:
        return deepcopy(self.data)

    def update(self, values: dict[str, object]) -> dict[str, object]:
        self.data.update(deepcopy(values))
        return self.get()


class AccountGroupProjectionHttpTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _app() -> FastAPI:
        app = FastAPI()
        app.include_router(accounts.create_router())
        return app

    async def test_proxy_group_projection_uses_backend_group_name(self) -> None:
        store = _MemoryConfig({
            "proxy_groups": [
                {
                    "id": "primary",
                    "name": "主出口",
                    "enabled": True,
                    "nodes": [
                        {"id": "node-1", "url": "http://127.0.0.1:7890", "enabled": True},
                    ],
                },
            ],
            "account_groups": [
                {"id": "writers", "name": "写作组", "proxy": "group:primary"},
            ],
        })
        proxy_management = ProxyManagementService(store)
        transport = httpx.ASGITransport(app=self._app())

        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.config", store),
            patch("api.accounts.proxy_management_service", proxy_management),
            patch("api.accounts.account_service.list_accounts", return_value=[]),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/account-groups")

        self.assertEqual(response.status_code, 200, response.text)
        group = response.json()["groups"][0]
        self.assertEqual(group["proxy"], "group:primary")
        self.assertEqual(group["proxy_group_id"], "primary")
        self.assertEqual(group["proxy_mode"], "group")
        self.assertEqual(group["proxy_label"], "代理组：主出口")

    async def test_projection_owns_default_direct_legacy_and_custom_labels(self) -> None:
        store = _MemoryConfig({
            "proxy_groups": [],
            "account_groups": [
                {"id": "default", "proxy": "global"},
                {"id": "direct", "proxy": "direct"},
                {"id": "legacy", "proxy": "profile:old-egress"},
                {"id": "custom", "proxy": "http://127.0.0.1:7890"},
            ],
        })
        proxy_management = ProxyManagementService(store)
        transport = httpx.ASGITransport(app=self._app())

        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.config", store),
            patch("api.accounts.proxy_management_service", proxy_management),
            patch("api.accounts.account_service.list_accounts", return_value=[]),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/account-groups")

        self.assertEqual(response.status_code, 200, response.text)
        groups = {group["id"]: group for group in response.json()["groups"]}
        self.assertEqual(
            {
                group_id: (group["proxy"], group["proxy_mode"], group["proxy_label"])
                for group_id, group in groups.items()
            },
            {
                "default": ("", "inherit", "使用默认出口"),
                "direct": ("direct", "direct", "强制直连"),
                "legacy": ("profile:old-egress", "profile", "历史代理：old-egress"),
                "custom": (
                    "http://127.0.0.1:7890",
                    "custom",
                    "http://127.0.0.1:7890",
                ),
            },
        )

    async def test_save_response_returns_the_projected_account_group(self) -> None:
        store = _MemoryConfig({
            "proxy_groups": [
                {
                    "id": "primary",
                    "name": "主出口",
                    "enabled": True,
                    "nodes": [
                        {"id": "node-1", "url": "http://127.0.0.1:7890", "enabled": True},
                    ],
                },
            ],
            "account_groups": [],
        })
        proxy_management = ProxyManagementService(store)
        transport = httpx.ASGITransport(app=self._app())

        with (
            patch("api.accounts.require_admin"),
            patch("api.accounts.config", store),
            patch("api.accounts.proxy_management_service", proxy_management),
            patch("api.accounts.account_service.list_accounts", return_value=[]),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/account-groups",
                    json={"id": "writers", "name": "写作组", "proxy": "group:primary"},
                )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["group"], response.json()["groups"][0])
        self.assertEqual(response.json()["group"]["proxy_label"], "代理组：主出口")


if __name__ == "__main__":
    unittest.main()
