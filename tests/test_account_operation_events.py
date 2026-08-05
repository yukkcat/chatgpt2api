from __future__ import annotations

import unittest
from unittest import mock

from api.accounts import _account_mutation_events, _account_operation_progress_for_api
from services.account_operation_events import (
    ACCOUNT_OPERATION_EVENT_LIMIT,
    append_account_operation_event,
    append_account_operation_events,
    normalize_account_operation_events,
    project_account_operation_presentation,
)
from services.account_service import AccountService


class AccountOperationEventContractTests(unittest.TestCase):
    def test_event_projection_is_whitelisted_and_scrubs_credentials(self) -> None:
        events = normalize_account_operation_events(
            [{
                "sequence": 4,
                "timestamp": "2026-07-31T00:00:00+00:00",
                "account_id": "account-1",
                "account_label": "person@example.com",
                "action": "refresh_access_token",
                "status": "failed",
                "message": "Bearer access-secret via http://user:pass@127.0.0.1:7890",
                "access_token": "access-secret",
            }],
            sensitive_values=("access-secret",),
            proxy_values=("http://user:pass@127.0.0.1:7890",),
        )

        self.assertEqual(
            set(events[0]),
            {"sequence", "timestamp", "account_id", "account_label", "action", "status", "tone", "message"},
        )
        self.assertEqual(events[0]["tone"], "danger")
        self.assertNotIn("access-secret", repr(events))
        self.assertNotIn("user:pass", repr(events))

    def test_event_list_keeps_only_the_bounded_tail(self) -> None:
        events: list[dict] = []
        for index in range(ACCOUNT_OPERATION_EVENT_LIMIT + 7):
            events = append_account_operation_event(
                events,
                account_id=f"account-{index}",
                action="sync_account",
                status="success",
                message="synced",
            )

        self.assertEqual(len(events), ACCOUNT_OPERATION_EVENT_LIMIT)
        self.assertEqual(events[0]["sequence"], 8)
        self.assertEqual(events[-1]["sequence"], ACCOUNT_OPERATION_EVENT_LIMIT + 7)

    def test_append_can_reuse_already_normalized_events_without_resanitizing_history(self) -> None:
        existing = normalize_account_operation_events([
            {
                "sequence": index,
                "account_id": f"account-{index}",
                "action": "import_account",
                "status": "info",
                "message": "credentials read",
            }
            for index in range(1, 401)
        ])

        with mock.patch(
            "services.account_operation_events.normalize_account_operation_events",
            wraps=normalize_account_operation_events,
        ) as normalize_history:
            events = append_account_operation_event(
                existing,
                account_id="account-401",
                action="import_account",
                status="success",
                message="saved",
                existing_events_normalized=True,
            )

        normalize_history.assert_not_called()
        self.assertEqual(events[-1]["sequence"], 401)
        self.assertEqual(events[-1]["status"], "success")

    def test_batch_append_normalizes_only_new_events_and_preserves_sequence(self) -> None:
        existing = normalize_account_operation_events([{
            "sequence": 7,
            "account_id": "account-7",
            "action": "import_account",
            "status": "failed",
            "message": "fetch failed",
        }])

        with mock.patch(
            "services.account_operation_events.normalize_account_operation_events",
            wraps=normalize_account_operation_events,
        ) as normalize_history:
            events = append_account_operation_events(
                existing,
                [
                    {
                        "account_id": "account-8",
                        "action": "import_account",
                        "status": "success",
                        "message": "saved access-secret",
                    },
                    {
                        "account_id": "account-9",
                        "action": "import_account",
                        "status": "skipped",
                        "message": "already exists",
                    },
                ],
                sensitive_values=("access-secret",),
                existing_events_normalized=True,
            )

        normalize_history.assert_not_called()
        self.assertEqual([event["sequence"] for event in events], [7, 8, 9])
        self.assertEqual([event["status"] for event in events], ["failed", "success", "skipped"])
        self.assertNotIn("access-secret", repr(events))

    def test_refresh_progress_exposes_real_per_account_event_without_token(self) -> None:
        service = object.__new__(AccountService)
        service.init_refresh_progress("progress-1", 1)
        service.update_refresh_progress(
            "progress-1",
            "access-secret",
            {
                "management_id": "account-1",
                "email": "person@example.com",
                "status": "\u6b63\u5e38",
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
            },
            action="refresh_access_token",
            event_status="success",
            event_message="access-secret refreshed",
        )

        progress = service.get_refresh_progress("progress-1")
        self.assertEqual(progress["processed"], 1)
        self.assertEqual(progress["events"][0]["account_id"], "account-1")
        self.assertEqual(progress["events"][0]["account_label"], "person@example.com")
        self.assertNotIn("access-secret", repr(progress))
        self.assertNotIn("refresh-secret", repr(progress))

    def test_api_progress_projection_keeps_events_at_top_level(self) -> None:
        payload = _account_operation_progress_for_api({
            "total": 1,
            "processed": 1,
            "done": True,
            "events": [{
                "sequence": 1,
                "account_id": "account-1",
                "action": "delete_account",
                "status": "success",
                "message": "deleted",
            }],
            "result": {"removed_ids": ["account-1"]},
        })
        self.assertEqual(payload["events"][0]["action"], "delete_account")
        self.assertEqual(payload["events"][0]["tone"], "success")
        self.assertEqual(payload["result"]["removed_ids"], ["account-1"])
        self.assertEqual(payload["status_label"], "已完成")
        self.assertEqual(payload["tone"], "success")
        self.assertEqual(payload["summary_items"][-1]["value"], 1)

    def test_progress_presentation_projects_partial_failure_and_active_counts(self) -> None:
        active = project_account_operation_presentation({
            "total": 5,
            "processed": 2,
            "done": False,
            "stage_label": "正在同步账号",
        })
        partial = project_account_operation_presentation({
            "total": 2,
            "processed": 2,
            "done": True,
            "result": {
                "refreshed": 1,
                "errors": [{"id": "account-2"}],
                "removed_ids": [],
            },
        })

        self.assertEqual(active["status_label"], "正在同步账号")
        self.assertEqual(active["tone"], "info")
        self.assertEqual([item["value"] for item in active["summary_items"]], [2, 3, 5])
        self.assertEqual(partial["status_label"], "部分完成")
        self.assertEqual(partial["tone"], "warning")
        self.assertEqual(partial["summary_items"][0]["label"], "刷新")
        self.assertIn("失败 1", partial["message"])

    def test_mutation_event_uses_error_code_and_message(self) -> None:
        events = _account_mutation_events(
            action="delete_account",
            errors=[{
                "id": "account-1",
                "code": "account_not_found",
                "message": "account not found",
            }],
            success_message="deleted",
        )
        self.assertEqual(events[0]["status"], "failed")
        self.assertIn("account_not_found", events[0]["message"])
        self.assertIn("account not found", events[0]["message"])


if __name__ == "__main__":
    unittest.main()
