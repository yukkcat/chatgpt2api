# Critical Flows

Status: current

These sequences identify the lifecycle owner and handoff points for workflows
that cross multiple Modules. They are navigation maps, not substitutes for
contracts or implementation.

## Account import

Manual JSON/credential import writes through the account API and
`AccountService`. CPA and Sub2API use one shared remote-job lifecycle.

```mermaid
sequenceDiagram
    participant UI as Accounts/Settings runtime
    participant API as accountImportsApi/accountsApi
    participant Route as api/accounts.py
    participant Source as CPAImportService or Sub2APIImportService
    participant Job as RemoteAccountImportJob
    participant Accounts as AccountService
    participant DB as Application Database

    UI->>API: Start import with target Account Group
    API->>Route: Validated request
    alt Manual import
        Route->>Accounts: Save one batch
    else CPA or Sub2API
        Route->>Source: start_import(...)
        Source->>Job: reserve and start worker
        Job->>Source: Fetch remote account payloads
        Job->>Accounts: finish with one normalized batch
        UI->>API: Poll import job
    end
    Accounts->>DB: Account Repository transaction
    DB-->>Accounts: Stored batch result
    Accounts-->>Route: Backend action result
    Route-->>API: Stable response projection
    API-->>UI: Result or polled progress
```

`RemoteImportJobCoordinator` enforces the shared active-job rule. Both remote
sources finish through `RemoteAccountImportJob.finish`; source adapters do not
implement a second save lifecycle. The UI owns polling and presentation only.

## Upstream Account memory maintenance

The Accounts runtime sends an explicit or scoped selection and an enable,
disable, refresh or clear action to `POST /api/accounts/memory`. The route resolves
a fixed list of management IDs and schedules `AccountService.manage_account_memory` through
the existing background operation lifecycle. The service obtains credentials
and account-processing capacity, calls `OpenAIBackendAPI`, and persists only
the relevant account metadata under credential and operation compare-and-swap
guards. In-process mutual exclusion covers switch and clear operations on the
same account; it does not provide cross-process upstream serialization.
A PATCH is followed by a settings read; accepted updates without verification
remain pending, while confirmed values update the switch snapshot.

Clearing sends `DELETE /backend-api/settings/clear_account_user_memory` with
JSON `{}` and reads `GET /backend-api/memories?include_memory_entries=true`
with cache bypass. Only an explicit empty `memories` list and
`memory_num_tokens=0` confirm success. Other accepted outcomes remain pending.
The clear record is independent of the switch snapshot and does not store
memory contents. Refreshing a pending clear performs verification only, never
another DELETE; confirmation updates the last-success time while retaining the
original attempt time. Failed verification preserves the switch snapshot and
past clear-success time. A historical clear does not imply that no memories
were saved afterward.

