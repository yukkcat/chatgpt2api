# 0002: Upstream Account memory controls

Status: pending-verification

- Owner: AccountService and the Accounts page
- Created: 2026-11-09
- Updated: 2026-11-09
- Related ADRs: 0001, 0004

## Problem and user outcome

Administrators need to inspect and switch upstream memory, and explicitly clear
saved memories, for one account or a selection, including every account matching filters across pages. The existing
account workspace already owns these interactions. Only the upstream `m3m`
protocol is borrowed from gpt2api-go; its UI and job architecture are not copied.

## Current behavior and evidence

`api/accounts.py` resolves explicit, filtered, and all-account selections before
starting maintenance. `AccountService` owns credentials, shared processing
capacity, account metadata and process-memory progress. `account_view` owns row
semantics. The Accounts page reuses Nanocat controls and a common operation drawer.
Memory switch maintenance already has a shared lifecycle and projection;
clearing saved memories extends those owners.

## Scope and non-goals

- Query memory state and explicitly enable or disable it, singly or in batches.
- Filter by all/enabled/disabled/unknown together with existing account filters.
- Clear saved memories singly or in batches, after an irreversible-action
  confirmation, without switching memory on or off.
- Record the latest clear outcome and attempt time independently of the switch,
  preserve the last confirmed clear time, and show the record in memory details.
- Persist the last confirmed state and timestamp, independently of the latest
  operation result. Imported and previously unqueried accounts remain unknown.
- Reuse existing menus, confirmation, scoped selection and progress components.
- Do not inspect or store memory contents, change unrelated upstream switches, add a new
  persistence owner, or automatically query upstream during list rendering.

## Domain language and unique owners

An Upstream Account memory snapshot records the last observed upstream `m3m`
setting. Disabling memory is distinct from deleting saved memories.
The clear record describes a past operation, not a promise that an account
currently has no memories; later upstream activity can save new memories.

| Concern | Authoritative owner | Interface | Forbidden mirror |
| --- | --- | --- | --- |
| Protocol and parsing | OpenAIBackendAPI | Query and set memory | Router-side HTTP calls |
| Credentials, mutations, bounded execution | AccountService | manage_account_memory | Separate memory worker framework |
| Stored snapshot | Account Repository | Existing account metadata | A second database/table owner |
| State and allowed actions | account_view | Row fields and state helper | Vue-derived business state |
| Filtered membership | api/accounts shared filter | List and selection scope | Page-only filtering |
| Results and progress | AccountService and account_operation_events | Existing operation progress | Synthetic frontend success |
| Selection, drafts and polling | Accounts runtimes | Existing selection/remote action flow | Go UI or duplicate polling |
| Layout, focus and overlays | Existing account components/Nanocat | Existing public components | A separate memory panel |

## Interfaces and persistence

`POST /api/accounts/memory` accepts the existing account selection plus
`action: enable | disable | refresh | clear`, requires administrator authorization and
rejects an empty target. It returns the existing background progress contract.
`GET /api/accounts/operations/{progress_id}` returns the result and events.

Account list and selection scopes gain `memory_state` with
`all | enabled | disabled | unknown`. Filtering happens before pagination; count,
preview, exclusion and all-matching selection use the same predicate. IDs are
resolved once at operation admission.

Account rows project `memory_clear_status: never | verified | pending | failed`,
`memory_clear_label`, `memory_clear_tone`,
`memory_clear_at`, `memory_cleared_at` and sanitized `memory_clear_error`.
`memory_clear_at` is the latest attempt time; `memory_cleared_at` retains the
last confirmed success even if a later attempt fails. The clear action does
not overwrite the memory switch snapshot or its latest operation outcome.

Account rows project state, label, tone, confirmation time, latest operation
outcome, sanitized diagnostics and permitted actions. Snapshot fields live in
the existing Account Repository record; no schema migration is required.

## Concurrency, security and failure behavior

Reuse Account Processing Concurrency, current credential renewal, account routing
and fingerprint. Do not hold account storage locks during network calls. Each
account has a bounded request time; one failure must not stop other accounts.
Concurrent deletion or credential replacement must not be overwritten by stale
results. Explicit set-value actions are idempotent; no blind toggle is exposed.

The upstream PATCH has no JSON body and only changes `m3m`. Both values are
followed by a cache-bypassing settings read. A matching valid value is confirmed;
an accepted update with unavailable verification is pending; an opposite value
is a failure with the observed snapshot retained. Failed reads preserve prior
confirmed values and times. Events must not expose tokens or raw settings.

