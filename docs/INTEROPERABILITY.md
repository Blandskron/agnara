# Interoperability and Composition

Agnara's kernel is transport neutral. The application compiles a capability
snapshot and invokes it through the same policy, validation and dependency
path whether the outer caller is Python, HTTP, MCP or a host framework.
Integration does not transfer authentication, routing, persistence or lifecycle
ownership into the kernel.

## Supported contract

The shipped contract is an explicit asynchronous bridge from plain input
values and a host-verified `Principal` to a compiled `CapabilityRuntime`.
It returns canonical `Success` or `Failure`. The host owns credential
verification, native routes, result mapping, sessions, transactions, connection
lifecycle and telemetry export. It never binds raw request, response, ORM,
session, credential or tracing objects into capability inputs or DI.

| Mode | Outer owner | Boundary |
| --- | --- | --- |
| Standalone | Agnara composition root | Compile and invoke with the kernel alone. |
| Agnara host | Agnara composition root | Reach infrastructure through application-owned ports. |
| Embedded Agnara | External host | Invoke an explicit runtime handle from a host route or task. |
| Side-by-side | External host | Keep native routes and Agnara exposures in one owned lifespan. |

A frozen registry and its plans can be shared. A live runtime and DI container
belong to one event loop; concurrent tasks on that loop are supported, while
cross-loop and cross-thread calls are not. Cancellation propagates. Closing one
runtime does not close another application. Nested calls use the same compiled
snapshot and re-evaluate authority. Idempotency is never authorization to retry.

The kernel imports no FastAPI, Starlette, Django, Litestar, ORM, MCP SDK or
OpenTelemetry SDK. HTTP and MCP are explicit adapter distributions. The
standard-library schema adapter ships in the kernel; optional Pydantic and
msgspec experiments are not packaged schema adapters.

## Validated integration evidence

The [Django async-view guide](DJANGO_EMBEDDING.md) and
[runnable example](../examples/django_embedding.py) exercise native views with
`AsyncRequestFactory` and an explicit application-owned async lifecycle.
Tests cover context isolation, cancellation and same-loop resource cleanup;
this fixture bypasses URL resolution, middleware and server startup.

The [Litestar embedding guide](LITESTAR_EMBEDDING.md) and its
[runnable example](../examples/litestar_embedding.py) demonstrate native host
identity, explicit JSON/outcome mapping and same-loop resource ownership.
Tests cover concurrent context isolation, propagated cancellation and
exceptional lifespan exit; this is optional pinned fixture evidence.

The [Starlette embedding guide](STARLETTE_EMBEDDING.md) and its
[runnable example](../examples/starlette_embedding.py) demonstrate native host
authentication, input/outcome mapping and same-loop resource ownership. Tests
exercise concurrent context isolation, cancellation and exceptional host exit;
this remains an optional pinned fixture rather than a general support tier.

The [SQLite persistence guide](SQLITE_PERSISTENCE.md) demonstrates an
application ledger port, explicit commit/rollback decisions over canonical
outcomes and cancellation, and session/engine cleanup. Its
[runnable example](../examples/sqlite_persistence.py) uses a small sequential
synchronous SQLite fixture; it does not introduce an ORM adapter or concurrent
session-sharing contract.

The [FastAPI embedding guide](FASTAPI_EMBEDDING.md) walks through the
[runnable example](../examples/fastapi_embedding.py), with example-level
tests for host authentication, policy refusal, concurrent context isolation
and runtime shutdown on the host loop.

These are executable repository fixtures, with pinned optional dependencies.
They validate the narrow contract shown, not a general support promise for
every feature or version of the host product.

