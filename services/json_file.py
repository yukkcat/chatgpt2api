from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable


def _backup_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".bak")


def read_json_file(
    path: Path,
    *,
    name: str | None = None,
    default_factory: Callable[[], Any] = dict,
    expected_types: type | tuple[type, ...] | None = None,
) -> Any:
    label = name or path.name
    for candidate, is_backup in ((path, False), (_backup_path(path), True)):
        if not candidate.exists():
            continue
        if candidate.is_dir():
            print(
                f"Warning: {label} at '{candidate}' is a directory; ignoring it.",
                file=sys.stderr,
            )
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if expected_types is not None and not isinstance(data, expected_types):
            continue
        if is_backup:
            print(
                f"Warning: {label} at '{path}' is unreadable; recovered from backup '{candidate.name}'.",
                file=sys.stderr,
            )
        return data
    return default_factory()


def read_json_object(path: Path, *, name: str | None = None) -> dict[str, Any]:
    return read_json_file(path, name=name, default_factory=dict, expected_types=dict)


def _write_text_with_fallback(path: Path, content: str) -> bool:
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        try:
            os.replace(tmp_path, path)
            return False
        except OSError as exc:
            try:
                path.write_text(content, encoding="utf-8")
                return True
            except OSError:
                raise exc
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def write_json_file(path: Path, data: Any, *, backup: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    used_fallback = _write_text_with_fallback(path, content)
    if used_fallback:
        print(
            f"Warning: '{path}' 原子替换失败，已改为直接写入。",
            file=sys.stderr,
        )

    if not backup:
        return
    backup_target = _backup_path(path)
    try:
        backup_used_fallback = _write_text_with_fallback(backup_target, content)
        if backup_used_fallback:
            print(
                f"Warning: 备份文件 '{backup_target}' 原子替换失败，已改为直接写入。",
                file=sys.stderr,
            )
    except OSError as exc:
        print(f"Warning: failed to update backup for '{path}': {exc}", file=sys.stderr)
