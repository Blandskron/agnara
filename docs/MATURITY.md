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
| `agnara-http` | `EXPERIMENTAL` | no | 7 | Publication-ready public composition API; documentation UI, Explorer and discovery stay internal. |
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
292 exports across 48 modules, all `provisional`. `agnara-cli` dropped from 17
public names to 4 in the baseline, because the other thirteen were implementation
helpers re-exported from underscore-prefixed modules and never documented,
used or designed as an API (ADR 0076).

`agnara-http` now declares a public surface: seven `provisional` names that
compose capabilities, compile an ASGI 3 application and project OpenAPI.
`docs/HTTP_COMPOSITION.md` is the supported guide.

It stays `EXPERIMENTAL` rather than becoming `IMPLEMENTED` because three
implemented subsystems are deliberately not reachable through it — the
documentation UI providers, the Explorer and the authorized discovery endpoint
— and because the surface is one release old. The transport behaviour is
settled; the spelling is not.

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
| Idempotency | `IMPLEMENTED` as metadata, `PLANNED` as behaviour | Declared and published; the runtime performs no deduplication or replay. |
| Streaming results | `IMPLEMENTED` (kernel and HTTP SSE) | ADR 0084, ADR 0085, ADR 0086, RFC 0009. `open_stream` owns a declared async generator: pull-based demand with no kernel buffer, policy and input validation before the first unit, `StreamInterrupted` for failure after output, and an explicit `StreamTerminal`. `output=...` declares and validates each unit before delivery; omitted output is the intentional unconstrained `Any` contract. `Http.sse` projects it over HTTP with a delayed response start, one `message` event per unit, an explicit terminal event and owned disconnect handling; MCP, A2A, events and WebSockets do not project it. |
| Audit trail | `PLANNED` | The word appears in docstrings; there is no audit system. |
| Capability-to-capability composition | `RESEARCH` | No nested `ExecutionContext`, no propagation contract. |
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
| SSE streaming projection | `DESIGNED` | ADR 0085 defines the projection; no `Http.sse` runtime or ASGI conformance suite exists yet. |
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
| Telemetry bridges | `IMPLEMENTED` | OpenTelemetry metrics and spans. ADR 0054-0058. |
| A2A | `PLANNED` | Namespace reserved. |
| Events / AsyncAPI | `PLANNED` | Namespace reserved. |
| Tasks and durable execution | `RESEARCH` | No package, no abstraction. |
| Workflows | `RESEARCH` | Whether Agnara should own one is undecided. |
| Realtime | `RESEARCH` | |
| Testing utilities | `PLANNED` | No first-party harness; the repository tests the framework, not applications built on it. |
| Plugin system | `RESEARCH` | No discovery, loading or trust model. |
| Persistence, cache, queue and scheduler integrations | `RESEARCH` | No port, no adapter, no dependency. `docs/INTEROPERABILITY.md` records the intent; I20 owns the work. |
| Framework embedding contract | `RESEARCH` | RFC 0008 states the questions. Nothing exists that an external host could call. |
| Side-by-side composition with an external framework | `RESEARCH` | HTTP now has a public composition surface (ADR 0071); interoperability with an external framework still requires its own conformance evidence and belongs to `1.0.0`. |
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
| Benchmarks | `IMPLEMENTED` (baseline only) | Four recorded baselines; no budgets, no regression gate. |
| Property testing and fuzzing | `PLANNED` | None. |
| Protocol conformance suites | `PLANNED` | MCP conformance is repository-authored; no upstream suite is run. |
| Security scanning, SBOM, signing | `PLANNED` | None configured. `SECURITY.md` records this. |
| Documentation consistency checks | `IMPLEMENTED` | This table is machine-checked where possible. |

## How to change this file

Change the code first. A status here is a claim about the repository, and the
consistency test exists so that the claim cannot outlive the code that made it
true. When a subsystem's status changes, the pull request that changes the
behaviour is the one that updates this row.
