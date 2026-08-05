<p align="center">
  <img src="web-vue/public/logo.svg" width="112" alt="ChatGPT2API logo" />
</p>

<h1 align="center">ChatGPT2API</h1>

<p align="center">Expose supported ChatGPT Web capabilities through OpenAI-compatible APIs, with a self-hosted console for multi-account orchestration and image workflows.</p>

<p align="center">
  <a href="./README.md">简体中文</a> · <strong>English</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-v3.0.0-111827" alt="Version v3.0.0" />
  <img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white" alt="Python 3.13" />
  <img src="https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white" alt="Vue 3" />
  <img src="https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL 18" />
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker ready" />
  <img src="https://img.shields.io/badge/License-CNC--1.0-red" alt="License CNC-1.0" />
</p>

<p align="center">
  <a href="https://github.com/yukkcat/chatgpt2api/releases/tag/v3.0.0">v3.0.0 Release</a>
  · <a href="./CHANGELOG.md">Changelog</a>
  · <a href="./docs/README.md">Documentation</a>
</p>

<p align="center"><strong>QQ Group: 1005859624</strong></p>

> [!IMPORTANT]
> `v3.0.0` is a new release baseline. The remote `main` history has been consolidated, and older source history, Git tags, releases, and container images are no longer maintained as part of the current release line. Version 3.0 uses a new Application Database and cannot read the distributed storage used by 2.x directly. Reconfigure the service or re-import accounts after upgrading.

> [!WARNING]
> This project accesses ChatGPT Web text, image, and file-generation capabilities through reverse engineering and is not an official OpenAI service. Upstream changes may break these interfaces or cause account restrictions and temporary or permanent bans; do not use important, frequently used, or high-value accounts.
>
> Users must understand the technical, account, and compliance risks and comply with OpenAI's terms and applicable laws. Bulk abuse, malicious competition, account theft, fraud, harassment, and the generation or distribution of illegal, violent, sexual, or minor-related content are strictly prohibited. Users assume all risks and consequences.

## Quick Start

### One-click installer

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/chatgpt2api/main/deploy/install.sh | sudo bash
```

The installer lets you choose SQLite, a local PostgreSQL 18 container, or an existing PostgreSQL URL. SQLite requires no additional service. Local PostgreSQL is started and persisted automatically through Compose.

To install the fixed `v3.0.0` release:

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/chatgpt2api/v3.0.0/deploy/install.sh | sudo bash -s -- --branch v3.0.0
```

### Docker Compose

SQLite is used by default:

```bash
git clone https://github.com/yukkcat/chatgpt2api.git
cd chatgpt2api
cp .env.example .env
# Edit .env and set a private CHATGPT2API_AUTH_KEY
test -f config.json || printf '{}\n' > config.json
docker compose up -d
```

| Endpoint | Address |
| :--- | :--- |
| Admin console | `http://localhost:3000` |
| OpenAI-compatible API | `http://localhost:3000/v1` |
| Data directory | `./data` |

`CHATGPT2API_AUTH_KEY` in `.env` takes precedence over `auth-key` in `config.json`. Console settings, upstream accounts, user keys, call records, and metrics are stored in the Application Database. Do not commit local `.env`, `config.json`, or `data/` files.

### PostgreSQL 18

