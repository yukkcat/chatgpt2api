from __future__ import annotations

import hashlib
import io
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from threading import Lock
from typing import Iterator
from urllib.parse import quote, urlparse
from uuid import uuid4

from curl_cffi import requests
from fastapi import HTTPException
from PIL import Image, ImageOps

from services.config import DATA_DIR, config
from services.image_failure import ImageFailureError, image_failure
from services.json_file import read_json_object, write_json_file
from services.storage.file_lock import interprocess_lock
from utils.timezone import beijing_datetime_from_timestamp, beijing_now, beijing_now_str

IMAGE_INDEX_FILE = DATA_DIR / "image_index.json"
IMAGE_INDEX_LOCK = Lock()
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
IMAGE_SYNC_MERGE_BATCH_SIZE = 64
IMAGE_MUTATION_BATCH_SIZE = 16


class ImageStorageError(RuntimeError):
    pass


class ImageBatchDeleteError(RuntimeError):
    def __init__(self, cause: Exception, completed_rels: set[str]) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.completed_rels = frozenset(completed_rels)


@dataclass(frozen=True)
class StoredImage:
    rel: str
    url: str
    storage: str
    size: int


@dataclass(frozen=True)
class LocalCopyRemoval:
    rel: str
    size: int
    remote_remains: bool


@dataclass(frozen=True)
class DeleteMutationResult:
    completed: bool
    removed: bool
    retry_remote: bool = False


def _clean(value: object) -> str:
    return str(value or "").strip()


def _raise_if_save_deadline_elapsed(deadline_monotonic: float | None) -> None:
    if (
        deadline_monotonic is not None
        and deadline_monotonic > 0
        and time.monotonic() >= deadline_monotonic
    ):
        raise ImageFailureError(
            "image request deadline exceeded before asset storage",
            failure=image_failure("task_interrupted"),
        )


def _now_iso() -> str:
    return beijing_now_str()


def _mtime_date(path: Path) -> str:
    return beijing_datetime_from_timestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def _mtime_datetime(path: Path) -> str:
    return beijing_datetime_from_timestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def normalize_image_relative_path(path: str) -> str:
    raw = str(path or "").strip()
    value = raw.replace("\\", "/")
    windows_path = PureWindowsPath(raw)
    if (
        not value
        or value.startswith("/")
        or bool(windows_path.drive)
        or bool(windows_path.root)
        or any(ord(char) < 32 for char in value)
    ):
        raise HTTPException(status_code=404, detail="image not found")
    parts = value.split("/")
    if any(part in {"", ".", ".."} or ":" in part for part in parts):
        raise HTTPException(status_code=404, detail="image not found")
    return PurePosixPath(*parts).as_posix()


def _image_dimensions(payload: bytes) -> tuple[int, int] | None:
    try:
        with Image.open(io.BytesIO(payload)) as image:
            return image.size
    except Exception:
        return None


def _is_image_rel(path: str) -> bool:
    try:
        safe_rel = normalize_image_relative_path(path)
    except HTTPException:
        return False
    return Path(safe_rel).suffix.lower() in IMAGE_EXTENSIONS


def image_local_path(relative_path: str, *, require_file: bool = False) -> Path:
    rel = normalize_image_relative_path(relative_path)
    root = config.images_dir.resolve()
    path = (root / rel).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="image not found") from exc
    if require_file and not path.is_file():
        raise HTTPException(status_code=404, detail="image not found")
    return path


def _read_json_object(path: Path) -> dict[str, object]:
    data = read_json_object(path, name=path.name)
    return data if isinstance(data, dict) else {}


def _write_json_object(path: Path, data: dict[str, object]) -> None:
    write_json_file(path, data)


class WebDAVClient:
    def __init__(self, settings: dict[str, object]):
        self.url = _clean(settings.get("webdav_url")).rstrip("/")
        self.username = _clean(settings.get("webdav_username"))
        self.password = _clean(settings.get("webdav_password"))
        self.root_path = _clean(settings.get("webdav_root_path")).strip("/")
        self.session = requests.Session()

    def _auth_kwargs(self) -> dict[str, object]:
        return {"auth": (self.username, self.password)} if self.username or self.password else {}

    def _request(self, method: str, url: str, **kwargs):
        response = self.session.request(method, url, timeout=30, **self._auth_kwargs(), **kwargs)
        if response.status_code >= 400 and not (method == "MKCOL" and response.status_code in {405}):
            raise ImageStorageError(f"WebDAV {method} failed: HTTP {response.status_code}")
        return response

    def remote_url(self, rel: str = "") -> str:
        parts = [
            part
            for part in [
                self.root_path,
                normalize_image_relative_path(rel) if rel else "",
            ]
            if part
        ]
        encoded = "/".join(quote(part, safe="") for item in parts for part in item.split("/") if part)
        return f"{self.url}/{encoded}" if encoded else self.url

    def ensure_dirs(self, rel: str) -> None:
        parts = [
            part
            for part in [
                self.root_path,
                Path(normalize_image_relative_path(rel)).parent.as_posix(),
            ]
            if part and part != "."
        ]
        current = self.url
        for item in "/".join(parts).split("/"):
            if not item:
                continue
            current = f"{current}/{quote(item, safe='')}"
            response = self.session.request("MKCOL", current, timeout=30, **self._auth_kwargs())
            if response.status_code in {201, 405}:
                continue
            if response.status_code >= 400:
                raise ImageStorageError(f"WebDAV MKCOL failed: HTTP {response.status_code}")

    def put(self, rel: str, payload: bytes, content_type: str = "image/png") -> str:
        self.ensure_dirs(rel)
        url = self.remote_url(rel)
        self._request("PUT", url, data=payload, headers={"Content-Type": content_type})
        return url

    def get(self, rel: str) -> bytes:
        response = self._request("GET", self.remote_url(rel))
        return bytes(response.content)

    def delete(self, rel: str) -> bool:
        response = self.session.request("DELETE", self.remote_url(rel), timeout=30, **self._auth_kwargs())
        if response.status_code in {200, 202, 204, 404}:
            return response.status_code != 404
        raise ImageStorageError(f"WebDAV DELETE failed: HTTP {response.status_code}")

    def test(self) -> dict[str, object]:
        if not self.url:
            return {"ok": False, "status": 0, "error": "WebDAV URL is required"}
        if urlparse(self.url).scheme not in {"http", "https"}:
            return {"ok": False, "status": 0, "error": "invalid WebDAV URL"}
        test_rel = ".chatgpt2api_webdav_test.txt"
        try:
            self.put(test_rel, b"chatgpt2api webdav test\n", content_type="text/plain")
            self.delete(test_rel)
            return {"ok": True, "status": 200, "error": None}
        except ImageStorageError as exc:
            return {"ok": False, "status": 0, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "status": 0, "error": str(exc) or exc.__class__.__name__}
        finally:
            self.session.close()


