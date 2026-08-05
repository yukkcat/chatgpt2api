from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from services import image_service
from services import image_storage_service as image_storage_module
from services import image_tags_service
from services.image_storage_service import ImageBatchDeleteError, ImageStorageError, ImageStorageService
from services.json_file import read_json_object, write_json_file


def delete_tombstone(
    generation: str,
    *,
    op_id: str = "delete-op",
    scope: str = "asset",
    remote: bool = True,
) -> dict[str, object]:
    return {
        "op_id": op_id,
        "generation": generation,
        "scope": scope,
        "remote": remote,
        "requested_at": "2026-07-27 12:00:00",
    }


class ImageCatalogConcurrencyTests(unittest.TestCase):
    def test_batch_delete_commits_catalog_once_and_preserves_unrelated_items(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            first = "2026/07/27/first.png"
            second = "2026/07/27/second.png"
            untouched = "2026/07/27/untouched.png"
            for rel in (first, second, untouched):
                path = root / "images" / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(rel.encode("utf-8"))
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": True,
                        "webdav": False,
                        "generation": f"generation-{Path(rel).stem}",
                    }
                    for rel in (first, second, untouched)
                }
            })

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "_save_index", wraps=service._save_index) as save_index,
            ):
                removed = service.delete_many([first, second, first])

            self.assertEqual(removed, {first, second})
            self.assertEqual(save_index.call_count, 1)
            self.assertFalse((root / "images" / first).exists())
            self.assertFalse((root / "images" / second).exists())
            self.assertTrue((root / "images" / untouched).is_file())
            self.assertEqual(set(read_json_object(index_path)["items"]), {untouched})
            self.assertEqual(
                read_json_object(service._remote_delete_file).get("items", {}),
                {},
            )

    def test_batch_delete_commits_completed_items_before_reraising_remote_failure(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            first = "2026/07/27/first.png"
            second = "2026/07/27/second.png"
            first_path = root / "images" / first
            first_path.parent.mkdir(parents=True)
            first_path.write_bytes(b"first")
            write_json_file(index_path, {
                "items": {
                    first: {
                        "path": first,
                        "local": True,
                        "webdav": True,
                        "generation": "generation-first",
                    },
                    second: {
                        "path": second,
                        "local": False,
                        "webdav": True,
                        "generation": "generation-second",
                    },
                }
            })

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "settings", return_value={}),
                patch.object(service, "_save_index", wraps=service._save_index) as save_index,
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                    side_effect=ImageStorageError("remote delete failed"),
                ),
            ):
                with self.assertRaises(ImageBatchDeleteError) as raised:
                    service.delete_many([first, second])

            self.assertEqual(raised.exception.completed_rels, {first})
            self.assertIsInstance(raised.exception.cause, ImageStorageError)
            self.assertEqual(save_index.call_count, 1)
            self.assertFalse(first_path.exists())
            self.assertEqual(set(read_json_object(index_path)["items"]), {second})
            pending = read_json_object(service._remote_delete_file)["items"]
            self.assertEqual(set(pending), {first, second})
            self.assertEqual(pending[first]["generation"], "generation-first")
            self.assertEqual(pending[second]["generation"], "generation-second")
            self.assertEqual(pending[first]["scope"], "asset")
            self.assertTrue(pending[first]["remote"])

    def test_batch_delete_reports_completed_items_when_catalog_commit_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            rel = "2026/07/27/first.png"
            image_path = root / "images" / rel
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"first")
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": True,
                        "webdav": False,
                        "generation": "generation-first",
                    }
                }
            })

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "_save_index", side_effect=OSError("catalog write failed")),
            ):
                with self.assertRaises(ImageBatchDeleteError) as raised:
                    service.delete_many([rel])

            self.assertEqual(raised.exception.completed_rels, {rel})
            self.assertIsInstance(raised.exception.cause, OSError)
            self.assertFalse(image_path.exists())

    def test_batch_delete_catalog_failure_is_recovered_by_next_sync(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            rel = "2026/07/27/catalog-recovery.png"
            image_path = root / "images" / rel
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"image")
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "size": len(b"image"),
                        "local": True,
                        "webdav": True,
                        "storage": "both",
                        "generation": "generation-recovery",
                    }
                }
            })

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "settings", return_value={}),
                patch.object(service, "_save_index", side_effect=OSError("catalog write failed")),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                    return_value=True,
                ),
            ):
                with self.assertRaises(ImageBatchDeleteError):
                    service.delete_many([rel])

            self.assertFalse(image_path.exists())
            self.assertIn(rel, read_json_object(index_path)["items"])
            pending = read_json_object(service._remote_delete_file)["items"]
            self.assertEqual(set(pending), {rel})
            self.assertEqual(pending[rel]["generation"], "generation-recovery")

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "mode", return_value="both"),
                patch.object(service, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                    return_value=False,
                ),
            ):
                result = service.sync_all()

            self.assertEqual(result, {"uploaded": 0, "skipped": 0, "failed": 0})
            self.assertNotIn(rel, read_json_object(index_path)["items"])
            self.assertEqual(read_json_object(service._remote_delete_file)["items"], {})

    def test_successful_delete_persists_tombstone_before_destructive_io(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            rel = "2026/07/27/durable-before-delete.png"
            image_path = root / "images" / rel
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"image")
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": True,
                        "webdav": True,
                        "generation": "generation-durable",
                    }
                }
            })
            observed_steps: list[str] = []

            def assert_durable(step: str) -> None:
                pending = read_json_object(service._remote_delete_file)["items"]
                self.assertEqual(set(pending), {rel})
                self.assertEqual(pending[rel]["generation"], "generation-durable")
                self.assertEqual(pending[rel]["scope"], "asset")
                self.assertTrue(pending[rel]["remote"])
                self.assertTrue(pending[rel]["op_id"])
                self.assertTrue(pending[rel]["requested_at"])
                observed_steps.append(step)

            class ObservedPath:
                def is_file(self) -> bool:
                    return image_path.is_file()

                def exists(self) -> bool:
                    return image_path.exists()

                def unlink(self) -> None:
                    assert_durable("local")
                    image_path.unlink()

            def delete_remote(_client, delete_rel: str) -> bool:
                self.assertEqual(delete_rel, rel)
                assert_durable("remote")
                return True

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "settings", return_value={}),
                patch.object(
                    image_storage_module,
                    "image_local_path",
                    return_value=ObservedPath(),
                ),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                    side_effect=delete_remote,
                ),
            ):
                self.assertTrue(service.delete(rel))

            self.assertEqual(observed_steps, ["local", "remote"])
            self.assertNotIn(rel, read_json_object(index_path)["items"])
            self.assertEqual(read_json_object(service._remote_delete_file)["items"], {})

    def test_crash_after_remote_delete_before_catalog_commit_is_recovered(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            rel = "2026/07/27/crash-window.png"
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": False,
                        "webdav": True,
                        "generation": "generation-crash-window",
                    }
                }
            })

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                    return_value=True,
                ) as delete_remote,
                patch.object(service, "_finalize_delete_batch", side_effect=SystemExit("crash")),
            ):
                with self.assertRaises(SystemExit):
                    service.delete_many([rel])

            delete_remote.assert_called_once()
            pending = read_json_object(service._remote_delete_file)["items"]
            self.assertEqual(set(pending), {rel})
            self.assertIn(rel, read_json_object(index_path)["items"])

            recovery = ImageStorageService(index_path)
            recovery._index_lock = threading.Lock()
            with (
                patch("services.config.DATA_DIR", root),
                patch.object(recovery, "mode", return_value="both"),
                patch.object(recovery, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                    return_value=False,
                ) as retry_delete,
            ):
                result = recovery.sync_all()

            self.assertEqual(result, {"uploaded": 0, "skipped": 0, "failed": 0})
            retry_delete.assert_called_once()
            self.assertNotIn(rel, read_json_object(index_path)["items"])
            self.assertEqual(read_json_object(service._remote_delete_file)["items"], {})

    def test_webdav_only_save_supersedes_old_delete_tombstone(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            rel = "2026/07/27/webdav-resave.png"
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": False,
                        "webdav": True,
                        "generation": "generation-old",
                    }
                }
            })
            write_json_file(service._remote_delete_file, {
                "items": {
                    rel: delete_tombstone(
                        "generation-old",
                        op_id="old-delete",
                    )
                }
            })

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "make_relative_path", return_value=rel),
                patch.object(service, "mode", return_value="webdav"),
                patch.object(service, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "put",
                    autospec=True,
                    return_value=f"https://webdav.test/{rel}",
                ),
            ):
                service.save(b"new-image", "http://localhost")

            item = read_json_object(index_path)["items"][rel]
            self.assertNotEqual(item["generation"], "generation-old")
            self.assertTrue(item["webdav"])
            self.assertFalse(item["local"])
            self.assertEqual(read_json_object(service._remote_delete_file)["items"], {})

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "mode", return_value="both"),
                patch.object(service, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                ) as delete_remote,
            ):
                service.sync_all()
            delete_remote.assert_not_called()
            self.assertEqual(
                read_json_object(index_path)["items"][rel]["generation"],
                item["generation"],
            )

    def test_save_after_delete_io_before_final_commit_survives(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            deleting = ImageStorageService(index_path)
            saving = ImageStorageService(index_path)
            deleting._index_lock = threading.Lock()
            saving._index_lock = threading.Lock()
            rel = "2026/07/27/save-before-finalize.png"
            image_path = root / "images" / rel
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"old-image")
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": True,
                        "webdav": False,
                        "generation": "generation-old",
                    }
                }
            })
            finalize_entered = threading.Event()
            release_finalize = threading.Event()
            errors: list[BaseException] = []
            original_finalize = deleting._finalize_delete_batch

            def blocked_finalize(planned, results) -> None:
                finalize_entered.set()
                release_finalize.wait(1)
                original_finalize(planned, results)

            def run_delete() -> None:
                try:
                    deleting.delete_many([rel])
                except BaseException as exc:
                    errors.append(exc)

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(deleting, "_finalize_delete_batch", side_effect=blocked_finalize),
                patch.object(saving, "make_relative_path", return_value=rel),
                patch.object(saving, "mode", return_value="local"),
            ):
                delete_thread = threading.Thread(target=run_delete)
                delete_thread.start()
                self.assertTrue(finalize_entered.wait(1))
                saved = saving.save(b"new-image", "http://localhost")
                generation = read_json_object(index_path)["items"][rel]["generation"]
                release_finalize.set()
                delete_thread.join(1)

            self.assertFalse(delete_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(saved.rel, rel)
            self.assertEqual(image_path.read_bytes(), b"new-image")
            self.assertNotEqual(generation, "generation-old")
            self.assertEqual(
                read_json_object(index_path)["items"][rel]["generation"],
                generation,
            )
            self.assertEqual(read_json_object(deleting._remote_delete_file)["items"], {})

    def test_generation_change_before_item_lock_skips_old_delete(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            deleting = ImageStorageService(index_path)
            saving = ImageStorageService(index_path)
            deleting._index_lock = threading.Lock()
            saving._index_lock = threading.Lock()
            rel = "2026/07/27/generation-race.png"
            image_path = root / "images" / rel
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"old-image")
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": True,
                        "webdav": False,
                        "generation": "generation-old",
                    }
                }
            })
            mutation_entered = threading.Event()
            release_mutation = threading.Event()
            errors: list[BaseException] = []
            original_mutation = deleting._mutate_delete_tombstone

            def blocked_mutation(delete_rel, tombstone, client):
                mutation_entered.set()
                release_mutation.wait(1)
                return original_mutation(delete_rel, tombstone, client)

            def run_delete() -> None:
                try:
                    deleting.delete_many([rel])
                except BaseException as exc:
                    errors.append(exc)

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(deleting, "_mutate_delete_tombstone", side_effect=blocked_mutation),
                patch.object(saving, "make_relative_path", return_value=rel),
                patch.object(saving, "mode", return_value="local"),
            ):
                delete_thread = threading.Thread(target=run_delete)
                delete_thread.start()
                self.assertTrue(mutation_entered.wait(1))
                saving.save(b"new-image", "http://localhost")
                generation = read_json_object(index_path)["items"][rel]["generation"]
                release_mutation.set()
                delete_thread.join(1)

            self.assertFalse(delete_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(image_path.read_bytes(), b"new-image")
            self.assertNotEqual(generation, "generation-old")
            self.assertEqual(
                read_json_object(index_path)["items"][rel]["generation"],
                generation,
            )
            self.assertEqual(read_json_object(deleting._remote_delete_file)["items"], {})

    def test_image_delete_wrapper_uses_one_batch_and_preserves_response(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images_dir = root / "images"
            thumbnails_dir = root / "image_thumbnails"
            images_dir.mkdir()
            thumbnails_dir.mkdir()
            first = "2026/07/27/first.png"
            second = "2026/07/27/second.png"
            fake_config = SimpleNamespace(
                images_dir=images_dir,
                image_thumbnails_dir=thumbnails_dir,
            )

            with (
                patch.object(image_service, "config", fake_config),
                patch.object(image_service, "image_storage_service") as storage,
                patch.object(image_service, "remove_tags") as remove_tags,
            ):
                storage.delete_many.return_value = {first}
                result = image_service.delete_images([first, second])

            storage.delete_many.assert_called_once_with([first, second])
            self.assertEqual(remove_tags.call_count, 2)
            self.assertEqual(result, {"removed": 1})

    def test_image_delete_wrapper_cleans_completed_items_before_reraising_batch_error(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            images_dir = root / "images"
            thumbnails_dir = root / "image_thumbnails"
            images_dir.mkdir()
            thumbnails_dir.mkdir()
            first = "2026/07/27/first.png"
            second = "2026/07/27/second.png"
            first_thumbnail = thumbnails_dir / f"{first}.png"
            second_thumbnail = thumbnails_dir / f"{second}.png"
            first_thumbnail.parent.mkdir(parents=True)
            first_thumbnail.write_bytes(b"first")
            second_thumbnail.write_bytes(b"second")
            fake_config = SimpleNamespace(
                images_dir=images_dir,
                image_thumbnails_dir=thumbnails_dir,
            )
            cause = ImageStorageError("remote delete failed")

            with (
                patch.object(image_service, "config", fake_config),
                patch.object(image_service, "image_storage_service") as storage,
                patch.object(image_service, "remove_tags") as remove_tags,
            ):
                storage.delete_many.side_effect = ImageBatchDeleteError(cause, {first})
                with self.assertRaisesRegex(ImageStorageError, "remote delete failed"):
                    image_service.delete_images([first, second])

            remove_tags.assert_called_once_with(first)
            self.assertFalse(first_thumbnail.exists())
            self.assertTrue(second_thumbnail.is_file())

    def test_independent_service_instances_serialize_index_mutations(self) -> None:
        with TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "image_index.json"
            first = ImageStorageService(index_path)
            second = ImageStorageService(index_path)
            first._index_lock = threading.Lock()
            second._index_lock = threading.Lock()
            first_entered = threading.Event()
            release_first = threading.Event()
            second_entered = threading.Event()

            def mutate(service: ImageStorageService, key: str, *, block: bool) -> None:
                with service._index_guard():
                    if block:
                        first_entered.set()
                        release_first.wait(1)
                    else:
                        second_entered.set()
                    items = service._load_clean_index()
                    items[key] = {"path": key}
                    service._save_index(items)

            first_thread = threading.Thread(
                target=mutate,
                args=(first, "first.png"),
                kwargs={"block": True},
            )
            second_thread = threading.Thread(
                target=mutate,
                args=(second, "second.png"),
                kwargs={"block": False},
            )
            first_thread.start()
            self.assertTrue(first_entered.wait(1))
            second_thread.start()
            self.assertFalse(second_entered.wait(0.05))
            release_first.set()
            first_thread.join(1)
            second_thread.join(1)

            self.assertFalse(first_thread.is_alive())
            self.assertFalse(second_thread.is_alive())
            self.assertEqual(
                set(read_json_object(index_path).get("items", {})),
                {"first.png", "second.png"},
            )

    def test_independent_tag_locks_preserve_concurrent_updates(self) -> None:
        with TemporaryDirectory() as tmp:
            tags_path = Path(tmp) / "image_tags.json"
            lock_path = tags_path.with_suffix(tags_path.suffix + ".lock")
            first_read = threading.Event()
            release_first = threading.Event()
            original_read = image_tags_service.read_json_object

            def controlled_read(path: Path, *, name: str | None = None):
                if threading.current_thread().name == "first-tag-writer":
                    first_read.set()
                    release_first.wait(1)
                return original_read(path, name=name)

            with (
                patch.object(image_tags_service, "TAGS_FILE", tags_path),
                patch.object(image_tags_service, "TAGS_FILE_LOCK", lock_path),
                patch.object(image_tags_service, "TAGS_LOCK", threading.Lock()),
                patch.object(image_tags_service, "read_json_object", side_effect=controlled_read),
            ):
                first_thread = threading.Thread(
                    target=image_tags_service.set_tags,
                    args=("first.png", ["first"]),
                    name="first-tag-writer",
                )
                first_thread.start()
                self.assertTrue(first_read.wait(1))

                # A separate process has its own in-memory lock but shares the file lock.
                image_tags_service.TAGS_LOCK = threading.Lock()
                second_thread = threading.Thread(
                    target=image_tags_service.set_tags,
                    args=("second.png", ["second"]),
                    name="second-tag-writer",
                )
                second_thread.start()
                time.sleep(0.05)
                release_first.set()
                first_thread.join(1)
                second_thread.join(1)

            self.assertFalse(first_thread.is_alive())
            self.assertFalse(second_thread.is_alive())
            self.assertEqual(
                read_json_object(tags_path),
                {"first.png": ["first"], "second.png": ["second"]},
            )

    def test_delete_waits_for_same_image_save_to_commit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            first = ImageStorageService(index_path)
            second = ImageStorageService(index_path)
            first._index_lock = threading.Lock()
            second._index_lock = threading.Lock()
            rel = "2026/07/26/shared.png"
            save_entered = threading.Event()
            release_save = threading.Event()
            errors: list[BaseException] = []
            original_save_index = first._save_index

            def blocked_save_index(items: dict[str, dict[str, object]]) -> None:
                save_entered.set()
                release_save.wait(1)
                original_save_index(items)

            def save_image() -> None:
                try:
                    first.save(b"same-image", "http://localhost")
                except BaseException as exc:
                    errors.append(exc)

            def delete_image() -> None:
                try:
                    second.delete(rel)
                except BaseException as exc:
                    errors.append(exc)

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(first, "make_relative_path", return_value=rel),
                patch.object(first, "mode", return_value="local"),
                patch.object(first, "_save_index", side_effect=blocked_save_index),
            ):
                save_thread = threading.Thread(target=save_image)
                delete_thread = threading.Thread(target=delete_image)
                save_thread.start()
                self.assertTrue(save_entered.wait(1))
                delete_thread.start()
                time.sleep(0.05)
                self.assertTrue((root / "images" / rel).is_file())
                self.assertTrue(delete_thread.is_alive())
                release_save.set()
                save_thread.join(1)
                delete_thread.join(1)

            self.assertFalse(save_thread.is_alive())
            self.assertFalse(delete_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertFalse((root / "images" / rel).exists())
            self.assertNotIn(rel, read_json_object(index_path).get("items", {}))

    def test_save_waits_for_same_image_delete_to_commit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            first = ImageStorageService(index_path)
            second = ImageStorageService(index_path)
            first._index_lock = threading.Lock()
            second._index_lock = threading.Lock()
            rel = "2026/07/26/shared.png"
            image_path = root / "images" / rel
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"old-image")
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": True,
                        "webdav": False,
                        "generation": "generation-old",
                    }
                }
            })
            delete_entered = threading.Event()
            release_delete = threading.Event()
            errors: list[BaseException] = []
            original_save_index = first._save_index

            def blocked_save_index(items: dict[str, dict[str, object]]) -> None:
                delete_entered.set()
                release_delete.wait(1)
                original_save_index(items)

            def delete_image() -> None:
                try:
                    first.delete(rel)
                except BaseException as exc:
                    errors.append(exc)

            def save_image() -> None:
                try:
                    second.save(b"new-image", "http://localhost")
                except BaseException as exc:
                    errors.append(exc)

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(first, "_save_index", side_effect=blocked_save_index),
                patch.object(second, "make_relative_path", return_value=rel),
                patch.object(second, "mode", return_value="local"),
            ):
                delete_thread = threading.Thread(target=delete_image)
                save_thread = threading.Thread(target=save_image)
                delete_thread.start()
                self.assertTrue(delete_entered.wait(1))
                save_thread.start()
                time.sleep(0.05)
                self.assertFalse(image_path.exists())
                self.assertTrue(save_thread.is_alive())
                release_delete.set()
                delete_thread.join(1)
                save_thread.join(1)

            self.assertFalse(delete_thread.is_alive())
            self.assertFalse(save_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(image_path.read_bytes(), b"new-image")
            self.assertTrue(read_json_object(index_path)["items"][rel]["local"])

    def test_webdav_sync_does_not_hold_index_lock_during_upload(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            peer = ImageStorageService(index_path)
            service._index_lock = threading.Lock()
            peer._index_lock = threading.Lock()
            rel = "2026/07/26/sync.png"
            image_path = root / "images" / rel
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"sync-image")
            upload_entered = threading.Event()
            release_upload = threading.Event()
            peer_committed = threading.Event()
            errors: list[BaseException] = []

            def blocked_put(_client, upload_rel: str, _payload: bytes, content_type: str = "image/png") -> str:
                del content_type
                self.assertEqual(upload_rel, rel)
                upload_entered.set()
                release_upload.wait(1)
                return f"https://webdav.test/{upload_rel}"

            def run_sync() -> None:
                try:
                    service.sync_all()
                except BaseException as exc:
                    errors.append(exc)

            def mutate_index() -> None:
                try:
                    with peer._index_guard():
                        items = peer._load_clean_index()
                        items["peer.png"] = {"path": "peer.png"}
                        peer._save_index(items)
                    peer_committed.set()
                except BaseException as exc:
                    errors.append(exc)

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "mode", return_value="both"),
                patch.object(service, "settings", return_value={}),
                patch.object(image_storage_module.WebDAVClient, "put", autospec=True, side_effect=blocked_put),
            ):
                sync_thread = threading.Thread(target=run_sync)
                peer_thread = threading.Thread(target=mutate_index)
                sync_thread.start()
                self.assertTrue(upload_entered.wait(1))
                peer_thread.start()
                self.assertTrue(peer_committed.wait(0.5))
                release_upload.set()
                sync_thread.join(1)
                peer_thread.join(1)

            self.assertFalse(sync_thread.is_alive())
            self.assertFalse(peer_thread.is_alive())
            self.assertEqual(errors, [])
            items = read_json_object(index_path)["items"]
            self.assertIn("peer.png", items)
            self.assertTrue(items[rel]["webdav"])

    def test_webdav_delete_does_not_hold_index_lock_during_remote_request(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            peer = ImageStorageService(index_path)
            service._index_lock = threading.Lock()
            peer._index_lock = threading.Lock()
            rel = "2026/07/26/remote.png"
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "webdav": True,
                        "local": False,
                        "generation": "generation-remote",
                    }
                }
            })
            delete_entered = threading.Event()
            release_delete = threading.Event()
            peer_committed = threading.Event()
            errors: list[BaseException] = []

            def blocked_delete(_client, delete_rel: str) -> bool:
                self.assertEqual(delete_rel, rel)
                delete_entered.set()
                release_delete.wait(1)
                return True

            def delete_image() -> None:
                try:
                    service.delete(rel)
                except BaseException as exc:
                    errors.append(exc)

            def mutate_index() -> None:
                try:
                    with peer._index_guard():
                        items = peer._load_clean_index()
                        items["peer.png"] = {"path": "peer.png"}
                        peer._save_index(items)
                    peer_committed.set()
                except BaseException as exc:
                    errors.append(exc)

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "settings", return_value={}),
                patch.object(image_storage_module.WebDAVClient, "delete", autospec=True, side_effect=blocked_delete),
            ):
                delete_thread = threading.Thread(target=delete_image)
                peer_thread = threading.Thread(target=mutate_index)
                delete_thread.start()
                self.assertTrue(delete_entered.wait(1))
                peer_thread.start()
                self.assertTrue(peer_committed.wait(0.5))
                release_delete.set()
                delete_thread.join(1)
                peer_thread.join(1)

            self.assertFalse(delete_thread.is_alive())
            self.assertFalse(peer_thread.is_alive())
            self.assertEqual(errors, [])
            items = read_json_object(index_path)["items"]
            self.assertIn("peer.png", items)
            self.assertNotIn(rel, items)

    def test_batch_webdav_delete_does_not_hold_index_lock_during_remote_request(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            peer = ImageStorageService(index_path)
            service._index_lock = threading.Lock()
            peer._index_lock = threading.Lock()
            rel = "2026/07/26/remote.png"
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "webdav": True,
                        "local": False,
                        "generation": "generation-remote",
                    }
                }
            })
            delete_entered = threading.Event()
            release_delete = threading.Event()
            peer_committed = threading.Event()
            errors: list[BaseException] = []

            def blocked_delete(_client, delete_rel: str) -> bool:
                self.assertEqual(delete_rel, rel)
                delete_entered.set()
                release_delete.wait(1)
                return True

            def delete_images() -> None:
                try:
                    service.delete_many([rel])
                except BaseException as exc:
                    errors.append(exc)

            def mutate_index() -> None:
                try:
                    with peer._index_guard():
                        items = peer._load_clean_index()
                        items["peer.png"] = {"path": "peer.png"}
                        peer._save_index(items)
                    peer_committed.set()
                except BaseException as exc:
                    errors.append(exc)

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "settings", return_value={}),
                patch.object(image_storage_module.WebDAVClient, "delete", autospec=True, side_effect=blocked_delete),
            ):
                delete_thread = threading.Thread(target=delete_images)
                peer_thread = threading.Thread(target=mutate_index)
                delete_thread.start()
                self.assertTrue(delete_entered.wait(1))
                peer_thread.start()
                self.assertTrue(peer_committed.wait(0.5))
                release_delete.set()
                delete_thread.join(1)
                peer_thread.join(1)

            self.assertFalse(delete_thread.is_alive())
            self.assertFalse(peer_thread.is_alive())
            self.assertEqual(errors, [])
            items = read_json_object(index_path)["items"]
            self.assertIn("peer.png", items)
            self.assertNotIn(rel, items)

    def test_blocking_remote_delete_holds_only_current_item_lock(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            peer = ImageStorageService(index_path)
            service._index_lock = threading.Lock()
            peer._index_lock = threading.Lock()
            blocked_rel = "2026/07/27/batch-blocked.png"
            candidate = 0
            while True:
                peer_rel = f"2026/07/27/batch-peer-{candidate}.png"
                candidate += 1
                if service._item_lock_path(peer_rel) != service._item_lock_path(blocked_rel):
                    break

            targets = [blocked_rel, peer_rel]
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": False,
                        "webdav": True,
                        "generation": f"generation-{Path(rel).stem}",
                    }
                    for rel in targets
                }
            })
            delete_entered = threading.Event()
            release_delete = threading.Event()
            peer_committed = threading.Event()
            errors: list[BaseException] = []

            def blocked_delete(_client, delete_rel: str) -> bool:
                if delete_rel == blocked_rel:
                    delete_entered.set()
                    release_delete.wait(1)
                    return True
                self.fail(f"new generation was deleted: {delete_rel}")

            def run_delete() -> None:
                try:
                    service.delete_many(targets)
                except BaseException as exc:
                    errors.append(exc)

            def mutate_peer() -> None:
                try:
                    peer.save(b"new-peer-image", "http://localhost")
                    peer_committed.set()
                except BaseException as exc:
                    errors.append(exc)

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "settings", return_value={}),
                patch.object(peer, "make_relative_path", return_value=peer_rel),
                patch.object(peer, "mode", return_value="webdav"),
                patch.object(peer, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "put",
                    autospec=True,
                    return_value=f"https://webdav.test/{peer_rel}",
                ),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                    side_effect=blocked_delete,
                ),
            ):
                delete_thread = threading.Thread(target=run_delete)
                peer_thread = threading.Thread(target=mutate_peer)
                delete_thread.start()
                self.assertTrue(delete_entered.wait(1))
                peer_thread.start()
                self.assertTrue(peer_committed.wait(0.5))
                release_delete.set()
                delete_thread.join(2)
                peer_thread.join(1)

            self.assertFalse(delete_thread.is_alive())
            self.assertFalse(peer_thread.is_alive())
            self.assertEqual(errors, [])
            items = read_json_object(index_path)["items"]
            self.assertNotIn(blocked_rel, items)
            self.assertIn(peer_rel, items)
            self.assertNotEqual(
                items[peer_rel]["generation"],
                f"generation-{Path(peer_rel).stem}",
            )

    def test_sync_reuploads_current_content_after_same_path_save(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            sync_service = ImageStorageService(index_path)
            save_service = ImageStorageService(index_path)
            sync_service._index_lock = threading.Lock()
            save_service._index_lock = threading.Lock()
            rel = "2026/07/26/shared.png"
            image_path = root / "images" / rel
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"old-image")
            first_upload_entered = threading.Event()
            release_first_upload = threading.Event()
            remote_payload: list[bytes] = []
            sync_result: list[dict[str, int]] = []
            errors: list[BaseException] = []

            def controlled_put(_client, upload_rel: str, payload: bytes, content_type: str = "image/png") -> str:
                del content_type
                self.assertEqual(upload_rel, rel)
                if payload == b"old-image":
                    first_upload_entered.set()
                    release_first_upload.wait(1)
                remote_payload[:] = [payload]
                return f"https://webdav.test/{upload_rel}"

            def run_sync() -> None:
                try:
                    sync_result.append(sync_service.sync_all())
                except BaseException as exc:
                    errors.append(exc)

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(sync_service, "mode", return_value="both"),
                patch.object(sync_service, "settings", return_value={}),
                patch.object(save_service, "make_relative_path", return_value=rel),
                patch.object(save_service, "mode", return_value="both"),
                patch.object(save_service, "settings", return_value={}),
                patch.object(image_storage_module.WebDAVClient, "put", autospec=True, side_effect=controlled_put),
            ):
                sync_thread = threading.Thread(target=run_sync)
                sync_thread.start()
                self.assertTrue(first_upload_entered.wait(1))
                save_service.save(b"new-image", "http://localhost")
                release_first_upload.set()
                sync_thread.join(2)

            self.assertFalse(sync_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(sync_result, [{"uploaded": 1, "skipped": 0, "failed": 0}])
            self.assertEqual(remote_payload, [b"new-image"])
            item = read_json_object(index_path)["items"][rel]
            self.assertEqual(item["size"], len(b"new-image"))
            self.assertTrue(item["webdav"])
            self.assertNotIn("remote_sync_pending", item)

    def test_sync_repair_failure_preserves_known_remote_copy(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            sync_service = ImageStorageService(index_path)
            save_service = ImageStorageService(index_path)
            sync_service._index_lock = threading.Lock()
            save_service._index_lock = threading.Lock()
            rel = "2026/07/26/pending-repair.png"
            image_path = root / "images" / rel
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"old-image")
            first_upload_entered = threading.Event()
            release_first_upload = threading.Event()
            uploaded: list[bytes] = []

            def controlled_put(
                _client,
                upload_rel: str,
                payload: bytes,
                content_type: str = "image/png",
            ) -> str:
                del content_type
                self.assertEqual(upload_rel, rel)
                uploaded.append(payload)
                if payload == b"old-image":
                    first_upload_entered.set()
                    release_first_upload.wait(1)
                    return f"https://webdav.test/{upload_rel}"
                raise ImageStorageError("repair upload failed")

            result: list[dict[str, int]] = []
            errors: list[BaseException] = []

            def run_sync() -> None:
                try:
                    result.append(sync_service.sync_all())
                except BaseException as exc:
                    errors.append(exc)

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(sync_service, "mode", return_value="both"),
                patch.object(sync_service, "settings", return_value={}),
                patch.object(save_service, "make_relative_path", return_value=rel),
                patch.object(save_service, "mode", return_value="local"),
                patch.object(save_service, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "put",
                    autospec=True,
                    side_effect=controlled_put,
                ),
            ):
                sync_thread = threading.Thread(target=run_sync)
                sync_thread.start()
                self.assertTrue(first_upload_entered.wait(1))
                save_service.save(b"new-image", "http://localhost")
                release_first_upload.set()
                sync_thread.join(2)

            self.assertFalse(sync_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(result, [{"uploaded": 0, "skipped": 0, "failed": 1}])
            self.assertEqual(uploaded, [b"old-image", b"new-image"])
            item = read_json_object(index_path)["items"][rel]
            self.assertEqual(item["size"], len(b"new-image"))
            self.assertEqual(item["storage"], "both")
            self.assertTrue(item["local"])
            self.assertTrue(item["webdav"])
            self.assertEqual(item["remote_url"], f"https://webdav.test/{rel}")
            self.assertTrue(item["remote_sync_pending"])

    def test_failed_remote_orphan_delete_is_retried_by_next_sync(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            service._index_lock = threading.Lock()
            rel = "2026/07/26/orphan.png"
            image_path = root / "images" / rel
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"orphan-image")
            delete_attempts = 0

            def upload_then_remove_local(
                _client,
                upload_rel: str,
                _payload: bytes,
                content_type: str = "image/png",
            ) -> str:
                del content_type
                self.assertEqual(upload_rel, rel)
                image_path.unlink()
                return f"https://webdav.test/{upload_rel}"

            def flaky_delete(_client, delete_rel: str) -> bool:
                nonlocal delete_attempts
                self.assertEqual(delete_rel, rel)
                delete_attempts += 1
                if delete_attempts == 1:
                    raise ImageStorageError("temporary delete failure")
                return True

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "mode", return_value="both"),
                patch.object(service, "settings", return_value={}),
                patch.object(image_storage_module.WebDAVClient, "put", autospec=True, side_effect=upload_then_remove_local),
                patch.object(image_storage_module.WebDAVClient, "delete", autospec=True, side_effect=flaky_delete),
            ):
                first = service.sync_all()
                pending_after_first = read_json_object(service._remote_delete_file)["items"]
                second = service.sync_all()

            self.assertEqual(first, {"uploaded": 0, "skipped": 0, "failed": 1})
            self.assertEqual(set(pending_after_first), {rel})
            self.assertEqual(pending_after_first[rel]["scope"], "remote")
            self.assertTrue(pending_after_first[rel]["remote"])
            self.assertEqual(second, {"uploaded": 0, "skipped": 0, "failed": 0})
            self.assertEqual(delete_attempts, 2)
            self.assertEqual(read_json_object(service._remote_delete_file)["items"], {})

    def test_delete_persists_remote_retry_after_local_delete_succeeds(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            service._index_lock = threading.Lock()
            rel = "2026/07/26/delete-retry.png"
            image_path = root / "images" / rel
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"local-image")
            index_payload = {
                "items": {
                    rel: {
                        "path": rel,
                        "local": True,
                        "webdav": True,
                        "storage": "both",
                        "generation": "generation-delete-retry",
                    }
                }
            }
            write_json_file(index_path, index_payload)
            delete_attempts = 0

            def flaky_delete(_client, delete_rel: str) -> bool:
                nonlocal delete_attempts
                self.assertEqual(delete_rel, rel)
                delete_attempts += 1
                if delete_attempts == 1:
                    raise ImageStorageError("temporary delete failure")
                return True

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "mode", return_value="both"),
                patch.object(service, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                    side_effect=flaky_delete,
                ),
            ):
                self.assertTrue(service.delete(rel))
                pending_after_delete = read_json_object(service._remote_delete_file)["items"]
                recovery_service = ImageStorageService(index_path)
                recovery_service._index_lock = threading.Lock()
                with (
                    patch.object(recovery_service, "mode", return_value="both"),
                    patch.object(recovery_service, "settings", return_value={}),
                ):
                    sync_result = recovery_service.sync_all()

            self.assertFalse(image_path.exists())
            self.assertNotIn(rel, read_json_object(index_path)["items"])
            self.assertEqual(set(pending_after_delete), {rel})
            self.assertEqual(
                pending_after_delete[rel]["generation"],
                "generation-delete-retry",
            )
            self.assertEqual(pending_after_delete[rel]["scope"], "asset")
            self.assertTrue(pending_after_delete[rel]["remote"])
            self.assertTrue(pending_after_delete[rel]["op_id"])
            self.assertTrue(pending_after_delete[rel]["requested_at"])
            self.assertEqual(sync_result, {"uploaded": 0, "skipped": 0, "failed": 0})
            self.assertEqual(delete_attempts, 2)
            self.assertEqual(read_json_object(service._remote_delete_file)["items"], {})

    def test_delete_persists_remote_retry_after_transport_failure(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            rel = "2026/07/26/delete-timeout.png"
            image_path = root / "images" / rel
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"local-image")
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": True,
                        "webdav": True,
                        "storage": "both",
                        "generation": "generation-timeout",
                    }
                }
            })

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                    side_effect=TimeoutError("WebDAV timed out"),
                ),
            ):
                removed = service.delete_many([rel])

            self.assertEqual(removed, {rel})
            self.assertFalse(image_path.exists())
            self.assertNotIn(rel, read_json_object(index_path)["items"])
            pending = read_json_object(service._remote_delete_file)["items"]
            self.assertEqual(set(pending), {rel})
            self.assertEqual(pending[rel]["generation"], "generation-timeout")
            self.assertEqual(pending[rel]["scope"], "asset")

    def test_repeated_delete_preserves_existing_remote_retry_intent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            rel = "2026/07/26/repeated-delete.png"
            write_json_file(index_path, {"items": {}})
            write_json_file(service._remote_delete_file, {
                "items": {
                    rel: delete_tombstone(
                        "generation-deleted",
                        op_id="first-delete",
                    )
                }
            })

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                    side_effect=ImageStorageError("still unavailable"),
                ),
            ):
                with self.assertRaises(ImageBatchDeleteError):
                    service.delete_many([rel])

            pending = read_json_object(service._remote_delete_file)["items"]
            self.assertEqual(set(pending), {rel})
            self.assertEqual(pending[rel]["generation"], "generation-deleted")
            self.assertTrue(pending[rel]["remote"])
            self.assertNotEqual(pending[rel]["op_id"], "first-delete")

    def test_sync_preserves_remote_delete_added_while_retrying_existing_item(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            sync_service = ImageStorageService(index_path)
            delete_service = ImageStorageService(index_path)
            sync_service._index_lock = threading.Lock()
            delete_service._index_lock = threading.Lock()
            existing_rel = "2026/07/26/existing-retry.png"
            concurrent_rel = "2026/07/26/concurrent-retry.png"
            concurrent_path = root / "images" / concurrent_rel
            concurrent_path.parent.mkdir(parents=True)
            concurrent_path.write_bytes(b"local-image")
            write_json_file(
                index_path,
                {
                    "items": {
                        concurrent_rel: {
                            "path": concurrent_rel,
                            "local": True,
                            "webdav": True,
                            "storage": "both",
                        }
                    }
                },
            )
            write_json_file(sync_service._remote_delete_file, {
                "items": {
                    existing_rel: delete_tombstone(
                        "",
                        scope="remote",
                        op_id="existing-delete",
                    )
                }
            })
            existing_delete_entered = threading.Event()
            release_existing_delete = threading.Event()
            errors: list[BaseException] = []

            def controlled_delete(_client, rel: str) -> bool:
                if rel == existing_rel:
                    existing_delete_entered.set()
                    release_existing_delete.wait(1)
                    return True
                if rel == concurrent_rel:
                    raise ImageStorageError("temporary concurrent delete failure")
                self.fail(f"unexpected remote delete: {rel}")

            def run_sync() -> None:
                try:
                    sync_service.sync_all()
                except BaseException as exc:
                    errors.append(exc)

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(sync_service, "mode", return_value="both"),
                patch.object(sync_service, "settings", return_value={}),
                patch.object(delete_service, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                    side_effect=controlled_delete,
                ),
            ):
                sync_thread = threading.Thread(target=run_sync)
                sync_thread.start()
                self.assertTrue(existing_delete_entered.wait(1))
                self.assertTrue(delete_service.delete(concurrent_rel))
                release_existing_delete.set()
                sync_thread.join(2)

            self.assertFalse(sync_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(
                set(read_json_object(sync_service._remote_delete_file)["items"]),
                {concurrent_rel},
            )

    def test_sync_finishes_pending_delete_left_with_stale_webdav_index(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            service._index_lock = threading.Lock()
            rel = "2026/07/26/crash-recovery.png"
            write_json_file(
                index_path,
                {
                    "items": {
                        rel: {
                            "path": rel,
                            "local": True,
                            "webdav": True,
                            "storage": "both",
                            "generation": "generation-crash",
                        }
                    }
                },
            )
            write_json_file(service._remote_delete_file, {
                "items": {
                    rel: delete_tombstone(
                        "generation-crash",
                        op_id="crash-delete",
                    )
                }
            })
            deleted: list[str] = []

            def record_delete(_client, delete_rel: str) -> bool:
                deleted.append(delete_rel)
                return True

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "mode", return_value="both"),
                patch.object(service, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                    side_effect=record_delete,
                ),
            ):
                result = service.sync_all()

            self.assertEqual(result, {"uploaded": 0, "skipped": 0, "failed": 0})
            self.assertEqual(deleted, [rel])
            self.assertEqual(read_json_object(service._remote_delete_file)["items"], {})
            self.assertNotIn(rel, read_json_object(index_path)["items"])

    def test_sync_discards_asset_tombstone_for_new_generation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            rel = "2026/07/27/new-generation.png"
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": False,
                        "webdav": True,
                        "generation": "generation-new",
                    }
                }
            })
            write_json_file(service._remote_delete_file, {
                "items": {
                    rel: delete_tombstone(
                        "generation-old",
                        op_id="old-delete",
                    )
                }
            })

            with (
                patch("services.config.DATA_DIR", root),
                patch.object(service, "mode", return_value="both"),
                patch.object(service, "settings", return_value={}),
                patch.object(
                    image_storage_module.WebDAVClient,
                    "delete",
                    autospec=True,
                ) as remote_delete,
            ):
                result = service.sync_all()

            self.assertEqual(result, {"uploaded": 0, "skipped": 0, "failed": 0})
            remote_delete.assert_not_called()
            self.assertIn(rel, read_json_object(index_path)["items"])
            self.assertEqual(read_json_object(service._remote_delete_file)["items"], {})

    def test_old_delete_batch_cannot_clear_new_op_tombstone(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "image_index.json"
            service = ImageStorageService(index_path)
            rel = "2026/07/27/new-delete-op.png"
            write_json_file(index_path, {
                "items": {
                    rel: {
                        "path": rel,
                        "local": False,
                        "webdav": True,
                        "generation": "generation-shared",
                    }
                }
            })

            with patch("services.config.DATA_DIR", root):
                old_plan = service._prepare_delete_batch([rel])
                new_tombstone = delete_tombstone(
                    "generation-shared",
                    op_id="new-delete",
                )
                write_json_file(service._remote_delete_file, {
                    "items": {rel: new_tombstone}
                })
                service._finalize_delete_batch(
                    old_plan,
                    {
                        rel: image_storage_module.DeleteMutationResult(
                            completed=True,
                            removed=True,
                        )
                    },
                )

            durable = read_json_object(service._remote_delete_file)["items"]
            self.assertEqual(durable[rel]["op_id"], "new-delete")
            self.assertIn(rel, read_json_object(index_path)["items"])


if __name__ == "__main__":
    unittest.main()
