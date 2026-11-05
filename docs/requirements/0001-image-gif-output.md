# 0001: GIF Output and gpt-image-2.6 Model Registration

Status: implementing

- Owner: unassigned
- Created: 2026-11-05
- Updated: 2026-11-05
- Related issues/ADRs: ADR 0002, ADR 0003

## Problem and user outcome

Callers need the three gpt-image-2.6 model names to work through the existing
image interfaces and need a small, explicit image output format contract. Operators
must be able to choose which supported image models may produce GIFs. A GIF
response must remain an animated GIF through the existing URL, Base64, and
image-storage paths.

## Current behavior and evidence

- The shared model catalogue contains earlier gpt-image aliases but no
  `gpt-image-2.6`, `gpt-image-2.6-flare`, or `gpt-image-2.6-sunburst` entries.
- Existing compatible image aliases use the upstream slug `auto`; the three
  new aliases use the same routing behavior and slug.
- Image generation, edit, chat-image, and compatibility requests already share
  image execution plumbing that can carry optional request metadata.
- Image responses and ImageStorageService currently have raster-image handling
  that must be bypassed or extended for GIF bytes, file extension, and media
  type.
- The current image execution path and Responses path already have established
  `n` and result-cardinality behavior. This requirement does not change it.

## Scope

- Register `gpt-image-2.6`, `gpt-image-2.6-flare`, and
  `gpt-image-2.6-sunburst` in the shared image model catalogue and supported
  model validation. Route all three exactly like the existing compatible image
  aliases, using upstream slug `auto`. Do not add `exact` aliases or 1K size
  mappings.
- Add a persisted `gif_models` setting to `Config` and the existing
  `/api/settings` GET/PATCH contract. It is a list of model identifiers, not a
  scope enum. Its default value is:

  ```json
  [
    "gpt-image-2.6",
    "gpt-image-2.6-flare",
    "gpt-image-2.6-sunburst"
  ]
  ```

  The Settings page exposes the supported image model identifiers and lets the
  operator add or remove each model independently. A GIF request is allowed
  only when its selected model is present in `gif_models`.
- Add these optional fields to the shared image execution request and preserve
  them through existing image generation, edit, chat-image, and compatibility
  entry points:

  ```json
  {
    "output_format": "gif",
    "frame_count": 20,
    "frame_duration_ms": 120
  }
  ```

- Accept `output_format` values `gif`, `png`, `jpg`, `jpeg`, and `webp`; treat
  `jpg` and `jpeg` as the same JPEG target. Append the selected format
  instruction to the derived internal prompt. Append `frame_count` and
  `frame_duration_ms` only when the corresponding request key is present. Use
  the supplied frame values as received; do not validate them, normalize them,
  or fill omitted fields with defaults. Do not mutate the caller's original
  prompt value.
- Reject a GIF request before upstream execution when the selected model is
  absent from `gif_models`. Reject GIF requests with `stream: true` during
  request validation so they do not enter the current single-image SSE flow.
- Preserve upstream GIF bytes. GIF results must skip PNG/JPEG/WebP conversion,
  image upscaling, and other single-frame processing. Store and serve the
  result with a `.gif` extension and `image/gif` media type while reusing the
  existing URL, Base64, local storage, WebDAV, and backup flows.
- For explicit `png`, `jpg`/`jpeg`, or `webp`, convert the upstream single-frame
  image locally before storage and response formatting. Store the converted
  bytes with the matching extension and media type.
- Keep the existing Responses image result cardinality and all existing `n`
  semantics unchanged.

## Non-goals

- No change to `n`, multi-image collection, truncation, or result cardinality.
- No new official API provider.
- No new forced-URL or forced-Base64 setting; keep `image_force_url` and the
  existing response format behavior unchanged.
- No R2 image-asset storage adapter and no change to Image Asset ownership.
- No arbitrary output formats beyond `gif`, `png`, `jpg`/`jpeg`, and `webp`.
- No new Studio Image Task controls or task-lifecycle changes.

## Domain language

- **Image Asset** and **Image Task** use the definitions in
  [`../../CONTEXT.md`](../../CONTEXT.md).
- **`gif_models`** is the persisted list of supported image model identifiers
  that are allowed to request GIF output.

## Unique owners

| Concern | Authoritative owner | Interface consumed by others | Forbidden mirror or fallback |
| --- | --- | --- | --- |
| Supported image models and routing | Existing model catalogue and backend model resolver | Supported-model set and upstream model slug | Endpoint-local model lists |
| GIF eligibility | `Config` and `SettingsManagementService` | `/api/settings` projection and runtime accessor | Scope enums or handler-local defaults |
| Request parsing and prompt hints | Existing image contracts and shared image execution request | Normalized request and derived upstream prompt | Per-endpoint GIF rules or prompt mutation |
| Image output bytes and media type | Shared image result formatter, `ImageStorageService`, and image response adapter | Converted or preserved asset, URL, Base64, and MIME projection | Direct writes or endpoint-local conversion |

