# Explicit dependency injection and resource ownership

Run this complete example from a synchronized development checkout:

```bash
uv sync
uv run python examples/dependencies.py
```

[examples/dependencies.py](../examples/dependencies.py) uses the public core
API and local resource fixtures. No database, server or external service is
required. The trusted principal is a demonstration fixture; authentication
belongs to the application boundary.

Expected output begins with:

```text
denied: forbidden
invalid: invalid_input
first: first
second: second
failed: internal_failure
pools: 1; sessions: 3
```

The final line lists resource events: one pool opens, each of three calls
opens a session and reader, enters the handler, closes the reader, then closes
the session. The pool closes last. The intentional handler exception also
produces a redacted operator log on standard error.

## Bind types before compiling plans

The application registers provider definitions explicitly:

```python
from agnara.di import DIContainer, DIRegistry
from agnara.execution import ExecutionPlan

dependencies = DIRegistry()
dependencies.bind(Pool, provide_pool)
dependencies.bind(Session, provide_session)
dependencies.bind(Reader, provide_reader)
dependencies.bind(Writer, provide_writer)
plan = ExecutionPlan.compile(app.compile()["storage.work"], dependencies)
container = DIContainer(dependencies)
```

These names refer to the classes and providers in the complete example.
The handler declares ordinary Python type annotations: `label: str` and
`fail: bool` are payload fields; `reader: Reader` and `writer: Writer` are
dependencies because their types are bound in this registry. The caller sends
only payload fields. No `Inject` annotation or application provider decorator
is required or implemented.

Binding a payload type such as `str` changes how parameters of that type are
classified. Prefer dedicated resource types, assemble bindings before plan
compilation and keep the registry unchanged during execution. An unbound
handler annotation is considered payload; it does not automatically become
a missing dependency error.

`agnara.di.provider` returns a `ProviderDefinition`, which is what `bind`
accepts. An undecorated callable is rejected. Providers declare a return
annotation; generator providers annotate their yielded resource with
`Iterator[T]` or `AsyncIterator[T]`. The explicit binding identifies the
injected type. Every provider parameter must itself be bound: providers do
not receive handler payload implicitly.

## Choose the implemented lifetime

Only `Scope.SINGLETON` and `Scope.INVOCATION` are implemented.

| Scope | Reuse | Generator cleanup owner |
| --- | --- | --- |
| `SINGLETON` | One cached value per bound type in a container | Application calls `container.aclose()` |
| `INVOCATION` | One cached value per bound type in an invocation resolution scope | Runtime exits the invocation scope |

Providers are acquired lazily when an authorized, validated invocation needs
them. Compilation validates the graph without constructing resources.
The example's singleton pool survives both successful calls and the failed
call. Three session instances are created, one per call. Reader and writer
providers both depend on `Session`, forming a diamond; they receive the same
session within each call. The next call receives a fresh session.

A singleton must only depend on other singletons. Compilation rejects a
singleton that would capture an invocation resource, which might already be
closed on later calls. Invocation providers can depend on singletons.
Dependency cycles, unbound provider parameters and unresolved annotations also
fail at startup with a `DefinitionError` subtype. Existing
[DI compiler tests](../tests/unit/di/test_compiler.py) exercise these graph diagnostics.

## Put cleanup around the yield

Providers can be synchronous functions, asynchronous functions, synchronous
generators or asynchronous generators. Functions return a value; generators
yield exactly one resource and put teardown in `finally`. Decorate the raw
generator with `provider`; the container manages its context. Do not wrap it
with another context-manager decorator first.

The example uses a synchronous pool generator, an asynchronous session
generator, a synchronous reader generator and an asynchronous writer function.
Only generator providers register resource teardown automatically. A returned
object's `close` or `aclose` method is not automatically called just because it
exists; use a generator provider when the application needs owned teardown.

Generator cleanup runs in reverse acquisition order. Reader closes before
the session it holds, including when the handler raises. The runtime maps
that handler error to redacted `FailureCode.INTERNAL_FAILURE`. Closing the
invocation does not close its shared pool. The application awaits
`container.aclose()` in `finally`, after invocation work has finished, to
release singleton resources. Drain owned calls before application shutdown;
this example does not race shutdown with active invocations.

Authorization and input validation happen before dependency resolution.
The first two calls deliberately fail those checks before anything opens.
Resources therefore cannot serve as implicit authorization, and malformed
input never enters this handler. An acquired resource is still application
state: injecting it does not define database transaction, rollback or retry
semantics.

The fixtures and their event lists belong to one demonstration and one event
loop. Real shared resources must own their synchronization and concurrency
contract. This sequential example makes no free-threading or production
database claim. For cancellation during handler work and asynchronous cleanup,
see the [deadline and cancellation guide](DEADLINES.md).

## Evidence

[Guide tests](../tests/docs/test_dependencies_example.py) verify singleton
identity, fresh sessions across calls, diamond reuse, reverse teardown on
success/failure, redaction, application closure when caller cancellation
propagates, no leftover tasks and bounded execution outside the checkout.
The example uses a separate five-second demonstration watchdog and creates
no background tasks. Existing DI compiler/resolver tests cover startup graph
refusal and provider kinds. No runtime contract or dependency is changed.
