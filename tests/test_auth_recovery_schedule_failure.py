from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from services.protocol import conversation, web_search_tool
from utils.helper import UpstreamHTTPError


def account(token: str) -> dict[str, str]:
    suffix = token.rsplit("-", 1)[-1]
    return {
        "access_token": token,
        "refresh_token": f"refresh-{suffix}",
        "email": f"{suffix}@example.com",
    }


class AuthRecoveryScheduleFailureTests(unittest.TestCase):
    class TextBackend:
        def __init__(self, access_token: str = "") -> None:
            self.access_token = access_token
            self.account_email = ""

        def close(self) -> None:
            pass

    request = SimpleNamespace(
        messages=[],
        model="gpt-5",
        prompt="",
        thinking_effort=None,
    )

    def test_text_switch_survives_recovery_schedule_failure(self) -> None:
        def events(active_backend: AuthRecoveryScheduleFailureTests.TextBackend, **_kwargs: object):
            if active_backend.access_token == "token-a":
                raise UpstreamHTTPError(
                    "/backend-api/conversation", 401, {"code": "token_revoked"}
                )
            yield {"type": "conversation.delta", "delta": "ok"}

        with (
            mock.patch.object(conversation, "OpenAIBackendAPI", self.TextBackend),
            mock.patch.object(conversation, "conversation_events", side_effect=events),
            mock.patch.object(conversation.account_service, "get_account", side_effect=account),
            mock.patch.object(
                conversation.account_service, "get_text_access_token", return_value="token-b"
            ),
            mock.patch.object(
                conversation.account_service,
                "schedule_auth_verification",
                side_effect=OSError("storage unavailable"),
            ),
            mock.patch.object(conversation.account_service, "mark_text_used"),
        ):
            result = "".join(
                conversation.stream_text_deltas(self.TextBackend("token-a"), self.request)
            )

        self.assertEqual(result, "ok")

    def test_text_after_output_preserves_original_401(self) -> None:
        failure = UpstreamHTTPError(
            "/backend-api/conversation", 401, {"code": "token_revoked"}
        )

        def events(_backend: object, **_kwargs: object):
            yield {"type": "conversation.delta", "delta": "partial"}
            raise failure

        with (
            mock.patch.object(conversation, "OpenAIBackendAPI", self.TextBackend),
            mock.patch.object(conversation, "conversation_events", side_effect=events),
            mock.patch.object(conversation.account_service, "get_account", side_effect=account),
            mock.patch.object(
                conversation.account_service,
                "schedule_auth_verification",
                side_effect=OSError("storage unavailable"),
            ),
        ):
            stream = conversation.stream_text_deltas(self.TextBackend("token-a"), self.request)
            self.assertEqual(next(stream), "partial")
            with self.assertRaises(UpstreamHTTPError) as raised:
                next(stream)

        self.assertIs(raised.exception, failure)

    def test_search_switch_survives_recovery_schedule_failure(self) -> None:
        class SearchBackend:
            def __init__(self, access_token: str = "") -> None:
                self.access_token = access_token

            def __enter__(self):
                return self

            def __exit__(self, *_args: object) -> None:
                pass

            def search(self, query: str) -> dict[str, str]:
                if self.access_token == "token-a":
                    raise UpstreamHTTPError(
                        "/backend-api/f/conversation",
                        401,
                        {"code": "token_revoked"},
                    )
                return {"answer": query}

        def select(excluded_tokens: set[str] | None = None) -> str:
            return "token-b" if "token-a" in set(excluded_tokens or ()) else "token-a"

        with (
            mock.patch.object(web_search_tool, "OpenAIBackendAPI", SearchBackend),
            mock.patch.object(
                web_search_tool.account_service,
                "get_text_access_token",
                side_effect=select,
            ),
            mock.patch.object(web_search_tool.account_service, "get_account", side_effect=account),
            mock.patch.object(
                web_search_tool.account_service,
                "schedule_auth_verification",
                side_effect=OSError("storage unavailable"),
            ),
            mock.patch.object(web_search_tool.account_service, "mark_text_used"),
        ):
            result = web_search_tool.run_web_search("query")

        self.assertEqual(result["answer"], "query")


if __name__ == "__main__":
    unittest.main()
