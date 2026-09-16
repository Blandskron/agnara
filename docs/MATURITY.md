# Subsystem Maturity

This document answers one question: **what exists today?**

It is the authoritative status record. `ROADMAP.md` says where Agnara is
going, `docs/INITIATIVES.md` says in what order, and this file says what is
true now. When they disagree, this file wins and the others are wrong.

Every status below was verified against the code on the commit that last
edited this file, not against another document. Where a status is qualified,
the qualification is the point: "the runtime propagates cancellation" and
"the runtime offers a cancellation API" are different claims, and conflating
them is how a framework acquires documentation nobody trusts.

`tests/architecture/test_documentation_consistency.py` checks the parts of
this table a machine can check, so a package cannot quietly gain or lose a
public surface without this file failing.

## Vocabulary

| Status | Meaning |
| --- | --- |
| `IMPLEMENTED` | Works today, covered by tests, usable from the published or repository packages. |
| `EXPERIMENTAL` | Works, but the surface is expected to change and is not a compatibility commitment. |
| `DESIGNED` | A decision exists in an ADR or RFC; no runtime behaviour yet. |
| `PLANNED` | Agreed to be built, with no design decision recorded yet. |
| `RESEARCH` | Not agreed. Needs an RFC before it becomes `PLANNED`. |
| `DEFERRED` | Deliberately postponed, with the reason recorded. |
| `DEPRECATED` | Still present, scheduled for removal. |
| `REMOVED` | Gone; kept here only while references may survive. |

A subsystem with no entry is `RESEARCH` by default. Absence is not a promise.

## Distributions

| Package | Status | Published to PyPI | Public names | Notes |
| --- | --- | --- | --- | --- |
| `agnara` | `IMPLEMENTED` | yes | 41 | The kernel. Standard library only. |
| `agnara-http` | `EXPERIMENTAL` | no | 14 | Public HTTP composition includes generated OpenAPI, built-in documentation UIs and authorized Explorer; third-party providers and discovery stay internal. |
| `agnara-mcp` | `IMPLEMENTED` | no | 20 | Publication-ready tool projection; see the MCP table. |
| `agnara-cli` | `IMPLEMENTED` | no | 4 | Publication-ready scaffolding, introspection and `agnara` script. |
| `agnara-telemetry` | `IMPLEMENTED` | no | 2 | Publication-ready OpenTelemetry metrics and tracing hooks. |
| `agnara-a2a` | `PLANNED` | no | 0 | Publication-ready reserved namespace; no implementation. |
| `agnara-events` | `PLANNED` | no | 0 | Publication-ready reserved namespace; no implementation. |

Only `agnara` is published. All seven distributions are versioned, buildable,
installable from their artifacts and ready for the tag workflow to publish as
one reviewed set; ADR 0021 keeps every version synchronized and ADR 0073 fixes
the publication boundary. Publication-ready is not published: the six new
PyPI projects still require their Pending Trusted Publishers before the tag.

Every distribution's public surface is classified in
`docs/public-api.json` and enforced in both directions by the release gate:
337 classified exports across 49 modules, all `provisional`. Those entries are
import paths rather than distinct symbols: 166 names are reachable at 337 paths,
because a name is classified once per module it can be imported from.
`agnara-cli` dropped from 17
public names to 4 in the baseline, because the other thirteen were implementation
helpers re-exported from underscore-prefixed modules and never documented,
used or designed as an API (ADR 0076).

`agnara-http` now declares fourteen `provisional` names that compose
capabilities, compile an ASGI 3 application, project OpenAPI and publish the
reviewed documentation profile. `docs/HTTP_COMPOSITION.md` is the supported
guide.

It stays `EXPERIMENTAL` rather than becoming `IMPLEMENTED` because the public
spelling is still provisional before 1.0, third-party provider extension and
the authorized discovery endpoint remain intentionally internal, and the
surface is newly expanded. The transport behaviour is settled; the spelling is
not.

## Kernel — `agnara`

