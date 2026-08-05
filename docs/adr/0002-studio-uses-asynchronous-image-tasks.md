---
status: accepted
---

# Studio uses asynchronous image tasks

Studio submits image generation and edit work through owner-scoped **Image Tasks** and reads their strict task projection instead of keeping a browser request open for the full upstream generation. The backend owns queue admission, execution, terminal status, assets, public errors, and resumable polling actions; the visible Studio page polls only non-terminal task IDs and maps the returned task state into local conversation messages.

## Consequences

Studio conversation history remains browser-local interaction state, while durable task truth remains server-side. Transport may later change from polling to push without changing the Image Task interface.
