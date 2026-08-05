from __future__ import annotations

import re


WINDOWS_INVALID_FILENAME_CHARS = frozenset('<>:"/\\|?*')
WINDOWS_RESERVED_FILENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
MAX_PUBLIC_FILENAME_LENGTH = 240


def is_safe_public_filename(value: object) -> bool:
    name = str(value or "")
    if (
        not name
        or len(name) > MAX_PUBLIC_FILENAME_LENGTH
        or name in {".", ".."}
        or name.endswith((" ", "."))
        or any(ord(character) < 32 for character in name)
        or any(character in WINDOWS_INVALID_FILENAME_CHARS for character in name)
    ):
        return False
    return name.split(".", 1)[0].upper() not in WINDOWS_RESERVED_FILENAMES


def sanitize_public_filename(value: object) -> str:
    name = re.split(r"[/\\]", str(value or "").strip())[-1]
    name = "".join(
        "_"
        if ord(character) < 32 or character in WINDOWS_INVALID_FILENAME_CHARS
        else character
        for character in name
    ).strip().rstrip(" .")
    if not name:
        return ""
    if name.split(".", 1)[0].upper() in WINDOWS_RESERVED_FILENAMES:
        name = f"_{name}"
    if len(name) > MAX_PUBLIC_FILENAME_LENGTH:
        dot_index = name.rfind(".")
        suffix = name[dot_index:] if dot_index > 0 and len(name) - dot_index <= 16 else ""
        name = name[:MAX_PUBLIC_FILENAME_LENGTH - len(suffix)].rstrip(" .") + suffix
    return name if is_safe_public_filename(name) else ""