| Subsystem | Status | Evidence and limits |
| --- | --- | --- |
| Capability declaration and metadata | `IMPLEMENTED` | Effects, risk, confirmation, idempotency, scopes. RFC 0001. |
| Capability identity | `IMPLEMENTED` | `<namespace>.<name>`; namespace is the owning app. ADR 0065. |
| Capability registry and freeze | `IMPLEMENTED` | ADR 0005. Registration closes at `compile()`. |
| App / bounded-context model | `IMPLEMENTED` | `App`, `AppDescriptor`, `Agnara.include`. ADR 0011, ADR 0065. |
| Duplicate app identity detection | `IMPLEMENTED` | `DuplicateAppError`. |
| Schema port | `IMPLEMENTED` | ADR 0004. Standard-library adapter ships; Pydantic and msgspec remain experiments. |
| Dependency injection | `IMPLEMENTED` | Compiled graph, `SINGLETON` and `INVOCATION` scopes, sync/async providers and generators with teardown. |
| Execution plan compilation | `IMPLEMENTED` | ADR 0005, ADR 0025. Startup-time schema, dependency and policy compilation. |
| Direct invocation | `IMPLEMENTED` | `invoke_result`; canonical `Success`/`Failure`. ADR 0022. |
| Canonical failure vocabulary | `IMPLEMENTED` | Ten codes. Transport-neutral. |
| Deadlines | `IMPLEMENTED` | Enforced with `asyncio.timeout_at`, mapped to `FailureCode.TIMEOUT`. |
| Cancellation | `IMPLEMENTED` (propagation only) | `CancelledError` is never caught or translated. There is no cooperative cancellation API and no disconnect signal. |
| Policy engine | `IMPLEMENTED` | Pre-handler evaluation, scopes, principals, confirmation. ADR 0024. |
| Confirmation requirements | `IMPLEMENTED` | Declaration and verification; no durable pending-approval state. |
| Telemetry hooks | `IMPLEMENTED` | Start and terminal events. ADR 0023. No span model in the kernel. |
| Unified exposure model | `IMPLEMENTED` | `agnara.exposure`: neutral identity, per-surface adapter compilation, one frozen availability registry. ADR 0070, RFC 0006. Both shipped adapters go through it. |
| Introspection snapshot | `IMPLEMENTED` | Versioned, frozen, no runtime objects reachable. ADR 0045. Exposures are derived from the frozen exposure registry. |
| Discovery visibility | `IMPLEMENTED` | Per-field publication decisions. ADR 0046. |
| Execution identity | `IMPLEMENTED` | ADRs 0087, 0088 and 0091. Each `ExecutionContext` owns an opaque runtime-generated identity; direct idempotency reuse adopts the claimed logical identity while each lifecycle invocation retains a fresh telemetry `invocation_id`. Caller metadata cannot choose it. HTTP returns only the generated identity in `agnara-execution-id`; HTTP/MCP request IDs are bounded untrusted correlation only, never execution selection, authority or idempotency proof. |
| Idempotency | `IMPLEMENTED` for explicit direct complete-result invocation; `PLANNED` for adapter projections | ADRs 0089 and 0091 define atomic capability/principal/key/fingerprint transitions and an explicit `ExecutionContext` option. An `Idempotency.YES` direct capability claims before dependencies and handler work, reuses completed successes, abandons failures/cancellation, and fails closed on store or stale-codec errors. The reusable store conformance suite fixes TTL start and inclusive expiry semantics, deterministic races and bounded cleanup; the in-memory reference store remains process-local. HTTP/MCP accept no idempotency key or selector. |
| Streaming results | `IMPLEMENTED` (kernel and HTTP SSE) | ADR 0084, ADR 0085, ADR 0086, RFC 0009. `open_stream` owns a declared async generator: pull-based demand with no kernel buffer, policy and input validation before the first unit, `StreamInterrupted` for failure after output, and an explicit `StreamTerminal`. `output=...` declares and validates each unit before delivery; omitted output is the intentional unconstrained `Any` contract. `Http.sse` projects it over HTTP with a delayed response start, one `message` event per unit, an explicit terminal event and owned disconnect handling; MCP, A2A, events and WebSockets do not project it. |
| Audit trail | `PLANNED` | The word appears in docstrings; there is no audit system. |
| Capability-to-capability composition | `IMPLEMENTED` for same-snapshot complete results | ADR 0093. `CapabilityRuntime` accepts one frozen capability snapshot and only its identity-matching compiled plans, then injects an invocation-scoped `CapabilityInvoker`; each child has fresh identity/context and its own policy, confirmation, validation and DI lifecycle. A child receives a detached direct actor and only a bounded correlation label: parent confirmation/idempotency, raw invocation metadata and delegation evidence do not cross. Deadline may only shorten, cancellation propagates through nested work, and direct/indirect recursion or depth exhaustion are refused before the next effect. A streaming target returns a canonical conflict before producer start; a streaming parent cannot receive an invoker. Delegation, stream and cross-app composition remain unsupported. |
| Multi-tenancy | `RESEARCH` | No tenant concept anywhere in the kernel. |
| Free-threaded Python | `RESEARCH` | Immutability after compile is designed for it; nothing is verified under a free-threaded build. |

