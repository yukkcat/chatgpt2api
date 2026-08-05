from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.ai as ai_module
from services.account_service import AccountService
from services.image_failure import (
    ImageDownloadError,
    ImageGenerationError,
    ImageFailureError,
    InvalidAccessTokenError,
    classify_conversation_failure,
    classify_image_exception,
    classify_message_facts,
    classify_upstream_message,
    extract_message_facts,
    image_failure,
    merge_message_failure,
)
from services.log_service import LoggedCall
from services.openai_backend_api import OpenAIBackendAPI
from services.protocol import conversation, openai_v1_chat_complete, openai_v1_response
from tests.support.account_repository import TestAccountRepository
from utils.helper import UpstreamHTTPError, image_sse_stream, sse_json_stream


class ImageFailureClassificationTests(unittest.TestCase):
    def test_natural_language_does_not_classify_quota_or_policy(self) -> None:
        failure = classify_image_exception(
            RuntimeError("quota exhausted and content policy blocked")
        )

        self.assertEqual(failure.code, "internal_error")
        self.assertIsNone(failure.capability)

    def test_structured_file_upload_429_only_blocks_upload(self) -> None:
        failure = classify_image_exception(
            UpstreamHTTPError(
                "/backend-api/files",
                429,
                {"detail": {"code": "rate_limit_exceeded"}},
            )
        )

        self.assertEqual(failure.code, "file_upload_throttled")
        self.assertEqual(failure.capability, "file_upload")
        self.assertTrue(failure.retryable)

    def test_all_file_upload_stages_only_block_upload(self) -> None:
        contexts = (
            "image_upload",
            "/backend-api/files/file-1/uploaded",
        )

        for context in contexts:
            with self.subTest(context=context):
                failure = classify_image_exception(
                    UpstreamHTTPError(
                        context,
                        429,
                        {"detail": {"code": "rate_limit_exceeded"}},
                    )
                )

                self.assertEqual(failure.code, "file_upload_throttled")
                self.assertEqual(failure.capability, "file_upload")

    def test_file_download_429_is_not_misclassified_as_upload(self) -> None:
        failure = classify_image_exception(
            UpstreamHTTPError(
                "/backend-api/files/file-1/download",
                429,
                {"detail": {"code": "rate_limit_exceeded"}},
            )
        )

        self.assertEqual(failure.code, "upstream_rate_limited")
        self.assertEqual(failure.capability, "image_generation")
        self.assertFalse(failure.retryable)
        self.assertTrue(failure.account_failure)

    def test_http_403_keeps_failure_boundary_despite_nested_policy_code(self) -> None:
        failure = classify_image_exception(
            UpstreamHTTPError(
                "/backend-api/conversation",
                403,
                {"error": {"code": "content_policy_violation"}},
            )
        )

        self.assertEqual(failure.code, "upstream_unavailable")
        self.assertIsNone(failure.capability)

    def test_account_http_401_takes_priority_over_policy_code(self) -> None:
        failure = classify_image_exception(
            UpstreamHTTPError(
                "/backend-api/conversation",
                401,
                {"error": {"code": "content_policy_violation"}},
            )
        )

        self.assertEqual(failure.code, "auth_invalid")
        self.assertEqual(failure.status_code, 401)
        self.assertTrue(failure.account_failure)


    def test_generic_http_403_does_not_invalidate_account(self) -> None:
        failure = classify_image_exception(
            UpstreamHTTPError(
                "/backend-api/conversation",
                403,
                {"detail": {"type": "forbidden"}},
            )
        )

        self.assertEqual(failure.code, "upstream_unavailable")
        self.assertIsNone(failure.capability)
        self.assertTrue(failure.retryable)

    def test_structured_http_failure_code_is_preserved(self) -> None:
        cases = {
            "unsupported_model": "unsupported_model",
            "image_tool_error": "invalid_image_input",
        }

        for upstream_code, expected_code in cases.items():
            with self.subTest(upstream_code=upstream_code):
                failure = classify_image_exception(
                    UpstreamHTTPError(
                        "/backend-api/conversation",
                        400,
                        {"error": {"code": upstream_code}},
                    )
                )

                self.assertEqual(failure.code, expected_code)

    def test_unclassified_http_400_remains_invalid_input(self) -> None:
        failure = classify_image_exception(
            UpstreamHTTPError(
                "/backend-api/conversation",
                400,
                {"error": {"code": "opaque_bad_request"}},
            )
        )

        self.assertEqual(failure.code, "invalid_image_input")

    def test_structured_tool_error_is_account_failure(self) -> None:
        failure = classify_upstream_message({
            "message": {
                "author": {"role": "tool"},
                "content": {"content_type": "system_error", "parts": ["opaque"]},
                "metadata": {"async_task_type": "image_gen", "is_error": True},
                "status": "finished_successfully",
            }
        })

        self.assertIsNotNone(failure)
        self.assertEqual(failure.code, "image_tool_error")
        self.assertEqual(failure.capability, "image_generation")

    def test_terminal_image_generation_text_is_terminal_failure(self) -> None:
        message = {
            "author": {"role": "assistant"},
            "content": {"content_type": "text", "parts": ["opaque final reply"]},
            "metadata": {"turn_use_case": "image gen"},
            "status": "finished_successfully",
            "end_turn": True,
        }

        message_failure = classify_upstream_message(message)
        conversation_failure = classify_conversation_failure({
            "mapping": {"node": {"message": message}},
        })

        self.assertIsNotNone(message_failure)
        self.assertEqual(message_failure.code, "upstream_text_reply")
        self.assertIsNotNone(conversation_failure)
        self.assertEqual(conversation_failure.code, "upstream_text_reply")

    def test_nonterminal_image_generation_text_is_not_terminal_failure(self) -> None:
        message = {
            "author": {"role": "assistant"},
            "content": {"content_type": "text", "parts": ["opaque progress"]},
            "metadata": {"turn_use_case": "image gen"},
            "status": "in_progress",
            "end_turn": False,
        }

        self.assertIsNone(classify_upstream_message(message))
        self.assertIsNone(classify_conversation_failure({
            "mapping": {"node": {"message": message}},
        }))

    def test_all_image_context_fields_preserve_terminal_text_failure(self) -> None:
        contexts = (
            {"turn_use_case": "image gen"},
            {"async_task_type": "image_gen"},
            {"message_type": "image_generation"},
        )

        for metadata in contexts:
            with self.subTest(metadata=metadata):
                failure = classify_upstream_message({
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["opaque final reply"]},
                    "metadata": metadata,
                    "status": "finished_successfully",
                    "end_turn": True,
                })

                self.assertIsNotNone(failure)
                self.assertEqual(failure.code, "upstream_text_reply")

    def test_empty_terminal_assistant_message_is_not_text_failure(self) -> None:
        failure = classify_upstream_message({
            "author": {"role": "assistant"},
            "content": {"content_type": "text", "parts": [""]},
            "metadata": {"turn_use_case": "image gen"},
            "status": "finished_successfully",
            "end_turn": True,
        })

        self.assertIsNone(failure)

    def test_terminal_image_tool_arguments_are_not_generic_message_failures(self) -> None:
        for tool_arguments in (
            json.dumps({"prompt": "draw a lighthouse", "size": "1024x1024", "n": 1}),
            json.dumps({"skipped_mainline": True}),
        ):
            with self.subTest(tool_arguments=tool_arguments):
                message = {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "code", "text": tool_arguments},
                    "metadata": {"turn_use_case": "image gen"},
                    "status": "finished_successfully",
                    "end_turn": True,
                }

                self.assertIsNone(classify_upstream_message(message))
                self.assertIsNone(classify_message_facts(
                    role="assistant",
                    content_type="code",
                    status="finished_successfully",
                    end_turn=True,
                    has_text=True,
                    raw_detail=tool_arguments,
                ))

    def test_pending_conversation_tool_arguments_are_not_failure(self) -> None:
        failure = classify_conversation_failure({
            "current_node": "tool",
            "mapping": {
                "user": {
                    "parent": None,
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["draw"]},
                    },
                },
                "code": {
                    "parent": "user",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"content_type": "code", "text": '{"size":"1024x1024","n":1}'},
                        "metadata": {"message_type": "next"},
                        "status": "finished_successfully",
                    },
                },
                "tool": {
                    "parent": "code",
                    "message": {
                        "author": {"role": "tool"},
                        "content": {"content_type": "text", "parts": ["processing image"]},
                        "status": "finished_successfully",
                    },
                },
            },
        })

        self.assertIsNone(failure)

    def test_unrelated_terminal_json_remains_plain_text_reply(self) -> None:
        failure = classify_upstream_message({
            "author": {"role": "assistant"},
            "content": {"content_type": "text", "parts": ['{"answer":42}']},
            "status": "finished_successfully",
            "end_turn": True,
        })

        self.assertIsNotNone(failure)
        self.assertEqual(failure.code, "upstream_text_reply")
        self.assertFalse(failure.account_failure)

    def test_nonterminal_image_tool_arguments_are_not_failure(self) -> None:
        failure = classify_upstream_message({
            "author": {"role": "assistant"},
            "content": {
                "content_type": "code",
                "text": '{"prompt":"draw a lighthouse","size":"1024x1024","n":1}',
            },
            "metadata": {"turn_use_case": "image gen"},
            "status": "in_progress",
            "end_turn": False,
        })

        self.assertIsNone(failure)

    def test_terminal_json_text_is_still_user_facing_text(self) -> None:
        for text in (
            '{"size":"1024x1024","n":1}',
            '{"prompt":"please explain size and n","size":"large","n":1}',
            '{"referenced_image_ids":[],"error":"cannot generate"}',
        ):
            with self.subTest(text=text):
                failure = classify_upstream_message({
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": [text]},
                    "metadata": {"turn_use_case": "image gen"},
                    "status": "finished_successfully",
                    "end_turn": True,
                })

                self.assertIsNotNone(failure)
                self.assertEqual(failure.code, "upstream_text_reply")

    def test_explicit_failed_status_is_terminal_without_error_text(self) -> None:
        expected_codes = {
            "failed": "upstream_error",
            "error": "upstream_error",
            "limited": "upstream_rate_limited",
            "rate_limited": "upstream_rate_limited",
        }
        for status, expected_code in expected_codes.items():
            with self.subTest(status=status):
                failure = classify_message_facts(
                    role="assistant",
                    content_type="text",
                    status=status,
                    has_text=False,
                )

                self.assertIsNotNone(failure)
                self.assertEqual(failure.code, expected_code)

    def test_image_output_wins_over_error_metadata(self) -> None:
        failure = classify_upstream_message({
            "author": {"role": "tool"},
            "content": {
                "content_type": "multimodal_text",
                "parts": [{"asset_pointer": "file-service://file-result"}],
            },
            "metadata": {
                "async_task_type": "image_gen",
                "is_error": True,
                "error": {"code": "insufficient_quota"},
            },
            "status": "finished_successfully",
        })

        self.assertIsNone(failure)

    def test_specific_failure_is_not_overridden_by_generic_failure(self) -> None:
        quota = image_failure("image_quota_exhausted")
        generic = image_failure("image_tool_error")

        self.assertEqual(merge_message_failure(quota, generic).code, quota.code)
        self.assertEqual(merge_message_failure(generic, quota).code, quota.code)

    def test_metadata_patch_extracts_structured_error_fields(self) -> None:
        facts = extract_message_facts({
            "p": "/message/metadata",
            "o": "replace",
            "v": {
                "is_error": True,
                "blocked": False,
                "error": {"code": "insufficient_quota"},
            },
        })

        self.assertTrue(facts["is_error"])
        self.assertIn("insufficient_quota", facts["codes"])

    def test_nested_metadata_code_patch_is_classified(self) -> None:
        facts = extract_message_facts({
            "p": "/message/metadata/error/code",
            "o": "replace",
            "v": "insufficient_quota",
        })
        failure = classify_message_facts(**facts)

        self.assertIsNotNone(failure)
        self.assertEqual(failure.code, "image_quota_exhausted")

    def test_known_structured_codes_are_shared_by_message_and_patch_paths(self) -> None:
        cases = {
            "unsupported_model": "unsupported_model",
            "image_tool_error": "image_tool_error",
            "auth_invalid": "auth_invalid",
            "rate_limit_exceeded": "upstream_rate_limited",
        }

        for upstream_code, expected_code in cases.items():
            with self.subTest(source="message", upstream_code=upstream_code):
                failure = classify_upstream_message({
                    "author": {"role": "tool"},
                    "content": {"content_type": "system_error", "parts": []},
                    "metadata": {"error_code": upstream_code},
                    "status": "failed",
                })
                self.assertIsNotNone(failure)
                self.assertEqual(failure.code, expected_code)

            with self.subTest(source="patch", upstream_code=upstream_code):
                facts = extract_message_facts({
                    "p": "/message/error/code",
                    "o": "replace",
                    "v": upstream_code,
                })
                failure = classify_message_facts(**facts)
                self.assertIsNotNone(failure)
                self.assertEqual(failure.code, expected_code)

    def test_specific_structured_code_overrides_generic_error_type(self) -> None:
        cases = {
            "rate_limit_exceeded": "upstream_rate_limited",
            "unsupported_model": "unsupported_model",
        }

        for upstream_code, expected_code in cases.items():
            with self.subTest(upstream_code=upstream_code):
                failure = classify_upstream_message({
                    "author": {"role": "tool"},
                    "content": {"content_type": "system_error", "parts": []},
                    "metadata": {
                        "is_error": True,
                        "error": {
                            "type": "image_tool_error",
                            "code": upstream_code,
                        },
                    },
                    "status": "failed",
                })

                self.assertIsNotNone(failure)
                self.assertEqual(failure.code, expected_code)

    def test_top_level_message_error_patch_is_terminal(self) -> None:
        facts = extract_message_facts([
            {"p": "/message/author/role", "o": "replace", "v": "tool"},
            {"p": "/message/is_error", "o": "replace", "v": True},
            {"p": "/message/metadata/status", "o": "replace", "v": "failed"},
        ])

        failure = classify_message_facts(**facts)

        self.assertIsNotNone(failure)
        self.assertEqual(failure.code, "upstream_error")

    def test_nonempty_structured_error_field_is_terminal_without_code(self) -> None:
        full_message_failure = classify_upstream_message({
            "author": {"role": "tool"},
            "content": {"content_type": "text", "parts": []},
            "metadata": {"async_task_type": "image_gen"},
            "error": {"message": "opaque upstream failure"},
            "status": "in_progress",
        })
        patch_facts = extract_message_facts({
            "p": "/message/metadata/error",
            "o": "replace",
            "v": {"message": "opaque upstream failure"},
        })
        patch_failure = classify_message_facts(**patch_facts)

        self.assertIsNotNone(full_message_failure)
        self.assertEqual(full_message_failure.code, "upstream_error")
        self.assertIsNotNone(patch_failure)
        self.assertEqual(patch_failure.code, "upstream_error")

    def test_string_error_code_is_shared_by_message_and_patch_paths(self) -> None:
        for field_owner in ("message", "metadata"):
            with self.subTest(field_owner=field_owner):
                message = {
                    "author": {"role": "tool"},
                    "content": {"content_type": "system_error", "parts": []},
                    "metadata": {"async_task_type": "image_gen"},
                    "status": "failed",
                }
                if field_owner == "message":
                    message["error"] = "insufficient_quota"
                else:
                    message["metadata"]["error"] = "insufficient_quota"

                failure = classify_upstream_message(message)

                self.assertIsNotNone(failure)
                self.assertEqual(failure.code, "image_quota_exhausted")

        patch_facts = extract_message_facts({
            "p": "/message/metadata/error",
            "o": "replace",
            "v": "insufficient_quota",
        })
        patch_failure = classify_message_facts(**patch_facts)
        self.assertIsNotNone(patch_failure)
        self.assertEqual(patch_failure.code, "image_quota_exhausted")

    def test_status_field_uses_the_shared_structured_classifier(self) -> None:
        expected_by_status = {
            "rate_limit_exceeded": "upstream_rate_limited",
            "quota_exhausted": "image_quota_exhausted",
            "auth_invalid": "auth_invalid",
            "content_policy_violation": "content_policy_violation",
        }

        for status, expected_code in expected_by_status.items():
            with self.subTest(status=status):
                failure = classify_message_facts(status=status)

                self.assertIsNotNone(failure)
                self.assertEqual(failure.code, expected_code)

    def test_top_level_blocked_field_is_policy_failure(self) -> None:
        failure = classify_upstream_message({
            "author": {"role": "assistant"},
            "content": {"content_type": "text", "parts": []},
            "blocked": True,
            "status": "failed",
        })

        self.assertIsNotNone(failure)
        self.assertEqual(failure.code, "content_policy_violation")


