# Reference Research Baseline

Last reviewed: 2026-09-04.

This document records external standards and projects that influence Agnara. It is not a dependency list.

## OpenTelemetry metrics bridge

Reviewed 2026-09-05 for E9.2 / Issue #216. The official Python guidance
recommends API-only dependencies for instrumented libraries, with the
application configuring the SDK. The Metrics API assigns instrument creation
to the meter and configuration to its provider. This supports supplying a
meter explicitly without global SDK installation in `agnara-telemetry`.

The published API and SDK baseline used for in-memory tests is 1.44.0. The
adapter consumes terminal count/duration data already available in the core
port; it does not introduce trace correlation or claim protocol-specific
semantic convention compatibility. See proposed ADR 0054 for measurements,
redaction, lifecycle ownership and limitations.

- [Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)
- [Metrics API](https://opentelemetry.io/docs/specs/otel/metrics/api/)
- [API 1.44.0](https://pypi.org/project/opentelemetry-api/1.44.0/)
- [SDK 1.44.0](https://pypi.org/project/opentelemetry-sdk/1.44.0/)

## Python 3.14

Agnara intentionally starts at Python 3.14.

Relevant direction:

- free-threaded CPython is officially supported as an optional build;
- modern asyncio/structured-concurrency tools are available;
- the project should avoid GIL-dependent correctness.

Reference:

- https://docs.python.org/3.14/whatsnew/3.14.html
- https://docs.python.org/3/howto/free-threading-python.html

## FastAPI

Study FastAPI for:

- developer API ergonomics;
- type-driven design;
- OpenAPI integration;
- dependency patterns;
- ecosystem lessons;
- backward-compatibility cost.

Do not copy its HTTP-first architecture.

Reference:

- https://github.com/fastapi/fastapi
- https://fastapi.tiangolo.com/history-design-future/

## HTTP framework benchmark pins

Reviewed 2026-09-03 for E6.10. The reproducible development-only comparison
pins FastAPI 0.141.1, Starlette 1.6.0 and Litestar 2.24.0, the current PyPI
releases observed on that date. All three declare Python 3.14 compatibility.
They are benchmark fixtures, not `agnara-http` dependencies.

The shared harness measures a warm in-process ASGI request, not server or
network throughput. FastAPI depends on Starlette and Pydantic; Starlette is the
minimal toolkit reference; Litestar brings a broader dependency surface and
uses msgspec. Those differences remain visible in the report rather than
being flattened into a claim that every scenario performs identical internal
work.

References:

- https://pypi.org/project/fastapi/0.141.1/
- https://pypi.org/project/starlette/1.6.0/
- https://pypi.org/project/litestar/2.24.0/
- `docs/benchmarks/http-frameworks.md`

## OpenAPI

Target modern OpenAPI support through the HTTP adapter.

Current baseline investigated:

- OpenAPI 3.2.0.

Reference:

- https://spec.openapis.org/oas/latest.html

## OpenAPI documentation interfaces

Reviewed: 2026-08-31 for RFC 0003 and ADR 0018. Swagger UI evidence refreshed
2026-09-03 for ADR 0036; ReDoc evidence refreshed 2026-09-03 for ADR 0037;
Scalar and alternative evidence refreshed 2026-09-03 for ADR 0038; shared
Chromium browser evidence added 2026-09-03 for ADR 0039.

This is a point-in-time comparison, not a permanent endorsement. OpenAPI 3.2
support is still evolving across renderers, so Agnara must test pinned versions
against its own fixtures instead of equating "accepts a 3.2 document" with full
conformance.

Registry sizes below are npm `dist.unpackedSize`, not browser transfer size.
They help expose packaging cost but do not replace a reproducible bundle/load
measurement with the exact assets Agnara would ship.

| Interface | Maintenance evidence | OAS 3.2 status | npm package snapshot | License |
|---|---|---|---|---|
| Swagger UI | `5.32.14`, published August 2026; active releases | `5.32.0` added basic 3.2 support; enhanced 3.2 features remain open | `swagger-ui-dist`: 11,755,365 bytes, 1 dependency | Apache-2.0 |
| ReDoc CE | `2.5.3`, released May 2026 | public docs still list 3.1/3.0/2.0; 3.2 issues remain, so treat compatibility as incomplete | `redoc`: 7,776,708 bytes, 21 dependencies | MIT |
| Scalar API Reference | `1.67.0`; frequent August 2026 monorepo releases | parser supports 3.2, but end-to-end API Reference 3.2 tracking is still open | `@scalar/api-reference`: 40,679,445 bytes, 25 dependencies | MIT |
| Stoplight Elements | `9.0.25`; security/maintenance commits in July 2026 | documents 3.1/3.0/2.0; no evidenced full 3.2 claim | `@stoplight/elements`: 2,809,144 bytes, 12 dependencies | Apache-2.0 |
| RapiDoc | npm `9.3.8`, last published roughly two years before this review | claims OpenAPI `3.x.x`, but no pinned 3.2 conformance evidence was found | `rapidoc`: 3,606,592 bytes, 8 dependencies | MIT |

### Swagger UI

Strengths:

- most familiar interactive baseline;
- built-in try-it, API key/basic/bearer preauthorization and OAuth
  configuration including PKCE;
- search/filter, deep links, request/response interceptors and plugin system;
- dependency-free `swagger-ui-dist` bundle can be served locally or loaded
  from a CDN; Docker distribution is available;
- active security policy and frequent releases;
- responsive metadata is present and embedding can be enabled explicitly in
  the Docker distribution.

Tradeoffs:

- the distribution is relatively large and its visual customization is less
  cohesive than modern alternatives;
- the current npm distribution declares Scarf installation analytics; a
  vendoring/build process must disable telemetry and audit install scripts;
- dark mode exists but embedded/default configuration remains incomplete;
- basic OpenAPI 3.2 support does not yet render every new 3.2 construct;
- long-running accessibility gaps remain open and require Agnara's own WCAG
  smoke testing;
- try-it, remote validator calls and OAuth enlarge the network/security
  surface. Agnara must disable the online validator and credential persistence
  by default and explicitly constrain submit methods.

E6.15 evidence and implementation boundary (2026-09-03):

- pinned release: `swagger-ui-dist@5.32.14`, released 2026-08-18;
- vendored browser payload: `swagger-ui-bundle.js` (1,553,809 bytes) and
  `swagger-ui.css` (185,784 bytes), both verified from the official npm tarball;
- acquisition uses `npm pack --ignore-scripts`, so the declared Scarf package
  dependency and installation lifecycle do not run;
- a versioned manifest records npm integrity, local SHA-256 and CDN SRI, while
  the upstream Apache-2.0 license and notice ship beside the assets;
- 5.32.0's basic 3.2 implementation explicitly deferred `$self`,
  `additionalOperations`, component `mediaTypes` and `pathItems`, Tag Object
  enhancements, `querystring` parameters and streaming `itemSchema`;
- the local provider is the production baseline; the exact-version unpkg
  variant has a distinct provider name, SRI and an explicit remote-assets gate.

Primary sources:

- https://github.com/swagger-api/swagger-ui/releases
- https://github.com/swagger-api/swagger-ui/releases/tag/v5.32.14
- https://github.com/swagger-api/swagger-ui/pull/10721
- https://github.com/swagger-api/swagger-ui/issues/10575
- https://github.com/swagger-api/swagger-ui/issues/10897
- https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/
- https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/
- https://swagger.io/docs/open-source-tools/swagger-ui/usage/installation/
- https://github.com/swagger-api/swagger-ui/issues/10663
- https://github.com/swagger-api/swagger-ui/issues/7350
- https://www.npmjs.com/package/swagger-ui-dist

### ReDoc Community Edition

Strengths:

- readable, responsive three-panel reference layout;
- navigation search, deep schema presentation, code samples and theming;
- deployable as a standalone local asset, CDN script, HTML element, React
  component or generated static HTML;
- supports CSP nonces and an `untrustedSpec` sanitization mode;
- strong embedding and mobile breakpoints;
- active maintenance and a large established user base.

Tradeoffs:

- Community Edition does not include the hosted product's try-it console;
- documented compatibility remains OpenAPI 3.1/3.0/2.0, while 3.2 work is
  incomplete despite recent crash fixes;
- the React/runtime dependency surface and standalone bundle need measurement;
- authentication UX is primarily documentation in CE, not a full interactive
  client;
- dark appearance is theme configuration rather than a first-class automatic
  mode;
- accessibility requires independent verification; no project-wide WCAG
  conformance claim was found.

E6.16 evidence and implementation boundary (2026-09-03):

- pinned release: `redoc@2.5.3`, with release notes dated 2026-05-27;
- vendored payload: `redoc.standalone.js` (1,097,271 bytes), verified from the
  official npm tarball;
- acquisition uses `npm pack --ignore-scripts`, so the package's 21 declared
  runtime dependencies and `prepare` hook do not run in Agnara installations;
- the exact `cdn.redoc.ly` version was downloaded and byte-compared with the
  tarball asset before recording SHA-384 SRI;
- the bundle injects styles and creates a search worker from `blob:`, both of
  which are explicit provider CSP requirements;
- ReDoc receives `untrustedSpec: true`; no external Google font origin occurs
  in the inspected 2.5.3 standalone bundle, and local CSP deliberately blocks
  its upstream footer-logo URL so branding cannot become a network dependency;
- 2.5.3 prevents a 3.2 crash, but the README still claims only 3.1/3.0/2.0 and
  the 3.2 issues remain open, so the provider declares only tested 3.1.0 and
  refuses Agnara's canonical 3.2.0 artifact;
- ReDoc CE has no try-it console, so that request is refused rather than
  ignored.

Primary sources:

- https://github.com/Redocly/redoc
- https://github.com/Redocly/redoc/releases/tag/v2.5.3
- https://github.com/Redocly/redoc/issues/2746
- https://github.com/Redocly/redoc/issues/2773
- https://redocly.com/docs/redoc/config
- https://www.npmjs.com/package/redoc

### Scalar API Reference

Strengths:

- strongest modern UX candidate in this review;
- first-class dark/light themes, search, responsive navigation, code samples,
  authentication and an integrated API client/try-it experience;
- highly customizable configuration and plugins;
- can be embedded through a standalone script or framework integrations and
  self-hosted; CDN versions can be pinned;
- very active maintenance, including recent hardening for untrusted OpenAPI
  links, prototype pollution and server-rendered CSS injection;
- its OpenAPI parser already supports 3.2.

Tradeoffs:

- the complete API Reference/client 3.2 checklist is still open;
- the npm package contains a broad multi-package feature surface and is the
  largest unpacked package in this comparison; browser bytes must be measured
  separately;
- strict `script-src` can use a nonce, but current rendering still requires
  `style-src 'unsafe-inline'` in documented integrations;
- plugins loaded from URLs and the integrated client are powerful extra trust
  boundaries and must be disabled or allowlisted explicitly;
- active ARIA/accessibility defects remain open, so modern appearance is not
  evidence of WCAG conformance;
- fast release cadence makes exact version pinning and upgrade tests essential.

E6.17 evidence and implementation boundary (2026-09-03):

- pinned release: `@scalar/api-reference@1.67.0`, published 2026-08-28 in
  release tag `release-2026-08-28-df40ed7`;
- vendored payload: the self-contained browser `standalone.js` IIFE
  (3,736,898 bytes), including the interactive client and verified from the
  official 9,050,339-byte npm tarball;
- acquisition uses `npm pack --ignore-scripts`; none of the package's 25
  declared dependencies or build/test scripts runs in Agnara installations;
- the exact-version jsDelivr entrypoint byte-matches the npm artifact and has
  recorded SHA-384 SRI; the MIT license comes from the exact release tag
  because the npm tarball does not contain it;
- the initializer disables telemetry, credential persistence, document
  editing/download, developer tools, agent/MCP affordances, proxy defaults and
  plugin URLs; try-it controls remain hidden unless independently selected;
- Scalar injects CSS and embeds `fonts.scalar.com` URLs. Inline styles are
  declared, but local CSP does not allow the font origin, so system fonts are
  used without a hidden network dependency;
- the bundle contains responsive media rules and ARIA markup, but issue #9725
  reports active ARIA failures; source inspection is not a WCAG/mobile claim,
  and E6.18 owns browser verification;
- the parser accepts 3.2 and Agnara preserves that version, but upstream issue
  #6715 still tracks uncompleted API Reference/client/workspace work. The
  provider names this partial boundary rather than claiming full conformance;
- the resulting `agnara-http` wheel is 1,937,150 bytes, up 1,095,884 bytes
  from the Swagger/ReDoc baseline build.

Primary sources:

- https://github.com/scalar/scalar
- https://github.com/scalar/scalar/releases
- https://github.com/scalar/scalar/issues/6715
- https://github.com/scalar/scalar/blob/main/packages/openapi-parser/README.md
- https://github.com/scalar/scalar/blob/main/documentation/configuration.md
- https://github.com/scalar/scalar/blob/main/documentation/integrations/nextjs.md
- https://github.com/scalar/scalar/issues/9725
- https://www.npmjs.com/package/@scalar/api-reference

### Stoplight Elements

Strengths:

- embeddable as React components or Web Components;
- responsive/sidebar/stacked layouts, try-it, authentication input, code
  samples and hiding of `x-internal` operations;
- Apache-2.0 and actively receives maintenance/security fixes;
- useful if Agnara later needs composition inside a larger documentation
  portal rather than a standalone page.

Tradeoffs:

- React-oriented transitive dependencies and styling are a larger integration
  surface than a single-purpose custom element suggests;
- no evidenced OpenAPI 3.2 support claim was found;
- dark mode/customization and CSP behavior require a focused spike;
- credentialed external references and Web Component navigation have open
  integration issues;
- current packages added Scarf installation telemetry, which an Agnara asset
  build must disable and audit;
- no complete WCAG conformance claim was found.

Primary sources:

- https://github.com/stoplightio/elements
- https://github.com/stoplightio/elements/blob/main/docs/getting-started/elements/elements-options.md
- https://github.com/stoplightio/elements/commits/main
- https://github.com/stoplightio/elements/issues/2292
- https://github.com/stoplightio/elements/issues/2792
- https://www.npmjs.com/package/@stoplight/elements

### RapiDoc

Strengths:

- framework-neutral Web Component with a single generated JavaScript bundle;
- built-in try-it, authentication controls, dark/light themes, search,
  extensive attributes and straightforward embedding;
- small conceptual integration boundary and MIT license;
- responsive layouts and local-spec/self-hosting support.

Tradeoffs:

- the npm release is materially older than the other active candidates;
- "OpenAPI 3.x.x" is not sufficient evidence of complete 3.2 rendering;
- WCAG 2 support and automated testing remain roadmap items;
- documented browser support still says Edge is untested;
- CSP/XSS hardening and current maintenance response require a dedicated spike
  before production use.

Primary sources:

- https://github.com/rapi-doc/RapiDoc
- https://rapidocweb.com/api.html
- https://www.npmjs.com/package/rapidoc

### Research decision

Swagger UI, ReDoc and Scalar now implement the same replaceable provider
contract without runtime UI dependencies. Keep Elements and RapiDoc as viable
later providers, not runtime assumptions: the refreshed maintenance,
dependency and compatibility evidence does not make either a stronger default.

E6.18 ran identical Playwright 1.62.0 Chromium 151.0.7922.34 fixtures over the
pinned local providers. Swagger UI and Scalar rendered the 3.2 fixture; ReDoc
rendered the equivalent 3.1 fixture and refused 3.2 before browser delivery.
All three kept the XSS marker inert, produced no successful external response,
accepted keyboard focus and avoided document overflow at 390 by 844 pixels.
CSP actively blocked the malicious image, Scalar font and ReDoc branding
origins.
Swagger/Scalar try-it followed the independent selection, credential-named
storage stayed empty, and Swagger's computed OAuth redirect was same-origin,
secretless and unpublished.

Do not select an unconditional documentation default yet. This evidence
validates the integration boundary, not complete OpenAPI or WCAG conformance.
Scalar's known ARIA defects remain open, ReDoc remains a read-only 3.1
provider, and the public composition API is still provisional. Scalar remains
the leading modern-UX candidate and Swagger UI the compatibility baseline.

Self-hosted, exact-version assets are the production baseline. CDN delivery is
opt-in and must document CSP, integrity, privacy and availability consequences.
No human UI replaces the machine-readable OpenAPI or Agnara introspection
contracts.

E6.19 converts that research rule into a provider-independent contract. CDN
scripts and styles now require an exact semantic version in the URL, SHA-384
SRI, anonymous CORS, an exactly matching canonical CSP origin and explicit
deployment allowlisting of that origin. Tests cross-check all three vendored
manifests, licensed files, byte lengths and SHA-256 values against packaged
resources. The normative basis is the W3C Subresource Integrity and CSP Level
3 specifications; SRI authenticates the received representation while CSP
limits which origin may supply it.

## MCP

MCP is a primary protocol adapter target.

Reviewed 2026-09-04 for E7.1. Agnara's first MCP adapter line targets the
authoritative `2026-07-28` specification and pins the official Python SDK to
`mcp==2.1.1`. PyPI identifies 2.1.1 as the current stable release, published
through the SDK repository's trusted-publishing workflow, and declares Python
3.14 support. The SDK's public `LATEST_PROTOCOL_VERSION` is `2026-07-28`.

The `2026-07-28` specification introduced/strengthened concepts including:

- stateless protocol core;
- Multi Round-Trip Requests;
- header-based routing;
- cacheable lists;
- authorization changes;
- extension framework;
- Tasks as an extension.

The official SDK also negotiates legacy revisions. Agnara deliberately
advertises only the revision covered by its own future conformance suite;
SDK capability alone is not framework conformance. Tool projection, schema,
discovery and the authorization bridge are now implemented; interaction-required
behavior, Tasks/MRTR and full conformance remain later E7 work.

References:

- https://modelcontextprotocol.io/specification/2026-07-28
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.1.1
- https://pypi.org/project/mcp/2.1.1/

The MCP adapter must pin and test the exact supported specification/SDK version rather than assuming evergreen compatibility.

For E7.3, the same tool specification establishes that `inputSchema` is a
required JSON Schema object, defaults to dialect 2020-12 when `$schema` is
absent, and recommends a closed object for a tool without parameters. Agnara
therefore wraps compiled input fragments in an object with
`additionalProperties: false`, while leaving optional `outputSchema` absent
until output validation exists in the core runtime.

Reviewed 2026-09-04 for E7.4. In the modern `2026-07-28` lifecycle,
`server/discover` is the server capability/version advertisement and
`tools/list` is the cacheable tool-definition surface. The official SDK stamps
server identity into result `_meta`, derives advertised capabilities from the
handlers actually registered, and represents tool lists with
`ListToolsResult`. MCP pagination uses opaque cursors; because Agnara's first
discovery boundary returns one complete immutable startup snapshot, it emits
no cursor and rejects every caller-supplied cursor as invalid rather than
silently assigning it meaning. Discovery results use an immediately stale,
private cache hint.

Additional references:

- https://modelcontextprotocol.io/specification/2026-07-28/server/discover
- https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/pagination
- https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching
- https://github.com/modelcontextprotocol/python-sdk/tree/v2.1.1

Reviewed 2026-09-04 for E7.5. The official SDK's bearer-auth middleware
validates a token through the configured `TokenVerifier`, then exposes its
`AccessToken` only through request-local authorization context. Its public
identity helper separates OAuth `client_id`, issuer and subject; Agnara does
not silently collapse those meanings into a core actor. Instead, an explicit
application mapper receives an immutable value containing only client,
issuer, subject, resource and scopes. Raw bearer credentials and arbitrary
claims do not cross that boundary, mapper failures become redacted internal
protocol errors, and concurrent requests do not share principals.

Discovery applies only the capability's statically declared scope subset to
the mapped principal. It preserves declaration order and private, immediately
stale caching. This reduces unauthorized metadata disclosure but is not full
policy evaluation and cannot authorize a future `tools/call`; invocation must
evaluate the core policy independently.

Authorization references:

- https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/src/mcp/server/auth/provider.py
- https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/src/mcp/server/auth/middleware/auth_context.py

Reviewed 2026-09-04 for E7.6. In MCP `2026-07-28`, an operation that needs
caller input returns an `InputRequiredResult` containing embedded input
requests; it does not open a server-to-client back-channel. Form elicitation
uses an `elicitation/create` request with a human-readable message and a
restricted JSON Schema limited to a flat object of primitive properties. The
official generated wire model does not include an `additionalProperties`
closure keyword for this schema, so Agnara does not publish or claim one.

The first Agnara projection maps only the canonical
`FailureCode.INTERACTION_REQUIRED` confirmation shape to a single required
boolean form field. It validates but does not serialize capability identity or
arbitrary hints. This boundary deliberately stops before `tools/call` and
MRTR resumption: a client `accept` action or boolean response is input, not
verifier-approved `ConfirmationEvidence`. The future resumption boundary must
validate responses and integrity-protect any `requestState` against the
principal, originating method/arguments, expiry and replay requirements.

Interaction references:

- https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation
- https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- https://py.sdk.modelcontextprotocol.io/handlers/multi-round-trip/
- https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/src/mcp_types/_types.py

Reviewed 2026-09-04 for E7.7. Tasks entered MCP in `2025-11-25` and left the
core specification in `2026-07-28`, continuing as an opt-in extension. The
pinned SDK encodes that split exactly: `mcp_types` defines `Task`,
`CreateTaskResult`, `GetTaskRequest`, `CancelTaskRequest`,
`GetTaskPayloadRequest`, `ListTasksRequest` and `TaskStatusNotification` as
types only, and their methods are absent from the dispatched request and
notification unions. `mcp` 2.1.1 ships no task store, lifecycle or `tasks/*`
handler, and its extension interface names `tasks/get` only as an example
contribution. `Tool.execution` with its `task_support` marker is likewise
`2025-11-25`-only; Agnara's projection never sets it.

Multi Round-Trip Requests are therefore the resumption mechanism the pinned
revision actually defines. An interactive request returns
`InputRequiredResult` instead of its normal result; the client fulfills the
server-assigned `input_requests` and retries the same request with
`input_responses` and the echoed `request_state`. The carrier set is closed to
`tools/call`, `prompts/get` and `resources/read`, so `tools/call` is Agnara's
only in-scope carrier.

The SDK's `RequestStateBoundary` seals outgoing state and verifies inbound
echoes before any handler runs, binding envelope version, issue and expiry
times, method, target, an arguments digest, audience and a principal claim,
and rejecting failures as `-32602` with a frozen message. Three limits matter
for Agnara. Only `MCPServer` installs the middleware, while `agnara-mcp`
builds on the lowlevel `Server`, so the boundary must be appended explicitly
with an explicit audience. `RequestStateSecurity.ephemeral()`, the
convenience policy, is process-local and rejects state minted by another
worker or before a restart, so multi-instance deployments need a shared key
ring. The envelope carries expiry but no single-use marker or consumed-token
store, so an identical round stays replayable within its TTL, which defaults
to 600 seconds; round integrity is not invocation-level replay safety.

`ElicitResult.action` (`accept`, `decline`, `cancel`) and its `content` are
client input, so neither can become `ConfirmationEvidence`. A resumption round
must still evaluate the core policy and call `ConfirmationVerifier.verify`
with capability identity, invocation and principal. Recorded as ADR 0042.

E7.8 exercises the pinned SDK's modern ClientSession/dispatcher boundary with
real Agnara projections, malformed requests and concurrent verified identity
contexts. Its in-process connection uses a direct dispatcher pair rather than
network transport or JSON-RPC framing. The bounded coverage and unsupported
surfaces are recorded in `docs/MCP_CONFORMANCE.md`; this is compatibility
evidence, not full protocol certification.

E7.8a adds explicit canonical result projection (ADR 0043). Successful public
JSON data is detached into an envelope with matching text, ordinary canonical
failures use isError tool content without details, and interaction requirements
reuse the strict E7.6 mapper. The pinned SDK validates the serialized results;
this does not implement tools/call or extend the transport support claim.

Reviewed 2026-09-05 for E7.8b and E7.9. E7.8b implements `tools/call` and
answers the open question above: discovery filtering cannot authorize
invocation, and a compiled plan carries no scope policy because declared
scopes are metadata (ADR 0008). The dispatcher therefore evaluates core's
`ScopePolicy` for the capability's declared scopes before any effect, in
addition to whatever policies the plan already carries. `requestState` and
`inputResponses` are refused with `INVALID_PARAMS` rather than ignored, so no
unverified resumption state is accepted while ADR 0042's boundary remains
unimplemented. Recorded as ADR 0044.

E7.9 compares that dispatcher with the pinned SDK's `MCPServer` (the v1
`FastMCP` module now raises on import). Two findings shaped the harness. The
SDK runs a synchronous tool through `anyio.to_thread.run_sync`, so a
sync-only comparison measures a worker-thread hop rather than dispatch;
scenarios are therefore split by handler kind. And the official client
revalidates a result against the tool's `outputSchema`, which only `MCPServer`
publishes, so the end-to-end boundary is not doing identical work for both.
Both are recorded in `docs/benchmarks/mcp-tool-invocation.md` rather than
normalized away.

Task and MRTR references:

- https://py.sdk.modelcontextprotocol.io/handlers/multi-round-trip/
- https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/src/mcp/server/request_state.py
- https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/src/mcp/server/extension.py
- https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/src/mcp_types/methods.py

## A2A

A2A is a post-v0.1 adapter target.

Current reviewed line:

- A2A Protocol 1.0.

The protocol supports independent agent interoperability, discovery, tasks, streaming and multiple protocol bindings.

Reference:

- https://github.com/a2aproject/A2A/blob/main/docs/specification.md

## AsyncAPI

Event-driven support should project to AsyncAPI rather than inventing a documentation format.

Current reviewed line:

- AsyncAPI 3.1.0.

Reference:

- https://www.asyncapi.com/docs/reference/specification/v3.1.0

## uv

Recommended workspace/package manager because its workspace model maps well to Agnara's package boundaries.

Reference:

- https://docs.astral.sh/uv/concepts/projects/workspaces/

## Ruff

Recommended lint and formatting tool.

Reference:

- https://docs.astral.sh/ruff/

## ty

Recommended initial type checker for a Python 3.14-native project. Keep the type-checking strategy replaceable if ecosystem requirements change.

Reference:

- https://docs.astral.sh/ty/

## Research rule

External projects are sources of lessons, not templates to copy wholesale.

Every imported architectural idea must be evaluated against Agnara's capability-first thesis.

## Django project/app ergonomics

Agnara deliberately learns from Django's project/application separation and `startapp` generator.

Useful lessons:

- one project can contain multiple apps;
- an app has a conventional package structure;
- scaffolding removes mechanical setup;
- explicit app registration/introspection improves modularity.

Agnara changes the semantics:

- apps are capability bounded contexts, not web-app packages;
- transports are adapters;
- generated default architecture is modular hexagonal;
- machine-readable and agent-oriented CLI output is required.

References:

- https://docs.djangoproject.com/en/6.0/intro/tutorial01/
- https://docs.djangoproject.com/en/6.0/ref/django-admin/#startapp
- https://docs.djangoproject.com/en/6.0/ref/applications/