Set `POSTGRES_PASSWORD` in `.env`, then layer the PostgreSQL Compose file over the base stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d
```

This configuration uses `postgres:18-alpine`, persists data in a named volume, and does not expose the database port by default. To use an existing PostgreSQL server, set:

```env
DATABASE_URL=postgresql://user:password@host:5432/database
```

See the [deployment guide](./docs/deployment.md) for upgrades, backups, PostgreSQL setup, and troubleshooting.

## Project Scope

ChatGPT2API is continuously developed from [basketikun/chatgpt2api](https://github.com/basketikun/chatgpt2api). It uses the ChatGPT Web protocol to expose the OpenAI-compatible interfaces implemented by this project.

## Capabilities

| | Area | Capabilities |
| :---: | :--- | :--- |
| 🔌 | API gateway | Chat Completions, Responses, Messages, search, image generation and editing, PPT/PSD generation, and unified editable-file tasks |
| 💬 | Chat and image studio | Text chat, web search, text-to-image, image-to-image, multiple references, local editing, Markdown, syntax highlighting, citations, and reasoning effort |
| 👥 | Account management | Manual, OAuth, Access Token, Session JSON, CPA, remote CPA, and Sub2API imports, plus search, filters, groups, exports, and batch actions |
| 🔑 | Credentials and quotas | Separate AT/RT states, RT-based AT renewal, plan and quota synchronization, pinned-account text/image tests, and invalid-account handling |
| ⚙️ | Scheduling and concurrency | Multi-account selection, account-processing concurrency, per-account image concurrency, parallel images, account switching, quotas, and rate-limit state |
| 🌐 | Proxy egress | Account and account-group proxies, multi-egress proxy groups, per-node image concurrency, rotation, default and fallback egress, and connectivity checks |
| 📊 | Logs and monitoring | Persisted call records, active requests, recent and slow requests, account switches, egress details, image stage timelines, and raw upstream diagnostics |
| 🖼️ | Images and files | Local/WebDAV storage, gallery, tags, thumbnails, downloads, ZIP archives, compression, cleanup, PPT/PSD artifacts, and optional image upscaling |
| ✨ | Prompt library | Local prompt assets, cloud-source synchronization, categorized selection, and source health |
| 💾 | Data and backups | SQLite, PostgreSQL 18, R2 backups, retention policies, request trends, success rates, and model metrics |
| 🖥️ | Admin console | Dashboard, accounts, proxies, logs, real-time monitoring, gallery, chat and image studio, and settings on desktop and mobile |

## Architecture

```mermaid
flowchart LR
  Client["Compatible API client"] --> API["/v1 compatible API"]
  User["Administrator / web user"] --> Console["Vue admin console"]
  API --> Services["Domain services"]
  Console --> AdminAPI["/api admin endpoints"]
  AdminAPI --> Services
  Services --> Scheduler["Account scheduling and proxy egress"]
  Scheduler --> Upstream["ChatGPT Web"]
  Services --> AppDB["Application Database<br/>SQLite / PostgreSQL 18"]
  Services --> Assets["Images and generated files<br/>Local / WebDAV"]
  Services --> Monitor["In-process real-time monitor"]
  Services --> Backup["R2 backup"]
```

The Application Database stores accounts, user keys, settings, call records, and metrics. Images and generated files remain in dedicated file storage. See the [storage architecture](./docs/storage-architecture.md) for ownership boundaries.

## API

All AI endpoints use a Bearer key:

```http
Authorization: Bearer <auth-key>
```

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/v1/models` | `GET` | Returns the merged local and live upstream model catalog |
| `/v1/chat/completions` | `POST` | Chat Completions entry point for text, search, and image scenarios |
| `/v1/responses` | `POST` | Responses entry point with text, search, and image tools |
| `/v1/messages` | `POST` | Anthropic Messages-compatible entry point |
| `/v1/search` | `POST` | Returns an answer, citations, and search results |
| `/v1/images/generations` | `POST` | Image generation with `n=1..4` |
| `/v1/images/edits` | `POST` | Image editing from multipart files, remote URLs, base64, data URLs, or multiple references |
| `/v1/editable-file-tasks` | `GET / POST` | Creates and queries editable PPT/PSD tasks |
| `/v1/editable-file-tasks/{task_id}` | `DELETE` | Deletes a task owned by the current key |
| `/v1/ppt/generations` | `POST` | PPT task shortcut |
| `/v1/psd/generations` | `POST` | PSD task shortcut |
| `/files/{file_path}` | `GET` | Publicly downloads a generated file from its random storage path |

Creating, querying, and deleting file tasks is isolated by API key. The `/files/...` links returned by successful tasks work like generated-image links: anyone holding the link can download the asset without authentication. Public downloads validate paths and file types and reject path traversal.

<details>
<summary>Chat Completions example</summary>

