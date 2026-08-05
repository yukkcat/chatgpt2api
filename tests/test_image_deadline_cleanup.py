from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from services.account_service import AccountService
from services.image_failure import (
    ImageFailureError,
    ImageGenerationError,
    classify_image_exception,
    image_failure,
)
from services.image_storage_service import ImageStorageService
from services.protocol import conversation
from tests.support.account_repository import TestAccountRepository


class _TrackingProxySettings:
    def __init__(self) -> None:
        self._egress_inflight: dict[str, int] = {}

    def acquire_image_egress(self, _profile, *, deadline_monotonic=None, cancel_event=None) -> int:
        self._egress_inflight["test-egress"] = self._egress_inflight.get("test-egress", 0) + 1
        return 0

    def release_image_egress(self, _profile) -> None:
        current = self._egress_inflight.get("test-egress", 0)
        if current <= 1:
            self._egress_inflight.pop("test-egress", None)
        else:
            self._egress_inflight["test-egress"] = current - 1

    @staticmethod
    def get_fallback_proxy_reference() -> str:
        return ""


class _DeadlineBackend:
    def __init__(self, *_args, **_kwargs) -> None:
        self.proxy_profile = SimpleNamespace(
            image_egress_reserved=False,
            image_concurrency_limit=4,
        )
        self.progress_callback = None

    def close(self) -> None:
        return None


class ImageDeadlineCleanupTests(unittest.TestCase):
    def test_parallel_deadline_releases_account_and_proxy_slots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = TestAccountRepository(Path(temp_dir) / "accounts.json")
            storage.save_accounts([{
                "access_token": "token-a",
                "quota": 50,
                "status": "正常",
                "fail": 0,
            }])
            accounts = AccountService(storage)
            proxies = _TrackingProxySettings()

            def reserve_account(**_kwargs) -> str:
                with accounts._image_slot_condition:
                    accounts._image_inflight["token-a"] = (
                        accounts._image_inflight.get("token-a", 0) + 1
                    )
                return "token-a"

            def expire_at_deadline(
                _backend,
                request: conversation.ConversationRequest,
                _index: int,
                _total: int,
            ):
                while time.monotonic() < request.deadline_monotonic:
                    time.sleep(0.002)
                raise ImageFailureError(
                    "image request deadline exceeded",
                    failure=image_failure("task_interrupted"),
                )
                yield  # pragma: no cover

            accounts.get_available_access_token = reserve_account
            request = conversation.ConversationRequest(
                model="gpt-image-2",
                prompt="draw four lighthouses",
                n=4,
                message_as_error=True,
            )

            with (
                mock.patch.object(conversation, "account_service", accounts),
                mock.patch.object(conversation, "proxy_settings", proxies),
                mock.patch.object(conversation, "OpenAIBackendAPI", _DeadlineBackend),
                mock.patch.object(conversation, "stream_image_outputs", expire_at_deadline),
                mock.patch.object(
                    type(conversation.config),
                    "image_parallel_generation",
                    new_callable=mock.PropertyMock,
                    return_value=True,
                ),
                mock.patch.object(
                    type(conversation.config),
                    "image_request_timeout_secs",
                    new_callable=mock.PropertyMock,
                    create=True,
                    return_value=0.08,
                ),
                mock.patch.object(
                    type(conversation.config),
                    "image_account_retry_enabled",
                    new_callable=mock.PropertyMock,
                    return_value=False,
                ),
            ):
                with self.assertRaises(ImageGenerationError) as raised:
                    conversation.collect_image_outputs(
                        conversation.stream_image_outputs_with_pool(request)
                    )

            self.assertEqual(raised.exception.failure.code, "task_interrupted")
            self.assertEqual(accounts._image_inflight, {})
            self.assertEqual(proxies._egress_inflight, {})
            self.assertEqual(accounts.get_account("token-a").get("fail"), 0)

    def test_expired_storage_deadline_is_not_an_account_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ImageStorageService(Path(temp_dir) / "image_index.json")

            with self.assertRaises(ImageFailureError) as raised:
                service.save(
                    b"image-bytes",
                    deadline_monotonic=time.monotonic() - 1,
                )

            failure = classify_image_exception(raised.exception)
            self.assertEqual(failure.code, "task_interrupted")
            self.assertFalse(failure.account_failure)


if __name__ == "__main__":
    unittest.main()
