---
status: accepted
---

# Deepen image storage before replacing the catalog

`ImageStorageService` owns primary **Image Asset** mutations and their catalog effects. Callers request save, delete, cleanup, compression, and synchronization through this module instead of changing image files or catalog rows directly. Each catalog item has a non-reusable `generation`; a path alone is not an asset identity.

Deletion persists a tombstone containing an operation ID, expected generation, scope, and remote-delete intent before local or WebDAV deletion begins. Destructive work holds only the current asset lock, including while WebDAV is in flight. Preparation and catalog merge batches contain at most 16 assets. Final catalog removal and tombstone cleanup compare both operation ID and generation, so an interrupted old delete cannot remove or clear recovery state for a newer asset at the same path.

The current catalog implementation remains JSON while mutation rules are consolidated. A database or other catalog adapter is considered only after callers no longer bypass the module; otherwise changing persistence would preserve the same split ownership and concurrency defects behind a new storage format.

## Consequences

Batch deletion, disk-threshold cleanup, and compression use the same bounded mutation rule. A local copy marked `remote_sync_pending`, or whose indexed size does not match the local file, is retained by disk cleanup until reconciliation succeeds. Synchronization also compares indexed and local sizes and retries instead of trusting a stale `webdav` flag. Verified gallery reads currently repair local presence and size metadata after an interrupted catalog write; moving that repair to an explicit reconciliation task remains future work. When an upload succeeded but a repair upload fails, the catalog keeps the known remote copy and records the pending local update. When physical deletion succeeds but the catalog commit fails, synchronization replays the matching tombstone idempotently. A newer generation supersedes the old tombstone without remote deletion. Tags and thumbnails remain derived metadata until their invalidation is coordinated inside the same mutation seam.
