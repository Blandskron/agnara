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

`tests/release/test_integrated_dogfooding.py` builds all seven wheels, installs
them in a fresh Python 3.14 environment with first-party index access closed,
checks public imports, and runs standalone, SQLite host, embedded FastAPI and
side-by-side FastAPI consumers under isolated Python mode. It also copies the
exact runnable FastAPI, Starlette, Litestar, Django and SQLite guide programs
into the external consumer directory and executes them with that environment's Python
`-I`. Existing optional host fixture versions are pinned in that environment;
they remain outside distributable dependencies.

The Starlette, Litestar and Django gate checks parsed JSON outcomes for authorized calls, policy
denial, missing/unknown credentials, malformed/invalid input and native health,
then verifies only the authorized order was recorded and audit/runtime cleanup
occurred in order. Negative tests prove missing/duplicate cases, incorrect
statuses/bodies, extra effects and broken cleanup fail the gate. This is
candidate-wheel evidence tied to the reviewed source commit, not a claim that
new guide behavior was tested against the already-published PyPI artifacts.
It adds no framework plugin, network-server, production-authentication or
durable-store support claim.

The exact FastAPI guide additionally checks parsed status/JSON responses for
scoped access, policy denial, missing/unknown credentials and native health,
plus acceptance of bounded correlation and rejection of oversized or injected
tokens. Its printed output does not independently prove resource cleanup;
the example-level lifecycle tests remain the evidence for that boundary.
The SQLite guide checks canonical success/refusal/failure/cancellation results,
the committed row through a fresh observer, and the complete ordered port,
transaction, runtime, session and engine trace. Denial and invalid input open
no port; failure and cancellation leave no persisted rows. Negative validator
tests reject changed outcomes, extra rows, commits replacing rollbacks, missing
port cleanup and reordered runtime/session/engine shutdown. Both exact sources
run outside the checkout under isolated Python mode with bounded timeouts and
the existing optional fixture pins.

The installed-wheel lane also copies the exact
[MCP tools guide source](../examples/mcp_tools.py). A separate external consumer
loads that copied source and calls its demonstration through the pinned
official client under Python `-I`, with an overall subprocess timeout. It checks
SDK discovery order, private zero-TTL listing, the closed input schema without
DI parameters, success/recovery text and structured envelopes, refusal/error
codes, diagnostic redaction, unknown-tool protocol errors and no effects from
rejected calls. It checks the complete ordered provider/handler effect trace
and that no connection tasks survive the demonstration. Negative tests reject
weakened discovery/schema, changed envelopes/codes, leaked diagnostics, forbidden
effects and missing/reordered cleanup. This is anonymous in-process dispatcher
evidence against candidate wheels; it does not test sockets, JSON-RPC framing,
OAuth, network transport or additional MCP features.

The same installed-wheel lane copies the exact
[HTTP SSE guide source](../examples/http_sse.py) and runs a self-contained
external consumer under Python `-I` with a bounded timeout. It exercises the six
demonstration cases and the original empty-stream path. An independent decoder
checks complete captured SSE frames against the guide's structured observations,
including exact units, terminal outcomes/counts, ordinary pre-stream problems,
redacted first/late failures and terminal-free disconnect. It also checks
headers, producer/provider lifecycle order, no resource acquisition on refusal,
no prefetch after disconnect and no surviving ASGI/lifespan tasks. Negative
tests reject corrupt frames/results/headers, unsupported or duplicate events,
diagnostic leaks and missing/reordered cleanup. JSON booleans cannot substitute
for integer units/counts, and diagnostic checks also inspect decoded JSON to
catch escaped text. This is bounded in-memory ASGI evidence against candidate
wheels, not network chunk parsing, socket/server,
reconnect, replay or deployment evidence.

The lane also loads the exact
[schema-contracts guide source](../examples/schema_contracts.py) from the copied
external directory under Python `-I`, keeping its module registered while the
dataclass annotations resolve. The consumer checks typed direct/JSON/default
successes, successful-value JSON serialization, direct input identity versus
detached JSON objects, unchanged wire input and exact handler events. It checks
denial, strict direct-mapping refusal, nested error paths, boolean/extra-field/
enum refusals, output redaction, unconstrained annotation-only output and the
demonstrated compiled input/output schemas. Negative tests reject changed
outcomes/paths, weakened schemas, unexpected effects, wrong identity and leaked
diagnostics. It checks that no tasks survive; the existing example tests remain
the separate evidence for container closure, policy-before-materialization order
and cancellation. This is standard-adapter candidate-wheel evidence at explicit
Python/JSON boundaries, not a new schema adapter, transport conformance claim
or a test against the published PyPI baseline.

The lane also loads the unchanged [dependency guide](../examples/dependencies.py)
from the external directory under Python `-I`, with bounded execution. It checks
success/refusal/error outcomes, input error paths and redacted failure details,
the complete ordered provider/handler trace, singleton reuse, distinct invocation
objects, shared session identity across provider branches and closed resource
flags. Negative tests reject changed outcomes, diagnostic leaks, unexpected
effects, missing/reordered cleanup, wrong resource counts/identity and unclosed
resources. No tasks survive the demonstration. The example's owner-cancellation
test remains separate checkout evidence; this consumer exercises normal owner
shutdown after success, refusal and handler failure. These are local resource
fixtures against candidate wheels, not database integration or a published-PyPI
regression claim.

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
