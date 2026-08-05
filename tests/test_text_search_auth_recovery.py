from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from services.protocol import conversation, openai_search, web_search_tool
from utils.helper import UpstreamHTTPError


def _account(access_token: str) -> dict[str, str]:
    suffix = access_token.rsplit("-", 1)[-1]
    return {
        "access_token": access_token,
        "refresh_token": f"refresh-{suffix}",
        "email": f"{suffix}@example.com",
    }


class _SearchBackend:
    def __init__(self, access_token: str = "") -> None:
        self.access_token = access_token

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def search(self, query: str) -> dict[str, str]:
        if self.access_token == "token-a":
            raise UpstreamHTTPError(
                "/backend-api/f/conversation",
                401,
                {"code": "token_revoked"},
            )
        return {"answer": query}


class TextAndSearchAuthRecoveryTests(unittest.TestCase):
    def test_ordinary_terminal_assistant_text_streams_through_real_parser(self) -> None:
        class TextBackend:
            def __init__(self, access_token: str = "") -> None:
                self.access_token = access_token
                self.account_email = ""

            def close(self) -> None:
                return None

            def stream_conversation(self, **_kwargs: object):
                yield json.dumps({
                    "message": {
                        "id": "message-1",
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": ["ordinary reply"]},
                        "status": "finished_successfully",
                        "end_turn": True,
                    },
                })
                yield "[DONE]"

        request = SimpleNamespace(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-5",
            prompt="",
            thinking_effort=None,
        )
        with (
            mock.patch.object(conversation, "OpenAIBackendAPI", TextBackend),
            mock.patch.object(conversation.account_service, "get_account", return_value=_account("token-a")),
            mock.patch.object(conversation.account_service, "mark_text_used") as mark_used,
        ):
            result = "".join(conversation.stream_text_deltas(TextBackend("token-a"), request))

        self.assertEqual(result, "ordinary reply")
        mark_used.assert_called_once_with("token-a")

    def test_structured_text_stream_auth_failure_switches_account_through_real_parser(self) -> None:
        class TextBackend:
            def __init__(self, access_token: str = "") -> None:
                self.access_token = access_token
                self.account_email = ""

            def close(self) -> None:
                return None

            def stream_conversation(self, **_kwargs: object):
                if self.access_token == "token-a":
                    yield json.dumps({
                        "message": {
                            "id": "message-auth-failure",
                            "author": {"role": "assistant"},
                            "content": {"content_type": "text", "parts": []},
                            "status": "token_revoked",
                            "end_turn": True,
                        },
                    })
                else:
                    yield json.dumps({
                        "message": {
                            "id": "message-success",
                            "author": {"role": "assistant"},
                            "content": {"content_type": "text", "parts": ["recovered"]},
                            "status": "finished_successfully",
                            "end_turn": True,
                        },
                    })
                yield "[DONE]"

        request = SimpleNamespace(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-5",
            prompt="",
            thinking_effort=None,
        )
        selected_exclusions: list[set[str]] = []

        def select_text_account(excluded_tokens: set[str]) -> str:
            selected_exclusions.append(set(excluded_tokens))
            return "token-b"

        with (
            mock.patch.object(conversation, "OpenAIBackendAPI", TextBackend),
            mock.patch.object(conversation.account_service, "get_account", side_effect=_account),
            mock.patch.object(
                conversation.account_service,
                "get_text_access_token",
                side_effect=select_text_account,
            ),
            mock.patch.object(conversation.account_service, "schedule_auth_verification") as schedule,
            mock.patch.object(conversation.account_service, "mark_text_used") as mark_used,
        ):
            result = "".join(conversation.stream_text_deltas(TextBackend("token-a"), request))

        self.assertEqual(result, "recovered")
        self.assertEqual(selected_exclusions, [{"token-a"}])
        schedule.assert_called_once()
        mark_used.assert_called_once_with("token-b")

    def test_both_search_entrypoints_switch_account_once(self) -> None:
        def select(excluded_tokens: set[str] | None = None) -> str:
            return "token-b" if "token-a" in set(excluded_tokens or ()) else "token-a"

        runners = (
            lambda: openai_search.handle({"prompt": "query"}),
            lambda: web_search_tool.run_web_search("query"),
        )
        for runner in runners:
            with self.subTest(runner=runner):
                with (
                    mock.patch.object(web_search_tool, "OpenAIBackendAPI", _SearchBackend),
                    mock.patch.object(
                        web_search_tool.account_service,
                        "get_text_access_token",
                        side_effect=select,
                    ) as select_token,
                    mock.patch.object(
                        web_search_tool.account_service,
                        "get_account",
                        side_effect=_account,
                    ),
                    mock.patch.object(
                        web_search_tool.account_service,
                        "schedule_auth_verification",
                    ) as schedule,
                    mock.patch.object(web_search_tool.account_service, "mark_text_used"),
                ):
                    result = runner()

                self.assertEqual(result["answer"], "query")
                self.assertEqual(select_token.call_count, 2)
                schedule.assert_called_once_with(
                    "token-a",
                    "search",
                    expected_access_token="token-a",
                    expected_refresh_token="refresh-a",
                    expected_last_token_refresh_at=None,
                )

    def test_search_switch_survives_verification_schedule_failure(self) -> None:
        def select(excluded_tokens: set[str] | None = None) -> str:
            return "token-b" if "token-a" in set(excluded_tokens or ()) else "token-a"

        with (
            mock.patch.object(web_search_tool, "OpenAIBackendAPI", _SearchBackend),
            mock.patch.object(
                web_search_tool.account_service,
                "get_text_access_token",
                side_effect=select,
            ),
            mock.patch.object(
                web_search_tool.account_service,
                "get_account",
                side_effect=_account,
            ),
            mock.patch.object(
                web_search_tool.account_service,
                "schedule_auth_verification",
                side_effect=OSError("storage unavailable"),
            ),
            mock.patch.object(web_search_tool.account_service, "mark_text_used"),
        ):
            result = web_search_tool.run_web_search("query")

        self.assertEqual(result["answer"], "query")

    def test_search_does_not_switch_more_than_once(self) -> None:
        class RejectedBackend(_SearchBackend):
            def search(self, query: str) -> dict[str, str]:
                raise UpstreamHTTPError(
                    "/backend-api/f/conversation",
                    401,
                    {"code": "token_revoked", "token": self.access_token},
                )

        with (
            mock.patch.object(web_search_tool, "OpenAIBackendAPI", RejectedBackend),
            mock.patch.object(
                web_search_tool.account_service,
                "get_text_access_token",
                side_effect=["token-a", "token-b", "token-c"],
            ) as select_token,
            mock.patch.object(
                web_search_tool.account_service,
                "get_account",
                side_effect=_account,
            ),
            mock.patch.object(
                web_search_tool.account_service,
                "schedule_auth_verification",
            ) as schedule,
        ):
            with self.assertRaises(UpstreamHTTPError):
                web_search_tool.run_web_search("query")

        self.assertEqual(select_token.call_count, 2)
        self.assertEqual(schedule.call_count, 2)

    def test_search_preserves_auth_error_when_no_second_account_exists(self) -> None:
        with (
            mock.patch.object(web_search_tool, "OpenAIBackendAPI", _SearchBackend),
            mock.patch.object(
                web_search_tool.account_service,
                "get_text_access_token",
                side_effect=["token-a", ""],
            ),
            mock.patch.object(
                web_search_tool.account_service,
                "get_account",
                side_effect=_account,
            ),
            mock.patch.object(
                web_search_tool.account_service,
                "schedule_auth_verification",
            ),
        ):
            with self.assertRaises(UpstreamHTTPError) as raised:
                web_search_tool.run_web_search("query")

        self.assertEqual(raised.exception.status_code, 401)

    def test_text_switch_survives_verification_schedule_failure(self) -> None:
        class TextBackend:
            def __init__(self, access_token: str = "") -> None:
                self.access_token = access_token
                self.account_email = ""

            def close(self) -> None:
                return None

        def events(active_backend: TextBackend, **_kwargs: object):
            if active_backend.access_token == "token-a":
                raise UpstreamHTTPError(
                    "/backend-api/conversation",
                    401,
                    {"code": "token_revoked"},
                )
            yield {"type": "conversation.delta", "delta": "ok"}

        request = SimpleNamespace(
            messages=[],
            model="gpt-5",
            prompt="",
            thinking_effort=None,
        )
        with (
            mock.patch.object(conversation, "OpenAIBackendAPI", TextBackend),
            mock.patch.object(conversation, "conversation_events", side_effect=events),
            mock.patch.object(conversation.account_service, "get_account", side_effect=_account),
            mock.patch.object(
                conversation.account_service,
                "get_text_access_token",
                return_value="token-b",
            ),
            mock.patch.object(
                conversation.account_service,
                "schedule_auth_verification",
                side_effect=OSError("storage unavailable"),
            ),
            mock.patch.object(conversation.account_service, "mark_text_used"),
        ):
            result = "".join(conversation.stream_text_deltas(TextBackend("token-a"), request))

        self.assertEqual(result, "ok")


if __name__ == "__main__":
    unittest.main()
