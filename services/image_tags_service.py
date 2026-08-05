from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Iterator

from services.config import DATA_DIR
from services.json_file import read_json_object, write_json_file
from services.storage.file_lock import interprocess_lock

TAGS_FILE = DATA_DIR / "image_tags.json"
TAGS_LOCK = Lock()
TAGS_FILE_LOCK = TAGS_FILE.with_suffix(TAGS_FILE.suffix + ".lock")


@contextmanager
def _tags_guard() -> Iterator[None]:
    with TAGS_LOCK:
        with interprocess_lock(TAGS_FILE_LOCK):
            yield


def _ensure_file() -> None:
    TAGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TAGS_FILE.exists():
        write_json_file(TAGS_FILE, {})


def load_tags() -> dict[str, list[str]]:
    with _tags_guard():
        _ensure_file()
        data = read_json_object(TAGS_FILE, name="image_tags.json")
        return data if isinstance(data, dict) else {}


def save_tags(data: dict[str, list[str]]) -> None:
    with _tags_guard():
        _ensure_file()
        write_json_file(TAGS_FILE, data)


def get_tags(image_rel: str) -> list[str]:
    return load_tags().get(image_rel, [])


def set_tags(image_rel: str, tags: list[str]) -> list[str]:
    with _tags_guard():
        _ensure_file()
        data = read_json_object(TAGS_FILE, name="image_tags.json")
        cleaned = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
        if cleaned:
            data[image_rel] = cleaned
        else:
            data.pop(image_rel, None)
        write_json_file(TAGS_FILE, data)
        return cleaned


def remove_tags(image_rel: str) -> None:
    with _tags_guard():
        _ensure_file()
        data = read_json_object(TAGS_FILE, name="image_tags.json")
        if data.pop(image_rel, None) is not None:
            write_json_file(TAGS_FILE, data)
