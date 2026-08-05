from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from services.protocol import conversation
from utils.helper import UpstreamHTTPError


class TextStreamAuthAuditTests(unittest.TestCase):
    def test_account_401_uses_structured_error_and_request_snapshot(self) -> None:
        class Backend:
            def __init__(self, access_token: str = "") -> None:
                self.access_token = access_token
                self.account_email = ""

            def close(self) -> None:
                return None

        def events(active_backend: Backend, **_kwargs: object):
            if active_backend.access_token == "token-a":
                raise UpstreamHTTPError(
                    "/backend-api/conversation",
                    401,
                    {"error": "unauthorized"},
                    credential_scope="account",
                )
            yield {"type": "conversation.delta", "delta": "ok"}

        request = SimpleNamespace(
            messages=[],
            model="gpt-5",
            prompt="",
            thinking_effort=None,
        )
        accounts = {
            "token-a": {"email": "a@example.com", "refresh_token": "refresh-a"},
            "token-b": {"email": "b@example.com", "refresh_token": "refresh-b"},
        }
        with (
            mock.patch.object(conversation, "OpenAIBackendAPI", Backend),
            mock.patch.object(conversation, "conversation_events", side_effect=events),
            mock.patch.object(
                conversation.account_service,
                "get_account",
                side_effect=lambda token: accounts.get(token),
            ),
            mock.patch.object(
                conversation.account_service,
                "get_text_access_token",
                return_value="token-b",
            ),
            mock.patch.object(conversation.account_service, "schedule_auth_verification") as schedule,
            mock.patch.object(conversation.account_service, "mark_text_used"),
        ):
            result = "".join(conversation.stream_text_deltas(Backend("token-a"), request))

        self.assertEqual(result, "ok")
        schedule.assert_called_once_with(
            "token-a",
            "text_stream",
            expected_access_token="token-a",
            expected_refresh_token="refresh-a",
            expected_last_token_refresh_at=None,
        )

    def test_second_account_auth_failure_is_not_retried_again(self) -> None:
        class Backend:
            def __init__(self, access_token: str = "") -> None:
                self.access_token = access_token
                self.account_email = ""

            def close(self) -> None:
                return None

        def events(active_backend: Backend, **_kwargs: object):
            raise UpstreamHTTPError(
                "/backend-api/conversation",
                401,
                {"error": "unauthorized", "token": active_backend.access_token},
                credential_scope="account",
            )
            yield

        request = SimpleNamespace(
            messages=[],
            model="gpt-5",
            prompt="",
            thinking_effort=None,
        )
        accounts = {
            "token-a": {"email": "a@example.com", "refresh_token": "refresh-a"},
            "token-b": {"email": "b@example.com", "refresh_token": "refresh-b"},
            "token-c": {"email": "c@example.com", "refresh_token": "refresh-c"},
        }
        with (
            mock.patch.object(conversation, "OpenAIBackendAPI", Backend),
            mock.patch.object(conversation, "conversation_events", side_effect=events),
            mock.patch.object(
                conversation.account_service,
                "get_account",
                side_effect=lambda token: accounts.get(token),
            ),
            mock.patch.object(
                conversation.account_service,
                "get_text_access_token",
                side_effect=["token-b", "token-c"],
            ) as select,
            mock.patch.object(
                conversation.account_service,
                "schedule_auth_verification",
            ) as schedule,
        ):
            with self.assertRaises(UpstreamHTTPError):
                list(conversation.stream_text_deltas(Backend("token-a"), request))

        select.assert_called_once()
        self.assertEqual(schedule.call_count, 2)


if __name__ == "__main__":
    unittest.main()