Progress uses existing process-memory retention and is lost on restart; this
feature does not add durable job recovery or automatic replay.
Clearing and switch maintenance share the same per-account exclusion and
credential/operation compare-and-swap guards. A clear command is never
automatically retried. An accepted command is confirmed only after an
independent empty-memory check; an inconclusive check remains pending.
The clearing protocol and its historical source evidence are documented in
[critical flows](../maps/critical-flows.md#upstream-account-memory-maintenance).
Refreshing a pending clear performs only a read. It can confirm the clear record
even when the independent switch read fails, without replacing the previous
switch snapshot. A failed or inconclusive clear read preserves its original
attempt time and last confirmed success time.

## Frontend interaction and responsive behavior

Add a memory filter to the existing toolbar and state to both account table and
cards. Existing known-state actions show the inverse command plus refresh;
unknown state permits either explicit command. Bulk actions reuse the same
remote operation flow as single actions, which pass one ID. Existing retained
snapshot loading, empty/error states, scroll ownership, menu focus and responsive
layout remain authoritative.

Memory has its own table column and uses the existing status component. Cards
show memory in a labeled row below the existing detail list. Labels are “开启”, “关闭”, and “未确认”;
unconfirmed state uses a neutral tone. Pending and failed operations use a compact
indicator in tables; confirmation time and diagnostics remain in the shared
HoverCard in both layouts. Filter labels retain the memory field name to
distinguish them from account status.

Single and batch menus add a destructive clear command. The existing confirmation
dialog identifies the selected count and explains that saved memories will be
permanently removed and the memory switch will stay unchanged. Clear history
appears in the existing memory HoverCard instead of adding another table column
or badge. Clear commands use the existing filtered selection and frozen target
scope, including preview and exclusions; clear history has no separate filter.

## Acceptance criteria and verification matrix

| Criterion | Verification | Status |
| --- | --- | --- |
| Both PATCH values, no body, account header and read-back | Mock protocol tests | passed |
| Unknown/confirmed/pending/failed snapshots and safe errors | Service/projection tests | passed |
| Combined filters, pagination, scoped count and exclusions | API/runtime tests | passed |
| Single/batch actions share selection and progress | API/runtime tests | passed |
| Partial failure, stale writes and shared capacity | Service tests | passed |
| Clear DELETE body, bounded read, strict empty-list and zero-token verification | Mock protocol tests | passed |
| Clear history independent of switch and old success retained on failure | Service/projection tests | passed |
| Pending clear read-only refresh, including switch-read failure | Service tests | passed |
| Clear commands reuse filtered scopes, frozen targets, exclusions and irreversible confirmation | API/runtime tests and isolated browser | passed |
| Existing UI controls, desktop/mobile and no horizontal overflow | Build and isolated browser inspection at 1280x720 / 390x844 | passed |
| Real upstream supports enabling and disabling | Authorized single-account test on 2026-11-09, both values read back | passed for tested account |
| Current upstream supports clearing saved memories | Authorized single-account test on 2026-11-09, verified test memory removed | passed for tested account |
| User accepts the visible behavior | User verification | pending |

Automated tests, browser inspection, live upstream verification, user acceptance
and publication are independent. The single-account live test below establishes
compatibility for that account at the time of testing; it does not establish
support for every account or future protocol versions.

Verification used an isolated SQLite database and mocked memory endpoints. Full
Python regression: 121 passed, including 96 focused memory tests. The frontend
build and `node tests/account-memory-runtime.mjs` passed. The full frontend
runtime script could not run because its pre-existing local test files are
absent. Browser checks exercised single disable, batch disable/enable, memory
refresh, both account layouts, filtering, and the eight main routes without
console errors. Those automated and isolated browser checks did not change any
real upstream account.
The clearing extension also exercised cancellation, single clear, a batch with
one confirmed/one pending/one failed outcome, keyboard
HoverCard details, both layouts and narrow-screen confirmation. These writes
used mocked upstream methods and disposable accounts. The real local preview
was inspected read-only after restarting its backend.

With explicit user authorization, a separate live test on 2026-11-09 used only
the first local account through its existing credentials, fingerprint and routing.
The initial read returned an empty memory list, zero memory tokens and
`m3m=false`. The test temporarily enabled memory and independently read back
`true`, then sent one normal saved conversation containing an artificial test
marker. The conversation returned HTTP 200; a subsequent memory read found
exactly one entry matching the marker and 58 memory tokens. A single clear
operation through `AccountService.manage_account_memory` returned one confirmed
result and no errors. Independent read-back returned an empty list, zero memory
tokens and no marker, while `m3m` remained `true`. Restoring the original switch
value returned one confirmed result; the final independent read returned an
empty list, zero memory tokens and `m3m=false`.

No other account was operated on, and credentials and upstream memory contents
were not printed or persisted by the test. The saved test conversation was not
deleted. The live test covered one artificial memory and clearing while memory
was enabled; real batch clearing, multiple entries, clearing while disabled,
failure cases and concurrency were not exercised against upstream.

The existing operation timeline displays an unavailable event time because its
generic diagnostic sanitizer alters ISO timestamps. This also exists in HEAD;
the clearing extension leaves it unchanged. Independent clear timestamps in the
account projection and HoverCard are valid.

## Documentation, ADR and rollback

Update the backend/frontend maps, critical flow, account data contract, domain
context and CHANGELOG alongside implementation. No new ADR is required because
existing service, projection, storage and UI owners are retained. Removing the
new controls and route reverses the application change; upstream settings
already changed are not automatically reversed.
Saved memories already cleared upstream cannot be restored by reverting code.

## Unresolved questions

- User acceptance of the visible account controls remains pending. Live
  compatibility evidence is limited to the single authorized account and
  scenario documented above; broader behavior retains mock coverage only.
