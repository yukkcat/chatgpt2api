from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ModelCatalogSourceKind = Literal["config", "accounts", "fallback"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelCatalogDefaults(_StrictModel):
    chat_model: str = Field(min_length=1)
    image_model: str = Field(min_length=1)


class ModelCatalogCapabilities(_StrictModel):
    image_upscale: bool = False
    high_resolution_image_models: tuple[str, ...] = ()


class ModelCatalogSource(_StrictModel):
    chat: ModelCatalogSourceKind
    image: ModelCatalogSourceKind


class ModelCatalogView(_StrictModel):
    object: Literal["model_catalog"] = "model_catalog"
    schema_version: Literal[1] = 1
    generated_at: str = Field(min_length=1)
    revision: str = Field(min_length=1, max_length=64)
    chat_models: tuple[str, ...]
    image_models: tuple[str, ...]
    all_models: tuple[str, ...]
    defaults: ModelCatalogDefaults
    capabilities: ModelCatalogCapabilities
    source: ModelCatalogSource
    openai_models_endpoint: Literal["/v1/models"] = "/v1/models"

    @model_validator(mode="after")
    def validate_catalog(self) -> "ModelCatalogView":
        if not self.chat_models:
            raise ValueError("chat_models must not be empty")
        if not self.image_models:
            raise ValueError("image_models must not be empty")
        if len(self.chat_models) != len(set(self.chat_models)):
            raise ValueError("chat_models must be unique")
        if len(self.image_models) != len(set(self.image_models)):
            raise ValueError("image_models must be unique")

        expected_all = tuple(dict.fromkeys((*self.chat_models, *self.image_models)))
        if self.all_models != expected_all:
            raise ValueError("all_models must be the ordered union of chat_models and image_models")
        if self.defaults.chat_model not in self.chat_models:
            raise ValueError("default chat model must be listed in chat_models")
        if self.defaults.image_model not in self.image_models:
            raise ValueError("default image model must be listed in image_models")

        image_models = set(self.image_models)
        if any(
            model not in image_models
            for model in self.capabilities.high_resolution_image_models
        ):
            raise ValueError("high resolution models must be listed in image_models")
        return self
