from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services.editable_file_failure import EditableFileFailureError
from services.image_failure import image_failure
from services.openai_backend_api import EditableFileArtifact, OpenAIBackendAPI
from utils.helper import UpstreamHTTPError


_PPT_SUFFIXES = (".ppt", ".pptx")
_PPT_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
}
_PPT_MIME_KEYWORDS = ("powerpoint",)
_PPT_EXPORT_RE = re.compile(r"(?:sandbox:)?(/mnt/data/[^\s]+\.(?:pptx?|zip))")


class _FakeResponse:
    def __init__(
        self,
        *,
        payload: object | None = None,
        sse_payloads: list[object] | None = None,
        status_code: int = 200,
        url: str = "https://chatgpt.com/backend-api/f/conversation",
    ) -> None:
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self.text = json.dumps(payload) if payload is not None else ""
        self.url = url
        self.content = b""
        self._payload = payload
        self._sse_payloads = list(sse_payloads or [])
        self.closed = False

    def json(self) -> object:
        return self._payload

    def iter_content(self):
        for payload in self._sse_payloads:
            encoded = payload if isinstance(payload, str) else json.dumps(payload)
            yield f"data: {encoded}\n\n".encode()
        yield b"data: [DONE]\n\n"

    def close(self) -> None:
        self.closed = True


class _FakeSession:
    def __init__(
        self,
        *,
        post_response: _FakeResponse | None = None,
        get_responses: list[_FakeResponse] | None = None,
    ) -> None:
        self.headers: dict[str, str] = {}
        self.post_response = post_response
        self.get_responses = list(get_responses or [])
        self.get_calls = 0

    def post(self, *_args, **_kwargs) -> _FakeResponse:
        if self.post_response is None:
            raise AssertionError("unexpected POST")
        return self.post_response

    def get(self, *_args, **_kwargs) -> _FakeResponse:
        self.get_calls += 1
        if not self.get_responses:
            raise AssertionError("unexpected GET")
        return self.get_responses.pop(0)

    def close(self) -> None:
        return None