```bash
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{"model":"gpt-5","messages":[{"role":"user","content":"Introduce this project"}],"stream":true}'
```

</details>

<details>
<summary>Image generation example</summary>

```bash
curl http://localhost:3000/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{"model":"gpt-image-2","prompt":"A cat floating in space, cinematic lighting","n":1,"response_format":"b64_json"}'
```

</details>

Available models depend on the upstream accounts and the current `/v1/models` response.

## Configuration

| Setting | Default | Purpose |
| :--- | :--- | :--- |
| `CHATGPT2API_AUTH_KEY` | Required | Administrator and default API key; the environment variable takes precedence over `config.json` |
| `DATABASE_URL` | SQLite | Application Database connection; defaults to `data/chatgpt2api.db` when unset |
| `CHATGPT2API_BASE_URL` | Current service URL | Public base URL used for generated image and file links |
| `CHATGPT2API_THREAD_TOKENS` | `120` | Capacity for synchronous backend worker threads; accepts any positive integer, while accounts, proxies, and upstream services retain their own limits |
| `account_processing_concurrency` | `30` | Capacity for account imports, refreshes, synchronization, and batch processing |
| `image_account_concurrency` | `1` | Per-account image concurrency, configurable from 1 to 3 |
| `image_stream_timeout_secs` | `80` | Maximum wait for the upstream image SSE/HTTP stream |
| `image_poll_timeout_secs` | `60` | Maximum wait for image result polling and parsing |
| `log_retention_days` | `30` | Automatic call-record retention period |

Other settings are managed through the console. The current backend projection is authoritative for defaults and constraints.

## Screenshots

<table width="100%">
  <tr><td width="50%"><img src="docs/images/1.png" alt="Console screenshot 1"></td><td width="50%"><img src="docs/images/2.png" alt="Console screenshot 2"></td></tr>
  <tr><td width="50%"><img src="docs/images/3.png" alt="Console screenshot 3"></td><td width="50%"><img src="docs/images/4.png" alt="Console screenshot 4"></td></tr>
  <tr><td width="50%"><img src="docs/images/5.png" alt="Console screenshot 5"></td><td width="50%"><img src="docs/images/6.png" alt="Console screenshot 6"></td></tr>
</table>

## Local Development

```bash
# Backend: Python 3.13 + uv
uv sync
uv run main.py

# Frontend: Node.js + npm
cd web-vue
npm install
npm run dev
```

The frontend development server defaults to `http://localhost:5173`, with backend requests forwarded by the Vite development proxy.

## Documentation

| Document | Scope |
| :--- | :--- |
| [Documentation index](./docs/README.md) | Entry point for current architecture and maintenance documents |
| [Deployment and operations](./docs/deployment.md) | Docker, PostgreSQL, upgrades, backups, and troubleshooting |
| [Storage architecture](./docs/storage-architecture.md) | Application Database and file-storage boundaries |
| [Console architecture](./docs/control-panel-architecture.md) | Frontend/backend responsibilities, business projections, and interaction state |
| [Image failure handling](./docs/image-failure-handling.md) | Image failure classification, retries, and account handling |
| [Upstream SSE](./docs/upstream-sse-conversation.md) | Conversation and stream-parsing boundaries |

If documentation conflicts with the implementation, the current code, tests, and public API contracts are authoritative.

## Project Contributors

<a href="https://github.com/yukkcat/chatgpt2api/graphs/contributors">
  <img alt="ChatGPT2API Contributors" src="https://contrib.rocks/image?repo=yukkcat/chatgpt2api" />
</a>

## Original Project and Contributors

This project evolved from [basketikun/chatgpt2api](https://github.com/basketikun/chatgpt2api). Thanks to the original author and all contributors:

<a href="https://github.com/basketikun/chatgpt2api/graphs/contributors">
  <img alt="Contributors" src="https://contrib.rocks/image?repo=basketikun/chatgpt2api" />
</a>

## Community and Links

- QQ group: [1005859624](https://qm.qq.com/q/yegwCqJisS)
- Community: [Linux.do](https://linux.do)
