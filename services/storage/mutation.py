from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from copy import deepcopy
from typing import Any, Iterable, Sequence

from services.storage.base import StorageCollection, StorageMutation


_IDENTITY_FIELDS: dict[StorageCollection, str] = {
    "accounts": "access_token",
    "auth_keys": "id",
}


def item_key(collection: StorageCollection, item: dict[str, Any]) -> str:
    field = _IDENTITY_FIELDS[collection]
    key = str(item.get(field) or "").strip()
    if not key:
        raise ValueError(f"{collection} item requires a non-empty {field!r}")
    return key


def normalize_items(
    collection: StorageCollection,
    items: Sequence[dict[str, Any]] | Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise TypeError(f"{collection} items must be dictionaries")
        item = deepcopy(raw)
        key = item_key(collection, item)
        if key in seen:
            raise ValueError(f"duplicate {collection} item identity")
        seen.add(key)
        normalized.append(item)
    return normalized


def normalize_mutation(
    collection: StorageCollection,
    mutation: StorageMutation,
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    upserts = normalize_items(collection, mutation.upserts)
    delete_keys = tuple(
        dict.fromkeys(str(value or "").strip() for value in mutation.delete_keys)
    )
    if any(not key for key in delete_keys):
        raise ValueError(f"{collection} delete keys must be non-empty")
    upsert_keys = {item_key(collection, item) for item in upserts}
    overlap = upsert_keys.intersection(delete_keys)
    if overlap:
        raise ValueError(
            f"{collection} identities cannot be deleted and upserted together"
        )
    return upserts, delete_keys


def revision_for_items(
    collection: StorageCollection,
    items: Sequence[Any],
) -> str:
    # A revision describes an unordered JSON collection. Sorting canonical item
    # encodings keeps legacy malformed entries readable so callers can replace
    # and clean them instead of failing during startup.
    canonical_items = sorted(
        json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for item in items
    )
    payload = (f"{collection}:[" + ",".join(canonical_items) + "]").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def apply_mutation_to_items(
    collection: StorageCollection,
    current_items: Sequence[dict[str, Any]],
    mutation: StorageMutation,
) -> tuple[list[dict[str, Any]], int, int, int]:
    upserts, delete_keys = normalize_mutation(collection, mutation)
    current = normalize_items(collection, current_items)
    by_key = OrderedDict((item_key(collection, item), item) for item in current)

    deleted = 0
    for key in delete_keys:
        if by_key.pop(key, None) is not None:
            deleted += 1

    inserted = 0
    updated = 0
    for item in upserts:
        key = item_key(collection, item)
        previous = by_key.get(key)
        if previous is None:
            by_key[key] = item
            inserted += 1
        elif previous != item:
            by_key[key] = item
            updated += 1

    return list(by_key.values()), inserted, updated, deleted


def replacement_counts(
    collection: StorageCollection,
    current_items: Sequence[Any],
    next_items: Sequence[dict[str, Any]],
) -> tuple[int, int, int]:
    current: dict[str, dict[str, Any]] = {}
    discarded = 0
    for raw in current_items:
        if not isinstance(raw, dict):
            discarded += 1
            continue
        try:
            key = item_key(collection, raw)
        except ValueError:
            discarded += 1
            continue
        if key in current:
            discarded += 1
        current[key] = raw
    desired = {
        item_key(collection, item): item
        for item in normalize_items(collection, next_items)
    }
    inserted = len(desired.keys() - current.keys())
    deleted = len(current.keys() - desired.keys()) + discarded
    updated = sum(
        current[key] != desired[key]
        for key in current.keys() & desired.keys()
    )
    return inserted, updated, deleted
