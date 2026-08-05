from __future__ import annotations

import base64
import re
import unittest
from types import SimpleNamespace
from unittest import mock

from services.editable_file_failure import EditableFileFailureError
from services.image_failure import image_failure
from services.openai_backend_api import EditableFileArtifact, OpenAIBackendAPI
from services.protocol import conversation, openai_search, web_search_tool
from utils.helper import UpstreamHTTPError


def account(token: str) -> dict[str, str]:
    suffix = token.rsplit("-", 1)[-1]
    return {
        "access_token": token,
        "refresh_token": f"refresh-{suffix}",
        "email": f"{suffix}@example.com",
    }


class TextAuthTests(unittest.TestCase):
    class Backend:
        def __init__(self, access_token: str = "") -> None:
            self.access_token = access_token
            self.account_email = ""

        def close(self) -> None:
            pass

    request = SimpleNamespace(messages=[], model="gpt-5", prompt="", thinking_effort=None)

    def test_401_after_output_is_isolated_without_replaying(self) -> None:
        def events(_backend: object, **_kwargs: object):
            yield {"type": "conversation.delta", "delta": "partial"}
            raise UpstreamHTTPError(
                "/backend-api/conversation", 401, {"code": "token_revoked"}
            )

        with (
            mock.patch.object(conversation, "OpenAIBackendAPI", self.Backend),
            mock.patch.object(conversation, "conversation_events", side_effect=events),
            mock.patch.object(conversation.account_service, "get_account", side_effect=account),
            mock.patch.object(conversation.account_service, "get_text_access_token") as select,
            mock.patch.object(conversation.account_service, "schedule_auth_verification") as schedule,
        ):
            stream = conversation.stream_text_deltas(self.Backend("token-a"), self.request)
            self.assertEqual(next(stream), "partial")
            with self.assertRaises(UpstreamHTTPError):
                next(stream)

        select.assert_not_called()
        schedule.assert_called_once()

    def test_structured_token_revoked_before_output_switches(self) -> None:
        def events(active_backend: TextAuthTests.Backend, **_kwargs: object):
            if active_backend.access_token == "token-a":
                yield {
                    "type": "conversation.event",
                    "_image_failure": image_failure(
                        "auth_invalid", raw_detail={"code": "token_revoked"}
                    ),
                }
                return
            yield {"type": "conversation.delta", "delta": "ok"}

        with (
            mock.patch.object(conversation, "OpenAIBackendAPI", self.Backend),
            mock.patch.object(conversation, "conversation_events", side_effect=events),
            mock.patch.object(conversation.account_service, "get_account", side_effect=account),
            mock.patch.object(
                conversation.account_service, "get_text_access_token", return_value="token-b"
            ),
            mock.patch.object(conversation.account_service, "schedule_auth_verification") as schedule,
            mock.patch.object(conversation.account_service, "mark_text_used"),
        ):
            result = "".join(
                conversation.stream_text_deltas(self.Backend("token-a"), self.request)
            )

        self.assertEqual(result, "ok")
        schedule.assert_called_once()


class SearchAuthTests(unittest.TestCase):
    class Backend:
        def __init__(self, access_token: str = "") -> None:
            self.access_token = access_token

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def search(self, query: str) -> dict[str, str]:
            if self.access_token == "token-a":
                raise UpstreamHTTPError(
                    "/backend-api/f/conversation", 401, {"code": "token_revoked"}
                )
            return {"answer": query}

    @staticmethod
    def select(excluded_tokens: set[str] | None = None) -> str:
        return "token-b" if "token-a" in set(excluded_tokens or ()) else "token-a"

    def test_both_search_entrypoints_retry_auth_once(self) -> None:
        runners = (
            lambda: openai_search.handle({"prompt": "query"}),
            lambda: web_search_tool.run_web_search("query"),
        )
        for runner in runners:
            with self.subTest(runner=runner):
                with (
                    mock.patch.object(web_search_tool, "OpenAIBackendAPI", self.Backend, create=True),
                    mock.patch.object(
                        web_search_tool.account_service,
                        "get_text_access_token",
                        side_effect=self.select,
                    ) as select,
                    mock.patch.object(web_search_tool.account_service, "get_account", side_effect=account),
                    mock.patch.object(
                        web_search_tool.account_service, "schedule_auth_verification"
                    ) as schedule,
                    mock.patch.object(web_search_tool.account_service, "mark_text_used"),
                ):
                    result = runner()

                self.assertEqual(result["answer"], "query")
                self.assertEqual(select.call_count, 2)
                schedule.assert_called_once()


class CodexAuthTests(unittest.TestCase):
    def test_terminal_event_does_not_wait_for_eof(self) -> None:
        class Raw:
            headers = {"content-type": "text/event-stream"}
            status = 200

            def __init__(self) -> None:
                self.lines = [
                    b'data: {"type":"response.completed","response":{"status":"completed"}}\n',
                    b"\n",
                ]

            def readline(self) -> bytes:
                if self.lines:
                    return self.lines.pop(0)
                raise AssertionError("read past terminal event")

        events = list(OpenAIBackendAPI._iter_codex_response_events(Raw()))
        self.assertEqual([event.get("type") for event in events], ["response.completed"])

    def test_image_plus_auth_failure_keeps_image_and_isolates_account(self) -> None:
        encoded = base64.b64encode(b"image-bytes").decode("ascii")
        backend = mock.Mock()
        backend.iter_codex_image_response_events.return_value = iter([
            {
                "type": "response.output_item.done",
                "item": {"type": "image_generation_call", "result": encoded},
            },
            {
                "type": "response.failed",
                "response": {"error": {"code": "token_revoked"}},
            },
        ])
        request = conversation.ConversationRequest(
            model="codex/gpt-image-2",
            prompt="draw",
            response_format="b64_json",
        )

        outputs = list(conversation.stream_codex_image_outputs(backend, request))

        self.assertTrue(outputs[0].data)
        backend._schedule_auth_recovery.assert_called_once_with(
            "codex_image_response_after_success"
        )