class ImageCapabilityCooldownTests(unittest.TestCase):
    def _service(self, root: Path) -> AccountService:
        storage = TestAccountRepository(root / "accounts.json")
        storage.save_accounts([
            {"access_token": "token-a", "quota": 5},
            {"access_token": "token-b", "quota": 5},
        ])
        return AccountService(storage)

    def test_file_upload_failure_blocks_account_until_remote_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))
            service.mark_image_result(
                "token-a",
                False,
                failure=image_failure("file_upload_throttled"),
            )

            ready_tokens = service._list_ready_candidate_tokens()

            self.assertNotIn("token-a", ready_tokens)
            self.assertIn("token-b", ready_tokens)

    def test_text_outcome_does_not_penalize_or_verify_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))
            before = service.get_account("token-a") or {}

            with mock.patch.object(service, "_schedule_account_refresh_after_image_failure") as refresh:
                after = service.mark_image_result(
                    "token-a",
                    False,
                    failure=image_failure("content_policy_violation"),
                ) or {}

            self.assertEqual(after.get("fail"), before.get("fail"))
            self.assertNotEqual(after.get("last_remote_check_result"), "pending")
            refresh.assert_not_called()

    def test_delivery_failure_does_not_penalize_or_verify_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))
            before = service.get_account("token-a") or {}

            with mock.patch.object(
                service,
                "_schedule_account_refresh_after_image_failure",
            ) as verify:
                after = service.mark_image_result(
                    "token-a",
                    False,
                    failure=image_failure("image_download_failed"),
                ) or {}

            self.assertEqual(after.get("fail"), before.get("fail"))
            self.assertNotEqual(after.get("last_remote_check_result"), "pending")
            verify.assert_not_called()

    def test_failure_state_is_written_before_waiting_selectors_are_woken(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))
            notified_failure_codes: list[str | None] = []

            class InspectingCondition:
                def __enter__(self):
                    service._lock.acquire()
                    return self

                def __exit__(self, exc_type, exc_value, traceback):
                    service._lock.release()

                def notify_all(self) -> None:
                    account = service._accounts["token-a"]
                    notified_failure_codes.append(
                        f"{account.get('last_remote_check_result')}:"
                        f"{account.get('pending_auth_scope')}"
                    )

            service._image_inflight["token-a"] = 1
            service._image_slot_condition = InspectingCondition()

            service.mark_image_result(
                "token-a",
                False,
                failure=image_failure("image_poll_timeout"),
            )

            self.assertEqual(notified_failure_codes, ["pending:image"])

    def test_success_does_not_bypass_pending_remote_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))
            with mock.patch.object(service, "_schedule_account_refresh_after_image_failure"):
                service.mark_image_result(
                    "token-a",
                    False,
                    failure=image_failure("image_tool_error"),
                )
            self.assertNotIn(
                "token-a",
                service._list_ready_candidate_tokens(),
            )

            service.mark_image_result(
                "token-a",
                True,
                capabilities={"image_generation"},
            )

            self.assertIn(
                "token-b",
                service._list_ready_candidate_tokens(),
            )
            self.assertNotIn(
                "token-a",
                service._list_ready_candidate_tokens(),
            )

    def test_auth_failure_blocks_account_until_remote_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))
            with mock.patch.object(service, "_schedule_account_refresh_after_image_failure"):
                service.mark_image_result(
                    "token-a",
                    False,
                    failure=image_failure("auth_invalid"),
                )

            self.assertNotIn(
                "token-a",
                service._list_ready_candidate_tokens(),
            )

            with mock.patch(
                "services.openai_backend_api.OpenAIBackendAPI",
                self._remote_backend({
                    "quota": 5,
                    "image_quota_unknown": False,
                    "status": "正常",
                }),
            ):
                service.fetch_remote_info("token-a", "test")

            self.assertIn(
                "token-a",
                service._list_ready_candidate_tokens(),
            )

    @staticmethod
    def _remote_backend(result: dict[str, object]):
        class FakeBackend:
            def __init__(self, _access_token: str, **_kwargs: object) -> None:
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def get_user_info(self) -> dict[str, object]:
                return dict(result)

        return FakeBackend

    def test_remote_quota_recovery_clears_quota_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))
            with mock.patch.object(service, "_schedule_account_refresh_after_image_failure"):
                service.mark_image_result(
                    "token-a",
                    False,
                    failure=image_failure("image_quota_exhausted"),
                )

            with mock.patch(
                "services.openai_backend_api.OpenAIBackendAPI",
                self._remote_backend({
                    "quota": 5,
                    "image_quota_unknown": False,
                    "status": "正常",
                }),
            ):
                service.fetch_remote_info("token-a", "test")

            self.assertIn(
                "token-a",
                service._list_ready_candidate_tokens(),
            )

    def test_remote_account_check_clears_tool_error_pending_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))
            with mock.patch.object(service, "_schedule_account_refresh_after_image_failure"):
                service.mark_image_result(
                    "token-a",
                    False,
                    failure=image_failure("image_tool_error"),
                )

            with mock.patch(
                "services.openai_backend_api.OpenAIBackendAPI",
                self._remote_backend({
                    "quota": 5,
                    "image_quota_unknown": False,
                    "status": "正常",
                }),
            ):
                service.fetch_remote_info("token-a", "test")

            self.assertIn(
                "token-a",
                service._list_ready_candidate_tokens(),
            )


