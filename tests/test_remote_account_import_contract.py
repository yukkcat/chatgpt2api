from __future__ import annotations

import copy
from pathlib import Path
import threading
import tempfile
import time
import unittest
from unittest import mock
from services import account_import_job, cpa_service, sub2api_service
from services.account_import_credentials import collect_import_diagnostic_values
from services.account_import_job import (
    ImportJobCheckpointGate,
    ImportJobFailureAccumulator,
    RemoteAccountImportJob,
    normalize_import_error,
    resolve_import_item_statuses,
)
from services.account_processing import AccountProcessingLimiter


def _database_url(root: Path) -> str:
    return f"sqlite:///{(root / 'app.db').as_posix()}"


def _job(total: int) -> dict:
    return {
        "job_id": "job-1",
        "status": "pending",
        "created_at": "2026-07-31T00:00:00+00:00",
        "updated_at": "2026-07-31T00:00:00+00:00",
        "total": total,
        "completed": 0,
        "added": 0,
        "skipped": 0,
        "synced": 0,
        "failed": 0,
        "errors": [],
    }


class _MemoryImportConfig:
    def __init__(self, normalizer, source_id: str, total: int):
        self._normalizer = normalizer
        self._source_id = source_id
        self._job = normalizer(_job(total), fail_unfinished=False)
        self.writes: list[dict] = []

    def get_import_job(self, source_id: str) -> dict | None:
        if source_id != self._source_id:
            return None
        return copy.deepcopy(self._job)

    def set_import_job(self, source_id: str, import_job: dict | None, *, expected_job_id: str | None = None) -> dict | None:
        if source_id != self._source_id:
            return None
        if expected_job_id is not None and self._job["job_id"] != expected_job_id:
            return None
        self._job = self._normalizer(import_job, fail_unfinished=False)
        self.writes.append(copy.deepcopy(self._job))
        return {"id": source_id, "import_job": copy.deepcopy(self._job)}

    def start_import_job(self, source_id: str, import_job: dict) -> dict | None:
        if source_id != self._source_id:
            return None
        self._job = self._normalizer(import_job, fail_unfinished=False)
        self.writes.append(copy.deepcopy(self._job))
        return {"id": source_id, "import_job": copy.deepcopy(self._job)}


