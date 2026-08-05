---
status: accepted
---

# Use one application database with domain repositories

ChatGPT2API uses one physical **Application Database** for durable structured
control-plane data. The default adapter is SQLite and deployments may use
PostgreSQL 18 through the same SQLAlchemy repositories. All repositories share
one process-wide engine and connection-pool policy for a resolved
`DATABASE_URL`.

Sharing a database does not transfer domain ownership to a generic storage
service. Upstream Accounts and User Keys, system settings and Proxy Groups,
Call Records, dashboard aggregates, prompt-library state, remote-import
configuration, cleanup/backup coordination, and Editable File Task metadata
keep separate repository interfaces and transaction boundaries. A repository
stores a domain projection; it does not normalize business rules or produce UI
semantics.

Image Assets and their local/WebDAV files, gallery catalog and tags, Image Task
state, thumbnails, temporary upload spools, and generated editable files remain
outside the Application Database. Active Requests and other live monitoring
windows remain process memory.

Database selection is infrastructure configuration. `DATABASE_URL` selects the
database and otherwise resolves to `data/chatgpt2api.db`. SQLite connections use
foreign keys, a busy timeout, WAL, and normal synchronous mode. PostgreSQL uses
a bounded process-wide pool. `CHATGPT2API_AUTH_KEY` remains bootstrap
configuration and is not loaded from application settings.

The cutover does not provide automatic import from JSON, JSONL, Git, or the old
account-only SQLite file, and it does not dual-write. A newly selected database
starts empty and becomes authoritative immediately. Schema creation and future
schema upgrades are explicit and versioned; schema setup must not infer or
silently migrate legacy application data.

## Consequences

`STORAGE_BACKEND` is removed as a public runtime choice after the cutover;
SQLite versus PostgreSQL is determined by `DATABASE_URL`. File paths must not
act as hidden database keys, and common JSON helpers must never redirect reads
or writes into the database. Tests inject a temporary database URL through the
same repository interfaces used by production.

Cross-domain transactions are introduced only when one coordinator owns the
complete lifecycle. Otherwise each domain repository commits independently,
preserving the existing service ownership boundaries.