The clearing protocol is supported by `clearUserMemory`, `deleteWithPayload`
and `getMemories` in the
[third-party archive of the ChatGPT frontend source](https://github.com/0xdevalias/chatgpt-source-watch/blob/88970f48f28e18a41341e446374f9727187dff08/unpacked/_next/static/chunks/pages/_app.js#L80875)
from April 26, 2024. The archive's content commit explicitly identifies that
date. This is historical protocol evidence, not official public API documentation.
The archive establishes the base `/memories` route. Current single-account
verification of both switch values, the clearing request and the
`include_memory_entries=true` read-back is recorded in the
[requirement verification evidence](../requirements/0002-account-memory-controls.md#acceptance-criteria-and-verification-matrix).

The switch snapshot feeds the shared account filter; clear history is shown
only in memory details.
Vue polls the generic operation endpoint
and renders backend-produced events and counters. Process restart loses the
existing in-memory progress and does not replay upstream changes.

## Studio Image Task

```mermaid
sequenceDiagram
    participant Studio as Studio image runtime
    participant API as imageTasksApi
    participant Route as api/image_tasks.py
    participant Task as ImageTaskService
    participant Upstream as Image generation services
    participant Assets as ImageStorageService
    participant Store as data/image_tasks.json

    Studio->>API: Create generation or edit task
    API->>Route: Owner-scoped request
    Route->>Task: Create task
    Task->>Store: Persist queued/running projection
    Task->>Upstream: Execute attempts and account switches
    Upstream->>Assets: Publish successful Image Assets
    Task->>Store: Persist terminal result
    Studio->>API: Poll owner-scoped task list
    API-->>Studio: Final task projection and asset URLs
```

`ImageTaskService` owns task admission, transitions, attempts, resumption, and
terminal state. `ImageStorageService` exclusively owns Image Asset catalogue and
storage mutations. Studio owns browser conversation presentation and polling,
not task truth.

## Call Record, live monitor, and metrics

```mermaid
sequenceDiagram
    participant Route as Public API route
    participant Call as LoggedCall
    participant Live as RealtimeMonitorService
    participant Logs as CallRecordService
    participant Metrics as DashboardMetricsService
    participant DB as Application Database

    Route->>Call: Wrap invocation
    opt Instrumented image request
        Call->>Live: start and stage events
    end
    Call->>Call: Resolve final result and diagnostics
    opt Instrumented image request
        Call->>Live: finish Active Request
    end
    Call->>Logs: Add final Call Record
    Logs->>DB: CallRecordRepository
    Metrics->>Logs: Incremental synchronization
    Metrics->>DB: DashboardMetricsRepository
```

The Call Record is durable final truth. Active Requests and live operations are
process-memory observations and may disappear on restart. The Dashboard Metric
Projection reads only Call Records after its stored sequence during normal
synchronization, updates affected hourly rows atomically, and rebuilds only when
an explicit repository operation rotates the Call Record generation or an
aggregate table is structurally incompatible. User-facing log deletion and
automatic retention preserve the cursor, so the 30-day history remains
independent of the shorter Call Record retention window. If only the projection
state table is recreated, startup checkpoints the current cursor without
deleting compatible hourly aggregates.

## Dashboard projection

```mermaid
sequenceDiagram
    participant Page as Dashboard/useDashboardPage
    participant API as statsApi
    participant Route as GET /api/dashboard
    participant View as build_dashboard_view
    participant Metrics as DashboardMetricsService
    participant Accounts as AccountService
    participant Runtime as RuntimeEnvironment/RealtimeMonitor

    Page->>API: Fetch dashboard immediately or on timer
    API->>Route: Authenticated request
    Route->>View: Build one response
    View->>Metrics: Read stored multi-range snapshot
    View->>Accounts: Read Account Pool stats
    View->>Runtime: Read runtime and live-operation snapshots
    View-->>Page: Stable Dashboard projection
```

The backend owns metric definitions, available ranges, units, health, and
runtime values. Account cards and Active Request counts read current state;
24-hour call cards and all chart ranges come from the same 30-day hourly
projection; runtime-environment samples are not persisted. The page selects one
returned range and owns refresh timing, retained snapshots, chart construction,
animation, layout, and responsive behavior.

## Managed-container online update

```mermaid
sequenceDiagram
    participant Shell as AppShell update overlay
    participant API as versionApi
    participant Status as UpdateStatusService
    participant Task as UpdateService
    participant Release as GitHub Release
    participant Runtime as Managed runtime directory

    Shell->>API: Check update status
    API->>Status: Read latest release projection
    Status->>Release: Fetch release metadata/changelog
    Shell->>API: Confirm and start update
    API->>Task: Start one update task
    Task->>Release: Resolve and download validated asset
    Task->>Runtime: Install files and synchronize dependencies
    Task-->>Shell: Persisted progress via polling
    Task->>Runtime: Exit for container restart
```

`UpdateService` owns the complete update task and rejects unsupported runtime
modes. The frontend only confirms, starts, polls, and renders progress. Update
task state is persisted in `data/update_task.json`; the container runtime owns
restarting the process after exit.
