# Documentation

Status: current

## Source of truth

When documentation and implementation disagree, use this order:

1. Current code, tests, and public request/response contracts.
2. [`../CONTEXT.md`](../CONTEXT.md) for domain terms and ownership.
3. Accepted records in [`adr/`](adr/).
4. Current documents in this directory.

Plans describe intended work, not completed behaviour. Historical smoke records,
old route maps, and documents for deleted features are not retained as current
documentation.

## Current documents

| Document | Status | Purpose |
| --- | --- | --- |
| [`control-panel-architecture.md`](control-panel-architecture.md) | current | Routes, ownership, persistence boundaries, and UI boundary |
| [`control-panel-data-contract.md`](control-panel-data-contract.md) | current | Backend projections and frontend consumption rules |
| [`control-panel-action-safety.md`](control-panel-action-safety.md) | current | Mutation ownership and destructive-action boundaries |
| [`control-panel-performance.md`](control-panel-performance.md) | current | Query, pagination, refresh, and rendering rules |
| [`image-failure-handling.md`](image-failure-handling.md) | current | Image failure classification, switching, and diagnostics |
| [`storage-architecture.md`](storage-architecture.md) | current | Independent persistence responsibilities |
| [`prompt-library-architecture.md`](prompt-library-architecture.md) | current | Prompt source and library projection lifecycle |
| [`deployment.md`](deployment.md) | current | Docker, source development, backup, and upgrade guidance |
| [`upstream-sse-conversation.md`](upstream-sse-conversation.md) | current | Internal Conversation SSE and result-resolution reference |

## Documentation rules

- Each new document must state whether it is `current`, `plan`, or `historical`.
- A current document only describes verified behaviour and real routes.
- A plan must name its non-goals and acceptance criteria.
- Removed routes and features must be removed from current documentation in the
  same change that removes them from the product.
- Do not add generated reports, one-off smoke logs, or local experiment notes to
  the current documentation set.