class EditableFileBackendTests(unittest.TestCase):
    @staticmethod
    def _backend_for_stream(response: _FakeResponse) -> OpenAIBackendAPI:
        backend = object.__new__(OpenAIBackendAPI)
        backend.base_url = "https://chatgpt.com"
        backend.access_token = "access-token"
        backend.session = _FakeSession(post_response=response)
        backend._closed = False
        backend._bootstrap = Mock()
        backend._get_chat_requirements = Mock(return_value=Mock())
        backend._image_headers = Mock(return_value={})
        backend._credential_access_token = "access-token"
        backend._credential_refresh_token = "refresh-token"
        backend._credential_last_token_refresh_at = 123
        return backend

    @staticmethod
    def _backend_for_poll(responses: list[_FakeResponse]) -> OpenAIBackendAPI:
        backend = object.__new__(OpenAIBackendAPI)
        backend.base_url = "https://chatgpt.com"
        backend.access_token = "access-token"
        backend.session = _FakeSession(get_responses=responses)
        backend._closed = False
        backend._credential_access_token = "access-token"
        backend._credential_refresh_token = "refresh-token"
        backend._credential_last_token_refresh_at = 123
        return backend

    @staticmethod
    def _wait_for_ppt(backend: OpenAIBackendAPI):
        return backend._wait_editable_output_artifacts(
            "conversation-1",
            "ppt",
            _PPT_SUFFIXES,
            _PPT_MIME_TYPES,
            _PPT_MIME_KEYWORDS,
            _PPT_EXPORT_RE,
            timeout_secs=1,
            poll_interval_secs=0,
        )

    def test_editable_failure_projection_never_mentions_image_generation(self) -> None:
        for code in (
            "auth_invalid",
            "content_policy_violation",
            "image_quota_exhausted",
            "upstream_rate_limited",
            "image_download_failed",
            "upstream_connection_timeout",
            "upstream_error",
        ):
            with self.subTest(code=code):
                error = EditableFileFailureError(failure=image_failure(code))

                self.assertEqual(error.failure.code, code)
                self.assertNotIn("image generation", str(error).lower())
                self.assertIn("editable file", str(error).lower())

    def test_editable_export_projects_prepare_http_401_and_schedules_recovery(self) -> None:
        response = _FakeResponse(
            payload={"error": {"code": "token_revoked"}},
            status_code=401,
        )
        backend = self._backend_for_stream(response)
        backend._schedule_auth_recovery = Mock()

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            self.assertRaises(EditableFileFailureError) as raised,
        ):
            backend._export_editable_file_zip(
                [],
                "Create a presentation",
                temp_dir,
                primary_label="ppt",
                primary_suffixes=_PPT_SUFFIXES,
                primary_mime_types=_PPT_MIME_TYPES,
                primary_mime_keywords=_PPT_MIME_KEYWORDS,
                primary_default_extension=".pptx",
                export_file_re=_PPT_EXPORT_RE,
                timeout_secs=1,
                poll_interval_secs=0,
            )

        self.assertEqual(raised.exception.failure.code, "auth_invalid")
        backend._schedule_auth_recovery.assert_called_once_with(
            "editable_export_http_failure"
        )

    def test_editable_export_projects_early_account_http_401(self) -> None:
        backend = self._backend_for_stream(_FakeResponse())
        backend._schedule_auth_recovery = Mock()
        backend._upload_editable_base64_image = Mock(
            side_effect=UpstreamHTTPError(
                "/backend-api/files",
                401,
                {"error": {"code": "token_revoked"}},
            )
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            self.assertRaises(EditableFileFailureError) as raised,
        ):
            backend._export_editable_file_zip(
                ["base64-image"],
                "Create a presentation",
                temp_dir,
                primary_label="ppt",
                primary_suffixes=_PPT_SUFFIXES,
                primary_mime_types=_PPT_MIME_TYPES,
                primary_mime_keywords=_PPT_MIME_KEYWORDS,
                primary_default_extension=".pptx",
                export_file_re=_PPT_EXPORT_RE,
                timeout_secs=1,
                poll_interval_secs=0,
            )

        self.assertEqual(raised.exception.failure.code, "auth_invalid")
        backend._schedule_auth_recovery.assert_called_once_with(
            "editable_export_http_failure"
        )

    def test_editable_export_keeps_signed_upload_failure_out_of_auth_recovery(self) -> None:
        backend = self._backend_for_stream(_FakeResponse())
        backend._schedule_auth_recovery = Mock()
        backend._upload_editable_base64_image = Mock(
            side_effect=UpstreamHTTPError(
                "image_upload",
                401,
                {"error": {"code": "token_revoked"}},
                credential_scope="signed_asset",
            )
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            self.assertRaises(EditableFileFailureError) as raised,
        ):
            backend._export_editable_file_zip(
                ["base64-image"],
                "Create a presentation",
                temp_dir,
                primary_label="ppt",
                primary_suffixes=_PPT_SUFFIXES,
                primary_mime_types=_PPT_MIME_TYPES,
                primary_mime_keywords=_PPT_MIME_KEYWORDS,
                primary_default_extension=".pptx",
                export_file_re=_PPT_EXPORT_RE,
                timeout_secs=1,
                poll_interval_secs=0,
            )

        self.assertEqual(raised.exception.failure.scope, "delivery")
        self.assertIn("transferred", str(raised.exception).lower())
        backend._schedule_auth_recovery.assert_not_called()

    def test_editable_export_projects_incomplete_download_set(self) -> None:
        backend = self._backend_for_stream(_FakeResponse())
        backend._prepare_editable_conversation = Mock(return_value="conduit-token")
        backend._run_editable_conversation = Mock(return_value="conversation-1")
        backend._wait_editable_output_artifacts = Mock(
            return_value=[EditableFileArtifact(name="output.pptx")]
        )
        backend._download_editable_artifact = Mock(
            return_value=Path("output.pptx")
        )

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            self.assertRaises(EditableFileFailureError) as raised,
        ):
            backend._export_editable_file_zip(
                [],
                "Create a presentation",
                temp_dir,
                primary_label="ppt",
                primary_suffixes=_PPT_SUFFIXES,
                primary_mime_types=_PPT_MIME_TYPES,
                primary_mime_keywords=_PPT_MIME_KEYWORDS,
                primary_default_extension=".pptx",
                export_file_re=_PPT_EXPORT_RE,
                timeout_secs=1,
                poll_interval_secs=0,
            )

        self.assertEqual(raised.exception.failure.code, "image_download_failed")
        self.assertEqual(raised.exception.failure.scope, "delivery")

    def test_editable_stream_accepts_ordinary_terminal_assistant_text(self) -> None:
        response = _FakeResponse(
            sse_payloads=[
                {
                    "conversation_id": "conversation-1",
                    "message": {
                        "id": "assistant-message",
                        "author": {"role": "assistant"},
                        "content": {
                            "content_type": "text",
                            "parts": ["The presentation is ready."],
                        },
                        "status": "finished_successfully",
                        "end_turn": True,
                    },
                }
            ]
        )
        backend = self._backend_for_stream(response)

        conversation_id = backend._run_editable_conversation(
            "Create a presentation",
            [],
            "conduit-token",
        )

        self.assertEqual(conversation_id, "conversation-1")
        self.assertTrue(response.closed)

    def test_editable_stream_accepts_terminal_assistant_file_links(self) -> None:
        response = _FakeResponse(
            sse_payloads=[
                {
                    "conversation_id": "conversation-1",
                    "message": {
                        "id": "assistant-message",
                        "author": {"role": "assistant"},
                        "content": {
                            "content_type": "text",
                            "parts": [
                                "Files are ready: "
                                "sandbox:/mnt/data/presentation.pptx "
                                "sandbox:/mnt/data/presentation.zip"
                            ],
                        },
                        "status": "finished_successfully",
                        "end_turn": True,
                    },
                }
            ]
        )
        backend = self._backend_for_stream(response)

        conversation_id = backend._run_editable_conversation(
            "Create a presentation",
            [],
            "conduit-token",
        )

        self.assertEqual(conversation_id, "conversation-1")
        self.assertTrue(response.closed)

    def test_editable_poll_waits_when_artifacts_arrive_after_success_text(self) -> None:
        user_message = {
            "id": "user-message",
            "author": {"role": "user"},
            "content": {"content_type": "text", "parts": ["Create a presentation"]},
            "create_time": 1,
        }
        assistant_message = {
            "id": "assistant-message",
            "author": {"role": "assistant"},
            "content": {
                "content_type": "text",
                "parts": ["The presentation is ready."],
            },
            "status": "finished_successfully",
            "end_turn": True,
            "create_time": 2,
        }
        text_only = {
            "mapping": {
                "user": {"message": user_message},
                "assistant": {"message": assistant_message},
            }
        }
        with_artifacts = {
            "mapping": {
                **text_only["mapping"],
                "tool": {
                    "message": {
                        "id": "tool-message",
                        "author": {"role": "tool"},
                        "content": {"content_type": "text", "parts": []},
                        "metadata": {
                            "attachments": [
                                {
                                    "id": "file-presentation",
                                    "name": "presentation.pptx",
                                    "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                },
                                {
                                    "id": "file-archive",
                                    "name": "presentation.zip",
                                    "mime_type": "application/zip",
                                },
                            ]
                        },
                        "create_time": 3,
                    }
                },
            }
        }
        backend = self._backend_for_poll(
            [
                _FakeResponse(payload=text_only),
                _FakeResponse(payload=with_artifacts),
            ]
        )

        artifacts = self._wait_for_ppt(backend)

        self.assertEqual(
            [artifact.name for artifact in artifacts],
            ["presentation.pptx", "presentation.zip"],
        )
        self.assertEqual(backend.session.get_calls, 2)

    def test_editable_stream_schedules_auth_recovery_before_raising_token_revoked(self) -> None:
        response = _FakeResponse(
            sse_payloads=[
                {
                    "conversation_id": "conversation-1",
                    "message": {
                        "id": "assistant-message",
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": []},
                        "status": "token_revoked",
                    },
                }
            ]
        )
        backend = self._backend_for_stream(response)
        recovery_started = False

        def mark_recovery(*_args, **_kwargs) -> None:
            nonlocal recovery_started
            recovery_started = True

        with (
            patch(
                "services.openai_backend_api.account_service.schedule_auth_verification",
                side_effect=mark_recovery,
            ) as schedule,
            self.assertRaises(EditableFileFailureError) as raised,
        ):
            backend._run_editable_conversation(
                "Create a presentation",
                [],
                "conduit-token",
            )

        self.assertTrue(recovery_started)
        self.assertEqual(raised.exception.failure.code, "auth_invalid")
        schedule.assert_called_once()

    def test_editable_stream_reads_auth_code_from_top_level_error(self) -> None:
        response = _FakeResponse(
            sse_payloads=[
                {
                    "conversation_id": "conversation-1",
                    "error": {"code": "token_revoked"},
                }
            ]
        )
        backend = self._backend_for_stream(response)

        with (
            patch(
                "services.openai_backend_api.account_service.schedule_auth_verification",
            ) as schedule,
            self.assertRaises(EditableFileFailureError) as raised,
        ):
            backend._run_editable_conversation(
                "Create a presentation",
                [],
                "conduit-token",
            )

        self.assertEqual(raised.exception.failure.code, "auth_invalid")
        schedule.assert_called_once()

    def test_editable_poll_schedules_auth_recovery_before_raising_auth_invalid(self) -> None:
        conversation = {
            "mapping": {
                "user": {
                    "message": {
                        "id": "user-message",
                        "author": {"role": "user"},
                        "content": {
                            "content_type": "text",
                            "parts": ["Create a presentation"],
                        },
                        "create_time": 1,
                    }
                },
                "assistant": {
                    "message": {
                        "id": "assistant-message",
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": []},
                        "status": "auth_invalid",
                        "create_time": 2,
                    }
                },
            }
        }
        backend = self._backend_for_poll([_FakeResponse(payload=conversation)])
        recovery_started = False

        def mark_recovery(*_args, **_kwargs) -> None:
            nonlocal recovery_started
            recovery_started = True

        with (
            patch(
                "services.openai_backend_api.account_service.schedule_auth_verification",
                side_effect=mark_recovery,
            ) as schedule,
            self.assertRaises(EditableFileFailureError) as raised,
        ):
            self._wait_for_ppt(backend)

        self.assertTrue(recovery_started)
        self.assertEqual(raised.exception.failure.code, "auth_invalid")
        schedule.assert_called_once()

    def test_editable_poll_reads_auth_code_from_metadata_error(self) -> None:
        conversation = {
            "current_node": "assistant",
            "mapping": {
                "user": {
                    "parent": "",
                    "message": {
                        "id": "user-message",
                        "author": {"role": "user"},
                        "content": {
                            "content_type": "text",
                            "parts": ["Create a presentation"],
                        },
                        "create_time": 1,
                    },
                },
                "assistant": {
                    "parent": "user",
                    "message": {
                        "id": "assistant-message",
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": []},
                        "status": "failed",
                        "metadata": {"error": {"code": "token_revoked"}},
                        "create_time": 2,
                    },
                },
            },
        }
        backend = self._backend_for_poll([_FakeResponse(payload=conversation)])

        with (
            patch(
                "services.openai_backend_api.account_service.schedule_auth_verification",
            ) as schedule,
            self.assertRaises(EditableFileFailureError) as raised,
        ):
            self._wait_for_ppt(backend)

        self.assertEqual(raised.exception.failure.code, "auth_invalid")
        schedule.assert_called_once()

    def test_editable_stream_http_401_schedules_auth_recovery(self) -> None:
        response = _FakeResponse(
            payload={"error": {"code": "token_revoked"}},
            status_code=401,
        )
        backend = self._backend_for_stream(response)
        backend._schedule_auth_recovery = Mock()

        with self.assertRaises(EditableFileFailureError) as raised:
            backend._run_editable_conversation(
                "Create a presentation",
                [],
                "conduit-token",
            )

        self.assertEqual(raised.exception.failure.code, "auth_invalid")
        backend._schedule_auth_recovery.assert_called_once_with(
            "editable_stream_http_failure"
        )

    def test_editable_poll_http_401_schedules_auth_recovery(self) -> None:
        backend = self._backend_for_poll(
            [
                _FakeResponse(
                    payload={"error": {"code": "token_revoked"}},
                    status_code=401,
                )
            ]
        )
        backend._schedule_auth_recovery = Mock()

        with self.assertRaises(EditableFileFailureError) as raised:
            self._wait_for_ppt(backend)

        self.assertEqual(raised.exception.failure.code, "auth_invalid")
        backend._schedule_auth_recovery.assert_called_once_with(
            "editable_poll_http_failure"
        )

    def test_editable_download_url_http_401_schedules_auth_recovery(self) -> None:
        backend = self._backend_for_poll(
            [
                _FakeResponse(
                    payload={"error": {"code": "token_revoked"}},
                    status_code=401,
                )
            ]
        )
        backend._schedule_auth_recovery = Mock()
        artifact = EditableFileArtifact(
            sandbox_path="/mnt/data/output.pptx",
            message_id="message-1",
        )

        with self.assertRaises(EditableFileFailureError) as raised:
            backend._resolve_editable_download_url("conversation-1", artifact)

        self.assertEqual(raised.exception.failure.code, "auth_invalid")
        backend._schedule_auth_recovery.assert_called_once_with(
            "editable_download_url_http_failure"
        )

    def test_editable_signed_asset_401_is_delivery_failure_without_auth_recovery(self) -> None:
        backend = self._backend_for_poll(
            [
                _FakeResponse(
                    payload={"error": {"code": "token_revoked"}},
                    status_code=401,
                    url="https://assets.example/output.pptx",
                )
            ]
        )
        backend._schedule_auth_recovery = Mock()
        artifact = EditableFileArtifact(name="output.pptx")

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.object(
                backend,
                "_resolve_editable_download_url",
                return_value="https://assets.example/output.pptx",
            ),
            self.assertRaises(EditableFileFailureError) as raised,
        ):
            backend._download_editable_artifact(
                "conversation-1",
                artifact,
                Path(temp_dir),
                _PPT_MIME_TYPES,
                _PPT_MIME_KEYWORDS,
                ".pptx",
            )

        self.assertEqual(raised.exception.failure.scope, "delivery")
        self.assertEqual(raised.exception.failure.code, "image_download_failed")
        backend._schedule_auth_recovery.assert_not_called()

    def test_editable_poll_timeout_uses_editable_failure_projection(self) -> None:
        backend = self._backend_for_poll([])

        with self.assertRaises(EditableFileFailureError) as raised:
            backend._wait_editable_output_artifacts(
                "conversation-1",
                "ppt",
                _PPT_SUFFIXES,
                _PPT_MIME_TYPES,
                _PPT_MIME_KEYWORDS,
                _PPT_EXPORT_RE,
                timeout_secs=0,
                poll_interval_secs=0,
            )

        self.assertEqual(raised.exception.failure.code, "image_poll_timeout")
        self.assertNotIn("image generation", str(raised.exception).lower())

    def test_editable_missing_download_url_uses_delivery_failure_projection(self) -> None:
        backend = self._backend_for_poll([])
        artifact = EditableFileArtifact(name="output.pptx")

        with self.assertRaises(EditableFileFailureError) as raised:
            backend._download_editable_artifact(
                "conversation-1",
                artifact,
                Path("."),
                _PPT_MIME_TYPES,
                _PPT_MIME_KEYWORDS,
                ".pptx",
            )

        self.assertEqual(raised.exception.failure.code, "image_download_failed")
        self.assertEqual(raised.exception.failure.scope, "delivery")

    def test_editable_download_url_404_falls_back_to_next_candidate(self) -> None:
        backend = self._backend_for_poll(
            [
                _FakeResponse(payload={"error": "not found"}, status_code=404),
                _FakeResponse(
                    payload={"download_url": "https://assets.example/output.pptx"}
                ),
            ]
        )
        artifact = EditableFileArtifact(
            attachment_id="file-1",
            sandbox_path="/mnt/data/output.pptx",
            message_id="message-1",
        )

        url = backend._resolve_editable_download_url("conversation-1", artifact)

        self.assertEqual(url, "https://assets.example/output.pptx")
        self.assertEqual(backend.session.get_calls, 2)


if __name__ == "__main__":
    unittest.main()
