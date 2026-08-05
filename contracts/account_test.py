from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AccountTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["chat", "image"]
    model: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=8000)


class AccountTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "failed"]
    status_label: str
    tone: Literal["success", "danger"]
    account_id: str
    account_label: str
    mode: Literal["chat", "image"]
    mode_label: str
    model: str
    duration_ms: int = Field(ge=0)
    content: str = ""
    quota_before_label: str = ""
    quota_after_label: str = ""
    quota_deducted: bool = False
    error_code: str = ""
    error_message: str = ""
