from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import prompts as prompts_api
from contracts.prompts import PromptLibraryView, PromptSourceSyncSummary
from services.prompt_library_service import PromptLibraryService
from services.storage.prompt_library_repository import PromptLibraryRepository


REGISTRY_BASE = "https://registry.example/dist"
SOURCE_ID = "banana-prompt-quicker"


def _raw_item(suffix: str, *, prompt: str = "same prompt") -> dict[str, object]:
    return {
        "id": f"{SOURCE_ID}:{suffix}",
        "sourceId": SOURCE_ID,
        "title": f"Prompt {suffix}",
        "prompt": prompt,
        "description": "Description",
        "coverUrl": "https://images.example/cover.png",
        "referenceImageUrls": ["https://images.example/reference.png"],
        "tags": ["工作", "海报", "Author"],
        "author": "Author",
        "sourceUrl": "https://source.example/prompts",
        "createdAt": "2026-07-26T00:00:00+00:00",
        "imageMode": "generate",
        "imageModel": "gpt-image-2",
        "imageSize": "1536x1024",
        "imageCount": 1,
    }


def _registry_payload(
    items: list[dict[str, object]],
    *,
    schema_version: int = 1,
    total: int | None = None,
    prompt_payload: bytes | None = None,
) -> tuple[bytes, bytes]:
    payload = prompt_payload if prompt_payload is not None else json.dumps(
        items,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    sources = [{
        "id": SOURCE_ID,
        "name": "Banana Prompt Quicker",
        "homepage": "https://source.example/",
        "upstreamUrl": "https://source.example/prompts.json",
        "count": len(items),
        "path": f"sources/{SOURCE_ID}.json",
        "sha256": hashlib.sha256(payload).hexdigest(),
    }]
    revision = hashlib.sha256(
        json.dumps(
            sources,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + payload
    ).hexdigest()
    manifest = {
        "schemaVersion": schema_version,
        "generatedAt": "2026-07-26T00:00:00+00:00",
        "registryHash": revision,
        "total": len(items) if total is None else total,
        "promptsPath": "prompts.json",
        "sources": sources,
    }
    return json.dumps(manifest, ensure_ascii=False).encode("utf-8"), payload


class _RegistryFetcher:
    def __init__(self, manifest: bytes, prompts: bytes) -> None:
        self.manifest = manifest
        self.prompts = prompts
        self.manifest_error: Exception | None = None
        self.prompt_error: Exception | None = None
        self.manifest_calls = 0
        self.prompt_calls = 0

    def __call__(self, url: str, _max_bytes: int) -> bytes:
        if url.endswith("/manifest.json"):
            self.manifest_calls += 1
            if self.manifest_error is not None:
                raise self.manifest_error
            return self.manifest
        if url.endswith("/prompts.json"):
            self.prompt_calls += 1
            if self.prompt_error is not None:
                raise self.prompt_error
            return self.prompts
        raise AssertionError(f"unexpected registry URL: {url}")


def _service(root: Path, fetcher: _RegistryFetcher) -> PromptLibraryService:
    return PromptLibraryService(
        database_url=f"sqlite:///{(root / 'app.db').as_posix()}",
        bundled_path=root / "missing-bundled.json",
        registry_base=REGISTRY_BASE,
        fetch_bytes=fetcher,
    )


class PromptLibraryRegistryTests(unittest.TestCase):
    def test_all_registry_sources_are_enabled_by_default(self) -> None:
        manifest, prompts = _registry_payload([_raw_item("one")])

        with tempfile.TemporaryDirectory() as temp_dir:
            view = _service(
                Path(temp_dir),
                _RegistryFetcher(manifest, prompts),
            ).view()

        self.assertGreater(view.source_count, 1)
        self.assertEqual(view.enabled_source_count, view.source_count)
        self.assertTrue(all(source.enabled for source in view.sources))

    def test_unsynced_source_projects_pending_sync_state(self) -> None:
        manifest, prompts = _registry_payload([_raw_item("one")])

        with tempfile.TemporaryDirectory() as temp_dir:
            source = _service(
                Path(temp_dir),
                _RegistryFetcher(manifest, prompts),
            ).view().sources[0]

        self.assertEqual(source.sync_state, "pending")
        self.assertEqual(source.sync_label, "待同步")
        self.assertEqual(source.sync_message, "提示词源等待首次同步")
        self.assertEqual(source.sync_tone, "muted")

    def test_source_projection_distinguishes_synced_and_cached_fallback(self) -> None:
        manifest, prompts = _registry_payload([_raw_item("one")])
        fetcher = _RegistryFetcher(manifest, prompts)

        with tempfile.TemporaryDirectory() as temp_dir:
            service = _service(Path(temp_dir), fetcher)
            synced = service.refresh().sources[0]
            fetcher.manifest_error = OSError("HTTP 503")
            cached = service.refresh().sources[0]

        self.assertEqual((synced.sync_state, synced.sync_label), ("synced", "已同步"))
        self.assertEqual(synced.sync_tone, "success")
        self.assertEqual((cached.sync_state, cached.sync_label), ("cached", "缓存可用"))
        self.assertEqual(cached.sync_message, "同步失败，继续使用本地缓存")
        self.assertEqual(cached.sync_tone, "warning")

    def test_library_projects_one_sync_summary_for_all_consumers(self) -> None:
        manifest, prompts = _registry_payload([_raw_item("one")])
        fetcher = _RegistryFetcher(manifest, prompts)

        with tempfile.TemporaryDirectory() as temp_dir:
            service = _service(Path(temp_dir), fetcher)
            synced = service.refresh()
            fetcher.manifest_error = OSError("HTTP 503")
            failed = service.refresh()

        self.assertEqual(
            synced.sync_summary.model_dump(),
            {
                "status": "success",
                "tone": "success",
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "message": "词源同步完成：成功 1，共 1 条提示词",
            },
        )
        self.assertEqual(failed.sync_summary.status, "failed")
        self.assertEqual(failed.sync_summary.tone, "danger")
        self.assertEqual(failed.sync_summary.total, 1)
        self.assertEqual(failed.sync_summary.failed, 1)

    def test_disabled_source_state_overrides_an_unavailable_snapshot(self) -> None:
        manifest, prompts = _registry_payload([_raw_item("one")])
        fetcher = _RegistryFetcher(manifest, prompts)
        fetcher.manifest_error = OSError("HTTP 503")

        with tempfile.TemporaryDirectory() as temp_dir:
            service = _service(Path(temp_dir), fetcher)
            failed = service.refresh().sources[0]
            disabled = service.update_source(SOURCE_ID, {"enabled": False}).sources[0]

        self.assertEqual((failed.sync_state, failed.sync_label), ("failed", "同步失败"))
        self.assertEqual(failed.sync_tone, "danger")
        self.assertEqual((disabled.sync_state, disabled.sync_label), ("disabled", "已停用"))
        self.assertEqual(disabled.sync_tone, "muted")
        view = service.view()
        self.assertNotIn(SOURCE_ID, {error.id for error in view.source_errors})
        self.assertEqual(
            view.source_error_count,
            sum(1 for source in view.sources if source.enabled and source.last_error),
        )

    def test_prompt_updates_use_one_configured_cloud_registry(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                PromptLibraryService._configured_registry_base(),
                "https://raw.githubusercontent.com/yukkcat/image-prompts/main/dist",
            )

        with patch.dict(
            os.environ,
            {"PROMPT_LIBRARY_REGISTRY_URL": "https://registry.example/dist/manifest.json"},
        ):
            self.assertEqual(
                PromptLibraryService._configured_registry_base(),
                "https://registry.example/dist",
            )

    def test_registry_snapshot_preserves_stable_ids_and_distinct_records(self) -> None:
        items = [_raw_item("one"), _raw_item("two")]
        manifest, prompts = _registry_payload(items)
        fetcher = _RegistryFetcher(manifest, prompts)

        with tempfile.TemporaryDirectory() as temp_dir:
            view = _service(Path(temp_dir), fetcher).refresh()

        self.assertIsNotNone(view)
        assert view is not None
        self.assertEqual(view.prompt_count, 2)
        self.assertEqual([item.id for item in view.items], [f"{SOURCE_ID}:one", f"{SOURCE_ID}:two"])
        self.assertEqual([item.prompt for item in view.items], ["same prompt", "same prompt"])
        self.assertEqual(view.items[0].category, "工作")
        self.assertEqual(view.items[0].sub_category, "海报")
        self.assertEqual(view.sources[0].prompt_count, 2)
        self.assertEqual(view.registry_revision, json.loads(manifest)["registryHash"])

    def test_database_snapshot_and_source_settings_survive_restart(self) -> None:
        manifest, prompts = _registry_payload([_raw_item("cached")])
        fetcher = _RegistryFetcher(manifest, prompts)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            initial_service = _service(root, fetcher)
            initial_service.refresh()
            initial_service.update_source(SOURCE_ID, {"enabled": False})

            service = _service(root, fetcher)
            initial = service.view()
            self.assertEqual(initial.prompt_count, 0)
            source = next(item for item in initial.sources if item.id == SOURCE_ID)
            self.assertFalse(source.enabled)
            self.assertTrue(source.cached)
            self.assertEqual(source.prompt_count, 1)

            enabled = service.update_source(SOURCE_ID, {"enabled": True})
            self.assertIsNotNone(enabled)
            assert enabled is not None
            self.assertEqual([item.id for item in enabled.items], [f"{SOURCE_ID}:cached"])

            fetcher.prompts = _registry_payload([_raw_item("remote")])[1]
            fetcher.manifest = _registry_payload([_raw_item("remote")])[0]
            refreshed = service.refresh()
            self.assertIsNotNone(refreshed)
            cache = service.repository.load().snapshot
            self.assertEqual(cache["schema_version"], 1)
            self.assertIn("items_by_source", cache)
            self.assertEqual(cache["items_by_source"][SOURCE_ID][0]["id"], f"{SOURCE_ID}:remote")

    def test_bad_registry_candidates_keep_the_complete_previous_snapshot(self) -> None:
        valid_items = [_raw_item("one"), _raw_item("two")]
        valid_manifest, valid_prompts = _registry_payload(valid_items)

        invalid_json_manifest, invalid_json_prompts = _registry_payload(
            valid_items,
            prompt_payload=b"{",
        )
        schema_manifest, schema_prompts = _registry_payload(valid_items, schema_version=2)
        count_manifest, count_prompts = _registry_payload(valid_items, total=99)
        duplicate_items = [_raw_item("duplicate"), _raw_item("duplicate")]
        duplicate_manifest, duplicate_prompts = _registry_payload(duplicate_items)
        hash_manifest = json.loads(valid_manifest)
        hash_manifest["registryHash"] = "0" * 64

        cases: list[tuple[str, bytes, bytes, Exception | None, Exception | None]] = [
            ("http", valid_manifest, valid_prompts, OSError("HTTP 503"), None),
            ("timeout", valid_manifest, valid_prompts, TimeoutError("timed out"), None),
            ("invalid-json", invalid_json_manifest, invalid_json_prompts, None, None),
            ("hash", json.dumps(hash_manifest).encode("utf-8"), valid_prompts, None, None),
            ("schema", schema_manifest, schema_prompts, None, None),
            ("count", count_manifest, count_prompts, None, None),
            ("duplicate-id", duplicate_manifest, duplicate_prompts, None, None),
        ]

        for name, manifest, prompts, manifest_error, prompt_error in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_dir:
                fetcher = _RegistryFetcher(valid_manifest, valid_prompts)
                service = _service(Path(temp_dir), fetcher)
                before = service.refresh()
                assert before is not None
                before_ids = [item.id for item in before.items]

                fetcher.manifest = manifest
                fetcher.prompts = prompts
                fetcher.manifest_error = manifest_error
                fetcher.prompt_error = prompt_error
                after = service.refresh()

                assert after is not None
                self.assertEqual([item.id for item in after.items], before_ids)
                self.assertEqual(after.prompt_count, len(before_ids))
                self.assertEqual(after.registry_revision, before.registry_revision)
                self.assertEqual(after.source_error_count, 1)
                self.assertTrue(after.sources[0].last_error)

    def test_equal_count_cache_corruption_forces_a_full_payload_refresh(self) -> None:
        items = [_raw_item("one"), _raw_item("two")]
        manifest, prompts = _registry_payload(items)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = _service(root, _RegistryFetcher(manifest, prompts))
            first.refresh()

            repository = PromptLibraryRepository(
                f"sqlite:///{(root / 'app.db').as_posix()}"
            )
            cache = repository.load().snapshot
            cache["items_by_source"][SOURCE_ID][0]["prompt"] = "tampered but same count"
            repository.replace_snapshot(cache)

            fetcher = _RegistryFetcher(manifest, prompts)
            restarted = _service(root, fetcher)
            self.assertEqual(restarted.view().items[0].prompt, "tampered but same count")
            repaired = restarted.refresh()

            assert repaired is not None
            self.assertEqual(fetcher.prompt_calls, 1)
            self.assertEqual(repaired.items[0].prompt, "same prompt")

    def test_view_stays_fast_and_old_until_new_snapshot_is_persisted(self) -> None:
        old_manifest, old_prompts = _registry_payload([_raw_item("old")])
        new_manifest, new_prompts = _registry_payload([_raw_item("new-a"), _raw_item("new-b")])
        fetcher = _RegistryFetcher(old_manifest, old_prompts)

        with tempfile.TemporaryDirectory() as temp_dir:
            service = _service(Path(temp_dir), fetcher)
            initial = service.refresh()
            assert initial is not None
            fetcher.manifest = new_manifest
            fetcher.prompts = new_prompts

            write_started = threading.Event()
            release_write = threading.Event()
            real_write = service.repository.replace_snapshot

            def blocked_write(data: dict[str, object]) -> object:
                write_started.set()
                release_write.wait(timeout=3)
                return real_write(data)

            with patch.object(service.repository, "replace_snapshot", side_effect=blocked_write):
                refresh_thread = threading.Thread(target=service.refresh, daemon=True)
                refresh_thread.start()
                self.assertTrue(write_started.wait(timeout=1))

                started = time.monotonic()
                during = service.view()
                elapsed = time.monotonic() - started
                self.assertLess(elapsed, 0.5)
                self.assertEqual([item.id for item in during.items], [f"{SOURCE_ID}:old"])

                release_write.set()
                refresh_thread.join(timeout=3)

            self.assertFalse(refresh_thread.is_alive())
            after = service.view()
            self.assertEqual(
                [item.id for item in after.items],
                [f"{SOURCE_ID}:new-a", f"{SOURCE_ID}:new-b"],
            )

    def test_source_mutation_returns_the_canonical_service_snapshot(self) -> None:
        manifest, prompts = _registry_payload([_raw_item("one")])
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _service(Path(temp_dir), _RegistryFetcher(manifest, prompts))
            service.refresh()
            result = service.update_source(SOURCE_ID, {"enabled": False})

            self.assertIs(result, service.view())
            assert result is not None
            self.assertEqual(result.prompt_count, 0)
            self.assertEqual(result.enabled_source_count, 0)

    def test_failed_source_settings_write_does_not_change_memory(self) -> None:
        manifest, prompts = _registry_payload([_raw_item("one")])
        with tempfile.TemporaryDirectory() as temp_dir:
            service = _service(Path(temp_dir), _RegistryFetcher(manifest, prompts))
            before = service.refresh()
            assert before is not None
            self.assertTrue(before.sources[0].enabled)

            with patch.object(
                service.repository,
                "replace_settings",
                side_effect=PermissionError("read only"),
            ):
                with self.assertRaises(PermissionError):
                    service.update_source(SOURCE_ID, {"enabled": False})

            after = service.view()
            self.assertIs(after, before)
            self.assertTrue(after.sources[0].enabled)


class PromptLibraryApiContractTests(unittest.TestCase):
    def test_all_prompt_routes_publish_the_same_response_model(self) -> None:
        routes = [route for route in prompts_api.create_router().routes if route.path.startswith("/api/")]
        self.assertEqual(
            {route.path for route in routes},
            {
                "/api/prompts",
                "/api/admin/prompt-sources/refresh",
                "/api/admin/prompt-sources/{source_id}/refresh",
                "/api/admin/prompt-sources/{source_id}",
            },
        )
        self.assertTrue(all(route.response_model is PromptLibraryView for route in routes))

    def test_tuple_backed_snapshot_serializes_as_json_arrays(self) -> None:
        view = PromptLibraryView(
            generated_at="2026-07-26T00:00:00+00:00",
            revision="revision",
            synced=False,
            prompt_count=0,
            source_count=0,
            enabled_source_count=0,
            cached_source_count=0,
            source_error_count=0,
            sync_summary=PromptSourceSyncSummary(
                status="success",
                tone="success",
                total=0,
                succeeded=0,
                failed=0,
                message="没有启用的提示词源",
            ),
        )
        service = Mock()
        service.view.return_value = view
        app = FastAPI()

        with (
            patch.object(prompts_api, "prompt_library_service", service),
            patch.object(prompts_api, "require_identity", return_value={"id": "user"}),
        ):
            app.include_router(prompts_api.create_router())
            response = TestClient(app).get("/api/prompts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(response.json()["sources"], [])
        service.view.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
