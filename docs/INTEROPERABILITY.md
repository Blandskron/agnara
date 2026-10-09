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
side-by-side FastAPI consumers under isolated Python mode. This is reproducible
artifact evidence for the reviewed source commit, not a framework plugin or a durable
store claim.

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
