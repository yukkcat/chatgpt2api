from __future__ import annotations

import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException
from PIL import Image

from services import image_service
from services import image_storage_service as image_storage_module
from services.image_storage_service import ImageStorageService
from services.json_file import read_json_object, write_json_file


MEBIBYTE = 1024 * 1024


class ImageStorageMutationTests(unittest.TestCase):
    def test_path_safety_is_exposed_by_the_image_storage_interface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            images_dir = Path(temp_dir) / "images"
            images_dir.mkdir()
            relative_path = "2026/07/30/example.png"
            local_path = images_dir / relative_path
            local_path.parent.mkdir(parents=True)
            local_path.write_bytes(b"image")

            with mock.patch.object(
                image_storage_module,
                "config",
                SimpleNamespace(images_dir=images_dir),
            ):
                self.assertEqual(
                    image_storage_module.normalize_image_relative_path(
                        "2026\\07\\30\\example.png"
                    ),
                    relative_path,
                )
                self.assertEqual(
                    image_storage_module.image_local_path(relative_path, require_file=True),
                    local_path,
                )
                for invalid in (
                    "",
                    ".",
                    "..",
                    "../outside.png",
                    "folder/../outside.png",
                    "/absolute/image.png",
                    "C:/absolute/image.png",
                    r"C:\absolute\image.png",
                    r"\\server\share\image.png",
                    "//server/share/image.png",
                    "folder/image.png:stream",
                    "folder//image.png",
                ):
                    with self.subTest(invalid=invalid):
                        with self.assertRaisesRegex(HTTPException, "image not found"):
                            image_storage_module.normalize_image_relative_path(invalid)

    def test_compression_updates_catalog_and_marks_remote_copy_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index_path = root / "image_index.json"
            storage = ImageStorageService(index_path)
            rel = "2026/07/27/compress.png"
            path = root / "images" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (128, 128), (20, 120, 200)).save(
                path,
                format="PNG",
                compress_level=0,
            )
            original_size = path.stat().st_size
            thumbnail = root / "image_thumbnails" / f"{rel}.png"
            thumbnail.parent.mkdir(parents=True, exist_ok=True)
            thumbnail.write_bytes(b"thumbnail")
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": True,
                        "webdav": True,
                        "storage": "both",
                        "remote_url": "https://webdav.test/compress.png",
                    }
                }
            })

            with (
                mock.patch("services.config.DATA_DIR", root),
                mock.patch.object(storage, "_save_index", wraps=storage._save_index) as save_index,
            ):
                result = storage.compress_local_images()

            self.assertEqual(result["compressed"], 1)
            self.assertEqual(result["saved_bytes"], original_size - path.stat().st_size)
            self.assertEqual(save_index.call_count, 1)
            self.assertFalse(thumbnail.exists())
            item = read_json_object(index_path)["items"][rel]
            self.assertEqual(item["size"], path.stat().st_size)
            self.assertEqual((item["width"], item["height"]), (128, 128))
            self.assertTrue(item["local"])
            self.assertTrue(item["webdav"])
            self.assertEqual(item["storage"], "both")
            self.assertEqual(item["remote_url"], "https://webdav.test/compress.png")
            self.assertTrue(item["remote_sync_pending"])

            with (
                mock.patch("services.config.DATA_DIR", root),
                mock.patch.object(storage, "mode", return_value="both"),
                mock.patch.object(storage, "settings", return_value={}),
                mock.patch.object(
                    image_storage_module.WebDAVClient,
                    "put",
                    autospec=True,
                    return_value="https://webdav.test/compressed.png",
                ),
            ):
                sync_result = storage.sync_all()

            self.assertEqual(sync_result, {"uploaded": 1, "skipped": 0, "failed": 0})
            synced_item = read_json_object(index_path)["items"][rel]
            self.assertTrue(synced_item["webdav"])
            self.assertNotIn("remote_sync_pending", synced_item)
            self.assertEqual(
                synced_item["remote_url"],
                "https://webdav.test/compressed.png",
            )

    def test_compression_catalog_failure_is_recovered_by_next_sync(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index_path = root / "image_index.json"
            storage = ImageStorageService(index_path)
            rel = "2026/07/27/recover-compress.png"
            path = root / "images" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (128, 128), (40, 80, 120)).save(
                path,
                format="PNG",
                compress_level=0,
            )
            original_size = path.stat().st_size
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "size": original_size,
                        "local": True,
                        "webdav": True,
                        "storage": "both",
                        "remote_url": "https://webdav.test/original.png",
                    }
                }
            })

            with (
                mock.patch("services.config.DATA_DIR", root),
                mock.patch.object(storage, "_save_index", side_effect=OSError("catalog unavailable")),
            ):
                with self.assertRaisesRegex(OSError, "catalog unavailable"):
                    storage.compress_local_images()

            self.assertLess(path.stat().st_size, original_size)
            stale_item = read_json_object(index_path)["items"][rel]
            self.assertEqual(stale_item["size"], original_size)
            self.assertNotIn("remote_sync_pending", stale_item)

            with (
                mock.patch("services.config.DATA_DIR", root),
                mock.patch.object(storage, "mode", return_value="both"),
                mock.patch.object(storage, "settings", return_value={}),
                mock.patch.object(
                    image_storage_module.WebDAVClient,
                    "put",
                    autospec=True,
                    return_value="https://webdav.test/recovered.png",
                ) as put,
            ):
                sync_result = storage.sync_all()

            self.assertEqual(sync_result, {"uploaded": 1, "skipped": 0, "failed": 0})
            put.assert_called_once()
            recovered_item = read_json_object(index_path)["items"][rel]
            self.assertEqual(recovered_item["size"], path.stat().st_size)
            self.assertEqual(recovered_item["remote_url"], "https://webdav.test/recovered.png")

    def test_local_catalog_size_is_reconciled_after_compression_commit_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index_path = root / "image_index.json"
            storage = ImageStorageService(index_path)
            rel = "2026/07/27/local-reconcile.png"
            path = root / "images" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (128, 128), (10, 40, 90)).save(
                path,
                format="PNG",
                compress_level=0,
            )
            original_size = path.stat().st_size
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "size": original_size,
                        "local": True,
                        "webdav": False,
                        "storage": "local",
                    }
                }
            })

            with (
                mock.patch("services.config.DATA_DIR", root),
                mock.patch.object(storage, "_save_index", side_effect=OSError("catalog unavailable")),
            ):
                with self.assertRaisesRegex(OSError, "catalog unavailable"):
                    storage.compress_local_images()

            self.assertLess(path.stat().st_size, original_size)
            with mock.patch("services.config.DATA_DIR", root):
                rows = storage.list_items(
                    "",
                    refresh_index=False,
                    verify_existing=True,
                )

            self.assertEqual(rows[0]["size"], path.stat().st_size)
            reconciled = read_json_object(index_path)["items"][rel]
            self.assertEqual(reconciled["size"], path.stat().st_size)
            self.assertNotIn("remote_sync_pending", reconciled)

    def test_compression_does_not_hold_catalog_lock_during_cpu_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index_path = root / "image_index.json"
            storage = ImageStorageService(index_path)
            peer = ImageStorageService(index_path)
            storage._index_lock = threading.Lock()
            peer._index_lock = threading.Lock()
            rel = "2026/07/27/compress.png"
            path = root / "images" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"uncompressed-image")
            compression_started = threading.Event()
            release_compression = threading.Event()
            peer_committed = threading.Event()
            errors: list[BaseException] = []

            def blocked_compression(_payload: bytes) -> bytes:
                compression_started.set()
                release_compression.wait(1)
                return b"png"

            def compress() -> None:
                try:
                    storage.compress_local_images()
                except BaseException as exc:
                    errors.append(exc)

            def update_catalog() -> None:
                try:
                    with peer._index_guard():
                        items = peer._load_clean_index()
                        items["peer.png"] = {"path": "peer.png"}
                        peer._save_index(items)
                    peer_committed.set()
                except BaseException as exc:
                    errors.append(exc)

            with (
                mock.patch("services.config.DATA_DIR", root),
                mock.patch.object(storage, "_compress_png", side_effect=blocked_compression),
            ):
                compression_thread = threading.Thread(target=compress)
                peer_thread = threading.Thread(target=update_catalog)
                compression_thread.start()
                self.assertTrue(compression_started.wait(1))
                peer_thread.start()
                self.assertTrue(peer_committed.wait(0.5))
                release_compression.set()
                compression_thread.join(1)
                peer_thread.join(1)

            self.assertFalse(compression_thread.is_alive())
            self.assertFalse(peer_thread.is_alive())
            self.assertEqual(errors, [])
            items = read_json_object(index_path)["items"]
            self.assertIn("peer.png", items)
            self.assertIn(rel, items)

    def test_compression_catalog_commits_use_bounded_asset_batches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index_path = root / "image_index.json"
            storage = ImageStorageService(index_path)
            rels = [
                f"2026/07/27/compress-{index}.png"
                for index in range(image_storage_module.IMAGE_MUTATION_BATCH_SIZE + 1)
            ]
            for rel in rels:
                path = root / "images" / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"uncompressed-image")

            guarded_batches: list[list[str]] = []

            @contextmanager
            def record_guards(batch):
                guarded_batches.append(list(batch))
                yield

            with (
                mock.patch("services.config.DATA_DIR", root),
                mock.patch.object(storage, "_compress_png", return_value=b"png"),
                mock.patch.object(storage, "_item_guards", side_effect=record_guards),
            ):
                result = storage.compress_local_images()

            self.assertEqual(result["compressed"], len(rels))
            self.assertEqual(
                [len(batch) for batch in guarded_batches],
                [image_storage_module.IMAGE_MUTATION_BATCH_SIZE, 1],
            )
            self.assertEqual(set(read_json_object(index_path)["items"]), set(rels))

    def test_disk_threshold_cleanup_updates_catalog_and_preserves_remote_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index_path = root / "image_index.json"
            storage = ImageStorageService(index_path)
            remote_rel = "2026/07/27/remote.png"
            local_rel = "2026/07/27/local.png"
            for rel in (remote_rel, local_rel):
                path = root / "images" / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * MEBIBYTE)
                thumbnail = root / "image_thumbnails" / f"{rel}.png"
                thumbnail.parent.mkdir(parents=True, exist_ok=True)
                thumbnail.write_bytes(b"thumbnail")
            write_json_file(index_path, {
                "items": {
                    remote_rel: {
                        "path": remote_rel,
                        "local": True,
                        "webdav": True,
                        "storage": "both",
                    },
                    local_rel: {
                        "path": local_rel,
                        "local": True,
                        "webdav": False,
                        "storage": "local",
                    },
                }
            })

            with (
                mock.patch("services.config.DATA_DIR", root),
                mock.patch.object(image_service, "image_storage_service", storage),
                mock.patch.object(image_service, "remove_tags") as remove_tags,
                mock.patch("shutil.disk_usage", return_value=SimpleNamespace(free=0)),
            ):
                result = image_service.delete_to_target(2)

            self.assertEqual(result["removed"], 2)
            self.assertEqual(result["freed_mb"], 2)
            self.assertTrue(result["done"])
            self.assertFalse((root / "images" / remote_rel).exists())
            self.assertFalse((root / "images" / local_rel).exists())
            self.assertFalse((root / "image_thumbnails" / f"{remote_rel}.png").exists())
            self.assertFalse((root / "image_thumbnails" / f"{local_rel}.png").exists())
            remove_tags.assert_called_once_with(local_rel)
            items = read_json_object(index_path)["items"]
            self.assertEqual(set(items), {remote_rel})
            self.assertFalse(items[remote_rel]["local"])
            self.assertTrue(items[remote_rel]["webdav"])
            self.assertEqual(items[remote_rel]["storage"], "webdav")

    def test_disk_cleanup_keeps_local_copy_while_remote_sync_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index_path = root / "image_index.json"
            storage = ImageStorageService(index_path)
            rel = "2026/07/27/pending.png"
            path = root / "images" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"new-local-content")
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "size": path.stat().st_size,
                        "local": True,
                        "webdav": True,
                        "storage": "both",
                        "remote_sync_pending": True,
                    }
                }
            })

            with mock.patch("services.config.DATA_DIR", root):
                removed = storage.delete_local_copies([rel])

            self.assertEqual(removed, {})
            self.assertTrue(path.is_file())
            item = read_json_object(index_path)["items"][rel]
            self.assertTrue(item["local"])
            self.assertTrue(item["webdav"])
            self.assertTrue(item["remote_sync_pending"])

    def test_disk_threshold_cleanup_skips_pending_oldest_and_keeps_scanning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index_path = root / "image_index.json"
            storage = ImageStorageService(index_path)
            pending_rel = "2026/07/27/pending-oldest.png"
            removable_rel = "2026/07/27/removable-next.png"
            pending_path = root / "images" / pending_rel
            removable_path = root / "images" / removable_rel
            for path in (pending_path, removable_path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * MEBIBYTE)
            os.utime(pending_path, (1, 1))
            os.utime(removable_path, (2, 2))
            write_json_file(index_path, {
                "items": {
                    pending_rel: {
                        "path": pending_rel,
                        "size": MEBIBYTE,
                        "local": True,
                        "webdav": True,
                        "storage": "both",
                        "remote_sync_pending": True,
                    },
                    removable_rel: {
                        "path": removable_rel,
                        "size": MEBIBYTE,
                        "local": True,
                        "webdav": False,
                        "storage": "local",
                    },
                }
            })

            with (
                mock.patch("services.config.DATA_DIR", root),
                mock.patch.object(image_service, "image_storage_service", storage),
                mock.patch.object(image_service, "remove_tags") as remove_tags,
                mock.patch("shutil.disk_usage", return_value=SimpleNamespace(free=0)),
            ):
                preview = image_service.delete_to_target(1, dry_run=True)
                result = image_service.delete_to_target(1)

            self.assertEqual(preview["removed"], 1)
            self.assertEqual(preview["freed_mb"], 1)
            self.assertTrue(preview["done"])
            self.assertEqual(result["removed"], 1)
            self.assertEqual(result["freed_mb"], 1)
            self.assertTrue(result["done"])
            self.assertTrue(pending_path.is_file())
            self.assertFalse(removable_path.exists())
            remove_tags.assert_called_once_with(removable_rel)

    def test_disk_cleanup_protects_unreconciled_local_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            index_path = root / "image_index.json"
            storage = ImageStorageService(index_path)
            rel = "2026/07/27/unreconciled.png"
            path = root / "images" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"new-local-content")
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "size": len(b"old-content"),
                        "local": True,
                        "webdav": False,
                        "storage": "local",
                    }
                }
            })

            with mock.patch("services.config.DATA_DIR", root):
                removals = storage.delete_local_copies_until([rel], 1)

            self.assertEqual(removals, [])
            self.assertTrue(path.is_file())

    def test_disk_threshold_dry_run_does_not_mutate_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rel = "2026/07/27/dry-run.png"
            path = root / "images" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * MEBIBYTE)
            storage = ImageStorageService(root / "image_index.json")

            with (
                mock.patch("services.config.DATA_DIR", root),
                mock.patch.object(image_service, "image_storage_service", storage),
                mock.patch.object(storage, "delete_local_copies") as delete_local_copies,
                mock.patch("shutil.disk_usage", return_value=SimpleNamespace(free=0)),
            ):
                result = image_service.delete_to_target(1, dry_run=True)

            delete_local_copies.assert_not_called()
            self.assertTrue(path.is_file())
            self.assertEqual(result["removed"], 1)
            self.assertEqual(result["freed_mb"], 1)
            self.assertTrue(result["dry_run"])


if __name__ == "__main__":
    unittest.main()
