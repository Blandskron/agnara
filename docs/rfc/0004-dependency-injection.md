# RFC 0004: Transport-Neutral Dependency Injection

**Status:** Accepted
**Epic:** E3.1

## 1. Summary

Agnara requires a Dependency Injection (DI) system to wire capabilities, repositories, and third-party services. Unlike HTTP-first frameworks (e.g., FastAPI), Agnara's capabilities can be invoked by HTTP, MCP, A2A, or background workers. Therefore, the DI system must be strictly **transport-neutral**, compiled ahead-of-time (DAG), and free of implicit context parameters like `Request` or `WebSocket`.

## 2. Motivation

Existing Python DI solutions fall into two problematic categories for Agnara:
1. **Implicit & Transport-bound (FastAPI `Depends`)**: Assumes all inputs originate from HTTP requests or global state, making it impossible to inject MCP connections cleanly.
2. **Heavyweight & Dynamic (Dependency Injector)**: Relies heavily on metaclasses and runtime reflection, violating Agnara's startup-compiled DAG and Python 3.14 native principles.

We need a system that:
- Detects cyclic dependencies at compile-time.
- Resolves standard Python type hints (`def get_user(db: Database)`).
- Supports execution scopes (Singleton, Invocation).
- Cleans up async resources safely (`AsyncGenerator` yields).

## 3. Design Constraints

As dictated by `AGENTS.md`:
- `agnara-core` MUST NOT import HTTP objects.
- Parameter classification rules must not be ambiguous. 

## 4. Proposed Architecture

### 4.1 Provider Abstraction

Providers are explicit factories registered to a `Container` or `Registry`.

```python
from agnara.core.di import provider, Scope

@provider(scope=Scope.SINGLETON)
async def provide_db() -> AsyncGenerator[Database, None]:
    db = Database()
    await db.connect()
    yield db
    await db.disconnect()
```

### 4.2 Compile-Time DAG

When an application boots, `agnara-core` compiles all `@capability` definitions and their required providers into a strict Directed Acyclic Graph (DAG).
If `ServiceA` requires `ServiceB`, and `ServiceB` requires `ServiceA`, the framework raises a `DependencyCycleError` before the server binds to a port.

### 4.3 Scopes

- `SINGLETON`: Instantiated once per application lifecycle.
- `INVOCATION`: Instantiated once per protocol execution (e.g., one HTTP request, one MCP tool call).

### 4.4 Injection Mechanics

Capabilities declare dependencies purely via type hints. No `Depends()` marker is needed in the signature.

```python
@app.capability()
async def transfer_funds(
    cmd: TransferCommand,  # Parsed from payload via Schema Adapter
    db: Database          # Resolved via DI graph
) -> Receipt:
    ...
```

To distinguish between payload fields and DI providers, the framework compiles the DAG: any type hint not registered as a Provider is treated as the input payload schema. If it cannot be resolved as either, compilation fails.

## 5. Extensibility

Interfaces can be bound to implementations during container assembly, which enables easy overriding during tests without patching.

```python
container.bind(Database, MockDatabase)
```
