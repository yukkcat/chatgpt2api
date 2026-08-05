from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.account_service import AccountService
from services.image_failure import InvalidAccessTokenError
from tests.support.account_repository import TestAccountRepository


class AccountRemoteCheckCASTests(unittest.TestCase):
    def _service(self, tmp_dir: str) -> AccountService:
        storage = TestAccountRepository(Path(tmp_dir) / "accounts.json")
        storage.save_accounts(
            [
                {
                    "access_token": "token-a",
                    "refresh_token": "refresh-a",
                    "status": "正常",
                }
            ]
        )
        return AccountService(storage)

    def test_thread_start_failure_does_not_overwrite_new_pending_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            test_case = self

            class FailingThread:
                def __init__(self, **_kwargs: object) -> None:
                    pass

                def start(self) -> None:
                    with mock.patch.object(
                        service,
                        "_schedule_account_refresh_after_image_failure",
                        return_value=True,
                    ):
                        test_case.assertTrue(
                            service.schedule_auth_verification(
                                "token-a",
                                "second_verification",
                                expected_access_token="token-a",
                                expected_refresh_token="refresh-a",
                                scope="image",
                            )
                        )
                    raise RuntimeError("thread start failed")

            with mock.patch("services.account_service.Thread", FailingThread):
                self.assertTrue(
                    service.schedule_auth_verification(
                        "token-a",
                        "first_verification",
                        expected_access_token="token-a",
                        expected_refresh_token="refresh-a",
                        scope="image",
                    )
                )

            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("last_remote_check_result"), "pending")
            self.assertEqual(account.get("last_remote_check_event"), "second_verification")
            self.assertIsNone(account.get("last_remote_check_error"))

    def test_stale_refresh_failure_does_not_overwrite_new_pending_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            refresh_calls = 0

            class Backend:
                def __init__(self, _access_token: str) -> None:
                    pass

                def __enter__(self) -> "Backend":
                    return self

                def __exit__(self, *_args: object) -> None:
                    return None

                def get_user_info(self) -> dict:
                    raise InvalidAccessTokenError("stale access token")

            def ensure_access_token(
                access_token: str,
                **_kwargs: object,
            ) -> str:
                nonlocal refresh_calls
                refresh_calls += 1
                return access_token

            def force_refresh_access_token(
                access_token: str,
                **_kwargs: object,
            ) -> str:
                nonlocal refresh_calls
                refresh_calls += 1
                self.assertTrue(
                    service.schedule_auth_verification(
                        "token-a",
                        "second_verification",
                        expected_access_token="token-a",
                        expected_refresh_token="refresh-a",
                        scope="account",
                    )
                )
                raise RuntimeError("oauth refresh failed")

            with (
                mock.patch.object(
                    service,
                    "_schedule_account_refresh_after_image_failure",
                    return_value=True,
                ),
                mock.patch.object(
                    service,
                    "ensure_access_token",
                    side_effect=ensure_access_token,
                ),
                mock.patch.object(
                    service,
                    "force_refresh_access_token",
                    side_effect=force_refresh_access_token,
                ),
                mock.patch("services.openai_backend_api.OpenAIBackendAPI", Backend),
            ):
                with self.assertRaisesRegex(RuntimeError, "oauth refresh failed"):
                    service.fetch_remote_info("token-a", "first_verification")

            self.assertEqual(refresh_calls, 2)
            account = service.get_account("token-a") or {}
            self.assertEqual(account.get("last_remote_check_result"), "pending")
            self.assertEqual(account.get("last_remote_check_event"), "second_verification")
            self.assertIsNone(account.get("last_remote_check_error"))


if __name__ == "__main__":
    unittest.main()
