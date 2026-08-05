# ChatGPT2API Context

ChatGPT2API exposes OpenAI-compatible text, search, and image interfaces backed by a managed pool of upstream ChatGPT accounts. Its control panel observes and manages those calls without becoming a second source of business semantics.

## Language

### Access and accounts

**Upstream Account**:
A ChatGPT credential that can be selected to execute an upstream request.
_Avoid_: User, user key, login account

**Upstream Credentials**:
The Access Token required by an Upstream Account plus its optional Refresh Token and ID Token. The backend projects Access Token state as `valid`, `expiring`, or `invalid`, and Refresh Token state as `valid`, `missing`, or `invalid`; only a confirmed terminal refresh failure makes a present Refresh Token invalid.
_Avoid_: User Key, frontend-derived token state, login retention setting

**Account Pool**:
The set of upstream accounts eligible for selection under the current model, status, quota, and policy filters.
_Avoid_: User pool

**Account Processing Concurrency**:
The process-wide capacity limit shared by Upstream Account batch tasks. Remote maintenance, including AT renewal, account and quota synchronization, import verification, and background checks, consumes one slot per active account. A local atomic batch mutation, including import save, enable, disable, reset, delete, and group binding, consumes one slot for the complete batch.
_Avoid_: Image generation concurrency, import batch size

**User Key**:
A local bearer credential that identifies a caller and grants control-panel capabilities.
_Avoid_: Upstream account, access token

**Capability**:
A named control-panel permission currently represented by `admin_console` or `studio`.
_Avoid_: Page visibility, role check

### Image execution

**Image Task**:
An owner-scoped asynchronous generation or edit request with a terminal result and one or more image assets.
_Avoid_: Conversation, call log

**Image Attempt**:
One upstream-account attempt within an image call, including its final result, diagnostics, and whether another account was selected.
_Avoid_: Image task, retry log

**Account Switch**:
The transition from one failed image attempt to a new attempt using another upstream account.
_Avoid_: Final result

**Image Text Result**:
A terminal image-request outcome in which upstream returned review or explanatory text instead of an image.
_Avoid_: Chat response, generic failure

**Image Asset**:
A generated or edited image exposed by URL or base64 data and optionally indexed by the gallery.
_Avoid_: Image task

**Editable File Task**:
An owner-scoped asynchronous PPT or PSD generation request whose terminal result exposes a primary editable file and a ZIP archive.
_Avoid_: Image task, chat attachment

**Editable File Asset**:
A published PPT, PSD, or ZIP file exposed by an unguessable public URL after an Editable File Task finishes exporting both artifacts.
_Avoid_: Editable file task, task record

### Observability and routing

**Call Record**:
The persisted final record of one public interface invocation, including its outcome, timing, diagnostics, and image attempts when present.
_Avoid_: Runtime event, active request

**Active Request**:
An in-memory request lifecycle currently tracked by real-time monitoring.
_Avoid_: Call record

**Proxy Group**:
A named set of proxy nodes and a selection strategy that can be referenced by accounts or defaults.
_Avoid_: Account group, proxy profile

**Proxy Reference**:
The normalized routing choice `direct`, `group`, or `custom` used by the default egress module. An account with no proxy selection defers to lower-priority routing; inheritance is absence, not a fourth Proxy Reference mode.
_Avoid_: Raw proxy string

**Proxy Session**:
Optional resource-proxy, TLS, and Cloudflare clearance behavior applied after an egress has been selected. It never supplies the default egress.
_Avoid_: Default proxy, proxy runtime egress

### Shared catalogues and persistence

**Model Catalog**:
The backend projection of supported text and image models, defaults, and model-related capabilities.
_Avoid_: A page-local model list

**Prompt Source**:
A configured upstream or bundled origin whose validated snapshot contributes items to the prompt library.
_Avoid_: Prompt item

**Prompt Library**:
The revisioned, merged view of prompt items and prompt-source health exposed to Studio and Settings.
_Avoid_: Prompt source cache file

**Application Database**:
The configured SQLite or PostgreSQL database shared by durable structured control-plane repositories. Sharing the physical database does not merge their domain ownership or transaction boundaries.
_Avoid_: Generic JSON document dump, Image Asset storage, process memory

**Account Repository**:
The Application Database repository that stores Upstream Accounts and User Keys.
_Avoid_: A global repository for settings, logs, images, and task state

## Relationships

- A **User Key** grants one or more **Capabilities** and owns its submitted **Image Tasks** and **Editable File Tasks**.
- An **Upstream Account** owns one set of **Upstream Credentials**; the Refresh Token renews the Access Token, while account and quota synchronization is a separate operation.
- **Account Processing Concurrency** limits remote maintenance per active **Upstream Account** and reserves one slot for each complete local atomic account batch; it does not limit Image Task execution slots.
- An **Image Task** produces zero or more **Image Assets** and exposes one terminal result.
- An **Editable File Task** publishes one primary **Editable File Asset** and one ZIP **Editable File Asset** when it succeeds; asset reads do not depend on retaining the task record.
- An image call contains one or more **Image Attempts**; an **Account Switch** links consecutive attempts but is not itself a terminal result.
- A completed public invocation produces one **Call Record**, while an **Active Request** exists only during the live request window.
- An **Upstream Account** can reference one **Proxy Reference**, which may select one **Proxy Group**.
- The default egress is exactly one **Proxy Reference**; **Proxy Session** behavior cannot replace it.
- Multiple **Prompt Sources** contribute items to one **Prompt Library**.
- The **Model Catalog** is consumed by Studio and shared control-panel surfaces.
- The **Application Database** hosts separate repositories for durable structured control-plane data.
- The **Account Repository** stores **Upstream Accounts** and **User Keys** only.
- **Image Assets**, gallery metadata, **Image Tasks**, and live monitoring state do not belong to the **Application Database**.

## Example dialogue

> **Developer:** "A user says image generation switched accounts and then succeeded. Is the switch the result?"
> **Domain expert:** "No. The **Image Task** succeeded. Its **Call Record** contains two **Image Attempts**, and the **Account Switch** describes the transition between them."
>
> **Developer:** "Does using one database make settings, logs, and accounts one repository?"
> **Domain expert:** "No. They share the **Application Database** connection infrastructure, while their domain services retain separate repositories and transaction boundaries."

## Flagged ambiguities

- "account" previously referred both to an **Upstream Account** and a local caller credential; use **User Key** for the latter.
- "access token" can mean an upstream ChatGPT token or the bearer value entered at login; use **Upstream Account** credential and **User Key** respectively.
- The UI label "text" can mean ordinary chat or `text_review`; use **Image Text Result** for the latter.
- "Unified database" means one physical **Application Database**, not one generic repository or a hidden redirection from file paths.
- "proxy group" and the legacy "proxy profile" are not interchangeable; new account routing uses **Proxy References** and **Proxy Groups**.