class AccountRefreshFailureTests(unittest.TestCase):
    def _service(self, root: Path) -> AccountService:
        storage = TestAccountRepository(root / "accounts.json")
        storage.save_accounts([{"access_token": "token-a", "quota": 5}])
        return AccountService(storage)

    def test_network_exception_is_reported_as_structured_refresh_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))
            with mock.patch.object(
                service,
                "fetch_remote_info",
                side_effect=ConnectionError("opaque connection failure"),
            ):
                result = service.refresh_accounts(["token-a"])

            self.assertEqual(len(result["errors"]), 1)
            self.assertEqual(
                result["errors"][0]["failure_code"],
                "upstream_connection_failed",
            )

    def test_unclassified_refresh_exception_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(Path(temp_dir))
            with mock.patch.object(
                service,
                "fetch_remote_info",
                side_effect=RuntimeError("opaque refresh failure"),
            ):
                result = service.refresh_accounts(["token-a"])

            self.assertEqual(len(result["errors"]), 1)

    def test_image_failure_refresh_waits_for_worker_capacity(self) -> None:
        class DeferredThread:
            started: list[object] = []

            def __init__(self, *, target, **_options: object) -> None:
                self.target = target

            def start(self) -> None:
                self.started.append(self.target)

        with tempfile.TemporaryDirectory() as temp_dir:
            storage = TestAccountRepository(Path(temp_dir) / "accounts.json")
            storage.save_accounts([
                {"access_token": "token-a", "quota": 5},
                {"access_token": "token-b", "quota": 5},
            ])
            service = AccountService(storage)
            refreshed: list[str] = []
            DeferredThread.started = []

            with (
                mock.patch(
                    "services.config.ConfigStore.account_processing_concurrency",
                    new_callable=mock.PropertyMock,
                    return_value=1,
                ),
                mock.patch("services.account_service.Thread", DeferredThread),
                mock.patch.object(
                    service,
                    "_refresh_account_after_image_failure",
                    side_effect=refreshed.append,
                ),
            ):
                service._schedule_account_refresh_after_image_failure("token-a")
                service._schedule_account_refresh_after_image_failure("token-b")

                self.assertEqual(len(DeferredThread.started), 1)
                DeferredThread.started.pop(0)()
                self.assertEqual(len(DeferredThread.started), 1)
                DeferredThread.started.pop(0)()

            self.assertEqual(refreshed, ["token-a", "token-b"])

    def test_image_failure_refresh_start_error_does_not_block_next_item(self) -> None:
        class StartFailingThread:
            start_calls = 0
            started: list[object] = []

            def __init__(self, *, target, **_options: object) -> None:
                self.target = target

            def start(self) -> None:
                type(self).start_calls += 1
                if type(self).start_calls == 1:
                    raise RuntimeError("thread start failed")
                type(self).started.append(self.target)

        with tempfile.TemporaryDirectory() as temp_dir:
            storage = TestAccountRepository(Path(temp_dir) / "accounts.json")
            storage.save_accounts([
                {"access_token": "token-a", "quota": 5},
                {"access_token": "token-b", "quota": 5},
            ])
            service = AccountService(storage)
            refreshed: list[str] = []
            StartFailingThread.start_calls = 0
            StartFailingThread.started = []

            with (
                mock.patch(
                    "services.config.ConfigStore.account_processing_concurrency",
                    new_callable=mock.PropertyMock,
                    return_value=1,
                ),
                mock.patch("services.account_service.Thread", StartFailingThread),
                mock.patch.object(
                    service,
                    "_refresh_account_after_image_failure",
                    side_effect=refreshed.append,
                ),
                mock.patch("services.account_service.log_service.add"),
            ):
                service._schedule_account_refresh_after_image_failure("token-a")
                service._schedule_account_refresh_after_image_failure("token-b")
                service._start_pending_image_failure_refreshes()

                self.assertEqual(StartFailingThread.start_calls, 2)
                self.assertEqual(len(StartFailingThread.started), 1)
                StartFailingThread.started.pop(0)()

            self.assertEqual(refreshed, ["token-b"])


