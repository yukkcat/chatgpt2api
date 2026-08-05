---
status: accepted
---

# Backend owns control-panel semantics

Control-panel business status, classification, effective values, diagnostics, and action results are produced by backend projection modules with explicit contracts. Frontend adapters validate and transport those contracts, while pages own rendering, drafts, selection, filters, charts, and lifecycle; this keeps one semantic source shared by the public response, account switching, logs, monitoring, and dashboard metrics.

## Consequences

Changing a label's business meaning or deriving a new outcome belongs in the backend projection and its contract tests. Frontend-only inference is limited to visual formatting and interaction state.