class RemoteAccountImportJobModuleTests(unittest.TestCase):
    def test_shared_module_owns_save_sync_events_and_terminal_projection(self) -> None:
        config = _MemoryImportConfig(
            cpa_service._normalize_import_job,
            "source-1",
            2,
        )
        job = RemoteAccountImportJob(
            config,
            source_id="source-1",
            total=2,
            worker_label="remote import worker",
            error_context=lambda *sources: dict(
                zip(
                    ("sensitive_values", "proxy_values"),
                    collect_import_diagnostic_values(*sources),
                )
            ),
            job_id="job-1",
        )

        self.assertTrue(job.begin())
        self.assertTrue(job.record_fetch("remote-1"))
        self.assertTrue(job.record_fetch("remote-2"))

        with (
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
                return_value={
                    "added": 1,
                    "skipped": 0,
                    "item_results": ["added", "invalid"],
                },
            ),
            mock.patch.object(
                account_import_job.account_service,
                "sync_accounts_and_quota",
                return_value={"synced": 1, "errors": []},
            ),
        ):
            job.finish([
                (
                    "remote-1",
                    {"access_token": "token-1", "email": "one@example.com"},
                ),
                (
                    "remote-2",
                    {"access_token": "token-2", "email": "two@example.com"},
                ),
            ])

        result = config.get_import_job("source-1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["synced"], 1)
        self.assertEqual(result["failed_total"], 1)
        self.assertEqual(
            [(event["account_label"], event["status"]) for event in result["events"]],
            [("one@example.com", "success"), ("two@example.com", "failed")],
        )


class RemoteImportNormalizerTests(unittest.TestCase):
    def test_job_presentation_is_projected_for_frontend_rendering(self) -> None:
        cases = (
            (
                {
                    "status": "running",
                    "stage": "sync_accounts",
                    "total": 10,
                    "completed": 10,
                    "stage_total": 8,
                    "stage_completed": 3,
                    "added": 8,
                    "skipped": 2,
                },
                {
                    "stage_label": "同步账号与额度",
                    "terminal": False,
                    "progress_total": 8,
                    "progress_completed": 3,
                    "status_label": "同步账号与额度",
                    "tone": "info",
                    "result_message": "",
                    "result_tone": "info",
                },
            ),
            (
                {
                    "status": "completed",
                    "total": 10,
                    "completed": 10,
                    "added": 7,
                    "skipped": 2,
                    "synced": 7,
                    "failed_total": 1,
                },
                {
                    "stage_label": "完成",
                    "terminal": True,
                    "progress_total": 10,
                    "progress_completed": 10,
                    "status_label": "部分完成",
                    "tone": "warning",
                    "result_tone": "warning",
                },
            ),
            (
                {
                    "status": "failed",
                    "total": 10,
                    "completed": 4,
                    "errors": [{"stage": "fetch", "error": "远端连接中断"}],
                },
                {
                    "stage_label": "完成",
                    "terminal": True,
                    "progress_total": 10,
                    "progress_completed": 4,
                    "status_label": "失败",
                    "tone": "danger",
                    "error": "远端连接中断",
                    "result_message": "导入失败 · 远端连接中断",
                    "result_tone": "danger",
                },
            ),
        )

        for raw, expected in cases:
            for normalize in (
                cpa_service._normalize_import_job,
                sub2api_service._normalize_import_job,
            ):
                with self.subTest(status=raw["status"], module=normalize.__module__):
                    job = normalize(raw, fail_unfinished=False)
                    for key, value in expected.items():
                        self.assertEqual(job[key], value)
                    self.assertEqual(
                        [item["key"] for item in job["summary_items"]],
                        ["added", "skipped", "synced", "failed"],
                    )

    def test_failure_accumulator_keeps_total_and_newest_details(self) -> None:
        failures = ImportJobFailureAccumulator(
            {
                "failed_total": 25,
                "failed": 25,
                "errors": [
                    {
                        "stage": "fetch",
                        "name": f"account-{index}",
                        "error": f"failed {index}",
                    }
                    for index in range(5, 25)
                ],
            }
        )

        failures.extend(
            {
                "stage": "fetch",
                "name": f"account-{index}",
                "error": f"failed {index}",
            }
            for index in range(25, 32)
        )

        self.assertEqual(failures.total, 32)
        self.assertEqual(len(failures.details), 20)
        self.assertEqual(failures.details[0]["name"], "account-12")
        self.assertEqual(failures.details[-1]["name"], "account-31")

    def test_checkpoint_gate_flushes_after_a_bounded_batch(self) -> None:
        gate = ImportJobCheckpointGate(interval_seconds=60, item_count=3)

        self.assertFalse(gate.mark())
        self.assertFalse(gate.mark())
        self.assertTrue(gate.mark())
        self.assertFalse(gate.mark())

    def test_item_status_projection_preserves_invalid_input_positions(self) -> None:
        self.assertEqual(
            resolve_import_item_statuses(
                {
                    "added": 1,
                    "skipped": 1,
                    "item_results": ["skipped", "invalid", "added"],
                },
                3,
            ),
            ["skipped", "invalid", "added"],
        )

    def test_invalid_default_error_stage_is_projected_as_fetch(self) -> None:
        self.assertEqual(
            normalize_import_error(
                {"stage": "worker", "error": "worker stopped"},
                default_stage="worker",
            )["stage"],
            "fetch",
        )

    def test_collects_remote_import_secrets_and_proxy_context(self) -> None:
        sensitive_values, proxy_values = collect_import_diagnostic_values(
            {
                "secret_key": "cpa-secret",
                "password": "server-password",
                "apiKey": "server-api-key",
                "proxy_username": "proxy-user",
                "proxy_password": "proxy-password",
                "credentials": (
                    '{"accessToken":"access","refresh_token":"refresh",'
                    '"idToken":"id"}'
                ),
                "proxy_url": "http://proxy-user:proxy-pass@127.0.0.1:7890",
            }
        )

        self.assertEqual(
            sensitive_values,
            (
                "cpa-secret",
                "server-password",
                "server-api-key",
                "proxy-user",
                "proxy-password",
                "access",
                "refresh",
                "id",
            ),
        )
        self.assertEqual(
            proxy_values,
            ("http://proxy-user:proxy-pass@127.0.0.1:7890",),
        )

    def test_source_browser_errors_are_sanitized_before_return(self) -> None:
        proxy_url = "http://proxy-user:proxy-pass@127.0.0.1:7890"
        with (
            mock.patch.object(
                cpa_service.proxy_settings,
                "build_session_kwargs",
                return_value={"verify": True, "proxy": proxy_url},
            ),
            mock.patch.object(
                cpa_service,
                "Session",
                side_effect=RuntimeError(f"cpa-secret {proxy_url}"),
            ),
            self.assertRaises(RuntimeError) as cpa_error,
        ):
            cpa_service.list_remote_files({
                "base_url": "https://cpa.example",
                "secret_key": "cpa-secret",
            })

        self.assertNotIn("cpa-secret", str(cpa_error.exception))
        self.assertNotIn("proxy-user", str(cpa_error.exception))
        self.assertNotIn("proxy-pass", str(cpa_error.exception))

        server = {
            "id": "server-1",
            "base_url": "https://sub2api.example",
            "api_key": "server-api-key",
        }
        sub2api_service._token_cache["server-1"] = (
            "server-login-token",
            time.time() + 3600,
        )
        try:
            with (
                mock.patch.object(
                    sub2api_service,
                    "Session",
                    side_effect=RuntimeError(
                        "server-api-key server-login-token"
                    ),
                ),
                self.assertRaises(RuntimeError) as sub2api_error,
            ):
                sub2api_service.list_remote_accounts(server)
        finally:
            sub2api_service._token_cache.pop("server-1", None)

        self.assertNotIn("server-api-key", str(sub2api_error.exception))
        self.assertNotIn("server-login-token", str(sub2api_error.exception))

    def test_failed_total_is_preserved_when_error_details_are_bounded(self) -> None:
        for normalize in (
            cpa_service._normalize_import_job,
            sub2api_service._normalize_import_job,
        ):
            with self.subTest(module=normalize.__module__):
                job = normalize(
                    {
                        "status": "failed",
                        "failed_total": 25,
                        "errors": [
                            {
                                "stage": "sync",
                                "name": f"account-{index}",
                                "error": f"sync failed {index}",
                            }
                            for index in range(25)
                        ],
                    },
                    fail_unfinished=False,
                )

                self.assertEqual(job["failed"], 25)
                self.assertEqual(job["failed_total"], 25)
                self.assertEqual(len(job["errors"]), 20)
                self.assertEqual(job["errors"][0]["name"], "account-5")
                self.assertEqual(job["errors"][-1]["name"], "account-24")

    def test_failed_job_preserves_actual_stage_progress(self) -> None:
        for normalize in (
            cpa_service._normalize_import_job,
            sub2api_service._normalize_import_job,
        ):
            with self.subTest(module=normalize.__module__):
                job = normalize(
                    {
                        "status": "failed",
                        "stage": "completed",
                        "total": 100,
                        "completed": 7,
                        "stage_total": 100,
                        "stage_completed": 7,
                    },
                    fail_unfinished=False,
                )

                self.assertEqual(job["completed"], 7)
                self.assertEqual(job["stage_completed"], 7)

    def test_error_total_keeps_growing_after_details_are_compacted(self) -> None:
        cases = (
            (
                cpa_service._normalize_import_job,
                "pool-1",
            ),
            (
                sub2api_service._normalize_import_job,
                "server-1",
            ),
        )
        for normalize, source_id in cases:
            with self.subTest(normalizer=normalize.__module__):
                config = _MemoryImportConfig(normalize, source_id, 100)
                existing_errors = [
                    {
                        "stage": "fetch",
                        "name": f"account-{index}",
                        "error": f"failed {index}",
                    }
                    for index in range(12, 32)
                ]
                config.set_import_job(
                    source_id,
                    {
                        **_job(100),
                        "status": "running",
                        "failed": 32,
                        "failed_total": 32,
                        "errors": existing_errors,
                    },
                )

                import_job = RemoteAccountImportJob(
                    config,
                    source_id=source_id,
                    total=100,
                    worker_label="remote import worker",
                    error_context=lambda *sources: {
                        "sensitive_values": (),
                        "proxy_values": (),
                    },
                    job_id="job-1",
                )
                import_job.update(
                    failed=len(existing_errors) + 1,
                    errors=[
                        *existing_errors,
                        {
                            "stage": "fetch",
                            "name": "account-32",
                            "error": "failed 32",
                        },
                    ],
                )

                job = config.get_import_job(source_id)
                self.assertEqual(job["failed"], 33)
                self.assertEqual(job["failed_total"], 33)
                self.assertEqual(len(job["errors"]), 20)
                self.assertEqual(job["errors"][-1]["name"], "account-32")

    def test_known_credentials_are_removed_from_error_projection(self) -> None:
        job = cpa_service._normalize_import_job(
            {
                "status": "failed",
                "errors": [{
                    "name": "access-secret",
                    "error": (
                        "secret=cpa-secret access=access-secret "
                        "refresh=refresh-secret id=id-secret via "
                        "http://proxy-user:proxy-pass@127.0.0.1:7890"
                    ),
                }],
            },
            fail_unfinished=False,
            sensitive_values=(
                "cpa-secret",
                "access-secret",
                "refresh-secret",
                "id-secret",
            ),
            proxy_values=("http://proxy-user:proxy-pass@127.0.0.1:7890",),
        )

        serialized = repr(job)
        for secret in (
            "cpa-secret",
            "access-secret",
            "refresh-secret",
            "id-secret",
            "proxy-user",
            "proxy-pass",
        ):
            self.assertNotIn(secret, serialized)
        self.assertEqual(job["errors"][0]["name"], "[credential]")

    def test_generator_context_is_applied_to_every_error_field(self) -> None:
        job = cpa_service._normalize_import_job(
            {
                "status": "failed",
                "errors": [
                    {"name": "first-secret", "error": "first-secret"},
                    {"name": "second", "error": "first-secret"},
                ],
            },
            fail_unfinished=False,
            sensitive_values=(value for value in ("first-secret",)),
        )

        self.assertNotIn("first-secret", repr(job))

    def test_config_normalizers_scrub_legacy_persisted_import_errors(self) -> None:
        raw_job = {
            "status": "failed",
            "errors": [{"error": "remote rejected known-secret"}],
        }

        pool = cpa_service._normalize_pool({
            "secret_key": "known-secret",
            "import_job": raw_job,
        })
        server = sub2api_service._normalize_server({
            "password": "known-secret",
            "api_key": "known-api-key",
            "import_job": {
                "status": "failed",
                "errors": [{"error": "known-secret known-api-key"}],
            },
        })

        self.assertNotIn("known-secret", repr(pool["import_job"]))
        self.assertNotIn("known-secret", repr(server["import_job"]))
        self.assertNotIn("known-api-key", repr(server["import_job"]))


class RemoteImportSingleFlightTests(unittest.TestCase):
    def _assert_only_one_job_starts(self, config, source_id: str) -> None:
        barrier = threading.Barrier(3)
        accepted: list[str] = []
        rejected: list[str] = []
        result_lock = threading.Lock()

        def start(job_id: str) -> None:
            job = {**_job(1), "job_id": job_id}
            barrier.wait()
            try:
                config.start_import_job(source_id, job)
            except ValueError:
                with result_lock:
                    rejected.append(job_id)
            else:
                with result_lock:
                    accepted.append(job_id)

        workers = [
            threading.Thread(target=start, args=(job_id,))
            for job_id in ("job-a", "job-b")
        ]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(2)

        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(config.get_import_job(source_id)["job_id"], accepted[0])

    def test_cpa_pool_allows_only_one_active_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = cpa_service.CPAConfig(database_url=_database_url(Path(temp_dir)))
            pool = config.add_pool(
                name="CPA",
                base_url="https://cpa.example",
                secret_key="secret",
            )

            self._assert_only_one_job_starts(config, pool["id"])

    def test_sub2api_server_allows_only_one_active_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = sub2api_service.Sub2APIConfig(database_url=_database_url(Path(temp_dir)))
            server = config.add_server(
                name="Sub2API",
                base_url="https://sub2api.example",
                email="",
                password="",
                api_key="key",
            )

            self._assert_only_one_job_starts(config, server["id"])

    def test_active_import_source_cannot_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cases = []
            cpa_config = cpa_service.CPAConfig(database_url=_database_url(Path(temp_dir)))
            pool = cpa_config.add_pool(
                name="CPA",
                base_url="https://cpa.example",
                secret_key="secret",
            )
            cases.append((cpa_config, pool["id"], cpa_config.delete_pool))

            sub2api_config = sub2api_service.Sub2APIConfig(database_url=_database_url(Path(temp_dir)))
            server = sub2api_config.add_server(
                name="Sub2API",
                base_url="https://sub2api.example",
                email="",
                password="",
                api_key="key",
            )
            cases.append((sub2api_config, server["id"], sub2api_config.delete_server))

            for config, source_id, delete_source in cases:
                with self.subTest(source_id=source_id):
                    config.start_import_job(source_id, _job(1))
                    with self.assertRaisesRegex(ValueError, "import job is active"):
                        delete_source(source_id)
                    self.assertEqual(config.get_import_job(source_id)["job_id"], "job-1")

    def test_active_import_source_cannot_be_edited(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cpa_config = cpa_service.CPAConfig(database_url=_database_url(Path(temp_dir)))
            pool = cpa_config.add_pool(
                name="CPA",
                base_url="https://cpa.example",
                secret_key="secret",
            )
            cpa_config.start_import_job(pool["id"], _job(1))
            with self.assertRaisesRegex(ValueError, "import job is active"):
                cpa_config.update_pool(pool["id"], {"name": "CPA updated"})

            sub2api_config = sub2api_service.Sub2APIConfig(database_url=_database_url(Path(temp_dir)))
            server = sub2api_config.add_server(
                name="Sub2API",
                base_url="https://sub2api.example",
                email="",
                password="",
                api_key="key",
            )
            sub2api_config.start_import_job(server["id"], _job(1))
            sub2api_service._token_cache[server["id"]] = (
                "cached-token",
                time.time() + 3600,
            )
            try:
                with self.assertRaisesRegex(ValueError, "import job is active"):
                    sub2api_config.update_server(
                        server["id"],
                        {"name": "Sub2API updated"},
                    )
                self.assertEqual(
                    sub2api_service._token_cache.get(server["id"]),
                    ("cached-token", mock.ANY),
                )
            finally:
                sub2api_service._token_cache.pop(server["id"], None)

            for config, source_id, expected_name in (
                (cpa_config, pool["id"], "CPA"),
                (sub2api_config, server["id"], "Sub2API"),
            ):
                with self.subTest(source_id=source_id):
                    source = (
                        config.get_pool(source_id)
                        if config is cpa_config
                        else config.get_server(source_id)
                    )
                    job = source["import_job"]
                    self.assertEqual(source["name"], expected_name)
                    self.assertEqual(job["job_id"], "job-1")
                    self.assertEqual(job["status"], "pending")

    def test_stale_worker_cannot_overwrite_a_newer_import_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cpa_config = cpa_service.CPAConfig(database_url=_database_url(Path(temp_dir)))
            pool = cpa_config.add_pool(
                name="CPA",
                base_url="https://cpa.example",
                secret_key="secret",
            )
            sub2api_config = sub2api_service.Sub2APIConfig(
                database_url=_database_url(Path(temp_dir))
            )
            server = sub2api_config.add_server(
                name="Sub2API",
                base_url="https://sub2api.example",
                email="",
                password="",
                api_key="key",
            )

            for config, source_id in (
                (cpa_config, pool["id"]),
                (sub2api_config, server["id"]),
            ):
                with self.subTest(source_id=source_id):
                    config.start_import_job(source_id, _job(1))
                    newer_job = {
                        **_job(1),
                        "job_id": "job-2",
                        "status": "running",
                    }
                    config.set_import_job(source_id, newer_job)

                    stale_result = config.set_import_job(
                        source_id,
                        {**_job(1), "status": "completed"},
                        expected_job_id="job-1",
                    )

                    self.assertIsNone(stale_result)
                    self.assertEqual(
                        config.get_import_job(source_id)["job_id"],
                        "job-2",
                    )

    def test_stale_worker_stops_before_remote_fetch(self) -> None:
        cpa_config = _MemoryImportConfig(
            cpa_service._normalize_import_job,
            "pool-1",
            1,
        )
        cpa_service_instance = cpa_service.CPAImportService(cpa_config)
        cpa_config.set_import_job(
            "pool-1",
            {**_job(1), "job_id": "job-2", "status": "running"},
        )
        with mock.patch.object(cpa_service, "fetch_remote_account_payload") as fetch:
            cpa_service_instance._run_import(
                "pool-1",
                {},
                ["account.json"],
                job_id="job-1",
            )
        fetch.assert_not_called()
        self.assertEqual(cpa_config.get_import_job("pool-1")["job_id"], "job-2")

        sub2_config = _MemoryImportConfig(
            sub2api_service._normalize_import_job,
            "server-1",
            1,
        )
        sub2_service = sub2api_service.Sub2APIImportService(sub2_config)
        sub2_config.set_import_job(
            "server-1",
            {**_job(1), "job_id": "job-2", "status": "running"},
        )
        with mock.patch.object(sub2api_service, "_fetch_access_tokens_for_accounts") as fetch:
            sub2_service._run_import("server-1", {}, ["account"], {}, job_id="job-1")
        fetch.assert_not_called()
        self.assertEqual(sub2_config.get_import_job("server-1")["job_id"], "job-2")

    def test_cpa_worker_losing_ownership_does_not_store_accounts(self) -> None:
        config = _MemoryImportConfig(
            cpa_service._normalize_import_job,
            "pool-1",
            1,
        )
        service = cpa_service.CPAImportService(config)

        def replace_job(_pool: dict, _file_name: str):
            config.set_import_job(
                "pool-1",
                {**_job(1), "job_id": "job-2", "status": "running"},
            )
            return {"access_token": "account-token"}, None

        with (
            mock.patch.object(
                cpa_service,
                "fetch_remote_account_payload",
                side_effect=replace_job,
            ) as fetch_remote,
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
            ) as add_accounts,
        ):
            service._run_import("pool-1", {}, ["account.json"], job_id="job-1")
        fetch_remote.assert_called_once()
        add_accounts.assert_not_called()
        self.assertEqual(config.get_import_job("pool-1")["job_id"], "job-2")


    def test_sub2api_worker_losing_ownership_does_not_store_accounts(self) -> None:
        config = _MemoryImportConfig(
            sub2api_service._normalize_import_job,
            "server-1",
            1,
        )
        service = sub2api_service.Sub2APIImportService(config)

        def replace_job(_server: dict, _account_ids: list[str]):
            config.set_import_job(
                "server-1",
                {**_job(1), "job_id": "job-2", "status": "running"},
            )
            return {"account": ("account-token", {})}, {}

        with (
            mock.patch.object(
                sub2api_service,
                "_fetch_access_tokens_for_accounts",
                side_effect=replace_job,
            ) as fetch_remote,
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
            ) as add_accounts,
        ):
            service._run_import(
                "server-1", {}, ["account"], {}, job_id="job-1"
            )

        fetch_remote.assert_called_once()
        add_accounts.assert_not_called()
        self.assertEqual(config.get_import_job("server-1")["job_id"], "job-2")

    def test_cpa_stale_failure_does_not_mutate_newer_job(self) -> None:
        config = _MemoryImportConfig(
            cpa_service._normalize_import_job,
            "pool-1",
            1,
        )
        service = cpa_service.CPAImportService(config)

        def replace_job(_pool: dict, _file_name: str):
            config.set_import_job(
                "pool-1",
                {**_job(1), "job_id": "job-2", "status": "running"},
            )
            return None, "download failed"

        with mock.patch.object(
            cpa_service,
            "fetch_remote_account_payload",
            side_effect=replace_job,
        ):
            service._run_import("pool-1", {}, ["account.json"], job_id="job-1")

        result = config.get_import_job("pool-1")

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["errors"], [])

    def test_sub2api_stale_failure_does_not_mutate_newer_job(self) -> None:
        config = _MemoryImportConfig(
            sub2api_service._normalize_import_job,
            "server-1",
            1,
        )
        service = sub2api_service.Sub2APIImportService(config)

        def replace_job(_server: dict, _account_ids: list[str]):
            config.set_import_job(
                "server-1",
                {**_job(1), "job_id": "job-2", "status": "running"},
            )
            return {}, {"account": "batch failed"}

        with (
            mock.patch.object(
                sub2api_service,
                "_fetch_access_tokens_for_accounts",
                side_effect=replace_job,
            ),
            mock.patch.object(
                sub2api_service,
                "_fetch_access_token_for_account",
                side_effect=RuntimeError("fallback failed"),
            ),
        ):
            service._run_import(
                "server-1", {}, ["account"], {}, job_id="job-1"
            )

        result = config.get_import_job("server-1")
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["errors"], [])
    def test_cpa_thread_start_failure_finishes_pending_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = cpa_service.CPAConfig(database_url=_database_url(Path(temp_dir)))
            pool = config.add_pool(
                name="CPA",
                base_url="https://cpa.example",
                secret_key="known-secret",
            )
            service = cpa_service.CPAImportService(config)

            with (
                mock.patch.object(
                    account_import_job.threading.Thread,
                    "start",
                    side_effect=RuntimeError("thread unavailable"),
                ),
                self.assertRaisesRegex(RuntimeError, "thread unavailable"),
            ):
                service.start_import(pool, ["account.json"])

            job = config.get_import_job(pool["id"])
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["failed"], 1)
            self.assertEqual(job["events"][-1]["status"], "failed")
            self.assertNotIn("known-secret", repr(job))

    def test_sub2api_thread_start_failure_finishes_pending_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = sub2api_service.Sub2APIConfig(database_url=_database_url(Path(temp_dir)))
            server = config.add_server(
                name="Sub2API",
                base_url="https://sub2api.example",
                email="",
                password="known-password",
                api_key="known-api-key",
            )
            service = sub2api_service.Sub2APIImportService(config)

            with (
                mock.patch.object(
                    account_import_job.threading.Thread,
                    "start",
                    side_effect=RuntimeError("thread unavailable"),
                ),
                self.assertRaisesRegex(RuntimeError, "thread unavailable"),
            ):
                service.start_import(
                    server,
                    ["account"],
                    create_account_groups=False,
                )

            job = config.get_import_job(server["id"])
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["failed"], 1)
            self.assertEqual(job["events"][-1]["status"], "failed")
            self.assertNotIn("known-password", repr(job))
            self.assertNotIn("known-api-key", repr(job))

    def test_cpa_worker_exception_finishes_running_job(self) -> None:
        config = _MemoryImportConfig(
            cpa_service._normalize_import_job,
            "pool-1",
            1,
        )
        service = cpa_service.CPAImportService(config)
        pool = {"secret_key": "known-secret"}

        with mock.patch.object(
            service,
            "_run_import",
            side_effect=RuntimeError("known-secret worker crashed"),
        ):
            service._run_import_guarded(
                "pool-1",
                pool,
                ["account.json"],
                job_id="job-1",
            )

        result = config.get_import_job("pool-1")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["errors"][0]["stage"], "fetch")
        self.assertEqual(result["events"][-1]["status"], "failed")
        self.assertNotIn("known-secret", repr(result))

    def test_sub2api_worker_exception_finishes_running_job(self) -> None:
        config = _MemoryImportConfig(
            sub2api_service._normalize_import_job,
            "server-1",
            1,
        )
        service = sub2api_service.Sub2APIImportService(config)
        server = {
            "id": "server-1",
            "password": "known-password",
            "api_key": "known-api-key",
        }

        with mock.patch.object(
            service,
            "_run_import",
            side_effect=RuntimeError("known-api-key worker crashed"),
        ):
            service._run_import_guarded(
                "server-1",
                server,
                ["account"],
                {},
                job_id="job-1",
            )

        result = config.get_import_job("server-1")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["events"][-1]["status"], "failed")
        self.assertNotIn("known-password", repr(result))
        self.assertNotIn("known-api-key", repr(result))

    def test_sub2api_reserves_job_before_creating_local_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = sub2api_service.Sub2APIConfig(database_url=_database_url(Path(temp_dir)))
            server = config.add_server(
                name="Sub2API",
                base_url="https://sub2api.example",
                email="",
                password="",
                api_key="key",
            )
            config.start_import_job(server["id"], _job(1))
            service = sub2api_service.Sub2APIImportService(config)

            with (
                mock.patch.object(
                    sub2api_service,
                    "_build_local_group_bindings",
                ) as build_groups,
                self.assertRaisesRegex(ValueError, "already running"),
            ):
                service.start_import(
                    server,
                    ["account"],
                    group_bindings=[{
                        "remote_group_id": "remote",
                        "name": "Remote",
                        "account_ids": ["account"],
                    }],
                )

            build_groups.assert_not_called()

    def test_sub2api_group_mapping_failure_finishes_reserved_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = sub2api_service.Sub2APIConfig(database_url=_database_url(Path(temp_dir)))
            server = config.add_server(
                name="Sub2API",
                base_url="https://sub2api.example",
                email="",
                password="",
                api_key="key",
            )
            service = sub2api_service.Sub2APIImportService(config)

            with (
                mock.patch.object(
                    sub2api_service,
                    "_build_local_group_bindings",
                    side_effect=RuntimeError("group mapping failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "group mapping failed"),
            ):
                service.start_import(
                    server,
                    ["account"],
                    group_bindings=[],
                )

            job = config.get_import_job(server["id"])
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["failed"], 1)
            self.assertEqual(job["events"][-1]["status"], "failed")


class CPAImportResultContractTests(unittest.TestCase):
    def test_worker_keeps_total_when_all_fetch_error_details_are_bounded(self) -> None:
        names = [f"account-{index}" for index in range(25)]
        config = _MemoryImportConfig(
            cpa_service._normalize_import_job,
            "pool-1",
            len(names),
        )
        service = cpa_service.CPAImportService(config)

        def fail_fetch(_pool: dict, name: str):
            time.sleep(0.001)
            return None, f"fetch failed for {name}"

        with (
            mock.patch.object(
                cpa_service,
                "account_processing_worker_count",
                return_value=1,
            ),
            mock.patch.object(
                cpa_service,
                "fetch_remote_account_payload",
                side_effect=fail_fetch,
            ),
        ):
            service._run_import("pool-1", {}, names, job_id="job-1")

        result = config.get_import_job("pool-1")
        self.assertEqual(result["failed"], 25)
        self.assertEqual(result["failed_total"], 25)
        self.assertEqual(len(result["errors"]), 20)
        self.assertEqual(result["errors"][0]["name"], "account-5")
        self.assertEqual(result["errors"][-1]["name"], "account-24")

    def test_invalid_account_is_failed_and_not_synced(self) -> None:
        config = _MemoryImportConfig(cpa_service._normalize_import_job, "pool-1", 1)
        service = cpa_service.CPAImportService(config)

        with (
            mock.patch.object(
                cpa_service,
                "fetch_remote_account_payload",
                return_value=({"access_token": "invalid-token"}, None),
            ),
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
                return_value={
                    "added": 0,
                    "skipped": 0,
                    "item_results": ["invalid"],
                },
            ),
            mock.patch.object(
                account_import_job.account_service,
                "sync_accounts_and_quota",
            ) as sync_accounts,
        ):
            service._run_import("pool-1", {}, ["invalid.json"])

        result = config.get_import_job("pool-1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["errors"][0]["name"], "invalid.json")
        self.assertEqual(result["events"][-1]["status"], "failed")
        sync_accounts.assert_not_called()

    def test_large_import_checkpoints_progress_in_batches(self) -> None:
        names = [f"account-{index}.json" for index in range(55)]
        config = _MemoryImportConfig(cpa_service._normalize_import_job, "pool-1", len(names))
        service = cpa_service.CPAImportService(config)

        with (
            mock.patch.object(
                account_import_job,
                "ImportJobCheckpointGate",
                side_effect=lambda: ImportJobCheckpointGate(
                    interval_seconds=60,
                    item_count=20,
                ),
            ),
            mock.patch.object(
                cpa_service,
                "fetch_remote_account_payload",
                side_effect=lambda _pool, name: ({"access_token": f"token-{name}"}, None),
            ),
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
                return_value={"added": len(names), "skipped": 0},
            ),
            mock.patch.object(
                account_import_job.account_service,
                "sync_accounts_and_quota",
                return_value={"synced": len(names), "errors": []},
            ),
        ):
            service._run_import("pool-1", {}, names)

        self.assertLess(len(config.writes), 12)
        self.assertEqual(config.get_import_job("pool-1")["completed"], len(names))

    def test_remote_fetches_use_configured_parallelism(self) -> None:
        config = _MemoryImportConfig(cpa_service._normalize_import_job, "pool-1", 4)
        service = cpa_service.CPAImportService(config)
        lock = threading.Lock()
        release = threading.Event()
        two_entered = threading.Event()
        active = 0
        maximum = 0

        def fetch(_pool: dict, name: str):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
                if active == 2:
                    two_entered.set()
            try:
                self.assertTrue(release.wait(2))
                return {"access_token": f"token-{name}"}, None
            finally:
                with lock:
                    active -= 1

        with (
            mock.patch(
                "services.config.ConfigStore.account_processing_concurrency",
                new_callable=mock.PropertyMock,
                return_value=2,
            ),
            mock.patch(
                "services.account_processing.account_processing_limiter",
                AccountProcessingLimiter(),
            ),
            mock.patch.object(cpa_service, "fetch_remote_account_payload", side_effect=fetch),
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
                return_value={"added": 4, "skipped": 0},
            ),
            mock.patch.object(
                account_import_job.account_service,
                "sync_accounts_and_quota",
                return_value={"synced": 4, "errors": []},
            ),
        ):
            worker = threading.Thread(
                target=service._run_import,
                args=("pool-1", {}, ["a", "b", "c", "d"]),
            )
            worker.start()
            self.assertTrue(two_entered.wait(1))
            time.sleep(0.05)
            self.assertEqual(maximum, 2)
            release.set()
            worker.join(3)

        self.assertFalse(worker.is_alive())
        self.assertEqual(config.get_import_job("pool-1")["status"], "completed")

    def test_partial_fetch_and_sync_errors_complete_with_one_error_shape(self) -> None:
        config = _MemoryImportConfig(cpa_service._normalize_import_job, "pool-1", 2)
        service = cpa_service.CPAImportService(config)

        def fetch(_pool: dict, name: str):
            if name == "good.json":
                return {
                    "access_token": "good-token",
                    "source_type": "codex",
                    "email": "good@example.com",
                }, None
            return None, "download failed"

        with (
            mock.patch.object(cpa_service, "fetch_remote_account_payload", side_effect=fetch),
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
                return_value={
                    "added": 1,
                    "skipped": 0,
                    "item_results": ["added"],
                },
            ),
            mock.patch.object(
                account_import_job.account_service,
                "sync_accounts_and_quota",
                return_value={
                    "synced": 0,
                    "errors": [{
                        "token": "good...oken",
                        "account_id": "local-good",
                        "account_label": "good@example.com",
                        "error": "quota failed",
                    }],
                },
            ),
        ):
            service._run_import("pool-1", {}, ["good.json", "bad.json"])

        result = config.get_import_job("pool-1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["failed"], 2)
        self.assertEqual(result["errors"], [
            {"stage": "fetch", "name": "bad.json", "error": "download failed"},
            {"stage": "sync", "name": "good...oken", "error": "quota failed"},
        ])
        self.assertTrue(result["events"])
        self.assertTrue(all(event["action"] == "import_account" for event in result["events"]))
        self.assertTrue(any(event["status"] == "failed" for event in result["events"]))
        read_events = [
            event
            for job in config.writes
            if job["stage"] == "read_credentials"
            for event in job["events"]
        ]
        self.assertTrue(all(event["status"] == "failed" for event in read_events))
        self.assertFalse(
            any("\u8d26\u53f7\u51ed\u636e\u5df2\u8bfb\u53d6" in event["message"] for event in result["events"])
        )
        self.assertTrue(
            any(
                event["account_id"] == "good.json"
                and event["account_label"] == "good@example.com"
                and event["status"] == "success"
                and event["message"] == "\u8d26\u53f7\u5bfc\u5165\u6210\u529f"
                for event in result["events"]
            )
        )
        self.assertTrue(
            any(
                event["account_id"] == "local-good"
                and event["account_label"] == "good@example.com"
                and event["status"] == "failed"
                for event in result["events"]
            )
        )

    def test_no_usable_payload_fails_the_job(self) -> None:
        config = _MemoryImportConfig(cpa_service._normalize_import_job, "pool-1", 1)
        service = cpa_service.CPAImportService(config)

        with mock.patch.object(
            cpa_service,
            "fetch_remote_account_payload",
            return_value=(None, "missing access_token"),
        ):
            service._run_import("pool-1", {}, ["bad.json"])

        result = config.get_import_job("pool-1")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["errors"][0]["stage"], "fetch")

    def test_local_account_write_failure_finishes_the_job_as_failed(self) -> None:
        config = _MemoryImportConfig(cpa_service._normalize_import_job, "pool-1", 2)
        service = cpa_service.CPAImportService(config)

        with (
            mock.patch.object(
                cpa_service,
                "fetch_remote_account_payload",
                side_effect=lambda _pool, name: (
                    {"access_token": f"token-{name}"},
                    None,
                ),
            ),
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
                side_effect=RuntimeError("storage unavailable"),
            ),
        ):
            service._run_import("pool-1", {}, ["first.json", "second.json"])

        result = config.get_import_job("pool-1")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["completed"], 2)
        self.assertEqual(result["failed"], 2)
        self.assertEqual(
            {error["name"] for error in result["errors"]},
            {"first.json", "second.json"},
        )
        self.assertTrue(all(error["stage"] == "sync" for error in result["errors"]))
        self.assertTrue(all(error["error"] == "storage unavailable" for error in result["errors"]))
        self.assertEqual(
            {
                event["account_id"]
                for event in result["events"]
                if event["status"] == "failed"
            },
            {"first.json", "second.json"},
        )

    def test_fetch_and_sync_errors_do_not_persist_known_credentials(self) -> None:
        config = _MemoryImportConfig(cpa_service._normalize_import_job, "pool-1", 2)
        service = cpa_service.CPAImportService(config)
        pool = {"secret_key": "cpa-secret"}
        payload = {
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "id_token": "id-secret",
        }

        def fetch(_pool: dict, name: str):
            if name == "good.json":
                return dict(payload), None
            return None, (
                "cpa-secret via "
                "http://proxy-user:proxy-pass@127.0.0.1:7890"
            )

        with (
            mock.patch.object(cpa_service, "fetch_remote_account_payload", side_effect=fetch),
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
                return_value={"added": 1, "skipped": 0},
            ),
            mock.patch.object(
                account_import_job.account_service,
                "sync_accounts_and_quota",
                return_value={
                    "synced": 0,
                    "errors": [{
                        "name": "access-secret",
                        "error": "access-secret refresh-secret id-secret",
                    }],
                },
            ),
        ):
            service._run_import("pool-1", pool, ["good.json", "bad.json"])

        serialized = repr(config.get_import_job("pool-1"))
        for secret in (
            "cpa-secret",
            "access-secret",
            "refresh-secret",
            "id-secret",
            "proxy-user",
            "proxy-pass",
        ):
            self.assertNotIn(secret, serialized)