| Evidence | What it exercises | Boundary |
| --- | --- | --- |
| `tests/reference_apps/standalone.py` | Core invocation, nested calls, direct idempotency, streaming, cancellation and telemetry. | No external framework required. |
| `tests/reference_apps/host_sqlite.py` and `tests/integration/persistence/test_sqlalchemy_sqlite.py` | SQLAlchemy + SQLite through an application `Ledger` port. | Host owns session and transaction. |
| `tests/integration/starlette/` | Native and embedded routes in one lifespan. | No implicit host-object injection. |
| `tests/integration/fastapi/` and `tests/reference_apps/embedded_fastapi.py` | Host authentication mapping, native routing and complete-result bridge. | Unknown credential fails closed. |
| `tests/reference_apps/side_by_side_fastapi.py` | Native FastAPI routes beside a compiled `agnara-http` surface. | Host explicitly coordinates lifespan; OpenAPI tables are not merged. |
| `tests/integration/django/` | Django-owned request and response mapping. | No Django dependency in core. |
| `tests/integration/litestar/` | Litestar-owned result serialization and same-loop runtime/resource lifespan. | Optional fixture evidence only. |
| `tests/integration/telemetry/` | OpenTelemetry metrics and spans in a shared host. | Host owns SDK and exporter. |
| `tests/conformance/test_host_harness.py` | Shared lifecycle, context, policy and cleanup assertions across host fixtures. | A fixture is not a support tier. |
| `tests/integration/test_surface_agreement.py` | Direct, HTTP and MCP projections of the same capability. | Transport policy cannot weaken core policy. |

## Installed candidate-wheel guide coverage

`tests/release/test_integrated_dogfooding.py` builds all seven candidate wheels,
installs them together in a fresh Python 3.14 environment with first-party index
access closed, audits public imports and verifies installed-package provenance.
It runs standalone, SQLite host, embedded and side-by-side FastAPI consumers,
then copies the exact guide sources into an external directory and runs them
under Python `-I` with bounded subprocess timeouts. Optional host/SDK fixture
versions stay pinned outside distributable dependencies.

| Exact guide | Checked behavior | Evidence boundary |
| --- | --- | --- |
| [Starlette](../examples/starlette_embedding.py), [Litestar](../examples/litestar_embedding.py), [Django](../examples/django_embedding.py) | Parsed JSON/status for success, denial, credentials, malformed/invalid input and native health; only authorized effects and ordered audit/runtime cleanup. | In-process host fixtures; no network server or production authentication. |
| [FastAPI](../examples/fastapi_embedding.py) | Parsed outcomes and acceptance/rejection of bounded correlation labels. | Printed outcomes do not independently prove cleanup; lifecycle tests remain separate. |
| [SQLite](../examples/sqlite_persistence.py) | Canonical success/refusal/failure/cancellation, fresh-observer rows, rollback and ordered port/runtime/session/engine teardown. | Sequential local fixture, not concurrent session sharing or a durable store adapter. |
| [MCP tools](../examples/mcp_tools.py) | Official-client discovery order/cache hints, closed schemas, text/structured envelopes, refusal/errors/redaction and provider/connection cleanup. | Anonymous in-process dispatcher; no sockets, JSON-RPC framing, OAuth or wider conformance. |
| [HTTP SSE](../examples/http_sse.py) | Independent complete-frame decoding, units/counts, terminal/problems/redaction, disconnect, empty stream and producer/provider order without prefetch. | In-memory ASGI capture; no socket chunk parsing, reconnect or replay. |
| [Schemas](../examples/schema_contracts.py) | Typed Python/JSON/default outcomes, serialization, input identity, unchanged wire data, error paths and complete compiled schemas. | Standard schema adapter only; container closure, policy/materialization order and cancellation remain separate checkout evidence. |
| [Dependencies](../examples/dependencies.py) | Refusals, singleton reuse, distinct invocation resources, shared branch identity, closed flags and complete effect/cleanup trace. | Local resources; owner-cancellation remains separate checkout evidence. |
| [Telemetry](../examples/invocation_telemetry.py) | Six outcomes, observer-failure isolation, paired unique attempt/execution IDs, correlation, field sets, duration/count contracts and payload privacy. | Local synchronous observers; container closure remains separate checkout evidence, with no exporter/production collector claim. |
| [Deadlines](../examples/deadlines.py) | Exact success/refusal/timeout/child cancellation and ordered handler/resource teardown. | Cooperative cancellation permits synchronous entry before the first suspension; owner cancellation/container closure remain separate checkout evidence, not hard timing guarantees. |
| [Confirmation](../examples/confirmation.py) | Nine outcomes, complete interaction envelopes, rejected metadata/forgery/input/actor/scope/replay/expiry and approved effect/cleanup trace. | Local single-loop authority; broader exact-binding/atomic contender and verifier-exception tests remain separate checkout evidence. No authenticated human or durable/multi-process approval service. |
| [Introspection](../examples/introspection.py) | Source descriptors, five complete filtered publications, redaction, detached JSON, independent invocation authority and effect/cleanup order. | Compiled descriptions and direct calls; no served discovery/OpenAPI/Explorer/MCP endpoint, authentication, network, browser or thread-safety evidence. |
| [Direct idempotency](../examples/direct_idempotency.py) | Exact receipts/refusals, nonempty execution identities, duplicate identity reuse, principal isolation and two authorized effects. | Sequential process-local store; no durable persistence, concurrent-contender, restart, HTTP/MCP-selector or independent resource-close evidence. |
| [Nested invocation](../examples/nested_invocation.py) | Exact authorized summary, explicit successful fallback for child denial, parent/no-scope refusal before effects, distinct root execution identities and ordered independent handler traces. | Sequential complete-result calls in one compiled application per case; no independent child identity/context, resource-close, cancellation, delegation or cross-application evidence from this guide consumer. |
| [Direct streaming](../examples/direct_streaming.py) | Seven ordered typed unit/count/terminal/refusal observations, exact redacted failures, demand and producer/provider traces, plus propagated caller cancellation and cleanup without surviving tasks. | Local direct Python stream owner; independent container-close/deadline checks remain checkout evidence, with no network backpressure, durable resumption or cross-task sharing claim. |

