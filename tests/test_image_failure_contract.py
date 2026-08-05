from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from services.image_failure import (
    ImagePollTimeoutError,
    classify_image_exception,
    image_failure,
)
from services.openai_backend_api import OpenAIBackendAPI
from utils.helper import UpstreamHTTPError


def test_delivery_failure_switches_attempt_without_invalidating_account() -> None:
    failure = image_failure("image_download_failed")

    assert failure.switch_account is True
    assert failure.verify_account is False
    assert failure.account_failure is False


def test_account_failure_switches_attempt_and_verifies_account() -> None:
    failure = classify_image_exception(
        UpstreamHTTPError(
            "/backend-api/conversation",
            401,
            {"error": {"code": "token_revoked"}},
        )
    )

    assert failure.switch_account is True
    assert failure.verify_account is True
    assert failure.account_failure is True


def test_signed_asset_auth_failure_is_not_an_account_failure() -> None:
    failure = classify_image_exception(
        UpstreamHTTPError(
            "image_download",
            401,
            {"error": {"code": "token_revoked"}},
            credential_scope="signed_asset",
        )
    )

    assert failure.code == "image_download_failed"
    assert failure.scope == "delivery"
    assert failure.switch_account is True
    assert failure.verify_account is False


def test_interrupted_local_task_does_not_invalidate_account() -> None:
    failure = image_failure("task_interrupted")

    assert failure.verify_account is False
    assert failure.account_failure is False


@pytest.mark.parametrize("status_code", [404, 409, 423])
def test_structured_conversation_not_ready_is_pollable_without_account_penalty(
    status_code: int,
) -> None:
    failure = classify_image_exception(
        UpstreamHTTPError(
            "/backend-api/conversation/conversation-1",
            status_code,
            {"detail": {"code": "conversation_not_ready"}},
        )
    )

    assert failure.code == "conversation_not_ready"
    assert failure.status_code == status_code
    assert failure.retryable is True
    assert failure.verify_account is False


def test_image_poll_budget_uses_monotonic_clock() -> None:
    class Clock:
        now = 0.0

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.now += max(0.0, float(seconds))

    backend = object.__new__(OpenAIBackendAPI)
    backend._query_backend_tasks = mock.Mock(return_value=[])
    backend._get_conversation = mock.Mock(return_value={"mapping": {}})
    backend._conversation_poll_snapshot = mock.Mock(return_value=({}, ""))
    backend._extract_image_tool_records = mock.Mock(return_value=[])
    clock = Clock()

    with (
        mock.patch(
            "services.openai_backend_api.config",
            SimpleNamespace(
                image_poll_initial_wait_secs=0,
                image_poll_interval_secs=1,
                image_settle_enabled=False,
                image_settle_secs=0,
                image_check_before_hit_enabled=False,
            ),
        ),
        mock.patch(
            "services.openai_backend_api.time.monotonic",
            side_effect=clock.monotonic,
        ),
        mock.patch(
            "services.openai_backend_api.time.time",
            side_effect=AssertionError("poll budget must not use wall time"),
        ),
        mock.patch(
            "services.openai_backend_api.time.sleep",
            side_effect=clock.sleep,
        ),
    ):
        with pytest.raises(ImagePollTimeoutError) as raised:
            OpenAIBackendAPI._poll_image_results(
                backend,
                "conversation-1",
                timeout_secs=1,
            )

    assert raised.value.failure.code == "image_poll_timeout"
    assert clock.now == 1