## HTTP — `agnara-http`

| Subsystem | Status | Notes |
| --- | --- | --- |
| ASGI boundary | `IMPLEMENTED` | `http` and `lifespan` scopes. ADR 0041. |
| Lifespan bridge | `IMPLEMENTED` | ADR 0029. |
| Routing | `IMPLEMENTED` | Compiled route registry. ADR 0034. |
| Request binding | `IMPLEMENTED` | Path, query, header, JSON body, cookie, form field and file upload. ADR 0026, ADR 0072. Repeated values and collections are refused by decision. |
| Response serialization | `IMPLEMENTED` | Deterministic success responses. ADR 0027. |
| RFC 9457 problem responses | `IMPLEMENTED` | ADR 0028, ADR 0030. |
| OpenAPI projection | `IMPLEMENTED` | Deterministic, pinned against a fixture. ADR 0032. |
| Documentation providers | `IMPLEMENTED` | Swagger UI, ReDoc and Scalar, vendored and version-pinned. ADR 0036-0040. |
| Discovery endpoint | `IMPLEMENTED` | ADR 0049. |
| Explorer | `IMPLEMENTED` | Read-only shell. ADR 0052. |
| Exposure compilation | `IMPLEMENTED` | Public `Http.compile()` derives neutral records from the compiled route table. ADR 0070, ADR 0071. |
| Public composition API | `IMPLEMENTED` | Seven provisional exports compose and compile an ASGI application through supported entry points. ADR 0071. |
| Cookies, forms, multipart, uploads | `IMPLEMENTED` | Public binding sources with bounded in-memory bodies and multipart part count. ADR 0072. |
| SSE streaming projection | `IMPLEMENTED` | ADR 0085. `Http.sse` is a GET-only, bounded projection with delayed response commitment, one message per unit, one explicit terminal event, no replay/keepalive policy, pull-based demand and owned disconnect cleanup. `tests/http/test_sse.py` supplies ASGI conformance evidence. |
| WebSockets | `PLANNED` | The ASGI boundary handles no `websocket` scope, and WebSocket streaming still needs its own decision. |
| Middleware / interceptors | `DEFERRED` | No extension point, deliberately: ADR 0072 keeps cross-cutting concerns at the ASGI layer, which already wraps an `HttpApplication`. |
| CORS, compression, static files, proxy headers, trusted hosts | `DEFERRED` | None present. ADR 0072 records where each belongs instead: the reverse proxy, the ASGI server, or ASGI middleware around the application. |
| Content negotiation, conditional and range requests | `RESEARCH` | None present. |
| HTTP/2, HTTP/3 | `RESEARCH` | A server concern today; no Agnara position recorded. |

## MCP — `agnara-mcp`

| Subsystem | Status | Notes |
| --- | --- | --- |
| Tool projection | `IMPLEMENTED` | ADR 0043, ADR 0044. |
| Exposure surface | `IMPLEMENTED` | `Mcp(app, surface=...)` and `compile_surface()` contribute neutral records. ADR 0070. |
| Tool invocation dispatch | `IMPLEMENTED` | |
| Schema mapping | `IMPLEMENTED` | |
| Result projection | `IMPLEMENTED` | Canonical results into MCP shapes. |
| Interaction-required projection | `IMPLEMENTED` | |
| Authorization and principal mapping | `IMPLEMENTED` | |
| Protocol version pinning | `IMPLEMENTED` | ADR 0010. |
| Task boundary | `DESIGNED` | ADR 0042 decides the boundary; no multi-round-trip runtime. |
| Resources, prompts | `RESEARCH` | Whether capabilities map to them coherently is undecided. |
| Progress, sessions, notifications | `PLANNED` | |
| Streamable HTTP, stdio transports | `PLANNED` | |
| Sampling, elicitation | `RESEARCH` | |
| Pagination | `PLANNED` | |

## Other surfaces

