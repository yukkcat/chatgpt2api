from __future__ import annotations

import unittest

from services.realtime_monitor_service import RealtimeMonitorService


class RealtimeMonitorLifecycleTests(unittest.TestCase):
    @staticmethod
    def _success_detail(call_id: str) -> dict[str, object]:
        return {
            "call_id": call_id,
            "endpoint": "/v1/images/generations",
            "model": "gpt-image-2",
            "status": "success",
            "duration_ms": 250,
        }

    @staticmethod
    def _records_for(snapshot: dict[str, object], section: str, call_id: str) -> list[dict[str, object]]:
        records = snapshot.get(section)
        if not isinstance(records, list):
            return []
        return [
            record
            for record in records
            if isinstance(record, dict) and record.get("call_id") == call_id
        ]

    def test_late_stage_does_not_resurrect_finished_call(self) -> None:
        monitor = RealtimeMonitorService()
        call_id = "finished-then-late-stage"
        monitor.start(call_id, endpoint="/v1/images/generations", model="gpt-image-2")
        monitor.finish(self._success_detail(call_id))

        monitor.stage(call_id, "image_generating", index=1, total=1)

        snapshot = monitor.snapshot()
        self.assertEqual(self._records_for(snapshot, "active", call_id), [])
        completed = self._records_for(snapshot, "recent", call_id)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["status"], "success")

    def test_duplicate_finish_keeps_one_completed_record(self) -> None:
        monitor = RealtimeMonitorService()
        call_id = "duplicate-finish"
        monitor.start(call_id, endpoint="/v1/images/generations", model="gpt-image-2")
        monitor.finish(self._success_detail(call_id))

        monitor.finish({
            **self._success_detail(call_id),
            "status": "failed",
            "failure_code": "task_interrupted",
            "status_code": 503,
        })

        completed = self._records_for(monitor.snapshot(), "recent", call_id)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["status"], "success")

    def test_finish_without_start_preserves_text_review_outcome(self) -> None:
        monitor = RealtimeMonitorService()
        call_id = "filtered-before-monitor-start"

        monitor.finish({
            "call_id": call_id,
            "endpoint": "/v1/images/generations",
            "model": "gpt-image-2",
            "status": "failed",
            "duration_ms": 5,
            "failure_code": "content_policy_violation",
            "status_code": 400,
        })

        completed = self._records_for(monitor.snapshot(), "recent", call_id)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["status"], "text_review")
        self.assertEqual(completed[0]["failure_code"], "content_policy_violation")


if __name__ == "__main__":
    unittest.main()