class ImagePollingRetryTests(unittest.TestCase):
    class _Clock:
        def __init__(self) -> None:
            self.now = 0.0
            self.perf_now = 0.0

        def time(self) -> float:
            return self.now

        def perf_counter(self) -> float:
            return self.perf_now

        def sleep(self, seconds: float) -> None:
            elapsed = max(0.0, float(seconds))
            self.now += elapsed
            self.perf_now += elapsed

        def advance_perf(self, seconds: float) -> None:
            self.perf_now += max(0.0, float(seconds))

    @staticmethod
    def _poll_config(interval: float = 0.0) -> SimpleNamespace:
        return SimpleNamespace(
            image_poll_initial_wait_secs=0,
            image_poll_interval_secs=interval,
            image_settle_enabled=False,
            image_settle_secs=0,
            image_check_before_hit_enabled=False,
        )

    def test_conversation_commit_statuses_are_retried(self) -> None:
        for status_code in (404, 409, 423):
            with self.subTest(status_code=status_code):
                backend = object.__new__(OpenAIBackendAPI)
                backend._query_backend_tasks = mock.Mock(return_value=[])
                backend._get_conversation = mock.Mock(side_effect=[
                    UpstreamHTTPError(
                        "/backend-api/conversation/conversation-1",
                        status_code,
                        {"detail": {"code": "conversation_not_ready"}},
                    ),
                    {},
                ])
                backend._conversation_poll_snapshot = mock.Mock(return_value=({}, ""))
                backend._extract_image_tool_records = mock.Mock(return_value=[{
                    "file_ids": ["file-1"],
                    "sediment_ids": [],
                }])

                with (
                    mock.patch("services.openai_backend_api.time.sleep"),
                    mock.patch("services.openai_backend_api.random.uniform", return_value=0),
                    mock.patch(
                        "services.openai_backend_api.config",
                        SimpleNamespace(
                            image_poll_initial_wait_secs=0,
                            image_poll_interval_secs=0,
                            image_settle_enabled=False,
                            image_settle_secs=0,
                            image_check_before_hit_enabled=False,
                        ),
                    ),
                ):
                    result = OpenAIBackendAPI._poll_image_results(
                        backend,
                        "conversation-1",
                        timeout_secs=1,
                    )

                self.assertEqual(result, (["file-1"], []))
                self.assertEqual(backend._get_conversation.call_count, 2)

    def test_poll_retryability_comes_from_canonical_failure(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._query_backend_tasks = mock.Mock(return_value=[])
        backend._get_conversation = mock.Mock(side_effect=[
            UpstreamHTTPError(
                "/backend-api/conversation/conversation-1",
                403,
                {"detail": {"type": "forbidden"}},
            ),
            {},
        ])
        backend._conversation_poll_snapshot = mock.Mock(return_value=({}, ""))
        backend._extract_image_tool_records = mock.Mock(return_value=[{
            "file_ids": ["file-1"],
            "sediment_ids": [],
        }])

        with (
            mock.patch("services.openai_backend_api.time.sleep"),
            mock.patch("services.openai_backend_api.random.uniform", return_value=0),
            mock.patch("services.openai_backend_api.config", self._poll_config()),
        ):
            result = OpenAIBackendAPI._poll_image_results(
                backend,
                "conversation-1",
                timeout_secs=1,
            )

        self.assertEqual(result, (["file-1"], []))
        self.assertEqual(backend._get_conversation.call_count, 2)

    def test_unstructured_404_is_not_retried_as_conversation_not_ready(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._query_backend_tasks = mock.Mock(return_value=[])
        upstream_error = UpstreamHTTPError(
            "/backend-api/conversation/conversation-1",
            404,
            {"detail": {"type": "not_found"}},
        )
        backend._get_conversation = mock.Mock(side_effect=upstream_error)
        clock = self._Clock()

        with (
            mock.patch("services.openai_backend_api.time.monotonic", side_effect=clock.time),
            mock.patch("services.openai_backend_api.time.sleep", side_effect=clock.sleep),
            mock.patch("services.openai_backend_api.random.uniform", return_value=0),
            mock.patch("services.openai_backend_api.config", self._poll_config()),
        ):
            with self.assertRaises(UpstreamHTTPError) as raised:
                OpenAIBackendAPI._poll_image_results(
                    backend,
                    "conversation-1",
                    timeout_secs=1,
                )

        self.assertIs(raised.exception, upstream_error)
        self.assertEqual(clock.now, 0)

    def test_account_rate_limit_ends_poll_even_with_task_failure(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._query_backend_tasks = mock.Mock(return_value=[{
            "image_gen_message": {
                "author": {"role": "tool"},
                "content": {"content_type": "system_error", "parts": ["opaque task error"]},
                "metadata": {"async_task_type": "image_gen", "is_error": True},
            },
        }])
        upstream_error = UpstreamHTTPError(
            "/backend-api/conversation/conversation-1",
            429,
            {"detail": {"code": "rate_limit_exceeded"}},
        )
        backend._get_conversation = mock.Mock(side_effect=upstream_error)
        clock = self._Clock()

        with (
            mock.patch("services.openai_backend_api.time.monotonic", side_effect=clock.time),
            mock.patch("services.openai_backend_api.time.sleep", side_effect=clock.sleep),
            mock.patch("services.openai_backend_api.random.uniform", return_value=0),
            mock.patch("services.openai_backend_api.config", self._poll_config()),
        ):
            with self.assertRaises(UpstreamHTTPError) as raised:
                OpenAIBackendAPI._poll_image_results(
                    backend,
                    "conversation-1",
                    timeout_secs=1,
                )

        self.assertIs(raised.exception, upstream_error)
        self.assertEqual(raised.exception.failure.code, "upstream_rate_limited")
        self.assertTrue(raised.exception.failure.account_failure)
        self.assertEqual(clock.now, 0)

    def test_task_auth_failure_without_image_ends_poll_before_conversation_probe(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        auth_error = UpstreamHTTPError(
            "/backend-api/tasks",
            401,
            {"detail": {"code": "token_revoked"}},
        )
        backend._query_backend_tasks = mock.Mock(side_effect=auth_error)
        backend._get_conversation = mock.Mock(return_value={"mapping": {}})
        backend._conversation_poll_snapshot = mock.Mock(return_value=({}, ""))
        backend._extract_image_tool_records = mock.Mock(return_value=[])
        clock = self._Clock()

        with (
            mock.patch("services.openai_backend_api.time.monotonic", side_effect=clock.time),
            mock.patch("services.openai_backend_api.time.sleep", side_effect=clock.sleep),
            mock.patch("services.openai_backend_api.random.uniform", return_value=0),
            mock.patch("services.openai_backend_api.config", self._poll_config(interval=1)),
        ):
            with self.assertRaises(UpstreamHTTPError) as raised:
                OpenAIBackendAPI._poll_image_results(
                    backend,
                    "conversation-1",
                    timeout_secs=1,
                )

        self.assertIs(raised.exception, auth_error)
        self.assertEqual(raised.exception.failure.code, "auth_invalid")
        backend._get_conversation.assert_not_called()
        self.assertEqual(clock.now, 0)

    def test_task_auth_failure_after_image_id_preserves_success_and_schedules_recovery(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._query_backend_tasks = mock.Mock(side_effect=UpstreamHTTPError(
            "/backend-api/tasks",
            401,
            {"detail": {"code": "token_revoked"}},
        ))
        backend._get_conversation = mock.Mock()
        backend._schedule_auth_recovery = mock.Mock()

        with mock.patch("services.openai_backend_api.config", self._poll_config()):
            result = OpenAIBackendAPI._poll_image_results(
                backend,
                "conversation-1",
                timeout_secs=1,
                initial_file_ids=["file-1"],
            )

        self.assertEqual(result, (["file-1"], []))
        backend._schedule_auth_recovery.assert_called_once_with(
            "image_task_probe_after_success"
        )
        backend._get_conversation.assert_not_called()
    @staticmethod
    def _auth_error(context: str) -> UpstreamHTTPError:
        return UpstreamHTTPError(
            context,
            401,
            {"detail": {"code": "token_revoked"}},
        )

    def test_task_detail_probe_propagates_account_auth_failure(self) -> None:
        auth_error = self._auth_error("/backend-api/tasks")
        backend = mock.Mock()
        backend._query_backend_tasks.side_effect = auth_error

        with self.assertRaises(UpstreamHTTPError) as raised:
            conversation._get_detailed_failure_from_tasks(
                backend,
                "conversation-1",
                wait_secs=0,
            )

        self.assertIs(raised.exception, auth_error)

    def test_conversation_id_recovery_propagates_account_auth_failure(self) -> None:
        auth_error = self._auth_error("/backend-api/conversations")
        backend = mock.Mock()
        backend.find_conversation_by_prompt.side_effect = auth_error
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )

        with self.assertRaises(UpstreamHTTPError) as raised:
            conversation._recover_image_conversation_id(
                backend,
                request,
                reason="test",
            )

        self.assertIs(raised.exception, auth_error)

    def test_stream_timeout_task_probe_propagates_account_auth_failure(self) -> None:
        auth_error = self._auth_error("/backend-api/tasks")
        backend = mock.Mock()
        backend._query_backend_tasks.side_effect = auth_error

        with self.assertRaises(UpstreamHTTPError) as raised:
            conversation._image_stream_timeout_task_diagnostics(
                backend,
                "conversation-1",
            )

        self.assertIs(raised.exception, auth_error)

    def test_stream_timeout_with_image_id_skips_diagnostic_auth_probe(self) -> None:
        backend = mock.Mock()
        backend._query_backend_tasks.side_effect = self._auth_error("/backend-api/tasks")
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )
        expected = conversation.ImageOutput(
            kind="result",
            model="gpt-image-2",
            index=1,
            total=1,
            data=[{"url": "https://example.invalid/image.png"}],
        )

        with (
            mock.patch.object(
                conversation,
                "_resolve_image_urls_with_monitor",
                return_value=["https://example.invalid/image.png"],
            ),
            mock.patch.object(
                conversation,
                "_image_result_output_from_urls",
                return_value=expected,
            ),
        ):
            result = conversation._recover_after_image_stream_timeout(
                backend,
                request,
                {"conversation_id": "conversation-1", "file_ids": ["file-1"]},
                TimeoutError("opaque stream timeout"),
                1,
                1,
                0.0,
            )

        self.assertIs(result, expected)
        backend._query_backend_tasks.assert_not_called()

    def test_stream_result_with_image_id_does_not_recover_missing_conversation_id(self) -> None:
        backend = mock.Mock()
        backend.find_conversation_by_prompt.side_effect = self._auth_error(
            "/backend-api/conversations"
        )
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )
        expected = conversation.ImageOutput(
            kind="result",
            model="gpt-image-2",
            index=1,
            total=1,
            data=[{"url": "https://example.invalid/image.png"}],
        )
        event = {
            "type": "conversation.done",
            "conversation_id": "",
            "file_ids": ["file-1"],
            "turn_use_case": "image gen",
        }

        with (
            mock.patch.object(conversation, "_backend_http_timing_data", return_value={}),
            mock.patch.object(conversation, "conversation_events", return_value=iter([event])),
            mock.patch.object(
                conversation,
                "_resolve_image_urls_with_monitor",
                return_value=["https://example.invalid/image.png"],
            ),
            mock.patch.object(
                conversation,
                "_image_result_output_from_urls",
                return_value=expected,
            ),
        ):
            outputs = list(conversation.stream_image_outputs(backend, request))

        self.assertEqual(outputs, [expected])
        backend.find_conversation_by_prompt.assert_not_called()

    def test_recent_conversation_probe_propagates_account_auth_failure(self) -> None:
        auth_error = self._auth_error("/backend-api/conversations")
        backend = object.__new__(OpenAIBackendAPI)
        backend.base_url = "https://example.test"
        backend.session = mock.Mock()
        backend._headers = mock.Mock(return_value={})
        backend.session.get.return_value = mock.Mock()

        with (
            mock.patch("services.openai_backend_api.ensure_ok", side_effect=auth_error),
            self.assertRaises(UpstreamHTTPError) as raised,
        ):
            OpenAIBackendAPI._list_recent_conversations(backend)

        self.assertIs(raised.exception, auth_error)

    def test_conversation_image_wins_over_stale_task_failure(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._query_backend_tasks = mock.Mock(return_value=[{
            "status": "success",
            "image_gen_message": {
                "author": {"role": "tool"},
                "content": {"content_type": "system_error", "parts": ["opaque stale error"]},
                "metadata": {"async_task_type": "image_gen", "is_error": True},
            },
        }])
        backend._get_conversation = mock.Mock(return_value={"mapping": {}})
        backend._conversation_poll_snapshot = mock.Mock(return_value=({}, ""))
        backend._extract_image_tool_records = mock.Mock(return_value=[{
            "file_ids": ["file-1"],
            "sediment_ids": [],
        }])

        with mock.patch("services.openai_backend_api.config", self._poll_config()):
            result = OpenAIBackendAPI._poll_image_results(
                backend,
                "conversation-1",
                timeout_secs=1,
            )

        self.assertEqual(result, (["file-1"], []))

    def test_task_failure_without_image_still_fails_immediately(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._query_backend_tasks = mock.Mock(return_value=[{
            "image_gen_message": {
                "author": {"role": "tool"},
                "content": {"content_type": "system_error", "parts": ["opaque task error"]},
                "metadata": {"async_task_type": "image_gen", "is_error": True},
            },
        }])
        backend._get_conversation = mock.Mock(return_value={"mapping": {}})
        backend._conversation_poll_snapshot = mock.Mock(return_value=({}, ""))
        backend._extract_image_tool_records = mock.Mock(return_value=[])

        with mock.patch("services.openai_backend_api.config", self._poll_config()):
            with self.assertRaises(ImageFailureError) as raised:
                OpenAIBackendAPI._poll_image_results(
                    backend,
                    "conversation-1",
                    timeout_secs=1,
                )

        self.assertEqual(raised.exception.failure.code, "image_tool_error")

    def test_conversation_policy_failure_overrides_generic_task_failure(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._query_backend_tasks = mock.Mock(return_value=[{
            "image_gen_message": {
                "author": {"role": "tool"},
                "content": {"content_type": "system_error", "parts": ["opaque task error"]},
                "metadata": {"async_task_type": "image_gen", "is_error": True},
            },
        }])
        backend._get_conversation = mock.Mock(return_value={
            "mapping": {
                "policy-node": {
                    "message": {
                        "author": {"role": "tool"},
                        "content": {"content_type": "system_error", "parts": ["blocked"]},
                        "metadata": {
                            "async_task_type": "image_gen",
                            "is_error": True,
                            "error": {"code": "content_policy_violation"},
                        },
                    },
                },
            },
        })
        backend._conversation_poll_snapshot = mock.Mock(return_value=({}, "blocked"))
        backend._extract_image_tool_records = mock.Mock(return_value=[])

        with mock.patch("services.openai_backend_api.config", self._poll_config()):
            with self.assertRaises(ImageFailureError) as raised:
                OpenAIBackendAPI._poll_image_results(
                    backend,
                    "conversation-1",
                    timeout_secs=1,
                )

        self.assertEqual(raised.exception.failure.code, "content_policy_violation")
        self.assertFalse(raised.exception.failure.account_failure)

    def test_terminal_retryable_poll_error_is_not_rewritten_as_timeout(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._query_backend_tasks = mock.Mock(return_value=[])
        upstream_error = UpstreamHTTPError(
            "/backend-api/conversation/conversation-1",
            503,
            {"detail": {"type": "unavailable"}},
        )
        backend._get_conversation = mock.Mock(side_effect=upstream_error)
        clock = self._Clock()

        with (
            mock.patch("services.openai_backend_api.time.monotonic", side_effect=clock.time),
            mock.patch("services.openai_backend_api.time.sleep", side_effect=clock.sleep),
            mock.patch("services.openai_backend_api.random.uniform", return_value=0),
            mock.patch("services.openai_backend_api.config", self._poll_config()),
        ):
            with self.assertRaises(UpstreamHTTPError) as raised:
                OpenAIBackendAPI._poll_image_results(
                    backend,
                    "conversation-1",
                    timeout_secs=1,
                )

        self.assertIs(raised.exception, upstream_error)

    def test_successful_poll_after_retryable_error_still_uses_timeout(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._query_backend_tasks = mock.Mock(return_value=[])
        backend._get_conversation = mock.Mock(side_effect=[
            UpstreamHTTPError(
                "/backend-api/conversation/conversation-1",
                503,
                {"detail": {"type": "unavailable"}},
                retry_after=0,
            ),
            {},
        ])
        backend._conversation_poll_snapshot = mock.Mock(return_value=({}, ""))
        backend._extract_image_tool_records = mock.Mock(return_value=[])
        clock = self._Clock()

        with (
            mock.patch("services.openai_backend_api.time.monotonic", side_effect=clock.time),
            mock.patch("services.openai_backend_api.time.sleep", side_effect=clock.sleep),
            mock.patch("services.openai_backend_api.random.uniform", return_value=0),
            mock.patch("services.openai_backend_api.config", self._poll_config(interval=1)),
        ):
            with self.assertRaises(conversation.ImagePollTimeoutError):
                OpenAIBackendAPI._poll_image_results(
                    backend,
                    "conversation-1",
                    timeout_secs=1,
                )

    def test_poll_wait_time_is_recorded_separately(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._query_backend_tasks = mock.Mock(return_value=[])
        backend._get_conversation = mock.Mock(return_value={})
        backend._conversation_poll_snapshot = mock.Mock(return_value=({}, ""))
        backend._extract_image_tool_records = mock.Mock(return_value=[])
        clock = self._Clock()
        poll_config = self._poll_config(interval=0.75)
        poll_config.image_poll_initial_wait_secs = 0.25

        with (
            mock.patch("services.openai_backend_api.time.monotonic", side_effect=clock.time),
            mock.patch("services.openai_backend_api.time.sleep", side_effect=clock.sleep),
            mock.patch("services.openai_backend_api.random.uniform", return_value=0),
            mock.patch("services.openai_backend_api.config", poll_config),
        ):
            with self.assertRaises(conversation.ImagePollTimeoutError):
                OpenAIBackendAPI._poll_image_results(
                    backend,
                    "conversation-1",
                    timeout_secs=1,
                )

        timing = backend.pop_image_result_timing()
        self.assertEqual(timing["poll_wait_ms"], 1000)

    def test_poll_request_time_is_accumulated_separately(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        clock = self._Clock()

        def query_tasks(**_kwargs: object) -> list[dict[str, object]]:
            clock.advance_perf(0.04)
            return []

        def get_conversation(_conversation_id: str, **_kwargs: object) -> dict[str, object]:
            clock.advance_perf(0.06)
            return {}

        backend._query_backend_tasks = mock.Mock(side_effect=query_tasks)
        backend._get_conversation = mock.Mock(side_effect=get_conversation)
        backend._conversation_poll_snapshot = mock.Mock(return_value=({}, ""))
        backend._extract_image_tool_records = mock.Mock(return_value=[{
            "file_ids": ["file-1"],
            "sediment_ids": [],
        }])

        with (
            mock.patch("services.openai_backend_api.time.perf_counter", side_effect=clock.perf_counter),
            mock.patch("services.openai_backend_api.config", self._poll_config()),
        ):
            result = OpenAIBackendAPI._poll_image_results(
                backend,
                "conversation-1",
                timeout_secs=1,
            )

        self.assertEqual(result, (["file-1"], []))
        timing = backend.pop_image_result_timing()
        self.assertEqual(timing["poll_request_ms"], 100)

    def test_poll_backoff_is_not_double_counted_as_request_time(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        clock = self._Clock()

        def query_tasks(**_kwargs: object) -> list[dict[str, object]]:
            clock.advance_perf(0.01)
            return []

        def get_conversation(_conversation_id: str, **_kwargs: object) -> dict[str, object]:
            clock.advance_perf(0.05)
            raise UpstreamHTTPError(
                "/backend-api/conversation/conversation-1",
                503,
                {"detail": {"type": "unavailable"}},
            )

        backend._query_backend_tasks = mock.Mock(side_effect=query_tasks)
        backend._get_conversation = mock.Mock(side_effect=get_conversation)

        with (
            mock.patch("services.openai_backend_api.time.monotonic", side_effect=clock.time),
            mock.patch("services.openai_backend_api.time.perf_counter", side_effect=clock.perf_counter),
            mock.patch("services.openai_backend_api.time.sleep", side_effect=clock.sleep),
            mock.patch("services.openai_backend_api.random.uniform", return_value=0),
            mock.patch("services.openai_backend_api.config", self._poll_config()),
        ):
            with self.assertRaises(UpstreamHTTPError):
                OpenAIBackendAPI._poll_image_results(
                    backend,
                    "conversation-1",
                    timeout_secs=1,
                )

        timing = backend.pop_image_result_timing()
        self.assertEqual(timing["poll_wait_ms"], 1000)
        self.assertEqual(timing["poll_request_ms"], 60)


class ImageDownloadUrlResolutionTests(unittest.TestCase):
    def test_final_url_resolution_has_its_own_timing(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._resolve_image_urls = mock.Mock(return_value=["https://example.com/image.png"])

        with mock.patch(
            "services.openai_backend_api.time.perf_counter",
            side_effect=[1.0, 1.125],
        ):
            result = OpenAIBackendAPI.resolve_conversation_image_urls(
                backend,
                "conversation-1",
                ["file-1"],
                [],
                poll=False,
            )

        self.assertEqual(result, ["https://example.com/image.png"])
        self.assertEqual(backend.pop_image_result_timing(), {"resolve_ms": 125})

    def test_retryable_download_url_error_is_raised_when_all_candidates_fail(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        upstream_error = UpstreamHTTPError(
            "/backend-api/files/file-1/download",
            429,
            {"detail": {"code": "rate_limit_exceeded"}},
        )
        backend._get_file_download_url = mock.Mock(side_effect=upstream_error)
        backend._get_attachment_download_url = mock.Mock()

        with self.assertRaises(UpstreamHTTPError) as raised:
            backend._resolve_image_urls("conversation-1", ["file-1"], [])

        self.assertIs(raised.exception, upstream_error)

    def test_successful_candidate_is_kept_when_another_candidate_fails(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._get_file_download_url = mock.Mock(side_effect=[
            UpstreamHTTPError(
                "/backend-api/files/file-1/download",
                503,
                {"detail": {"code": "service_unavailable"}},
            ),
            "https://example.test/image.png",
        ])
        backend._get_attachment_download_url = mock.Mock()

        urls = backend._resolve_image_urls(
            "conversation-1",
            ["file-1", "file-2"],
            [],
        )

        self.assertEqual(urls, ["https://example.test/image.png"])

    def test_file_not_ready_is_retried_then_raises_delivery_failure(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._get_file_download_url = mock.Mock(side_effect=UpstreamHTTPError(
            "/backend-api/files/file-1/download",
            404,
            {"detail": {"code": "file_not_ready"}},
        ))
        backend._get_attachment_download_url = mock.Mock()

        with self.assertRaises(ImageDownloadError) as raised:
            backend._resolve_image_urls("conversation-1", ["file-1"], [])

        self.assertEqual(backend._get_file_download_url.call_count, 2)
        self.assertEqual(raised.exception.failure.code, "image_download_failed")
        self.assertEqual(raised.exception.failure.scope, "delivery")

    def test_empty_download_url_is_retried_then_raises_delivery_failure(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._get_file_download_url = mock.Mock(return_value="")
        backend._get_attachment_download_url = mock.Mock()

        with self.assertRaises(ImageDownloadError) as raised:
            backend._resolve_image_urls("conversation-1", ["file-1"], [])

        self.assertEqual(backend._get_file_download_url.call_count, 2)
        self.assertEqual(raised.exception.failure.code, "image_download_failed")
        self.assertEqual(raised.exception.failure.scope, "delivery")


    def test_auth_recovery_schedule_failure_does_not_discard_resolved_url(self) -> None:
        backend = object.__new__(OpenAIBackendAPI)
        backend._credential_access_token = "token-a"
        backend._credential_refresh_token = "refresh-a"

        def resolve(file_id: str) -> str:
            if file_id == "file-auth":
                raise UpstreamHTTPError(
                    "/backend-api/files/file-auth/download",
                    401,
                    {"detail": {"code": "token_revoked"}},
                )
            return "https://assets.example/image.png"

        backend._get_file_download_url = mock.Mock(side_effect=resolve)
        backend._get_attachment_download_url = mock.Mock()
        with mock.patch(
            "services.openai_backend_api.account_service.schedule_auth_verification",
            side_effect=RuntimeError("scheduler unavailable"),
        ):
            urls = backend._resolve_image_urls(
                "conversation-1",
                ["file-auth", "file-ok"],
                [],
            )

        self.assertEqual(urls, ["https://assets.example/image.png"])


class ImageAssetAuthenticationBoundaryTests(unittest.TestCase):
    @staticmethod
    def _response(status_code: int, body: dict[str, object]) -> mock.Mock:
        response = mock.Mock()
        response.status_code = status_code
        response.headers = {}
        response.text = json.dumps(body)
        response.content = b"image-bytes"
        response.json.return_value = body
        return response

    @staticmethod
    def _backend(session: mock.Mock) -> OpenAIBackendAPI:
        backend = object.__new__(OpenAIBackendAPI)
        backend.base_url = "https://chatgpt.com"
        backend.access_token = "account-secret"
        backend.user_agent = "test-agent"
        backend.session = session
        return backend

    @staticmethod
    def _constructed_backend(session: mock.Mock) -> OpenAIBackendAPI:
        proxy_profile = SimpleNamespace(image_egress_reserved=False)
        with (
            mock.patch(
                "services.openai_backend_api.account_service.get_account",
                return_value={},
            ),
            mock.patch(
                "services.openai_backend_api.proxy_settings.build_session_kwargs_from_profile",
                return_value={},
            ),
            mock.patch(
                "services.openai_backend_api.requests.Session",
                return_value=session,
            ),
        ):
            return OpenAIBackendAPI(
                access_token="account-secret",
                proxy_profile=proxy_profile,
            )

    def test_account_authenticated_download_url_401_invalidates_account(self) -> None:
        session = mock.Mock()
        session.headers = {"User-Agent": "test-agent"}
        session.get.return_value = self._response(
            401,
            {"detail": {"code": "token_revoked"}},
        )
        backend = self._backend(session)

        with self.assertRaises(UpstreamHTTPError) as raised:
            backend._get_file_download_url("file-1")

        failure = classify_image_exception(raised.exception)
        self.assertEqual(failure.code, "auth_invalid")
        self.assertTrue(failure.account_failure)
        self.assertEqual(
            session.get.call_args.kwargs["headers"]["Authorization"],
            "Bearer account-secret",
        )

    def test_signed_download_401_is_delivery_failure_not_account_failure(self) -> None:
        session = mock.Mock()
        session.headers = {"User-Agent": "test-agent"}
        session.get.return_value = self._response(
            401,
            {"detail": {"code": "token_revoked"}},
        )
        backend = self._backend(session)

        with self.assertRaises(ImageFailureError) as raised:
            backend.download_image_bytes(["https://assets.example/image.png"])

        failure = classify_image_exception(raised.exception)
        self.assertEqual(failure.code, "image_download_failed")
        self.assertEqual(failure.scope, "delivery")
        self.assertFalse(failure.account_failure)

    def test_signed_asset_requests_do_not_send_account_bearer(self) -> None:
        session = mock.Mock()
        session.headers = {}
        session.get.return_value = self._response(200, {})
        backend = self._constructed_backend(session)

        self.assertNotIn("Authorization", session.headers)

        images = backend.download_image_bytes(["https://assets.example/image.png"])

        self.assertEqual(images, [b"image-bytes"])
        sent_headers = session.get.call_args.kwargs["headers"]
        self.assertNotIn("Authorization", sent_headers)
        self.assertNotIn("Bearer account-secret", sent_headers.values())

    def test_signed_upload_401_is_not_an_account_failure(self) -> None:
        session = mock.Mock()
        session.headers = {}
        session.post.return_value = self._response(
            200,
            {
                "file_id": "file-1",
                "upload_url": "https://assets.example/upload",
            },
        )
        session.put.return_value = self._response(
            401,
            {"detail": {"code": "token_revoked"}},
        )
        backend = self._constructed_backend(session)

        with (
            mock.patch.object(backend, "_decode_image_base64", return_value=b"image"),
            mock.patch(
                "services.openai_backend_api.Image.open",
                return_value=SimpleNamespace(size=(1, 1), format="PNG"),
            ),
            self.assertRaises(UpstreamHTTPError) as raised,
        ):
            backend._upload_image("opaque-image")

        failure = classify_image_exception(raised.exception)
        self.assertEqual(failure.scope, "delivery")
        self.assertFalse(failure.account_failure)
        self.assertNotEqual(failure.code, "auth_invalid")
        sent_headers = session.put.call_args.kwargs["headers"]
        self.assertNotIn("Authorization", sent_headers)


class ImageProtocolRequestTests(unittest.TestCase):
    @staticmethod
    def _result_output() -> conversation.ImageOutput:
        return conversation.ImageOutput(
            kind="result",
            model="gpt-image-2",
            index=1,
            total=1,
            data=[{"b64_json": "aW1hZ2U="}],
        )

    def test_chat_image_requests_treat_message_outputs_as_errors(self) -> None:
        captured: list[conversation.ConversationRequest] = []

        def stream(request: conversation.ConversationRequest):
            captured.append(request)
            return iter([self._result_output()])

        with (
            mock.patch.object(
                openai_v1_chat_complete,
                "chat_image_args",
                return_value=("gpt-image-2", "draw a lighthouse", 1, [], None),
            ),
            mock.patch.object(
                openai_v1_chat_complete,
                "stream_image_outputs_with_pool",
                side_effect=stream,
            ),
        ):
            openai_v1_chat_complete.image_chat_response({})
            list(openai_v1_chat_complete.image_chat_events({}))

        self.assertEqual(len(captured), 2)
        self.assertTrue(all(request.message_as_error for request in captured))

    def test_responses_image_requests_treat_message_outputs_as_errors(self) -> None:
        captured: list[conversation.ConversationRequest] = []

        def stream(request: conversation.ConversationRequest):
            captured.append(request)
            return iter([self._result_output()])

        body = {
            "model": "gpt-image-2",
            "input": "draw a lighthouse",
            "tools": [{"type": "image_generation"}],
        }
        with mock.patch.object(
            openai_v1_response,
            "stream_image_outputs_with_pool",
            side_effect=stream,
        ):
            list(openai_v1_response.response_events(body))

        self.assertEqual(len(captured), 1)
        self.assertTrue(captured[0].message_as_error)

    def test_empty_single_image_output_is_not_reported_as_success(self) -> None:
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
            message_as_error=True,
        )

        with mock.patch.object(conversation, "_generate_single_image", return_value=[]):
            with self.assertRaises(conversation.ImageGenerationError) as raised:
                list(conversation.stream_image_outputs_with_pool(request))

        self.assertEqual(raised.exception.failure.code, "no_image_generated")

    def test_stream_timeout_recovery_preserves_retryable_result_errors(self) -> None:
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )
        backend = mock.Mock()
        backend._get_conversation.return_value = {}
        backend._conversation_poll_snapshot.return_value = ({}, "")
        backend._extract_image_tool_records.return_value = []
        errors = (
            UpstreamHTTPError(
                "/backend-api/files/file-1/download",
                401,
                {"detail": {"code": "invalid_access_token"}},
            ),
            UpstreamHTTPError(
                "/backend-api/files/file-1/download",
                429,
                {"detail": {"code": "rate_limit_exceeded"}},
            ),
            UpstreamHTTPError(
                "/backend-api/files/file-1/download",
                503,
                {"detail": {"code": "service_unavailable"}},
            ),
            ConnectionError("opaque network failure"),
        )

        for expected in errors:
            with self.subTest(error=type(expected).__name__, status=getattr(expected, "status_code", None)):
                with (
                    mock.patch.object(
                        conversation,
                        "_image_stream_timeout_task_diagnostics",
                        return_value=(None, "", [], ""),
                    ),
                    mock.patch.object(
                        conversation,
                        "_resolve_image_urls_with_monitor",
                        side_effect=expected,
                    ),
                ):
                    with self.assertRaises(type(expected)) as raised:
                        conversation._recover_after_image_stream_timeout(
                            backend,
                            request,
                            {
                                "conversation_id": "conversation-1",
                                "file_ids": ["file-1"],
                            },
                            TimeoutError("opaque stream timeout"),
                            1,
                            1,
                            0.0,
                        )

                self.assertIs(raised.exception, expected)

class ImagePublicErrorTests(unittest.IsolatedAsyncioTestCase):
    TOOL_ERROR_MESSAGE = "The image generation tool encountered an error. Please try again."
    TIMEOUT_MESSAGE = "Image generation timed out. Please try again."
    QUOTA_MESSAGE = "No image generation quota is currently available."

    @staticmethod
    def _failure() -> ImageGenerationError:
        return ImageGenerationError(
            "private upstream diagnostic",
            failure=image_failure(
                "upstream_rate_limited",
                raw_detail={"detail": {"code": "rate_limit_exceeded"}},
            ),
            raw_error="private upstream diagnostic",
            upstream_error="private upstream response body",
        )

    async def test_non_stream_image_protocols_share_canonical_public_error(self) -> None:
        endpoints = (
            "/v1/images/generations",
            "/v1/images/edits",
            "/v1/chat/completions",
            "/v1/responses",
        )

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                def handler():
                    raise self._failure()

                call = LoggedCall(
                    {"id": "key-1", "name": "Key", "role": "admin"},
                    endpoint,
                    "gpt-image-2",
                    "image request",
                )
                with mock.patch.object(call, "log"):
                    response = await call.run(handler)
                payload = json.loads(response.body)["error"]

                self.assertEqual(response.status_code, 429)
                self.assertEqual(payload["code"], "upstream_rate_limited")
                self.assertEqual(payload["message"], self.TOOL_ERROR_MESSAGE)
                self.assertNotIn("private upstream", response.body.decode("utf-8"))

    def test_image_protocol_sse_errors_share_canonical_public_error(self) -> None:
        def failing_items():
            raise self._failure()
            yield {}

        for serializer in (image_sse_stream, sse_json_stream):
            with self.subTest(serializer=serializer.__name__):
                payload = "".join(serializer(failing_items()))

                self.assertIn('"code": "upstream_rate_limited"', payload)
                self.assertIn(self.TOOL_ERROR_MESSAGE, payload)
                self.assertNotIn("private upstream", payload)

    def test_safe_terminal_upstream_text_is_returned_verbatim(self) -> None:
        upstream_text = (
            "You've hit the Free plan limit for image generations requests. "
            "You can create more images when the limit resets in 2 hours."
        )
        error = ImageGenerationError(
            upstream_text,
            failure=image_failure("upstream_text_reply", raw_detail=upstream_text),
            raw_error=upstream_text,
            upstream_error=upstream_text,
            raw_upstream_message=upstream_text,
        )

        self.assertEqual(error.to_openai_error()["error"]["message"], upstream_text)

    def test_safe_quota_text_is_returned_verbatim(self) -> None:
        upstream_text = (
            "You've hit the Free plan limit for image generations requests. "
            "You can create more images when the limit resets in 2 hours. "
            "See https://chatgpt.com for details; status=limited."
        )
        error = ImageGenerationError(
            upstream_text,
            failure=image_failure("image_quota_exhausted", raw_detail=upstream_text),
            raw_upstream_message=upstream_text,
        )

        self.assertEqual(error.to_openai_error()["error"]["message"], upstream_text)

    def test_safe_tool_error_text_is_returned_verbatim(self) -> None:
        upstream_text = (
            "You've hit the Free plan limit for image generations requests. "
            "You can create more images when the limit resets in 2 hours."
        )
        error = ImageGenerationError(
            "opaque image tool failure",
            failure=image_failure("image_tool_error"),
            raw_upstream_message=upstream_text,
        )

        self.assertEqual(error.to_openai_error()["error"]["message"], upstream_text)

    def test_account_pool_quota_diagnostic_uses_quota_fallback(self) -> None:
        error = ImageGenerationError(
            "image_account_selection:quota_exhausted; all matched accounts are unavailable",
            failure=image_failure(
                "insufficient_quota",
                raw_detail=(
                    "image_account_selection:quota_exhausted; "
                    "all matched accounts are unavailable"
                ),
            ),
        )

        self.assertEqual(error.to_openai_error()["error"]["message"], self.QUOTA_MESSAGE)

    def test_safe_no_image_text_is_returned_verbatim(self) -> None:
        upstream_text = "Image generation is unavailable for this request."
        error = ImageGenerationError(
            upstream_text,
            failure=image_failure("no_image_generated", raw_detail=upstream_text),
        )

        self.assertEqual(error.to_openai_error()["error"]["message"], upstream_text)

    def test_explicit_upstream_text_is_preserved_for_generic_failure(self) -> None:
        upstream_text = "The upstream service is temporarily unavailable."
        error = ImageGenerationError(
            "opaque internal diagnostic",
            failure=image_failure("upstream_error"),
            raw_upstream_message=upstream_text,
        )

        self.assertEqual(error.to_openai_error()["error"]["message"], upstream_text)

    def test_direct_terminal_text_is_preserved_without_duplicate_raw_fields(self) -> None:
        upstream_text = "This request was rejected by the upstream safety system."
        error = ImageGenerationError(
            upstream_text,
            failure=image_failure("content_policy_violation"),
        )

        self.assertEqual(error.to_openai_error()["error"]["message"], upstream_text)

    def test_only_system_generated_image_messages_are_rewritten(self) -> None:
        cases = (
            ("image_poll_timeout", "opaque poll diagnostic", self.TIMEOUT_MESSAGE),
            ("image_stream_interrupted", "opaque stream diagnostic", self.TOOL_ERROR_MESSAGE),
            ("no_image_generated", '{"size":"1024x1024","n":1}', self.TOOL_ERROR_MESSAGE),
            ("no_image_generated", '```json\n{"size":"1024x1024"}\n```', self.TOOL_ERROR_MESSAGE),
            ("no_image_generated", '```json {"size":"1024x1024"}```', self.TOOL_ERROR_MESSAGE),
            ("image_quota_exhausted", "", self.QUOTA_MESSAGE),
            ("image_quota_exhausted", "insufficient_quota", self.QUOTA_MESSAGE),
        )

        for code, raw_message, expected in cases:
            with self.subTest(code=code):
                error = ImageGenerationError(
                    raw_message,
                    failure=image_failure(code, raw_detail=raw_message),
                    raw_error=raw_message,
                    raw_upstream_message=raw_message,
                )
                self.assertEqual(error.to_openai_error()["error"]["message"], expected)

    def test_responses_image_tool_masks_unexpected_handler_error(self) -> None:
        app = FastAPI()
        app.include_router(ai_module.create_router())

        with (
            mock.patch.object(
                ai_module,
                "require_identity",
                return_value={"id": "key-1", "name": "Key", "role": "admin"},
            ),
            mock.patch.object(
                ai_module.openai_v1_response,
                "handle",
                side_effect=RuntimeError("private upstream diagnostic"),
            ),
            mock.patch("services.log_service.log_service.add"),
        ):
            response = TestClient(app).post(
                "/v1/responses",
                json={
                    "model": "gpt-5.5",
                    "input": "draw a lighthouse",
                    "tools": [{"type": "image_generation"}],
                },
            )

        payload = response.json()["error"]
        self.assertEqual(response.status_code, 500)
        self.assertEqual(payload["code"], "internal_error")
        self.assertEqual(payload["message"], self.TOOL_ERROR_MESSAGE)
        self.assertNotIn("private upstream", response.text)

    async def test_responses_image_stream_masks_error_after_first_event(self) -> None:
        def handler():
            def items():
                yield {"type": "response.created"}
                raise RuntimeError("private upstream diagnostic")

            return items()

        call = LoggedCall(
            {"id": "key-1", "name": "Key", "role": "admin"},
            "/v1/responses",
            "gpt-5.5",
            "image request",
            image_request=True,
        )
        with mock.patch.object(call, "log"):
            response = await call.run(handler)
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)

        payload = "".join(chunks)
        self.assertIn('"code": "internal_error"', payload)
        self.assertIn(self.TOOL_ERROR_MESSAGE, payload)
        self.assertNotIn("private upstream", payload)

    async def test_responses_image_stream_masks_serializer_error(self) -> None:
        def handler():
            def items():
                yield {"type": "response.created"}
                yield {"type": "response.output_item.added", "item": object()}

            return items()

        call = LoggedCall(
            {"id": "key-1", "name": "Key", "role": "admin"},
            "/v1/responses",
            "gpt-5.5",
            "image request",
            image_request=True,
        )
        with mock.patch.object(call, "log"):
            response = await call.run(handler)
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)

        payload = "".join(chunks)
        self.assertIn('"code": "internal_error"', payload)
        self.assertIn(self.TOOL_ERROR_MESSAGE, payload)
        self.assertNotIn("not JSON serializable", payload)


class CrossAccountRetryTests(unittest.TestCase):
    def test_auth_failure_immediately_uses_a_different_account(self) -> None:
        selected: list[set[str]] = []

        def select_account(**kwargs: object) -> str:
            excluded = set(kwargs.get("excluded_tokens") or set())
            selected.append(excluded)
            return "token-b" if "token-a" in excluded else "token-a"

        class FakeBackend:
            def __init__(self, access_token: str, **_kwargs: object) -> None:
                self.access_token = access_token
                self.proxy_profile = SimpleNamespace(image_concurrency_limit=0)
                self.cancel_checker = None
                self.progress_callback = None

            def close(self) -> None:
                return None

        def stream(backend: FakeBackend, request: object, index: int, total: int):
            if backend.access_token in {"token-a", "token-a2"}:
                raise InvalidAccessTokenError("opaque auth failure")
            yield conversation.ImageOutput(
                kind="result",
                model="gpt-image-2",
                index=index,
                total=total,
                data=[{"b64_json": "aW1hZ2U="}],
            )

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
            message_as_error=True,
        )

        with (
            mock.patch.object(
                conversation.account_service,
                "get_available_access_token",
                side_effect=select_account,
            ),
            mock.patch.object(conversation.account_service, "get_account", return_value={}),
            mock.patch.object(conversation.account_service, "mark_image_result"),
            mock.patch.object(
                conversation.account_service,
                "refresh_access_token",
                return_value="token-a2",
            ) as refresh_access_token,
            mock.patch.object(conversation.account_service, "handle_invalid_token") as handle_invalid,
            mock.patch.object(conversation, "OpenAIBackendAPI", FakeBackend),
            mock.patch.object(conversation, "is_codex_image_model", return_value=False),
            mock.patch.object(conversation, "stream_image_outputs", side_effect=stream),
            mock.patch.object(conversation.proxy_settings, "acquire_image_egress", return_value=0),
            mock.patch.object(conversation, "_cleanup_image_conversations_after_success"),
        ):
            outputs = conversation._generate_single_image(request, 1, 1)

        self.assertEqual([output.kind for output in outputs], ["result"])
        self.assertEqual(selected, [set(), {"token-a"}])
        refresh_access_token.assert_not_called()
        handle_invalid.assert_not_called()

    def test_account_failure_text_is_not_emitted_when_retry_succeeds(self) -> None:
        selected: list[set[str]] = []

        def select_account(**kwargs: object) -> str:
            excluded = set(kwargs.get("excluded_tokens") or set())
            selected.append(excluded)
            return "token-b" if "token-a" in excluded else "token-a"

        class FakeBackend:
            def __init__(self, access_token: str, **_kwargs: object) -> None:
                self.access_token = access_token
                self.proxy_profile = SimpleNamespace(image_concurrency_limit=0)
                self.cancel_checker = None
                self.progress_callback = None

            def close(self) -> None:
                return None

        def stream(backend: FakeBackend, request: object, index: int, total: int):
            if backend.access_token == "token-a":
                quota_text = (
                    "You've hit the Free plan limit for image generations requests. "
                    "You can create more images when the limit resets in 2 hours."
                )
                raise conversation.ImageGenerationError(
                    quota_text,
                    failure=image_failure("image_quota_exhausted", raw_detail=quota_text),
                    raw_upstream_message=quota_text,
                )
            yield conversation.ImageOutput(
                kind="result",
                model="gpt-image-2",
                index=index,
                total=total,
                data=[{"b64_json": "aW1hZ2U="}],
            )

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
            message_as_error=True,
        )

        with (
            mock.patch.object(
                conversation.account_service,
                "get_available_access_token",
                side_effect=select_account,
            ),
            mock.patch.object(
                conversation.account_service,
                "get_account",
                side_effect=lambda token: {"email": f"{token}@example.test"},
            ),
            mock.patch.object(conversation.account_service, "mark_image_result") as mark_result,
            mock.patch.object(conversation, "OpenAIBackendAPI", FakeBackend),
            mock.patch.object(conversation, "is_codex_image_model", return_value=False),
            mock.patch.object(conversation, "stream_image_outputs", side_effect=stream),
            mock.patch.object(conversation.proxy_settings, "acquire_image_egress", return_value=0),
            mock.patch.object(conversation, "_cleanup_image_conversations_after_success"),
        ):
            outputs = conversation._generate_single_image(request, 1, 1)

        self.assertEqual([output.kind for output in outputs], ["result"])
        self.assertEqual(selected, [set(), {"token-a"}])
        self.assertEqual(mark_result.call_count, 2)
        first_failure = mark_result.call_args_list[0].kwargs["failure"]
        self.assertEqual(first_failure.code, "image_quota_exhausted")
        self.assertEqual(
            mark_result.call_args_list[1].kwargs["capabilities"],
            {"auth", "image_generation"},
        )

    def test_failure_switches_until_configured_attempt_limit(self) -> None:
        selected: list[set[str]] = []

        def select_account(**kwargs: object) -> str:
            excluded = set(kwargs.get("excluded_tokens") or set())
            selected.append(excluded)
            if "token-b" in excluded:
                return "token-c"
            return "token-b" if "token-a" in excluded else "token-a"

        class FakeBackend:
            def __init__(self, access_token: str, **_kwargs: object) -> None:
                self.access_token = access_token
                self.proxy_profile = SimpleNamespace(image_concurrency_limit=0)
                self.cancel_checker = None
                self.progress_callback = None

            def close(self) -> None:
                return None

        def stream(*_args: object, **_kwargs: object):
            raise conversation.ImagePollTimeoutError("opaque timeout")
            yield

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
            message_as_error=True,
        )

        with (
            mock.patch.object(
                type(conversation.config),
                "image_account_retry_enabled",
                new_callable=mock.PropertyMock,
                return_value=True,
            ),
            mock.patch.object(
                type(conversation.config),
                "image_max_account_attempts",
                new_callable=mock.PropertyMock,
                return_value=3,
            ),
            mock.patch.object(
                conversation.account_service,
                "get_available_access_token",
                side_effect=select_account,
            ),
            mock.patch.object(conversation.account_service, "get_account", return_value={}),
            mock.patch.object(conversation.account_service, "mark_image_result"),
            mock.patch.object(conversation, "OpenAIBackendAPI", FakeBackend),
            mock.patch.object(conversation, "is_codex_image_model", return_value=False),
            mock.patch.object(conversation, "stream_image_outputs", side_effect=stream),
            mock.patch.object(conversation.proxy_settings, "acquire_image_egress", return_value=0),
        ):
            with self.assertRaises(conversation.ImageGenerationError) as raised:
                conversation._generate_single_image(request, 1, 1)

        self.assertEqual(selected, [set(), {"token-a"}, {"token-a", "token-b"}])
        self.assertEqual(len(raised.exception.image_attempts), 3)
        self.assertEqual(
            [attempt["switched_account"] for attempt in raised.exception.image_attempts],
            [True, True, False],
        )


class ConversationStateFailureTests(unittest.TestCase):
    def test_outer_structured_code_overrides_nested_terminal_text(self) -> None:
        payloads = iter([
            json.dumps({
                "error_code": "insufficient_quota",
                "message": {
                    "id": "message-1",
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["opaque final reply"]},
                    "metadata": {"async_task_type": "image_gen"},
                    "status": "finished_successfully",
                    "end_turn": True,
                },
            }),
            "[DONE]",
        ])

        events = list(conversation.iter_conversation_payloads(payloads))

        self.assertEqual(events[-1]["_image_failure"].code, "image_quota_exhausted")

    def test_blocked_metadata_patch_is_carried_to_done(self) -> None:
        payloads = iter([
            json.dumps({
                "message": {
                    "id": "message-1",
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": [""]},
                    "metadata": {"async_task_type": "image_gen"},
                    "status": "in_progress",
                },
            }),
            json.dumps({
                "p": "/message/metadata/blocked",
                "o": "replace",
                "v": True,
            }),
            "[DONE]",
        ])

        events = list(conversation.iter_conversation_payloads(payloads))

        self.assertTrue(events[-1]["blocked"])
        self.assertEqual(events[-1]["_image_failure"].code, "content_policy_violation")

    def test_terminal_tool_arguments_survive_empty_followup_message(self) -> None:
        payloads = iter([
            json.dumps({
                "conversation_id": "conversation-id",
                "message": {
                    "id": "message-1",
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "code",
                        "text": '{"prompt":"draw a lighthouse","size":"1024x1024","n":1}',
                    },
                    "metadata": {"async_task_type": "image_gen"},
                    "status": "finished_successfully",
                    "end_turn": True,
                },
            }),
            json.dumps({
                "message": {
                    "id": "message-2",
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": [""]},
                    "metadata": {"async_task_type": "image_gen"},
                    "status": "finished_successfully",
                    "end_turn": True,
                },
            }),
            "[DONE]",
        ])

        events = list(conversation.iter_conversation_payloads(payloads))

        self.assertIsNone(events[-1]["_image_failure"])
        self.assertEqual(
            events[-1]["_terminal_tool_arguments"]["content_type"],
            "code",
        )

        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )
        with (
            mock.patch.object(conversation, "conversation_events", return_value=iter(events)),
            mock.patch.object(conversation, "_backend_http_timing_data", return_value={}),
            mock.patch.object(conversation, "_resolve_image_urls_with_monitor") as resolve_urls,
        ):
            outputs = list(conversation.stream_image_outputs(mock.Mock(), request))

        self.assertEqual(outputs[-1].failure.code, "image_tool_error")
        resolve_urls.assert_not_called()

    def test_terminal_tool_arguments_do_not_enter_result_polling(self) -> None:
        payloads = iter([
            json.dumps({
                "conversation_id": "conversation-id",
                "message": {
                    "id": "message-1",
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "code",
                        "text": '{"prompt":"draw a lighthouse","size":"1024x1024","n":1}',
                    },
                    "metadata": {"async_task_type": "image_gen"},
                    "status": "finished_successfully",
                    "end_turn": True,
                },
            }),
            "[DONE]",
        ])
        events = list(conversation.iter_conversation_payloads(payloads))
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )

        with (
            mock.patch.object(conversation, "conversation_events", return_value=iter(events)),
            mock.patch.object(conversation, "_backend_http_timing_data", return_value={}),
            mock.patch.object(conversation, "_get_detailed_failure_from_tasks", return_value=(None, "")),
            mock.patch.object(conversation, "_resolve_image_urls_with_monitor", return_value=[]) as resolve_urls,
        ):
            outputs = list(conversation.stream_image_outputs(mock.Mock(), request))

        resolve_urls.assert_not_called()
        self.assertIsNone(events[-1]["_image_failure"])
        self.assertEqual(outputs[-1].failure.code, "image_tool_error")

    def test_nonterminal_image_arguments_without_prompt_enter_result_polling(self) -> None:
        payloads = iter([
            json.dumps({
                "conversation_id": "conversation-id",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "code",
                        "text": '{"size":"1024x1024","n":1,"prompt":null}',
                    },
                    "metadata": {"message_type": "next"},
                    "status": "finished_successfully",
                    "end_turn": False,
                },
            }),
            "[DONE]",
        ])
        events = list(conversation.iter_conversation_payloads(payloads))
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )

        with (
            mock.patch.object(conversation, "conversation_events", return_value=iter(events)),
            mock.patch.object(conversation, "_backend_http_timing_data", return_value={}),
            mock.patch.object(
                conversation,
                "_resolve_image_urls_with_monitor",
                return_value=[],
            ) as resolve_urls,
        ):
            list(conversation.stream_image_outputs(mock.Mock(), request))

        resolve_urls.assert_called_once()

    def test_terminal_tool_arguments_with_pending_context_enter_result_polling(self) -> None:
        payloads = iter([
            json.dumps({
                "conversation_id": "conversation-id",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "code",
                        "text": '{"size":"1024x1024","n":1}',
                    },
                    "metadata": {"turn_use_case": "image gen"},
                    "status": "finished_successfully",
                    "end_turn": False,
                },
            }),
            "[DONE]",
        ])
        events = list(conversation.iter_conversation_payloads(payloads))
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )

        with (
            mock.patch.object(conversation, "conversation_events", return_value=iter(events)),
            mock.patch.object(conversation, "_backend_http_timing_data", return_value={}),
            mock.patch.object(
                conversation,
                "_resolve_image_urls_with_monitor",
                return_value=[],
            ) as resolve_urls,
        ):
            list(conversation.stream_image_outputs(mock.Mock(), request))

        resolve_urls.assert_called_once()

    def test_nonterminal_image_generation_state_is_not_terminal_failure(self) -> None:
        payloads = iter([
            json.dumps({
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["opaque progress"]},
                    "metadata": {"turn_use_case": "image gen"},
                    "status": "in_progress",
                    "end_turn": False,
                }
            }),
            "[DONE]",
        ])

        events = list(conversation.iter_conversation_payloads(payloads))

        self.assertIsNone(events[-1]["_image_failure"])
        self.assertEqual(events[-1]["turn_use_case"], "image gen")

    def test_terminal_image_generation_text_is_carried_as_structured_failure(self) -> None:
        payloads = iter([
            json.dumps({
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["opaque final reply"]},
                    "metadata": {"turn_use_case": "image gen"},
                    "status": "finished_successfully",
                    "end_turn": True,
                }
            }),
            "[DONE]",
        ])

        events = list(conversation.iter_conversation_payloads(payloads))

        self.assertEqual(events[-1]["_image_failure"].code, "upstream_text_reply")
        self.assertEqual(events[-1]["turn_use_case"], "image gen")

    def test_terminal_assistant_text_is_carried_as_structured_failure(self) -> None:
        payloads = iter([
            json.dumps({
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["opaque reply"]},
                    "status": "finished_successfully",
                    "end_turn": True,
                }
            }),
            "[DONE]",
        ])

        events = list(conversation.iter_conversation_payloads(payloads))

        self.assertEqual(events[-1]["_image_failure"].code, "upstream_text_reply")

    def test_structured_error_metadata_patch_is_carried_to_done(self) -> None:
        payloads = iter([
            json.dumps({
                "message": {
                    "author": {"role": "tool"},
                    "content": {"content_type": "text", "parts": []},
                    "metadata": {"async_task_type": "image_gen"},
                    "status": "in_progress",
                }
            }),
            json.dumps({
                "p": "/message/metadata",
                "o": "replace",
                "v": {
                    "is_error": True,
                    "error": {"code": "insufficient_quota"},
                },
            }),
            "[DONE]",
        ])

        events = list(conversation.iter_conversation_payloads(payloads))

        self.assertEqual(events[-1]["_image_failure"].code, "image_quota_exhausted")

    def test_terminal_text_built_from_patches_is_carried_to_done(self) -> None:
        payloads = iter([
            json.dumps({
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": [""]},
                    "metadata": {"turn_use_case": "image gen"},
                    "status": "in_progress",
                }
            }),
            json.dumps({
                "p": "",
                "o": "patch",
                "v": [
                    {"p": "/message/content/parts/0", "o": "append", "v": "opaque final reply"},
                    {"p": "/message/status", "o": "replace", "v": "finished_successfully"},
                    {"p": "/message/end_turn", "o": "replace", "v": True},
                ],
            }),
            "[DONE]",
        ])

        events = list(conversation.iter_conversation_payloads(payloads))

        self.assertEqual(events[-1]["_image_failure"].code, "upstream_text_reply")

    def test_terminal_image_tool_arguments_built_from_patches_are_failure(self) -> None:
        tool_arguments = json.dumps({
            "prompt": "draw a lighthouse",
            "size": "1024x1024",
            "n": 1,
        })
        payloads = iter([
            json.dumps({
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "code", "text": ""},
                    "metadata": {"turn_use_case": "image gen"},
                    "status": "in_progress",
                }
            }),
            json.dumps({
                "p": "",
                "o": "patch",
                "v": [
                    {"p": "/message/content/text", "o": "append", "v": tool_arguments},
                    {"p": "/message/status", "o": "replace", "v": "finished_successfully"},
                    {"p": "/message/end_turn", "o": "replace", "v": True},
                ],
            }),
            "[DONE]",
        ])

        events = list(conversation.iter_conversation_payloads(payloads))

        self.assertIsNone(events[-1]["_image_failure"])
        self.assertEqual(
            events[-1]["_terminal_tool_arguments"]["content_type"],
            "code",
        )

    def test_image_output_clears_preceding_tool_arguments_failure(self) -> None:
        payloads = iter([
            json.dumps({
                "message": {
                    "id": "message-1",
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "code",
                        "text": '{"prompt":"draw a lighthouse","size":"1024x1024","n":1}',
                    },
                    "metadata": {"turn_use_case": "image gen"},
                    "status": "finished_successfully",
                    "end_turn": True,
                },
            }),
            json.dumps({
                "message": {
                    "id": "message-2",
                    "author": {"role": "tool"},
                    "content": {
                        "content_type": "multimodal_text",
                        "parts": [{"asset_pointer": "file-service://file-result"}],
                    },
                    "metadata": {"async_task_type": "image_gen"},
                    "status": "finished_successfully",
                },
            }),
            "[DONE]",
        ])

        events = list(conversation.iter_conversation_payloads(payloads))

        self.assertIsNone(events[-1]["_image_failure"])
        self.assertEqual(events[-1]["file_ids"], ["file-result"])

    def test_image_output_clears_preceding_generic_tool_failure(self) -> None:
        payloads = iter([
            json.dumps({
                "message": {
                    "author": {"role": "tool"},
                    "content": {"content_type": "system_error", "parts": ["opaque transient error"]},
                    "metadata": {"async_task_type": "image_gen", "is_error": True},
                    "status": "finished_successfully",
                }
            }),
            json.dumps({
                "message": {
                    "author": {"role": "tool"},
                    "content": {
                        "content_type": "multimodal_text",
                        "parts": [{"asset_pointer": "file-service://file-result"}],
                    },
                    "metadata": {"async_task_type": "image_gen"},
                    "status": "finished_successfully",
                }
            }),
            "[DONE]",
        ])

        events = list(conversation.iter_conversation_payloads(payloads))

        self.assertIsNone(events[-1]["_image_failure"])
        self.assertEqual(events[-1]["file_ids"], ["file-result"])

    def test_terminal_stream_failure_does_not_enter_image_polling(self) -> None:
        terminal_failure = image_failure(
            "upstream_text_reply",
            raw_detail="opaque final reply",
        )
        events = iter([{
            "type": "conversation.done",
            "text": "opaque final reply",
            "conversation_id": "conversation-id",
            "file_ids": [],
            "sediment_ids": [],
            "blocked": False,
            "tool_invoked": True,
            "turn_use_case": "image gen",
            "_image_failure": terminal_failure,
        }])
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )

        with (
            mock.patch.object(conversation, "conversation_events", return_value=events),
            mock.patch.object(conversation, "_backend_http_timing_data", return_value={}),
            mock.patch.object(conversation, "_get_detailed_failure_from_tasks", return_value=(None, "")),
            mock.patch.object(conversation, "_resolve_image_urls_with_monitor") as resolve_urls,
        ):
            outputs = list(conversation.stream_image_outputs(mock.Mock(), request))

        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0].kind, "message")
        self.assertEqual(outputs[0].failure.code, "upstream_text_reply")
        resolve_urls.assert_not_called()

    def test_terminal_text_uses_structured_task_failure_without_polling(self) -> None:
        terminal_failure = image_failure(
            "upstream_text_reply",
            raw_detail="opaque final reply",
        )
        quota_failure = image_failure(
            "image_quota_exhausted",
            raw_detail="opaque quota detail",
        )
        events = iter([{
            "type": "conversation.done",
            "text": "opaque final reply",
            "conversation_id": "conversation-id",
            "file_ids": [],
            "sediment_ids": [],
            "blocked": False,
            "tool_invoked": True,
            "turn_use_case": "image gen",
            "_image_failure": terminal_failure,
        }])
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="draw a lighthouse",
        )

        with (
            mock.patch.object(conversation, "conversation_events", return_value=events),
            mock.patch.object(conversation, "_backend_http_timing_data", return_value={}),
            mock.patch.object(
                conversation,
                "_get_detailed_failure_from_tasks",
                return_value=(quota_failure, "opaque quota detail"),
            ) as task_probe,
            mock.patch.object(conversation, "_resolve_image_urls_with_monitor") as resolve_urls,
        ):
            outputs = list(conversation.stream_image_outputs(mock.Mock(), request))

        self.assertEqual(outputs[0].failure.code, "image_quota_exhausted")
        self.assertEqual(outputs[0].text, "opaque quota detail")
        task_probe.assert_called_once()
        resolve_urls.assert_not_called()

    def test_image_edit_terminal_failure_does_not_enter_image_polling(self) -> None:
        terminal_failure = image_failure(
            "upstream_text_reply",
            raw_detail="opaque final reply",
        )
        events = iter([{
            "type": "conversation.done",
            "text": "opaque final reply",
            "conversation_id": "conversation-id",
            "file_ids": [],
            "sediment_ids": [],
            "blocked": False,
            "tool_invoked": True,
            "turn_use_case": "image gen",
            "_image_failure": terminal_failure,
        }])
        request = conversation.ConversationRequest(
            model="gpt-image-2",
            prompt="edit a lighthouse",
            images=[b"source-image"],
        )

        with (
            mock.patch.object(conversation, "conversation_events", return_value=events),
            mock.patch.object(conversation, "_backend_http_timing_data", return_value={}),
            mock.patch.object(conversation, "_resolve_image_urls_with_monitor") as resolve_urls,
        ):
            outputs = list(conversation.stream_image_outputs(mock.Mock(), request))

        self.assertEqual(outputs[0].failure.code, "upstream_text_reply")
        resolve_urls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