## Backend Modules and Interfaces

Extend the existing model catalogue, settings contract, runtime configuration,
image request adapters, shared image execution path, result formatter, and
ImageStorageService. Do not add a provider, repository, or second image-storage
owner. GIF eligibility and `stream` rejection happen before upstream image
execution and return the existing client-error shape. Unsupported output
formats return the existing client-error shape. Existing URL/Base64 response
envelopes remain stable.

The model catalogue is the source of selectable image model values. The
`gif_models` setting stores only those model identifiers. Missing values in
legacy configuration resolve to the three 2.6 defaults without changing other
settings.

## Frontend interaction and responsive behavior

Add a per-model GIF selection control to the existing Settings page. Populate
the choices from the settings/model projection, reuse the current settings
load, save, validation, conflict, and error behavior, and keep the control
usable at the existing desktop and narrow-screen layouts. No new Studio
interaction is included.

## Persistence impact

Persist `gif_models` through the existing configuration/settings owner. Existing
configurations without this field use the default three-model list; no data
migration or ownership change is required. GIF assets continue through the
existing ImageStorageService local/WebDAV and backup paths, with their GIF
extension and media type retained.

## Concurrency, security, and failure behavior

Use the existing image request lifecycle, account selection, retries,
deadlines, storage locks, URL safety checks, and cleanup behavior. Perform GIF
eligibility and streaming checks before network work. Frame values are opaque
request values and are not interpreted for validation. Storage failures follow
the existing image-result failure path. Do not introduce new concurrency or
retry rules.

## Acceptance criteria

- [ ] The three 2.6 aliases pass supported-model validation, appear in the
  built-in model catalogue, and all route to upstream slug `auto`. No `exact`
  alias or 1K mapping is added.
- [ ] `gif_models` is persisted, defaults to the three 2.6 aliases, round-trips
  through `/api/settings` GET/PATCH, and allows independent per-model
  selection in the Settings page.
- [ ] The shared image execution request carries `output_format`,
  `frame_count`, and `frame_duration_ms` through all existing image entry
  points that use it.
- [ ] Prompt tests prove that the selected output format and only-present frame fields are appended,
  omitted fields receive no defaults, supplied frame values are not validated
  or normalized, and the original prompt remains unchanged.
- [ ] `gif`, `png`, `jpg`/`jpeg`, and `webp` are accepted; unknown output
  formats are rejected before upstream execution.
- [ ] A GIF request for a model outside `gif_models`, and any GIF request with
  `stream: true`, fails before upstream execution.
- [ ] A multi-frame GIF fixture is returned and stored byte-for-byte unchanged
  with a `.gif` path and `image/gif` media type. URL, Base64, local, WebDAV,
  and existing backup behavior remain covered.
- [ ] GIF processing does not invoke image upscaling or single-frame raster
  conversion.
- [ ] Explicit PNG, JPEG, and WebP requests return converted bytes with the
  matching extension and media type through URL and Base64 responses.
- [ ] Responses keeps its existing single-image behavior, and existing `n` and
  multi-image behavior is unchanged.

## Verification matrix

| Acceptance criterion | Verification level | Evidence required | Status |
| --- | --- | --- | --- |
| Model aliases and routing | Contract/unit | Model validation, catalogue, and resolver tests | pending |
| GIF model setting | Contract/integration/build | Settings GET/PATCH, legacy-config, and Settings UI tests | pending |
| Request fields and prompt hints | Contract/unit | Generation, edit, chat-image, and compatibility request tests | pending |
| Eligibility and stream rejection | Contract/integration | Rejected requests do not invoke mocked upstream execution | pending |
| GIF bytes, MIME, and storage | Unit/integration | Multi-frame fixture and response/storage checks | pending |
| Existing behavior boundaries | Contract/regression | Responses cardinality and `n` regression tests | pending |

Automated tests, browser verification, user acceptance, and publication remain
separate states. Local tests must remain ignored and untracked as required by
the repository rules.

## Documentation and CHANGELOG impact

During implementation, update the current backend map for model registration,
image execution, and GIF storage behavior; inspect the settings contract
documentation for the new field; and add an Unreleased entry to
`CHANGELOG.md`. Do not update current documents or the changelog while this
requirement remains a draft.

## ADR requirement

No new ADR is required if the implementation reuses the existing model
resolver, SettingsManagementService, shared image execution path, and
ImageStorageService. Moving image assets to R2 or changing Image Asset
ownership is outside this requirement and requires a separate decision.

## Rollback

Remove the `gif_models` setting, the three model aliases, GIF request plumbing,
and GIF storage handling as one change. Existing non-GIF image behavior and
existing settings values must remain readable. Do not delete already stored GIF
assets during rollback.

## Unresolved questions

- None. The requested model aliases, shared upstream slug, per-model setting,
  GIF request fields, and unchanged `n` behavior are defined above.