class ImageStorageService:
    def __init__(self, index_file: Path = IMAGE_INDEX_FILE):
        self.index_file = index_file
        self._index_lock = IMAGE_INDEX_LOCK
        self._index_file_lock = index_file.with_suffix(index_file.suffix + ".lock")
        self._item_lock_dir = index_file.with_suffix(index_file.suffix + ".item-locks")
        self._sync_file_lock = index_file.with_suffix(index_file.suffix + ".sync.lock")
        self._remote_delete_file = index_file.with_suffix(index_file.suffix + ".remote-deletes.json")

    @contextmanager
    def _index_guard(self) -> Iterator[None]:
        with self._index_lock:
            with interprocess_lock(self._index_file_lock):
                yield

    def _item_lock_path(self, rel: str) -> Path:
        safe_rel = normalize_image_relative_path(rel)
        stripe = hashlib.sha256(safe_rel.encode("utf-8")).hexdigest()[:2]
        return self._item_lock_dir / f"{stripe}.lock"

    @contextmanager
    def _item_guard(self, rel: str) -> Iterator[None]:
        with interprocess_lock(self._item_lock_path(rel)):
            yield

    @contextmanager
    def _item_guards(self, rels: list[str] | dict[str, object]) -> Iterator[None]:
        lock_paths = sorted({self._item_lock_path(rel) for rel in rels}, key=str)
        with ExitStack() as stack:
            for lock_path in lock_paths:
                stack.enter_context(interprocess_lock(lock_path))
            yield

    def settings(self) -> dict[str, object]:
        return config.get_image_storage_settings()

    def mode(self) -> str:
        return _clean(self.settings().get("mode")) or "local"

    def _load_index(self) -> dict[str, dict[str, object]]:
        raw = _read_json_object(self.index_file)
        items = raw.get("items")
        if not isinstance(items, dict):
            return {}
        return {str(key): value for key, value in items.items() if isinstance(value, dict)}

    def _load_clean_index(self) -> dict[str, dict[str, object]]:
        items = self._load_index()
        return {rel: item for rel, item in items.items() if _is_image_rel(rel)}

    def _save_index(self, items: dict[str, dict[str, object]]) -> None:
        _write_json_object(self.index_file, {"items": items})

    @staticmethod
    def _new_generation() -> str:
        return uuid4().hex

    @staticmethod
    def _item_generation(item: dict[str, object] | None) -> str:
        return _clean((item or {}).get("generation"))

    @staticmethod
    def _tombstone_matches(
        current: dict[str, object] | None,
        expected: dict[str, object],
    ) -> bool:
        return bool(
            isinstance(current, dict)
            and _clean(current.get("op_id"))
            and _clean(current.get("op_id")) == _clean(expected.get("op_id"))
        )

    @classmethod
    def _asset_generation_matches(
        cls,
        current: dict[str, object] | None,
        tombstone: dict[str, object],
        *,
        allow_missing: bool,
    ) -> bool:
        if current is None:
            return allow_missing
        return cls._item_generation(current) == _clean(tombstone.get("generation"))

    @staticmethod
    def _delete_tombstone(
        *,
        generation: str,
        scope: str,
        remote: bool,
    ) -> dict[str, object]:
        return {
            "op_id": uuid4().hex,
            "generation": generation,
            "scope": scope,
            "remote": remote,
            "requested_at": _now_iso(),
        }

    def _load_remote_delete_pending(self) -> dict[str, dict[str, object]]:
        raw = _read_json_object(self._remote_delete_file)
        values = raw.get("items")
        if not isinstance(values, dict):
            return {}
        pending: dict[str, dict[str, object]] = {}
        for value, tombstone in values.items():
            try:
                safe_rel = normalize_image_relative_path(str(value or ""))
            except HTTPException:
                continue
            if not _is_image_rel(safe_rel) or not isinstance(tombstone, dict):
                continue
            op_id = _clean(tombstone.get("op_id"))
            scope = _clean(tombstone.get("scope"))
            if not op_id or scope not in {"asset", "remote"}:
                continue
            pending[safe_rel] = {
                "op_id": op_id,
                "generation": _clean(tombstone.get("generation")),
                "scope": scope,
                "remote": bool(tombstone.get("remote")),
                "requested_at": _clean(tombstone.get("requested_at")),
            }
        return pending

    def _save_remote_delete_pending(self, items: dict[str, dict[str, object]]) -> None:
        _write_json_object(
            self._remote_delete_file,
            {"items": {rel: items[rel] for rel in sorted(items)}},
        )

    def _sync_item(
        self,
        path: Path,
        rel: str,
        item: dict[str, object],
        payload: bytes,
        remote_url: str,
    ) -> dict[str, object]:
        dimensions = _image_dimensions(payload)
        return {
            "rel": rel,
            "path": rel,
            "name": path.name,
            "date": "-".join(rel.split("/")[:3]) if len(rel.split("/")) >= 4 else _mtime_date(path),
            "size": len(payload),
            "created_at": str(item.get("created_at") or _mtime_datetime(path)),
            "storage": "both",
            "local": True,
            "webdav": True,
            "remote_url": remote_url,
            "generation": self._item_generation(item) or self._new_generation(),
            "_content_sha256": hashlib.sha256(payload).hexdigest(),
            **({"width": dimensions[0], "height": dimensions[1]} if dimensions else {}),
        }

    def _public_url(self, rel: str, base_url: str | None = None) -> str:
        settings = self.settings()
        public_base_url = _clean(settings.get("public_base_url"))
        if public_base_url:
            return f"{public_base_url.rstrip('/')}/{normalize_image_relative_path(rel)}"
        return (
            f"{(base_url or config.base_url).rstrip('/')}/images/"
            f"{normalize_image_relative_path(rel)}"
        )

    def make_relative_path(self, image_data: bytes) -> str:
        file_hash = hashlib.md5(image_data).hexdigest()
        filename = f"{int(time.time())}_{file_hash}.png"
        now = beijing_now()
        relative_dir = Path(now.strftime("%Y"), now.strftime("%m"), now.strftime("%d"))
        return f"{relative_dir.as_posix()}/{filename}"

    def save(
        self,
        image_data: bytes,
        base_url: str | None = None,
        *,
        deadline_monotonic: float | None = None,
    ) -> StoredImage:
        _raise_if_save_deadline_elapsed(deadline_monotonic)
        rel = self.make_relative_path(image_data)
        with self._item_guard(rel):
            # Once the physical mutation starts, finish the catalog commit so a
            # deadline cannot leave an unindexed local or remote asset behind.
            _raise_if_save_deadline_elapsed(deadline_monotonic)
            mode = self.mode()
            if mode not in {"local", "webdav", "both"}:
                mode = "local"
            stored_local = False
            stored_webdav = False
            remote_url = ""

            if mode in {"local", "both"}:
                path = image_local_path(rel)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(image_data)
                stored_local = True

            if mode in {"webdav", "both"}:
                client = WebDAVClient(self.settings())
                try:
                    remote_url = client.put(rel, image_data)
                    stored_webdav = True
                finally:
                    client.session.close()

            dimensions = _image_dimensions(image_data)
            item = {
                "rel": rel,
                "path": rel,
                "name": Path(rel).name,
                "date": "-".join(rel.split("/")[:3]),
                "size": len(image_data),
                "created_at": _now_iso(),
                "storage": "both" if stored_local and stored_webdav else ("webdav" if stored_webdav else "local"),
                "local": stored_local,
                "webdav": stored_webdav,
                "remote_url": remote_url,
                "generation": self._new_generation(),
            }
            if dimensions:
                item["width"], item["height"] = dimensions
            with self._index_guard():
                items = self._load_clean_index()
                items[rel] = item
                self._save_index(items)
                pending = self._load_remote_delete_pending()
                if rel in pending:
                    pending.pop(rel, None)
                    self._save_remote_delete_pending(pending)
        return StoredImage(rel=rel, url=self._public_url(rel, base_url), storage=str(item["storage"]), size=len(image_data))

    def get_bytes(self, rel: str) -> bytes:
        safe_rel = normalize_image_relative_path(rel)
        if not _is_image_rel(safe_rel):
            raise HTTPException(status_code=404, detail="image not found")
        # File paths are not an authorization boundary: only assets registered
        # in the Gallery index may be read through this service.
        with self._index_guard():
            item = self._load_clean_index().get(safe_rel)
        if not isinstance(item, dict):
            raise HTTPException(status_code=404, detail="image not found")
        path = image_local_path(safe_rel)
        if bool(item.get("local")) and path.is_file():
            return path.read_bytes()
        if bool(item.get("webdav")):
            client = WebDAVClient(self.settings())
            try:
                return client.get(safe_rel)
            finally:
                client.session.close()
        raise HTTPException(status_code=404, detail="image not found")

    def record_genbox_push(self, rel: str, *, status: str, sha256: str, updated_at: str) -> dict[str, str]:
        safe_rel = normalize_image_relative_path(rel)
        if not _is_image_rel(safe_rel):
            raise HTTPException(status_code=404, detail="image not found")
        with self._item_guard(safe_rel), self._index_guard():
            items = self._load_clean_index()
            item = items.get(safe_rel)
            if item is None:
                raise HTTPException(status_code=404, detail="image not found")
            item["genbox_push"] = {
                "status": status,
                "sha256": sha256,
                "updated_at": updated_at,
            }
            items[safe_rel] = item
            self._save_index(items)
        return dict(item["genbox_push"])

    def get_genbox_push_state(self, rel: str) -> dict[str, str] | None:
        safe_rel = normalize_image_relative_path(rel)
        if not _is_image_rel(safe_rel):
            return None
        with self._index_guard():
            items = self._load_clean_index()
            raw = items.get(safe_rel, {}).get("genbox_push")
        if not isinstance(raw, dict):
            return None
        status = _clean(raw.get("status"))
        sha256 = _clean(raw.get("sha256"))
        updated_at = _clean(raw.get("updated_at"))
        if not status or not sha256 or not updated_at:
            return None
        return {"status": status, "sha256": sha256, "updated_at": updated_at}

    def exists(self, rel: str) -> bool:
        return bool(self.existing_paths([rel]))

    def existing_paths(self, rels: list[str]) -> set[str]:
        safe_rels = list(dict.fromkeys(
            safe_rel
            for rel in rels
            if _is_image_rel(safe_rel := normalize_image_relative_path(rel))
        ))
        existing = {
            safe_rel
            for safe_rel in safe_rels
            if image_local_path(safe_rel).is_file()
        }
        remote_rels = [safe_rel for safe_rel in safe_rels if safe_rel not in existing]
        if not remote_rels:
            return existing

        items = self._load_clean_index()
        existing.update(
            safe_rel
            for safe_rel in remote_rels
            if items.get(safe_rel, {}).get("webdav")
        )
        return existing

    def has_local(self, rel: str) -> bool:
        safe_rel = normalize_image_relative_path(rel)
        return _is_image_rel(safe_rel) and image_local_path(safe_rel).is_file()

    @staticmethod
    def _catalog_size_matches_local(item: dict[str, object], local_size: int) -> bool:
        indexed_size = item.get("size")
        if indexed_size in {None, ""}:
            return True
        try:
            return int(indexed_size) == local_size
        except (TypeError, ValueError):
            return False

    def _delete_local_copies(
        self,
        rels: list[str],
        *,
        required_bytes: int | None = None,
        dry_run: bool = False,
    ) -> list[LocalCopyRemoval]:
        safe_rels = list(dict.fromkeys(
            safe_rel
            for rel in rels
            if _is_image_rel(safe_rel := normalize_image_relative_path(rel))
        ))
        target = None if required_bytes is None else max(0, int(required_bytes))
        if target == 0:
            return []

        removals: list[LocalCopyRemoval] = []
        reclaimed = 0
        for offset in range(0, len(safe_rels), IMAGE_MUTATION_BATCH_SIZE):
            if target is not None and reclaimed >= target:
                break
            batch = safe_rels[offset:offset + IMAGE_MUTATION_BATCH_SIZE]
            with self._item_guards(batch):
                with self._index_guard():
                    snapshot = self._load_clean_index()

                selected: list[tuple[str, int]] = []
                for safe_rel in batch:
                    if target is not None and reclaimed >= target:
                        break
                    item = snapshot.get(safe_rel, {})
                    if item.get("remote_sync_pending"):
                        continue
                    path = image_local_path(safe_rel)
                    try:
                        local_size = path.stat().st_size
                    except OSError:
                        continue
                    if not self._catalog_size_matches_local(item, local_size):
                        continue
                    if not dry_run:
                        try:
                            path.unlink()
                        except OSError:
                            continue
                    selected.append((safe_rel, local_size))
                    reclaimed += local_size

                if not selected:
                    continue
                if dry_run:
                    removals.extend(
                        LocalCopyRemoval(
                            rel=rel,
                            size=size,
                            remote_remains=bool(snapshot.get(rel, {}).get("webdav")),
                        )
                        for rel, size in selected
                    )
                    continue

                with self._index_guard():
                    items = self._load_clean_index()
                    changed = False
                    for rel, size in selected:
                        item = items.get(rel)
                        remote_remains = bool(item and item.get("webdav"))
                        removals.append(LocalCopyRemoval(rel, size, remote_remains))
                        if item is None:
                            continue
                        if remote_remains:
                            items[rel] = {
                                **item,
                                "local": False,
                                "storage": "webdav",
                            }
                        else:
                            items.pop(rel, None)
                        changed = True
                    if changed:
                        self._save_index(items)
        return removals

    def delete_local_copies(self, rels: list[str]) -> dict[str, bool]:
        return {
            removal.rel: removal.remote_remains
            for removal in self._delete_local_copies(rels)
        }

    def delete_local_copies_until(
        self,
        rels: list[str],
        required_bytes: int,
        *,
        dry_run: bool = False,
    ) -> list[LocalCopyRemoval]:
        return self._delete_local_copies(
            rels,
            required_bytes=required_bytes,
            dry_run=dry_run,
        )

    def list_items(
        self,
        base_url: str,
        start_date: str = "",
        end_date: str = "",
        *,
        refresh_index: bool = True,
        verify_existing: bool = True,
    ) -> list[dict[str, object]]:
        with self._index_guard():
            indexed = self._load_clean_index()
            root = config.images_dir
            changed = False
            if refresh_index:
                for path in root.rglob("*"):
                    if not path.is_file() or not _is_image_rel(path.name):
                        continue
                    rel = path.relative_to(root).as_posix()
                    if rel in indexed:
                        continue
                    dimensions = None
                    try:
                        dimensions = _image_dimensions(path.read_bytes())
                    except Exception:
                        dimensions = None
                    indexed[rel] = {
                        "rel": rel,
                        "path": rel,
                        "name": path.name,
                        "date": "-".join(rel.split("/")[:3]) if len(rel.split("/")) >= 4 else _mtime_date(path),
                        "size": path.stat().st_size,
                        "created_at": _mtime_datetime(path),
                        "storage": "local",
                        "local": True,
                        "webdav": False,
                        "generation": self._new_generation(),
                        **({"width": dimensions[0], "height": dimensions[1]} if dimensions else {}),
                    }
                    changed = True

            items: list[dict[str, object]] = []
            for rel, item in list(indexed.items()):
                if not _is_image_rel(rel):
                    indexed.pop(rel, None)
                    changed = True
                    continue
                if not self._item_generation(item):
                    item = {**item, "generation": self._new_generation()}
                    indexed[rel] = item
                    changed = True
                if verify_existing:
                    local_path = image_local_path(rel)
                    local = local_path.is_file()
                    webdav = bool(item.get("webdav"))
                    if not local and not webdav:
                        indexed.pop(rel, None)
                        changed = True
                        continue
                    storage = "both" if local and webdav else ("webdav" if webdav else "local")
                    local_size: int | None = None
                    if local:
                        try:
                            local_size = local_path.stat().st_size
                        except OSError:
                            local = False
                            storage = "webdav" if webdav else "local"
                    if not local and not webdav:
                        indexed.pop(rel, None)
                        changed = True
                        continue
                    indexed_size = item.get("size")
                    size_changed = (
                        local_size is not None
                        and indexed_size not in {None, ""}
                        and not self._catalog_size_matches_local(item, local_size)
                    )
                    size_needs_update = (
                        local_size is not None
                        and (indexed_size in {None, ""} or size_changed)
                    )
                    if (
                        item.get("local") != local
                        or item.get("storage") != storage
                        or size_needs_update
                    ):
                        item = {
                            **item,
                            "local": local,
                            "storage": storage,
                        }
                        if local_size is not None:
                            item["size"] = local_size
                        if size_changed and webdav:
                            item["remote_sync_pending"] = True
                        indexed[rel] = item
                        changed = True
                day = str(item.get("date") or "")
                if start_date and day < start_date:
                    continue
                if end_date and day > end_date:
                    continue
                items.append({
                    **item,
                    "rel": rel,
                    "path": rel,
                    "url": self._public_url(rel, base_url),
                })
            if changed:
                self._save_index(indexed)
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return items

    def delete(self, rel: str) -> bool:
        safe_rel = normalize_image_relative_path(rel)
        try:
            return safe_rel in self.delete_many([safe_rel])
        except ImageBatchDeleteError as exc:
            raise exc.cause from exc

    def _prepare_delete_batch(
        self,
        rels: list[str],
    ) -> dict[str, dict[str, object]]:
        planned: dict[str, dict[str, object]] = {}
        with self._item_guards(rels):
            with self._index_guard():
                items = self._load_clean_index()
                pending = self._load_remote_delete_pending()
                catalog_changed = False
                for rel in rels:
                    item = items.get(rel)
                    existing = pending.get(rel)
                    generation = self._item_generation(item)
                    if item is not None and not generation:
                        generation = self._new_generation()
                        items[rel] = {**item, "generation": generation}
                        item = items[rel]
                        catalog_changed = True
                    if item is None and existing is not None:
                        generation = _clean(existing.get("generation"))
                    tombstone = self._delete_tombstone(
                        generation=generation,
                        scope="asset",
                        remote=bool(
                            (item and item.get("webdav"))
                            or (existing and existing.get("remote"))
                        ),
                    )
                    pending[rel] = tombstone
                    planned[rel] = tombstone
                if catalog_changed:
                    self._save_index(items)
                self._save_remote_delete_pending(pending)
        return planned

    def _mutate_delete_tombstone(
        self,
        rel: str,
        tombstone: dict[str, object],
        client: WebDAVClient | None,
    ) -> tuple[DeleteMutationResult, Exception | None]:
        with self._item_guard(rel):
            with self._index_guard():
                current = self._load_clean_index().get(rel)
                durable = self._load_remote_delete_pending().get(rel)
            if (
                not self._tombstone_matches(durable, tombstone)
                or not self._asset_generation_matches(
                    current,
                    tombstone,
                    allow_missing=True,
                )
            ):
                return DeleteMutationResult(completed=False, removed=False), None

            removed = False
            path = image_local_path(rel)
            if path.is_file():
                try:
                    path.unlink()
                except Exception as exc:
                    if path.exists():
                        return DeleteMutationResult(completed=False, removed=False), exc
                removed = True

            if tombstone.get("remote"):
                if client is None:
                    return (
                        DeleteMutationResult(
                            completed=removed,
                            removed=removed,
                            retry_remote=True,
                        ),
                        ImageStorageError("WebDAV client is unavailable"),
                    )
                try:
                    removed = client.delete(rel) or removed
                except Exception as exc:
                    return (
                        DeleteMutationResult(
                            completed=removed,
                            removed=removed,
                            retry_remote=True,
                        ),
                        None if removed else exc,
                    )

            return DeleteMutationResult(completed=True, removed=removed), None

    def _finalize_delete_batch(
        self,
        planned: dict[str, dict[str, object]],
        results: dict[str, DeleteMutationResult],
    ) -> None:
        with self._item_guards(planned):
            with self._index_guard():
                items = self._load_clean_index()
                pending = self._load_remote_delete_pending()
                catalog_changed = False
                pending_changed = False
                for rel, tombstone in planned.items():
                    durable = pending.get(rel)
                    if not self._tombstone_matches(durable, tombstone):
                        continue
                    current = items.get(rel)
                    generation_matches = self._asset_generation_matches(
                        current,
                        tombstone,
                        allow_missing=True,
                    )
                    result = results.get(rel)
                    if result is not None and result.completed and generation_matches:
                        if current is not None:
                            items.pop(rel, None)
                            catalog_changed = True
                    if (
                        result is None
                        or not generation_matches
                        or not result.retry_remote
                    ):
                        pending.pop(rel, None)
                        pending_changed = True
                if catalog_changed:
                    self._save_index(items)
                if pending_changed:
                    self._save_remote_delete_pending(pending)

    def delete_many(self, rels: list[str]) -> set[str]:
        safe_rels = list(dict.fromkeys(normalize_image_relative_path(rel) for rel in rels))
        if not safe_rels:
            return set()

        removed_rels: set[str] = set()
        completed_rels: set[str] = set()
        client: WebDAVClient | None = None
        terminal_error: Exception | None = None
        try:
            for offset in range(0, len(safe_rels), IMAGE_MUTATION_BATCH_SIZE):
                batch = safe_rels[offset:offset + IMAGE_MUTATION_BATCH_SIZE]
                try:
                    planned = self._prepare_delete_batch(batch)
                except Exception as exc:
                    terminal_error = exc
                    break
                results: dict[str, DeleteMutationResult] = {}
                batch_error: Exception | None = None
                if client is None and any(bool(item.get("remote")) for item in planned.values()):
                    try:
                        client = WebDAVClient(self.settings())
                    except Exception as exc:
                        batch_error = exc

                if batch_error is None:
                    for safe_rel, tombstone in planned.items():
                        try:
                            result, error = self._mutate_delete_tombstone(
                                safe_rel,
                                tombstone,
                                client,
                            )
                        except Exception as exc:
                            results[safe_rel] = DeleteMutationResult(
                                completed=False,
                                removed=False,
                                retry_remote=True,
                            )
                            batch_error = exc
                            break
                        results[safe_rel] = result
                        if error is not None:
                            batch_error = error
                            break

                completed_rels.update(
                    rel for rel, result in results.items() if result.completed
                )
                removed_rels.update(
                    rel for rel, result in results.items() if result.removed
                )
                try:
                    self._finalize_delete_batch(planned, results)
                except Exception as exc:
                    batch_error = exc
                if batch_error is not None:
                    terminal_error = batch_error
                    break
        finally:
            if client is not None:
                client.session.close()

        if terminal_error is not None:
            raise ImageBatchDeleteError(terminal_error, completed_rels) from terminal_error
        return removed_rels

    @staticmethod
    def _compress_png(payload: bytes) -> bytes:
        output = io.BytesIO()
        with Image.open(io.BytesIO(payload)) as image:
            image = ImageOps.exif_transpose(image)
            image.save(output, format="PNG", optimize=True)
        return output.getvalue()

    @staticmethod
    def _remove_thumbnail(rel: str) -> None:
        safe_rel = normalize_image_relative_path(rel)
        for path in (
            config.image_thumbnails_dir / f"{safe_rel}.png",
            config.image_thumbnails_dir / safe_rel,
        ):
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass

    def compress_local_images(self, quality: int = 60) -> dict[str, int]:
        del quality  # Kept for the existing API contract; PNG optimization has no quality level.
        updates: dict[str, dict[str, object]] = {}
        image_root = config.images_dir
        for path in sorted(image_root.rglob("*.png")):
            if not path.is_file():
                continue
            rel = path.relative_to(image_root).as_posix()
            temp_path = path.with_name(f".{path.name}.compress.tmp")
            with self._item_guard(rel):
                try:
                    original = path.read_bytes()
                    compressed = self._compress_png(original)
                    if len(compressed) >= len(original):
                        continue
                    temp_path.write_bytes(compressed)
                    temp_path.replace(path)
                    stat = path.stat()
                    dimensions = _image_dimensions(compressed)
                    self._remove_thumbnail(rel)
                    updates[rel] = {
                        "size": len(compressed),
                        "saved_bytes": len(original) - len(compressed),
                        "mtime_ns": stat.st_mtime_ns,
                        **({"width": dimensions[0], "height": dimensions[1]} if dimensions else {}),
                    }
                except Exception:
                    continue
                finally:
                    if temp_path.is_file():
                        try:
                            temp_path.unlink()
                        except OSError:
                            pass

        committed: dict[str, dict[str, object]] = {}
        update_items = list(updates.items())
        for offset in range(0, len(update_items), IMAGE_MUTATION_BATCH_SIZE):
            batch = dict(update_items[offset:offset + IMAGE_MUTATION_BATCH_SIZE])
            batch_committed: dict[str, dict[str, object]] = {}
            with self._item_guards(batch):
                for rel, update in batch.items():
                    path = image_local_path(rel)
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    if stat.st_size != update["size"] or stat.st_mtime_ns != update["mtime_ns"]:
                        continue
                    batch_committed[rel] = update

                if not batch_committed:
                    continue
                with self._index_guard():
                    items = self._load_clean_index()
                    for rel, update in batch_committed.items():
                        path = image_local_path(rel)
                        current = items.get(rel, {})
                        remote_stale = bool(
                            current.get("webdav") or current.get("remote_sync_pending")
                        )
                        remote_exists = bool(current.get("webdav"))
                        item = {
                            **current,
                            "rel": rel,
                            "path": rel,
                            "name": path.name,
                            "date": str(
                                current.get("date")
                                or (
                                    "-".join(rel.split("/")[:3])
                                    if len(rel.split("/")) >= 4
                                    else _mtime_date(path)
                                )
                            ),
                            "size": int(update["size"]),
                            "created_at": str(current.get("created_at") or _mtime_datetime(path)),
                            "storage": "both" if remote_exists else "local",
                            "local": True,
                            "webdav": remote_exists,
                            "remote_url": str(current.get("remote_url") or ""),
                            "generation": self._item_generation(current) or self._new_generation(),
                        }
                        if "width" in update and "height" in update:
                            item["width"] = int(update["width"])
                            item["height"] = int(update["height"])
                        if remote_stale:
                            item["remote_sync_pending"] = True
                        else:
                            item.pop("remote_sync_pending", None)
                        items[rel] = item
                    self._save_index(items)
            committed.update(batch_committed)

        saved = sum(int(update["saved_bytes"]) for update in committed.values())
        return {
            "compressed": len(committed),
            "saved_bytes": saved,
            "saved_mb": saved // (1024 * 1024),
        }

    @staticmethod
    def _published_sync_item(update: dict[str, object]) -> dict[str, object]:
        return {key: value for key, value in update.items() if not key.startswith("_")}

    def _repair_stale_sync_item(
        self,
        client: WebDAVClient,
        rel: str,
    ) -> tuple[bool, bool, bool]:
        with self._item_guard(rel):
            path = image_local_path(rel)
            if not path.is_file():
                return False, True, False
            try:
                payload = path.read_bytes()
                with self._index_guard():
                    current = self._load_clean_index().get(rel, {})
                update = self._sync_item(path, rel, current, payload, "")
                remote_url = client.put(rel, payload)
                update["remote_url"] = remote_url
                update = self._published_sync_item(update)
                with self._index_guard():
                    items = self._load_clean_index()
                    current = items.get(rel, {})
                    merged = {
                        **current,
                        **update,
                        "created_at": str(current.get("created_at") or update["created_at"]),
                        "generation": (
                            self._item_generation(current)
                            or self._item_generation(update)
                            or self._new_generation()
                        ),
                    }
                    merged.pop("remote_sync_pending", None)
                    items[rel] = merged
                    self._save_index(items)
                return True, False, False
            except Exception:
                return False, False, True

    def _commit_sync_batch(
        self,
        client: WebDAVClient,
        updates: dict[str, dict[str, object]],
    ) -> tuple[set[str], set[str], int]:
        merged_rels: set[str] = set()
        cleanup_remote: set[str] = set()
        stale_rels: set[str] = set()
        with self._item_guards(updates):
            current_payloads: dict[str, bytes] = {}
            for rel in updates:
                path = image_local_path(rel)
                if not path.is_file():
                    cleanup_remote.add(rel)
                    continue
                try:
                    current_payloads[rel] = path.read_bytes()
                except OSError:
                    cleanup_remote.add(rel)

            with self._index_guard():
                items = self._load_clean_index()
                changed = False
                for rel, update in updates.items():
                    if rel in cleanup_remote:
                        continue
                    current_payload = current_payloads[rel]
                    if hashlib.sha256(current_payload).hexdigest() != update.get("_content_sha256"):
                        current = items.get(rel, {})
                        remote_url = str(update.get("remote_url") or current.get("remote_url") or "")
                        local_update = self._published_sync_item(
                            self._sync_item(
                                image_local_path(rel),
                                rel,
                                current,
                                current_payload,
                                remote_url,
                            )
                        )
                        pending = {
                            **current,
                            **local_update,
                            "storage": "both",
                            "local": True,
                            "webdav": True,
                            "remote_url": remote_url,
                            "remote_sync_pending": True,
                            "generation": (
                                self._item_generation(current)
                                or self._item_generation(local_update)
                                or self._new_generation()
                            ),
                        }
                        items[rel] = pending
                        stale_rels.add(rel)
                        changed = True
                        continue
                    current = items.get(rel, {})
                    published = self._published_sync_item(update)
                    merged = {
                        **current,
                        **published,
                        "created_at": str(current.get("created_at") or published["created_at"]),
                        "generation": (
                            self._item_generation(current)
                            or self._item_generation(published)
                            or self._new_generation()
                        ),
                    }
                    merged.pop("remote_sync_pending", None)
                    items[rel] = merged
                    merged_rels.add(rel)
                    changed = True
                if changed:
                    self._save_index(items)

        failed = 0
        for rel in stale_rels:
            repaired, needs_cleanup, repair_failed = self._repair_stale_sync_item(client, rel)
            if repaired:
                merged_rels.add(rel)
            if needs_cleanup:
                cleanup_remote.add(rel)
            if repair_failed:
                failed += 1
        return merged_rels, cleanup_remote, failed

    def _cleanup_remote_candidates(
        self,
        client: WebDAVClient,
        candidates: set[str],
        pending: dict[str, dict[str, object]],
    ) -> int:
        candidate_rels = sorted(candidates)
        for offset in range(0, len(candidate_rels), IMAGE_MUTATION_BATCH_SIZE):
            batch = candidate_rels[offset:offset + IMAGE_MUTATION_BATCH_SIZE]
            with self._item_guards(batch):
                with self._index_guard():
                    items = self._load_clean_index()
                    durable = self._load_remote_delete_pending()
                    changed = False
                    for rel in batch:
                        if rel in durable:
                            continue
                        if items.get(rel) is not None or image_local_path(rel).is_file():
                            continue
                        durable[rel] = self._delete_tombstone(
                            generation="",
                            scope="remote",
                            remote=True,
                        )
                        changed = True
                    if changed:
                        self._save_remote_delete_pending(durable)

        failed = 0
        for rel in sorted(candidates | set(pending)):
            with self._item_guard(rel):
                with self._index_guard():
                    current = self._load_clean_index().get(rel)
                    tombstone = self._load_remote_delete_pending().get(rel)
                if tombstone is None:
                    continue
                local_exists = image_local_path(rel).is_file()

                scope = _clean(tombstone.get("scope"))
                generation_matches = self._asset_generation_matches(
                    current,
                    tombstone,
                    allow_missing=True,
                )
                superseded = (
                    (scope == "asset" and not generation_matches)
                    or (scope == "remote" and (current is not None or local_exists))
                )
                if superseded:
                    with self._index_guard():
                        durable = self._load_remote_delete_pending()
                        if self._tombstone_matches(durable.get(rel), tombstone):
                            durable.pop(rel, None)
                            self._save_remote_delete_pending(durable)
                    continue

                if scope == "asset" and local_exists:
                    try:
                        image_local_path(rel).unlink()
                    except Exception:
                        if image_local_path(rel).exists():
                            failed += 1
                            continue

                if tombstone.get("remote"):
                    try:
                        client.delete(rel)
                    except Exception:
                        failed += 1
                        continue

                with self._index_guard():
                    items = self._load_clean_index()
                    durable = self._load_remote_delete_pending()
                    if not self._tombstone_matches(durable.get(rel), tombstone):
                        continue
                    latest = items.get(rel)
                    if scope == "asset" and self._asset_generation_matches(
                        latest,
                        tombstone,
                        allow_missing=True,
                    ):
                        if latest is not None:
                            items.pop(rel, None)
                            self._save_index(items)
                    durable.pop(rel, None)
                    self._save_remote_delete_pending(durable)
        return failed

    def _sync_all_locked(self, settings: dict[str, object]) -> dict[str, int]:
        with self._index_guard():
            snapshot = self._load_clean_index()
            pending_remote_deletes = self._load_remote_delete_pending()

        skipped = 0
        failed = 0
        updates: dict[str, dict[str, object]] = {}
        uncertain_remote: set[str] = set()
        client = WebDAVClient(settings)
        image_root = config.images_dir
        try:
            for path in sorted(image_root.rglob("*")):
                if not path.is_file() or not _is_image_rel(path.name):
                    continue
                rel = path.relative_to(image_root).as_posix()
                item = snapshot.get(rel, {})
                tombstone = pending_remote_deletes.get(rel)
                if (
                    tombstone is not None
                    and _clean(tombstone.get("scope")) == "asset"
                    and self._asset_generation_matches(
                        item if item else None,
                        tombstone,
                        allow_missing=True,
                    )
                ):
                    continue
                indexed_size = item.get("size")
                try:
                    catalog_matches_local = int(indexed_size) == path.stat().st_size
                except (OSError, TypeError, ValueError):
                    catalog_matches_local = False
                if (
                    item.get("webdav")
                    and not item.get("remote_sync_pending")
                    and catalog_matches_local
                ):
                    skipped += 1
                    continue
                try:
                    payload = path.read_bytes()
                    update = self._sync_item(path, rel, item, payload, "")
                    remote_url = client.put(rel, payload)
                    update["remote_url"] = remote_url
                    updates[rel] = update
                except Exception:
                    failed += 1
                    uncertain_remote.add(rel)

            merged: set[str] = set()
            cleanup_remote: set[str] = set()
            update_items = list(updates.items())
            for offset in range(0, len(update_items), IMAGE_SYNC_MERGE_BATCH_SIZE):
                batch = dict(update_items[offset:offset + IMAGE_SYNC_MERGE_BATCH_SIZE])
                batch_merged, batch_cleanup, batch_failed = self._commit_sync_batch(client, batch)
                merged.update(batch_merged)
                cleanup_remote.update(batch_cleanup)
                failed += batch_failed

            failed += self._cleanup_remote_candidates(
                client,
                cleanup_remote | uncertain_remote,
                pending_remote_deletes,
            )
            return {"uploaded": len(merged), "skipped": skipped, "failed": failed}
        finally:
            client.session.close()

    def sync_all(self) -> dict[str, int]:
        settings = self.settings()
        if self.mode() not in {"webdav", "both"}:
            raise ImageStorageError("WebDAV 图片存储未启用")
        with interprocess_lock(self._sync_file_lock):
            return self._sync_all_locked(settings)

    def test_webdav(self) -> dict[str, object]:
        return WebDAVClient(self.settings()).test()


image_storage_service = ImageStorageService()
