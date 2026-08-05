from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import api.system as system_module
import services.gallery_view as gallery_view_module
import services.image_service as image_service_module
import services.image_storage_service as image_storage_module
import services.retention_cleanup_service as retention_cleanup_module
from api.gallery_contract import (
    GalleryCleanupResult,
    GalleryCleanupTargetResult,
    GalleryCompressResult,
    GalleryGenBoxPushResult,
    GalleryPage,
    GalleryRow,
)
from services.image_storage_service import ImageStorageService
from utils.timezone import BEIJING_TZ


NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=BEIJING_TZ)


class FakeImageStorage:
    def __init__(self, items: list[dict[str, object]], payloads: dict[str, bytes] | None = None):
        self.items = [dict(item) for item in items]
        self.payloads = dict(payloads or {})
        self.get_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.local_delete_calls: list[str] = []

    def list_items(
        self,
        base_url: str,
        start_date: str = "",
        end_date: str = "",
        *,
        refresh_index: bool = True,
        verify_existing: bool = True,
    ) -> list[dict[str, object]]:
        del refresh_index, verify_existing
        result: list[dict[str, object]] = []
        for source in self.items:
            date = str(source.get("date") or "")
            if start_date and date < start_date:
                continue
            if end_date and date > end_date:
                continue
            item = dict(source)
            path = str(item.get("path") or item.get("rel") or "")
            item.setdefault("url", f"{base_url.rstrip('/')}/images/{path}")
            result.append(item)
        return result

    def has_local(self, relative_path: str) -> bool:
        item = self._item(relative_path)
        return bool(item and item.get("local"))

    def exists(self, relative_path: str) -> bool:
        item = self._item(relative_path)
        return bool(item and (item.get("local") or item.get("webdav")))

    def existing_paths(self, relative_paths: list[str]) -> set[str]:
        return {relative_path for relative_path in relative_paths if self.exists(relative_path)}

    def get_bytes(self, relative_path: str) -> bytes:
        self.get_calls.append(relative_path)
        try:
            return self.payloads[relative_path]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="image not found") from exc

    def record_genbox_push(self, relative_path: str, *, status: str, sha256: str, updated_at: str) -> dict[str, str]:
        item = self._item(relative_path)
        if item is None:
            raise HTTPException(status_code=404, detail="image not found")
        state = {
            "status": status,
            "sha256": sha256,
            "updated_at": updated_at,
        }
        item["genbox_push"] = state
        return dict(state)

    def delete(self, relative_path: str) -> bool:
        self.delete_calls.append(relative_path)
        item = self._item(relative_path)
        if item is None:
            return False
        self.items.remove(item)
        self.payloads.pop(relative_path, None)
        return True

    def delete_local_copies(self, relative_paths: list[str]) -> dict[str, bool]:
        removed: dict[str, bool] = {}
        for relative_path in relative_paths:
            item = self._item(relative_path)
            if item is None or not item.get("local"):
                continue
            self.local_delete_calls.append(relative_path)
            remote_remains = bool(item.get("webdav"))
            removed[relative_path] = remote_remains
            if remote_remains:
                item["local"] = False
                item["storage"] = "webdav"
            else:
                self.items.remove(item)
                self.payloads.pop(relative_path, None)
        return removed

    def _item(self, relative_path: str) -> dict[str, object] | None:
        return next(
            (
                item
                for item in self.items
                if str(item.get("path") or item.get("rel") or "") == relative_path
            ),
            None,
        )


class GalleryContractApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.images_dir = root / "images"
        self.thumbnails_dir = root / "image-thumbnails"
        self.images_dir.mkdir(parents=True)
        self.thumbnails_dir.mkdir(parents=True)

        self.items = [
            {
                "path": "2026/07/24/hero-alpha.png",
                "name": "hero-alpha.png",
                "url": "https://cdn.example.test/images/hero-alpha.png",
                "date": "2026-07-24",
                "size": 120,
                "created_at": "2026-07-24 12:00:00",
                "storage": "local",
                "local": True,
                "webdav": False,
                "width": 1024,
                "height": 768,
            },
            {
                "path": "2026/06/01/hero-beta.webp",
                "name": "hero-beta.webp",
                "date": "2026-06-01",
                "size": 80,
                "created_at": "2026-06-01 12:00:00",
                "storage": "webdav",
                "local": False,
                "webdav": True,
                "width": 640,
                "height": 640,
            },
            {
                "path": "2026/07/23/hero-preview.png",
                "name": "hero-preview.png",
                "date": "2026-06-02",
                "size": 200,
                "created_at": "2026-06-02 12:00:00",
                "storage": "both",
                "local": True,
                "webdav": True,
            },
            {
                "path": "2026/07/22/theme.webp",
                "name": "theme.webp",
                "date": "2026-07-22",
                "size": 300,
                "created_at": "2026-07-22 12:00:00",
                "storage": "webdav",
                "local": False,
                "webdav": True,
            },
        ]
        self.tags = {
            "2026/07/24/hero-alpha.png": ["featured", "warm"],
            "2026/06/01/hero-beta.webp": ["featured"],
            "2026/07/23/hero-preview.png": ["featured"],
            "2026/07/22/theme.webp": ["audio"],
        }
        self.storage = FakeImageStorage(
            self.items,
            payloads={"2026/06/01/hero-beta.webp": b"webdav-only-image"},
        )
        fake_config = SimpleNamespace(
            base_url="https://console.example.test",
            image_retention_days=30,
            images_dir=self.images_dir,
            image_thumbnails_dir=self.thumbnails_dir,
        )

        patchers = [
            mock.patch.object(system_module, "require_admin", lambda _authorization: {"id": "admin"}),
            mock.patch.object(system_module, "resolve_image_base_url", lambda _request: "https://console.example.test"),
            mock.patch.object(system_module, "image_storage_service", self.storage),
            mock.patch.object(image_service_module, "image_storage_service", self.storage),
            mock.patch.object(image_service_module, "config", fake_config),
            mock.patch.object(retention_cleanup_module, "config", fake_config),
            mock.patch.object(image_service_module, "load_tags", lambda: dict(self.tags)),
            mock.patch.object(image_service_module, "remove_tags", lambda _path: None),
            mock.patch.object(gallery_view_module, "beijing_now", lambda: NOW),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        app = FastAPI()
        app.include_router(system_module.create_router("test"))
        self.client = TestClient(app)

    def test_get_images_returns_strict_rows_and_expiration_projection(self) -> None:
        response = self.client.get("/api/images")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        validated = GalleryPage.model_validate(payload)
        self.assertEqual(set(payload), set(GalleryPage.model_fields))
        self.assertEqual(len(validated.items), 4)
        for item in payload["items"]:
            self.assertEqual(set(item), set(GalleryRow.model_fields))
            self.assertEqual(item["id"], item["path"])

        rows = {item["id"]: item for item in payload["items"]}
        fresh = rows["2026/07/24/hero-alpha.png"]
        self.assertEqual(fresh["filename"], "hero-alpha.png")
        self.assertEqual(fresh["size_bytes"], 120)
        self.assertEqual(fresh["media_type"], "image")
        self.assertEqual(fresh["url"], "https://cdn.example.test/images/hero-alpha.png")
        self.assertEqual(fresh["tags"], ["featured", "warm"])
        self.assertEqual(fresh["thumbnail_url"], "https://console.example.test/image-thumbnails/2026/07/24/hero-alpha.png")
        self.assertFalse(fresh["expired"])
        self.assertEqual(fresh["expires_at"], "2026-08-23 12:00:00")
        self.assertEqual(fresh["expires_in_seconds"], 29 * 86400)
        self.assertTrue(fresh["available"])

        expired = rows["2026/06/01/hero-beta.webp"]
        self.assertFalse(expired["expired"])
        self.assertIsNone(expired["expires_at"])
        self.assertIsNone(expired["expires_in_seconds"])
        self.assertEqual(expired["storage"], "webdav")
        self.assertFalse(expired["local"])
        self.assertTrue(expired["webdav"])
        self.assertTrue(expired["available"])

        expiring_local_copy = rows["2026/07/23/hero-preview.png"]
        self.assertTrue(expiring_local_copy["expired"])
        self.assertEqual(expiring_local_copy["expires_at"], "2026-07-02 12:00:00")
        self.assertEqual(expiring_local_copy["expires_in_seconds"], 0)

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["generated_at"], "2026-07-25T12:00:00+08:00")
        self.assertEqual(payload["total"], 4)
        self.assertEqual(payload["total_size_bytes"], 700)
        self.assertEqual(payload["retention_days"], 30)
        self.assertEqual(payload["media_type"], "all")
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["page_size"], 24)
        self.assertEqual(payload["page_count"], 1)
        self.assertFalse(payload["has_more"])

    def test_get_images_filters_then_paginates_and_returns_filtered_facets(self) -> None:
        response = self.client.get(
            "/api/images",
            params={
                "media_type": "image",
                "tag": "featured",
                "search": "hero",
                "page": 2,
                "page_size": 1,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = GalleryPage.model_validate(response.json()).model_dump()
        self.assertEqual([item["id"] for item in payload["items"]], ["2026/06/01/hero-beta.webp"])
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["total_size_bytes"], 400)
        self.assertEqual(payload["facets"]["media_types"], {
            "all": 3,
            "image": 3,
        })
        self.assertEqual(payload["facets"]["tags"], ["audio", "featured", "warm"])
        self.assertEqual(payload["media_type"], "image")
        self.assertEqual(payload["page"], 2)
        self.assertEqual(payload["page_size"], 1)
        self.assertEqual(payload["page_count"], 3)
        self.assertTrue(payload["has_more"])

    def test_webdav_only_image_can_be_downloaded_in_zip(self) -> None:
        relative_path = "2026/06/01/hero-beta.webp"
        self.assertFalse((self.images_dir / relative_path).exists())

        response = self.client.post("/api/images/download", json={"paths": [relative_path]})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(response.content), "r") as archive:
            self.assertEqual(archive.namelist(), ["hero-beta.webp"])
            self.assertEqual(archive.read("hero-beta.webp"), b"webdav-only-image")
        self.assertEqual(self.storage.get_calls, [relative_path])

    def test_genbox_push_endpoint_returns_state_and_source_retained(self) -> None:
        relative_path = "2026/07/24/hero-alpha.png"
        state = {
            "status": "imported",
            "sha256": "a" * 64,
            "updated_at": "2026-07-25T12:00:00Z",
        }
        seen: list[str] = []

        def fake_push(path: str) -> dict[str, object]:
            seen.append(path)
            return {"path": path, **state, "source_retained": True}

        with mock.patch.object(system_module, "push_gallery_image", side_effect=fake_push):
            response = self.client.post("/api/images/genbox-push", json={"path": relative_path})

        self.assertEqual(response.status_code, 200, response.text)
        payload = GalleryGenBoxPushResult.model_validate(response.json()).model_dump()
        self.assertEqual(payload, {
            "path": relative_path,
            **state,
            "source_retained": True,
        })
        self.assertEqual(seen, [relative_path])

    def test_genbox_push_state_is_projected_only_when_valid(self) -> None:
        self.storage.items[0]["genbox_push"] = {
            "status": "imported",
            "sha256": "b" * 64,
            "updated_at": "2026-07-25T12:00:00Z",
        }
        self.storage.items[1]["genbox_push"] = {
            "status": "pending",
            "sha256": "c" * 64,
            "updated_at": "2026-07-25T12:00:00Z",
        }

        response = self.client.get("/api/images")

        self.assertEqual(response.status_code, 200, response.text)
        payload = GalleryPage.model_validate(response.json()).model_dump()
        rows = {item["id"]: item for item in payload["items"]}
        self.assertEqual(rows["2026/07/24/hero-alpha.png"]["genbox_push"], {
            "status": "imported",
            "sha256": "b" * 64,
            "updated_at": "2026-07-25T12:00:00Z",
        })
        self.assertIsNone(rows["2026/06/01/hero-beta.webp"]["genbox_push"])

    def test_retention_cleanup_runs_entirely_on_backend(self) -> None:
        self.assertEqual(image_service_module.preview_image_retention_cleanup(), {
            "removed": 1,
            "removed_size_bytes": 200,
            "retention_days": 30,
            "dry_run": True,
        })

        response = self.client.post("/api/images/retention-cleanup")

        self.assertEqual(response.status_code, 200, response.text)
        payload = GalleryCleanupResult.model_validate(response.json()).model_dump()
        self.assertEqual(payload, {
            "removed": 1,
            "removed_size_bytes": 200,
            "retention_days": 30,
            "message": "已清理 1 个过期本地副本；仍有 WebDAV 副本的图库记录已保留。",
        })
        self.assertEqual(self.storage.local_delete_calls, ["2026/07/23/hero-preview.png"])
        self.assertEqual(self.storage.delete_calls, [])
        remote_only = self.storage._item("2026/06/01/hero-beta.webp")
        self.assertIsNotNone(remote_only)
        retained_remote = self.storage._item("2026/07/23/hero-preview.png")
        self.assertIsNotNone(retained_remote)
        self.assertFalse(retained_remote["local"])
        self.assertTrue(retained_remote["webdav"])
        self.assertEqual(retained_remote["storage"], "webdav")

    def test_compression_returns_backend_owned_action_presentation(self) -> None:
        raw_result = {
            "compressed": 2,
            "saved_bytes": 1536,
            "saved_mb": 0,
        }
        with mock.patch.object(system_module, "compress_images", return_value=raw_result):
            response = self.client.post("/api/images/storage/compress")

        self.assertEqual(response.status_code, 200, response.text)
        payload = GalleryCompressResult.model_validate(response.json()).model_dump()
        self.assertEqual(payload, {
            **raw_result,
            "message": "压缩完成：处理 2 张，节省 1.5 KB。",
        })

    def test_cleanup_to_target_returns_backend_owned_action_presentation(self) -> None:
        cases = [
            (
                True,
                {
                    "removed": 2,
                    "freed_mb": 12,
                    "target_free_mb": 500,
                    "current_free_mb": 420,
                    "done": False,
                    "dry_run": True,
                },
                "预估会清理 2 张，预计释放 12.0 MB。当前剩余 420.0 MB / 目标 500.0 MB，仍未达到目标。",
            ),
            (
                False,
                {
                    "removed": 0,
                    "current_free_mb": 640,
                    "target_free_mb": 500,
                    "done": True,
                },
                "没有需要清理的图片。当前剩余 640.0 MB / 目标 500.0 MB。",
            ),
            (
                True,
                {
                    "removed": 0,
                    "freed_mb": 0,
                    "target_free_mb": 500,
                    "current_free_mb": 420,
                    "done": False,
                    "dry_run": True,
                },
                "没有可清理的图片。当前剩余 420.0 MB / 目标 500.0 MB，仍未达到目标。",
            ),
        ]
        for dry_run, raw_result, expected_message in cases:
            with self.subTest(dry_run=dry_run, removed=raw_result["removed"]):
                with mock.patch.object(
                    system_module.retention_cleanup_coordinator,
                    "cleanup_images_to_target",
                    return_value=raw_result,
                ):
                    response = self.client.post(
                        "/api/images/storage/cleanup-to-target",
                        params={"target_free_mb": 500, "dry_run": dry_run},
                    )

                self.assertEqual(response.status_code, 200, response.text)
                payload = GalleryCleanupTargetResult.model_validate(response.json()).model_dump()
                self.assertEqual(payload, {
                    "removed": int(raw_result["removed"]),
                    "freed_mb": int(raw_result.get("freed_mb", 0)),
                    "target_free_mb": 500,
                    "current_free_mb": int(raw_result["current_free_mb"]),
                    "done": bool(raw_result["done"]),
                    "dry_run": dry_run,
                    "message": expected_message,
                })

    def test_cleanup_to_target_rejects_non_positive_target(self) -> None:
        response = self.client.post(
            "/api/images/storage/cleanup-to-target",
            params={"target_free_mb": 0},
        )

        self.assertEqual(response.status_code, 422, response.text)

    def test_local_retention_preserves_remote_copy_and_removes_local_only_index(self) -> None:
        root = Path(self.temp_dir.name)
        local_only = "2026/06/01/local-only.png"
        mirrored = "2026/06/01/mirrored.png"
        for relative_path in (local_only, mirrored):
            path = self.images_dir / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"image")

        storage = ImageStorageService(root / "image-index.json")
        storage._save_index({
            local_only: {
                "path": local_only,
                "local": True,
                "webdav": False,
                "storage": "local",
            },
            mirrored: {
                "path": mirrored,
                "local": True,
                "webdav": True,
                "storage": "both",
            },
        })

        with mock.patch.object(
            image_storage_module,
            "config",
            SimpleNamespace(images_dir=self.images_dir),
        ):
            result = storage.delete_local_copies([local_only, mirrored])

        self.assertEqual(result, {local_only: False, mirrored: True})
        self.assertFalse((self.images_dir / local_only).exists())
        self.assertFalse((self.images_dir / mirrored).exists())
        indexed = storage._load_clean_index()
        self.assertNotIn(local_only, indexed)
        self.assertFalse(indexed[mirrored]["local"])
        self.assertTrue(indexed[mirrored]["webdav"])
        self.assertEqual(indexed[mirrored]["storage"], "webdav")

    def test_thumbnail_cleanup_loads_remote_index_once_per_batch(self) -> None:
        root = Path(self.temp_dir.name)
        remote_paths = [
            "2026/07/24/remote-alpha.webp",
            "2026/07/24/remote-beta.png",
        ]
        orphan_path = "2026/07/24/orphan.jpg"
        for relative_path in [*remote_paths, orphan_path]:
            thumbnail = self.thumbnails_dir / f"{relative_path}.png"
            thumbnail.parent.mkdir(parents=True, exist_ok=True)
            thumbnail.write_bytes(b"thumbnail")
        non_png = self.thumbnails_dir / "2026/07/24/invalid.cache"
        non_png.write_bytes(b"not-a-thumbnail")

        storage = ImageStorageService(root / "image-index.json")
        storage._save_index({
            relative_path: {
                "path": relative_path,
                "local": False,
                "webdav": True,
                "storage": "webdav",
            }
            for relative_path in remote_paths
        })

        with (
            mock.patch.object(
                image_storage_module,
                "config",
                SimpleNamespace(images_dir=self.images_dir),
            ),
            mock.patch.object(image_service_module, "image_storage_service", storage),
            mock.patch.object(storage, "_load_clean_index", wraps=storage._load_clean_index) as load_index,
        ):
            removed = image_service_module.cleanup_image_thumbnails()

        self.assertEqual(removed, 2)
        self.assertEqual(load_index.call_count, 1)
        for relative_path in remote_paths:
            self.assertTrue((self.thumbnails_dir / f"{relative_path}.png").is_file())
        self.assertFalse((self.thumbnails_dir / f"{orphan_path}.png").exists())
        self.assertFalse(non_png.exists())


if __name__ == "__main__":
    unittest.main()