class EditableAuthTests(unittest.TestCase):
    class Response:
        def __init__(self, status_code: int, payload: object) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)
            self.headers = {}

        def json(self) -> object:
            return self._payload

        def close(self) -> None:
            pass

    @staticmethod
    def backend(session: mock.Mock) -> OpenAIBackendAPI:
        backend = object.__new__(OpenAIBackendAPI)
        backend.base_url = "https://chatgpt.example"
        backend.access_token = "access-token"
        backend.session = session
        backend._bootstrap = lambda: None
        backend._get_chat_requirements = lambda: {}
        backend._image_headers = lambda *_args, **_kwargs: {}
        backend._editable_download_headers = lambda *_args, **_kwargs: {}
        backend._credential_access_token = "access-token"
        backend._credential_refresh_token = "refresh-token"
        backend._credential_last_token_refresh_at = 123
        backend._schedule_auth_recovery = mock.Mock()
        return backend

    @staticmethod
    def revoked_conversation() -> dict[str, object]:
        return {
            "current_node": "node-1",
            "mapping": {
                "node-1": {
                    "message": {
                        "id": "message-1",
                        "author": {"role": "assistant"},
                        "status": "failed",
                        "content": {"content_type": "text", "parts": []},
                        "metadata": {"error": {"code": "token_revoked"}},
                    }
                }
            },
        }

    def test_account_download_url_401_raises_auth_failure(self) -> None:
        session = mock.Mock()
        session.get.return_value = self.Response(
            401, {"error": {"code": "token_revoked"}}
        )
        backend = self.backend(session)
        artifact = EditableFileArtifact(
            sandbox_path="/mnt/data/output.pptx", message_id="message-1"
        )

        with self.assertRaises(EditableFileFailureError) as raised:
            backend._resolve_editable_download_url("conversation-1", artifact)

        self.assertEqual(raised.exception.failure.code, "auth_invalid")
        backend._schedule_auth_recovery.assert_called_once_with(
            "editable_download_url_http_failure"
        )
        self.assertEqual(session.get.call_count, 1)

    def test_download_url_404_can_fall_back_to_next_candidate(self) -> None:
        session = mock.Mock()
        session.get.side_effect = [
            self.Response(404, {"error": "not found"}),
            self.Response(200, {"download_url": "https://assets.example/output.pptx"}),
        ]
        backend = self.backend(session)
        artifact = EditableFileArtifact(
            attachment_id="file-1",
            sandbox_path="/mnt/data/output.pptx",
            message_id="message-1",
        )

        url = backend._resolve_editable_download_url("conversation-1", artifact)

        self.assertEqual(url, "https://assets.example/output.pptx")
        self.assertEqual(session.get.call_count, 2)

    def test_editable_sse_token_revoked_is_not_treated_as_conversation_success(self) -> None:
        session = mock.Mock()
        session.post.return_value = self.Response(200, {})
        backend = self.backend(session)
        payload = '{"conversation_id":"conversation-1","error":{"code":"token_revoked"}}'

        with (
            mock.patch(
                "services.openai_backend_api.iter_sse_payloads",
                return_value=iter([payload]),
            ),
            self.assertRaises(Exception) as raised,
        ):
            backend._run_editable_conversation("prompt", [], "conduit")

        self.assertEqual(
            getattr(getattr(raised.exception, "failure", None), "code", ""),
            "auth_invalid",
        )

    def test_editable_poll_auth_failure_stops_without_waiting_for_timeout(self) -> None:
        backend = self.backend(mock.Mock())
        backend._get_editable_conversation_detail = lambda _conversation_id: self.revoked_conversation()

        with self.assertRaises(Exception) as raised:
            backend._wait_editable_output_artifacts(
                "conversation-1",
                "ppt",
                (".pptx",),
                {"application/pptx"},
                ("presentation",),
                re.compile(r"/mnt/data/[^ ]+"),
                timeout_secs=1,
                poll_interval_secs=0,
            )

        self.assertEqual(
            getattr(getattr(raised.exception, "failure", None), "code", ""),
            "auth_invalid",
        )

    def test_editable_poll_preserves_complete_artifacts_and_schedules_recovery(self) -> None:
        backend = self.backend(mock.Mock())
        artifacts = [
            EditableFileArtifact(name="output.pptx"),
            EditableFileArtifact(name="assets.zip"),
        ]
        backend._get_editable_conversation_detail = lambda _conversation_id: self.revoked_conversation()
        backend._extract_editable_artifacts = lambda *_args, **_kwargs: artifacts
        backend._pick_editable_target_artifacts = lambda *_args, **_kwargs: artifacts
        backend._schedule_auth_recovery = mock.Mock()

        result = backend._wait_editable_output_artifacts(
            "conversation-1",
            "ppt",
            (".pptx",),
            {"application/pptx"},
            ("presentation",),
            re.compile(r"/mnt/data/[^ ]+"),
            timeout_secs=1,
            poll_interval_secs=0,
        )

        self.assertEqual(result, artifacts)
        backend._schedule_auth_recovery.assert_called_once_with(
            "editable_artifact_after_success"
        )


if __name__ == "__main__":
    unittest.main()