| Subsystem | Status | Notes |
| --- | --- | --- |
| CLI scaffolding | `IMPLEMENTED` | `project create`, `app create`, architectures, `--with`, profiles, aliases. |
| CLI introspection | `IMPLEMENTED` | `apps`, `inspect`, `graph`, `schema openapi`, `context`. |
| Project manifest | `IMPLEMENTED` | `agnara.toml`. ADR 0059. No schema version field yet. |
| Telemetry bridges | `IMPLEMENTED` | Optional OpenTelemetry metrics and spans. `tests/integration/telemetry/` proves one FastAPI 0.141.1 host trace with nested capability spans, concurrent isolation, stream terminal closure and redaction using SDK 1.44.0 in-memory export. Host extraction, providers, exporters and shutdown remain application-owned; compilation, nested invocation and streaming are additionally proven in an interpreter where `opentelemetry` is unimportable. No network-exporter or framework-support claim follows. ADR 0054-0058. |
| A2A | `PLANNED` | Namespace reserved. |
| Events / AsyncAPI | `PLANNED` | Namespace reserved. |
| Tasks and durable execution | `RESEARCH` | No package, no abstraction. |
| Workflows | `RESEARCH` | Whether Agnara should own one is undecided. |
| Realtime | `RESEARCH` | |
| Testing utilities | `PLANNED` | No first-party harness; the repository tests the framework, not applications built on it. |
| Plugin system | `RESEARCH` | No discovery, loading or trust model. |
| Persistence, cache, queue and scheduler integrations | `RESEARCH` | No shipped port, adapter or runtime dependency. `tests/integration/persistence/` is an optional SQLAlchemy 2.0.54/SQLite fixture that proves host-owned `Session` and transaction decisions around the existing DI boundary; it does not make Agnara an ORM or claim PostgreSQL, async-session, migration, cache, queue or scheduler support. |
| Framework embedding contract | `DESIGNED` | ADR 0094 accepts an explicit async complete-result host boundary over existing provisional runtime values: lifecycle/resource ownership, principal/context/error/telemetry bridges and one-event-loop reuse rules are defined. Version-pinned Starlette 1.6.0, FastAPI 0.141.1 and Django 6.1.1 fixtures exercise those provisional values without adding a framework dependency or support claim. |
| Side-by-side composition with an external framework | `EXPERIMENTAL` | `tests/integration/starlette/` exercises native and direct-runtime routes in one Starlette 1.6.0 lifespan. `tests/integration/fastapi/` adds FastAPI 0.141.1 native dependency/security, exception and middleware ownership, direct invocation, idempotency, composition, disconnect cancellation and explicitly coordinated mounted HTTP/SSE projection. Both are optional fixtures: neither claims integration support, automatic mounted-lifespan handling, OpenAPI merging nor release-gate closure. |
| Host-diversity fixture | `EXPERIMENTAL` | `tests/integration/litestar/` exercises the same public embedding boundary in Litestar 2.24.0, including host-owned canonical-result/status serialization. It is selected conditional evidence, not Litestar or Flask support. |
| Second shipped schema adapter | `RESEARCH` | Pydantic and msgspec remain `experiments/`; neither is packaged or supported. |
| Typed client generation | `RESEARCH` | |
| Native acceleration | `DEFERRED` | ADR-level position: only after measured bottlenecks. |

## Quality infrastructure

| Subsystem | Status | Notes |
| --- | --- | --- |
| Lint, format, type check | `IMPLEMENTED` | Ruff and ty, enforced in CI. |
| Test suite | `IMPLEMENTED` | Unit, architecture, contract, conformance, integration and release tiers. |
| Architecture enforcement tests | `IMPLEMENTED` | Package boundaries, import direction, introspection field decisions, generated-app layering. |
| Cross-platform CI | `IMPLEMENTED` | Linux, macOS, Windows. |
| Packaging gate | `IMPLEMENTED` | Builds and inspects all seven wheels/sdists, then installs all seven wheels outside the workspace with first-party index access disabled. |
| Release readiness program | `IMPLEMENTED` | Evidence expires against the commit it was recorded on. |
| Benchmarks | `IMPLEMENTED` | Five recorded baselines. `benchmarks/runtime_paths.py` covers dependency injection, policy evaluation, execution identity, idempotency, nested invocation, streaming and compile scaling. |
| Performance budgets | `IMPLEMENTED` | `docs/performance/budgets.json` holds 13 calibrated limits enforced by `scripts/check_performance_budgets.py` in CI. Budgets are ratios between scenarios measured in the same run, not absolute latency. The gate is demonstrated to fail on a real regression. Limits were calibrated on one developer machine and remain subject to maintainer approval. |
| Property testing and fuzzing | `PLANNED` | None. |
| Protocol conformance suites | `PLANNED` | MCP conformance is repository-authored; no upstream suite is run. |
| Security scanning, SBOM, signing | `PLANNED` | None configured. `SECURITY.md` records this. |
| Documentation consistency checks | `IMPLEMENTED` | This table is machine-checked where possible. |

## How to change this file

Change the code first. A status here is a claim about the repository, and the
consistency test exists so that the claim cannot outlive the code that made it
true. When a subsystem's status changes, the pull request that changes the
behaviour is the one that updates this row.
