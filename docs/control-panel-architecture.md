# Control-Panel Architecture

Status: current

## Purpose

ChatGPT2API exposes OpenAI-compatible text, search, and image interfaces backed
by an Account Pool of Upstream Accounts. The control panel observes and manages
those calls without becoming another source of business semantics.

Domain names and storage ownership are defined in [`../CONTEXT.md`](../CONTEXT.md).
The accepted decisions in [`adr/`](adr/) override this document when necessary.

## Data flow

```text
domain services and storage
        -> backend projection and action result
        -> web-vue API adapter
        -> page state and rendering
```

- Backend projections own business results, effective values, diagnostics,
  display labels, tones, and metrics.
- `web-vue/src/api/` validates and transports those projections.
- Pages own drafts, filters, selection, dialogs, charts, request lifecycle, and
  responsive layout.
- Pages do not infer a business result by matching error text or combining raw
  status fields.

This is backend-owned business semantics with frontend rendering, not backend
HTML rendering.

## Current routes

| Route | Page responsibility |
| --- | --- |
| `/login` | Authenticate a User Key and redirect to an allowed route |
| `/` | Render dashboard metrics supplied by the backend |
| `/accounts` | Manage Upstream Accounts and Account Pool actions |
| `/settings` | Manage runtime settings, User Keys, Prompt Sources, and integrations |
| `/proxy` | Manage Proxy Groups and default Proxy References |
| `/logs` | Browse Call Records and their backend-projected diagnostics |
| `/monitor` | Show Active Requests and recent runtime observations |
| `/gallery` | Browse and manage Image Assets |
| `/studio` | Run text, search, image, and editable-file workflows; follow owner-scoped asynchronous tasks |

There is no current documentation-center, debug-center, or registration-machine route.
Prompt Library is a cross-page capability: Settings manages Prompt Sources, while
Studio consumes the resulting Prompt Library.

## Image execution

An Image Task is server-side truth. Studio creates a task, keeps browser-local
conversation state, and reads the task projection until it is terminal. The
backend owns queue admission, attempts, Account Switches, public errors, and
Image Assets. See ADR 0002 for the full decision.

## Editable-file execution

An Editable File Task is also server-side truth. Studio submits PPT or PSD work
through `/v1/editable-file-tasks`, persists only the task identity in its local
conversation, and reads the owner-scoped task projection until it is terminal.
The frontend never treats an Editable File Task as an Image Task, even when the
request includes reference images.

Editable files are downloaded as public assets, like Image Assets. Generation
writes to a private staging directory and publishes the primary file and ZIP
together after both are complete. `/files/...` validates the asset path and
reads storage directly; it does not reverse-query the task index. Creating,
querying, and deleting the task remain owner-scoped operations.

## Persistence ownership

- The Account Storage Backend stores Upstream Accounts and User Keys.
- Call Records, real-time observations, Image Tasks, Editable File Tasks, Image Assets, and Editable File Assets have
  separate persistence responsibilities; changing Account Storage Backend does
  not implicitly move them.
- `ImageStorageService` owns primary Image Asset mutations and catalog effects.
  See ADR 0003 for deletion, synchronization, and concurrency rules.

## UI ownership

`nanocat-ui` is the npm-delivered source of generic visual and interaction
modules: tokens, form controls, menus, generic overlays, keyboard behaviour, and
theme states. `chatgpt2api` owns AppShell, page composition, tables, charts,
business timelines, and product-specific responsive layout.

A generic UI Module is extracted to Nanocat only when it has more than one real
consumer or a concrete cross-project use case. A page-specific implementation
stays in this repository while it remains page-specific.

## Page lifecycle

Pages distinguish initial loading, a refresh with a retained snapshot, a true
empty result, and an error. A background refresh must not clear a prior snapshot.