class Sub2APIImportResultContractTests(unittest.TestCase):
    def test_worker_keeps_total_when_all_fetch_error_details_are_bounded(self) -> None:
        account_ids = [f"account-{index}" for index in range(25)]
        config = _MemoryImportConfig(
            sub2api_service._normalize_import_job,
            "server-1",
            len(account_ids),
        )
        service = sub2api_service.Sub2APIImportService(config)

        def fail_fetch(_server: dict, account_id: str):
            time.sleep(0.001)
            raise RuntimeError(f"fetch failed for {account_id}")

        with (
            mock.patch.object(
                sub2api_service,
                "account_processing_worker_count",
                return_value=1,
            ),
            mock.patch.object(
                sub2api_service,
                "_fetch_access_tokens_for_accounts",
                return_value=({}, {}),
            ),
            mock.patch.object(
                sub2api_service,
                "_fetch_access_token_for_account",
                side_effect=fail_fetch,
            ),
        ):
            service._run_import(
                "server-1",
                {},
                account_ids,
                {},
                job_id="job-1",
            )

        result = config.get_import_job("server-1")
        self.assertEqual(result["failed"], 25)
        self.assertEqual(result["failed_total"], 25)
        self.assertEqual(len(result["errors"]), 20)
        self.assertEqual(result["errors"][0]["name"], "account-5")
        self.assertEqual(result["errors"][-1]["name"], "account-24")

    def test_invalid_account_is_failed_and_not_synced(self) -> None:
        config = _MemoryImportConfig(sub2api_service._normalize_import_job, "server-1", 1)
        service = sub2api_service.Sub2APIImportService(config)

        with (
            mock.patch.object(
                sub2api_service,
                "_fetch_access_tokens_for_accounts",
                return_value=({"invalid": ("invalid-token", {})}, {}),
            ),
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
                return_value={
                    "added": 0,
                    "skipped": 0,
                    "item_results": ["invalid"],
                },
            ),
            mock.patch.object(
                account_import_job.account_service,
                "sync_accounts_and_quota",
            ) as sync_accounts,
        ):
            service._run_import("server-1", {}, ["invalid"], {})

        result = config.get_import_job("server-1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["errors"][0]["name"], "invalid")
        self.assertEqual(result["events"][-1]["status"], "failed")
        sync_accounts.assert_not_called()

    def test_large_import_checkpoints_progress_in_batches(self) -> None:
        account_ids = [f"account-{index}" for index in range(55)]
        config = _MemoryImportConfig(
            sub2api_service._normalize_import_job,
            "server-1",
            len(account_ids),
        )
        service = sub2api_service.Sub2APIImportService(config)
        batch_results = {
            account_id: (f"token-{account_id}", {})
            for account_id in account_ids
        }

        with (
            mock.patch.object(
                account_import_job,
                "ImportJobCheckpointGate",
                side_effect=lambda: ImportJobCheckpointGate(
                    interval_seconds=60,
                    item_count=20,
                ),
            ),
            mock.patch.object(
                sub2api_service,
                "_fetch_access_tokens_for_accounts",
                return_value=(batch_results, {}),
            ),
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
                return_value={"added": len(account_ids), "skipped": 0},
            ),
            mock.patch.object(
                account_import_job.account_service,
                "sync_accounts_and_quota",
                return_value={"synced": len(account_ids), "errors": []},
            ),
        ):
            service._run_import("server-1", {}, account_ids, {})

        self.assertLess(len(config.writes), 12)
        self.assertEqual(config.get_import_job("server-1")["completed"], len(account_ids))

    def test_fallback_fetches_use_configured_parallelism(self) -> None:
        account_ids = ["a", "b", "c", "d"]
        config = _MemoryImportConfig(
            sub2api_service._normalize_import_job,
            "server-1",
            len(account_ids),
        )
        service = sub2api_service.Sub2APIImportService(config)
        lock = threading.Lock()
        release = threading.Event()
        two_entered = threading.Event()
        active = 0
        maximum = 0

        def fetch(_server: dict, account_id: str):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
                if active == 2:
                    two_entered.set()
            try:
                self.assertTrue(release.wait(2))
                return f"token-{account_id}", {}
            finally:
                with lock:
                    active -= 1

        with (
            mock.patch(
                "services.config.ConfigStore.account_processing_concurrency",
                new_callable=mock.PropertyMock,
                return_value=2,
            ),
            mock.patch(
                "services.account_processing.account_processing_limiter",
                AccountProcessingLimiter(),
            ),
            mock.patch.object(
                sub2api_service,
                "_fetch_access_tokens_for_accounts",
                return_value=({}, {account_id: "batch skipped" for account_id in account_ids}),
            ),
            mock.patch.object(
                sub2api_service,
                "_fetch_access_token_for_account",
                side_effect=fetch,
            ),
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
                return_value={"added": 4, "skipped": 0},
            ),
            mock.patch.object(
                account_import_job.account_service,
                "sync_accounts_and_quota",
                return_value={"synced": 4, "errors": []},
            ),
        ):
            worker = threading.Thread(
                target=service._run_import,
                args=("server-1", {}, account_ids, {}),
            )
            worker.start()
            self.assertTrue(two_entered.wait(1))
            time.sleep(0.05)
            self.assertEqual(maximum, 2)
            release.set()
            worker.join(3)

        self.assertFalse(worker.is_alive())
        self.assertEqual(config.get_import_job("server-1")["status"], "completed")

    def test_partial_fetch_and_sync_errors_complete_with_one_error_shape(self) -> None:
        config = _MemoryImportConfig(sub2api_service._normalize_import_job, "server-1", 2)
        service = sub2api_service.Sub2APIImportService(config)

        with (
            mock.patch.object(
                sub2api_service,
                "_fetch_access_tokens_for_accounts",
                return_value=(
                    {"good": ("good-token", {"email": "good@example.com"})},
                    {"bad": "export skipped"},
                ),
            ),
            mock.patch.object(
                sub2api_service,
                "_fetch_access_token_for_account",
                side_effect=RuntimeError("fallback failed"),
            ),
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
                return_value={
                    "added": 1,
                    "skipped": 0,
                    "item_results": ["added"],
                },
            ),
            mock.patch.object(
                account_import_job.account_service,
                "sync_accounts_and_quota",
                return_value={
                    "synced": 0,
                    "errors": [{
                        "id": "local-account",
                        "account_id": "good",
                        "account_label": "good@example.com",
                        "error": "quota failed",
                    }],
                },
            ),
        ):
            service._run_import("server-1", {}, ["good", "bad"], {})

        result = config.get_import_job("server-1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["failed"], 2)
        self.assertEqual(result["errors"], [
            {
                "stage": "fetch",
                "name": "bad",
                "error": "batch export skipped: export skipped; fallback failed: fallback failed",
            },
            {"stage": "sync", "name": "local-account", "error": "quota failed"},
        ])
        self.assertTrue(result["events"])
        self.assertTrue(all(event["action"] == "import_account" for event in result["events"]))
        self.assertTrue(any(event["status"] == "failed" for event in result["events"]))
        read_events = [
            event
            for job in config.writes
            if job["stage"] == "read_credentials"
            for event in job["events"]
        ]
        self.assertTrue(all(event["status"] == "failed" for event in read_events))
        self.assertFalse(
            any("\u8d26\u53f7\u51ed\u636e\u5df2\u8bfb\u53d6" in event["message"] for event in result["events"])
        )
        self.assertTrue(
            any(
                event["account_id"] == "good"
                and event["account_label"] == "good@example.com"
                and event["status"] == "success"
                and event["message"] == "\u8d26\u53f7\u5bfc\u5165\u6210\u529f"
                for event in result["events"]
            )
        )
        self.assertTrue(
            any(
                event["account_id"] == "good"
                and event["account_label"] == "good@example.com"
                and event["status"] == "failed"
                for event in result["events"]
            )
        )

    def test_no_usable_payload_fails_the_job(self) -> None:
        config = _MemoryImportConfig(sub2api_service._normalize_import_job, "server-1", 1)
        service = sub2api_service.Sub2APIImportService(config)

        with (
            mock.patch.object(
                sub2api_service,
                "_fetch_access_tokens_for_accounts",
                side_effect=RuntimeError("export unavailable"),
            ),
            mock.patch.object(
                sub2api_service,
                "_fetch_access_token_for_account",
                side_effect=RuntimeError("fallback unavailable"),
            ),
        ):
            service._run_import("server-1", {}, ["bad"], {})

        result = config.get_import_job("server-1")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["errors"][0]["stage"], "fetch")

    def test_local_account_write_failure_finishes_the_job_as_failed(self) -> None:
        config = _MemoryImportConfig(sub2api_service._normalize_import_job, "server-1", 2)
        service = sub2api_service.Sub2APIImportService(config)

        with (
            mock.patch.object(
                sub2api_service,
                "_fetch_access_tokens_for_accounts",
                return_value=(
                    {
                        "first": ("first-token", {}),
                        "second": ("second-token", {}),
                    },
                    {},
                ),
            ),
            mock.patch.object(
                account_import_job.account_service,
                "add_account_items",
                side_effect=RuntimeError("storage unavailable"),
            ),
        ):
            service._run_import("server-1", {}, ["first", "second"], {})

        result = config.get_import_job("server-1")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["completed"], 2)
        self.assertEqual(result["failed"], 2)
        self.assertEqual(
            {error["name"] for error in result["errors"]},
            {"first", "second"},
        )
        self.assertTrue(all(error["stage"] == "sync" for error in result["errors"]))
        self.assertTrue(all(error["error"] == "storage unavailable" for error in result["errors"]))
        self.assertEqual(
            {
                event["account_id"]
                for event in result["events"]
                if event["status"] == "failed"
            },
            {"first", "second"},
        )

    def test_import_errors_do_not_persist_server_or_account_credentials(self) -> None:
        config = _MemoryImportConfig(sub2api_service._normalize_import_job, "server-1", 2)
        service = sub2api_service.Sub2APIImportService(config)
        server = {
            "id": "server-1",
            "password": "server-password",
            "api_key": "server-api-key",
        }
        sub2api_service._token_cache["server-1"] = (
            "server-login-token",
            time.time() + 3600,
        )
        try:
            with (
                mock.patch.object(
                    sub2api_service,
                    "_fetch_access_tokens_for_accounts",
                    return_value=(
                        {
                            "good": (
                                "access-secret",
                                {
                                    "refresh_token": "refresh-secret",
                                    "id_token": "id-secret",
                                },
                            ),
                        },
                        {"bad": "server-api-key server-login-token"},
                    ),
                ),
                mock.patch.object(
                    sub2api_service,
                    "_fetch_access_token_for_account",
                    side_effect=RuntimeError("server-password"),
                ),
                mock.patch.object(
                    account_import_job.account_service,
                    "add_account_items",
                    return_value={"added": 1, "skipped": 0},
                ),
                mock.patch.object(
                    account_import_job.account_service,
                    "sync_accounts_and_quota",
                    return_value={
                        "synced": 0,
                        "errors": [{
                            "name": "access-secret",
                            "error": "access-secret refresh-secret id-secret",
                        }],
                    },
                ),
            ):
                service._run_import("server-1", server, ["good", "bad"], {})
        finally:
            sub2api_service._token_cache.pop("server-1", None)

        serialized = repr(config.get_import_job("server-1"))
        for secret in (
            "server-password",
            "server-api-key",
            "server-login-token",
            "access-secret",
            "refresh-secret",
            "id-secret",
        ):
            self.assertNotIn(secret, serialized)


if __name__ == "__main__":
    unittest.main()