Each guide has negative validation proofs in `tests/release/` for its stated
contract: altered results/metadata, leaked internals, unexpected effects and
missing/reordered cleanup fail the corresponding gate. SSE units/counts and
schema booleans cannot be substituted with equal Python numeric values;
SSE diagnostic checks also inspect decoded JSON for escaped text. Structured
consumers check that no tasks survive. Introspection additionally rejects shared
mutable serialization containers before exercising mutation isolation.
Deferred dataclass annotations resolve through registered unchanged modules.

This is candidate-wheel evidence tied to the reviewed source commit, not a
regression claim against already-published PyPI artifacts or a new general
framework support tier. Current source-specific tests retain the detailed
checks; this table summarizes their boundary rather than duplicating a growing
chronology of completed work.

The installed-wheel side-by-side FastAPI consumer compiles its live HTTP child
inside the host lifespan and explicitly exchanges ASGI startup/shutdown
messages through an owned task group with bounded handshake waits.
[FastAPI does not drive mounted-child lifespan automatically](https://fastapi.tiangolo.com/advanced/events/#sub-applications).
The fixture verifies the child's actual lifecycle callbacks and singleton
resource reuse, then resource closure before child stop and host stop on one
loop, for normal and exceptional host exits. Its local tests additionally
exercise cancellation after draining HTTP calls, failed handshakes and a silent
startup timeout without orphan tasks. This remains fixture wiring, not a
generic host adapter, automatic drainage or merged OpenAPI contract.

The Litestar fixture constructs its runtime and container inside the host's
lifespan, invokes them on that loop and closes them at lifespan exit. Generator
resource probes verify singleton reuse, invocation isolation and cleanup on
success, handler failure and an exceptional test-client exit. Denied calls
acquire no resources. The host drains invocation work before singleton
shutdown; tests do not manually close an active runtime from the test caller's
loop. This is application-owned fixture wiring, not automatic lifecycle
integration or permission to share a runtime across loops or threads.

## Experimental

The Pydantic and msgspec adapters in `experiments/` are research examples.
Host fixtures may demonstrate an application pattern without creating an
official integration package. Every new adapter must define ownership,
authority, failure translation, cancellation, cleanup and a conformance lane
before support is claimed.

## Research and unsupported boundaries

There is no generic host facade, synchronous embedding bridge, automatic
mounted-child lifespan management, OpenAPI merge, automatic retry, durable
idempotency store, cross-application invocation or delegated authority.
WebSockets and MCP streaming are not projections of the kernel stream.
`agnara-a2a` and `agnara-events` expose no runtime API. GraphQL, gRPC,
brokers, task queues and workflow engines require separate contracts before
implementation.

The [maturity matrix](MATURITY.md) owns current subsystem claims;
[architecture](../ARCHITECTURE.md), [security](../SECURITY.md) and
[public API policy](PUBLIC_API.md) own their respective contracts.
