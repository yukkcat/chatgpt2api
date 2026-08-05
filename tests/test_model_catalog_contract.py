from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import system as system_api
from contracts.models import (
    ModelCatalogCapabilities,
    ModelCatalogDefaults,
    ModelCatalogSource,
    ModelCatalogView,
)
from services import model_catalog_service as catalog_module
from services.model_catalog_service import ModelCatalogService
from services.protocol import openai_v1_models


def _view() -> ModelCatalogView:
    return ModelCatalogView(
        generated_at="2026-07-26T00:00:00Z",
        revision="revision",
        chat_models=("auto", "gpt-5"),
        image_models=("gpt-image-2", "codex-gpt-image-2"),
        all_models=("auto", "gpt-5", "gpt-image-2", "codex-gpt-image-2"),
        defaults=ModelCatalogDefaults(
            chat_model="auto",
            image_model="gpt-image-2",
        ),
        capabilities=ModelCatalogCapabilities(
            image_upscale=False,
            high_resolution_image_models=("codex-gpt-image-2",),
        ),
        source=ModelCatalogSource(chat="fallback", image="accounts"),
    )


class ModelCatalogContractTests(unittest.TestCase):
    def test_service_owns_defaults_capabilities_and_ordered_union(self) -> None:
        settings = {
            "model_catalog": {
                "chat_models": ["auto", "gpt-5", "gpt-5"],
                "image_api_models": [
                    "gpt-image-2",
                    "codex-gpt-image-2",
                    "plus-codex-gpt-image-2",
                ],
            },
            "image_upscale_enabled": True,
        }
        with (
            patch.object(catalog_module.config, "get", return_value=settings),
            patch.object(catalog_module.account_service, "list_accounts") as list_accounts,
        ):
            view = ModelCatalogService().view()

        list_accounts.assert_not_called()
        self.assertEqual(view.chat_models, ("auto", "gpt-5"))
        self.assertEqual(
            view.image_models,
            ("gpt-image-2", "codex-gpt-image-2", "plus-codex-gpt-image-2"),
        )
        self.assertEqual(view.all_models, (*view.chat_models, *view.image_models))
        self.assertEqual(view.defaults.chat_model, "auto")
        self.assertEqual(view.defaults.image_model, "gpt-image-2")
        self.assertTrue(view.capabilities.image_upscale)
        self.assertEqual(
            view.capabilities.high_resolution_image_models,
            ("codex-gpt-image-2", "plus-codex-gpt-image-2"),
        )

    def test_fallback_snapshot_is_complete_when_no_account_is_available(self) -> None:
        with (
            patch.object(catalog_module.config, "get", return_value={}),
            patch.object(catalog_module.account_service, "list_accounts", return_value=[]),
        ):
            view = ModelCatalogService().view()

        self.assertEqual(view.source.chat, "fallback")
        self.assertEqual(view.source.image, "fallback")
        self.assertIn("auto", view.chat_models)
        self.assertEqual(view.image_models, ("gpt-image-2",))

    def test_openai_models_adapts_catalog_and_upstream_without_rederiving_accounts(self) -> None:
        view = _view()
        backend = MagicMock()
        backend.__enter__.return_value.list_models.return_value = {
            "data": [{"id": "upstream-only"}, {"id": "gpt-5"}],
        }
        with (
            patch.object(openai_v1_models, "get_model_catalog", return_value=view) as getter,
            patch.object(openai_v1_models, "OpenAIBackendAPI", return_value=backend),
        ):
            payload = openai_v1_models.list_models()

        getter.assert_called_once_with()
        self.assertEqual(
            [item["id"] for item in payload["data"]],
            ["auto", "gpt-5", "upstream-only", "gpt-image-2", "codex-gpt-image-2"],
        )

    def test_management_route_publishes_the_strict_response_model(self) -> None:
        route = next(
            route
            for route in system_api.create_router("test").routes
            if route.path == "/api/model-catalog"
        )
        self.assertIs(route.response_model, ModelCatalogView)

        app = FastAPI()
        with (
            patch.object(system_api, "require_identity", return_value={"id": "user"}),
            patch.object(system_api, "get_model_catalog", return_value=_view()) as getter,
        ):
            app.include_router(system_api.create_router("test"))
            response = TestClient(app).get("/api/model-catalog")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["schema_version"], 1)
        self.assertEqual(response.json()["all_models"], list(_view().all_models))
        getter.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
