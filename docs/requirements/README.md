# Product Requirements

Status: current

This directory owns requirements that describe intended product changes and
their acceptance criteria. It does not describe current implementation truth;
use the current implementation documents linked from
[`../README.md`](../README.md) for that purpose.

## Lifecycle

```text
draft -> approved -> implementing -> pending-verification -> implemented
   \-> rejected
```

| Status | Meaning |
| --- | --- |
| `draft` | Problem, scope, or ownership is still being discussed. |
| `approved` | The user has accepted the scope and acceptance criteria. |
| `implementing` | Work has started, but the document still expresses intent. |
| `pending-verification` | Implementation and automated checks are done; required product verification remains. |
| `implemented` | Acceptance evidence exists and affected current documentation is synchronized. |
| `rejected` | The proposal will not be implemented; the reason is recorded. |

Create a requirement from [`_template.md`](_template.md) and name it
`NNNN-short-name.md`. Keep active requirements here. Completed or rejected
requirements may move to `archive/` after links and this index are updated.

## Active requirements

- [`0001-image-gif-output.md`](0001-image-gif-output.md) — GIF output and
  gpt-image-2.6 compatibility (`implementing`).

PRDs are planning evidence, never proof that the product already behaves as
described.
