# Golden API Design Examples

These examples define desired developer experience before implementation.

The implementation must not be allowed to dictate the public API accidentally.

## 1. Smallest application

```python
from agnara import Agnara

app = Agnara("hello")
```

## 2. Simple capability

```python
@app.capability
def add(a: int, b: int) -> int:
    return a + b
```

## 3. Async capability

```python
@app.capability
async def get_user(user_id: str) -> User:
    return await repository.get(user_id)
```

## 4. HTTP exposure

```python
http.get("/users/{user_id}", get_user)
```

## 5. MCP exposure

```python
mcp.tool(get_user)
```

## 6. A2A exposure

```python
a2a.skill(get_user)
```

## 7. Same capability, multiple surfaces

```python
http.get("/users/{user_id}", get_user)
mcp.tool(get_user)
a2a.skill(get_user)
```

## 8. Dependency injection

```python
@app.capability
async def get_user(
    user_id: str,
    repo: Inject[UserRepository],
) -> User:
    return await repo.get(user_id)
```

## 9. Invocation-scoped dependency

```python
@app.provider(scope="invocation")
async def database_session() -> AsyncIterator[Session]:
    async with Session() as session:
        yield session
```

## 10. Security scope

```python
@app.capability(scopes={"users:read"})
async def get_user(...) -> User:
    ...
```

## 11. Side-effect metadata

```python
@app.capability(
    effects={"database-write"},
    idempotent=False,
)
async def create_user(...) -> User:
    ...
```

## 12. High-risk capability

```python
@app.capability(
    effects={"destructive"},
    risk="high",
    confirmation="required",
)
async def delete_account(...) -> DeleteReceipt:
    ...
```

## 13. Human interaction

```python
@app.capability
async def approve_transfer(command: Transfer, ctx: Context) -> Receipt:
    if command.amount > 10_000:
        await ctx.require_confirmation(
            title="Confirm transfer",
            message="This transfer exceeds the automatic approval threshold.",
        )
    return await transfer(command)
```

Exact API pending RFC.

## 14. Deadline-aware handler

```python
@app.capability(timeout=5.0)
async def lookup(...) -> Result:
    ...
```

Runtime cancellation must propagate.

## 15. Streaming

```python
@app.capability(streaming=True)
async def generate_report(...) -> AsyncIterator[ReportChunk]:
    ...
```

Streaming semantics require a dedicated RFC.

## 16. Direct invocation

```python
result = await app.invoke(
    get_user,
    user_id="u_123",
    context=context,
)
```

Direct invocation keeps ordinary Python semantics: it returns the handler
value and raises exceptions. Transport adapters use the canonical boundary so
all protocols observe the same success/failure meaning:

```python
from agnara.execution import Failure, Success, invoke_result

match await invoke_result(plan, context):
    case Success(value):
        ...
    case Failure(code, message):
        ...
```

`FailureCode` is protocol-neutral. An HTTP, MCP or A2A adapter maps it to its
own representation; core never stores a transport status code.

## 17. Capability introspection

```python
definition = app.capabilities["users.get_user"]
print(definition.effects)
print(definition.exposures)
```

The final registry API may differ but this must be easy.

## 18. OpenAPI projection

```python
http = app.use(Http(openapi=True))
```

OpenAPI is generated from HTTP exposures plus shared capability schemas.

The complete semantic input is:

```text
CapabilityDefinition
+ compiled HTTP exposure
+ schema adapter output
+ explicitly publishable policy/discovery metadata
        ↓
OpenAPI 3.2
```

Developers do not maintain a parallel OpenAPI document for generated
exposures. Capabilities without an HTTP exposure do not appear as invented
OpenAPI operations.

`Http(openapi=True)` remains a golden-design sketch. It is not stable syntax.
The implementation must review typed schema/documentation configuration,
route collision handling and independent enable/disable controls before
freezing the API.

## 19. Agent-readable metadata

```python
manifest = app.describe(format="agnara")
```

The manifest should include permissions, effects, risk and available exposures.

The final API returns or serializes a versioned, filtered introspection
snapshot. It must not expose internal runtime objects, secret configuration or
private capabilities merely because they are registered.

OpenAPI and the Agnara snapshot are separate projections. Agents never need to
parse a documentation HTML page to discover capabilities.

## 19A. Optional documentation interfaces

Conceptual target only:

```python
http = app.use(
    Http(
        openapi=True,
        docs=True,
        redoc=False,
        explorer=True,
    )
)
```

The booleans and default routes are deliberately provisional. The reviewed
public API must make these independent:

- OpenAPI schema generation and serving;
- one or more replaceable OpenAPI UI providers;
- Agnara Explorer;
- interactive "try it" execution;
- visibility/authorization policy for each published surface.

Target route shapes such as `/openapi.json`, `/docs`, `/redoc` and `/agnara`
are familiar candidates, not stable contracts. Every route must be
configurable, disableable and checked for collisions.

Documentation providers consume an already-filtered OpenAPI contract. Agnara
Explorer consumes the already-filtered protocol-neutral snapshot instead.

No UI provider is required for OpenAPI export. Production deployments can
disable all HTML while preserving an authorized machine-readable schema or
snapshot.

## 20. Testing without a server

```python
async def test_get_user(app, context):
    result = await app.invoke(
        get_user,
        user_id="u_123",
        context=context,
    )
    assert result.id == "u_123"
```

## Design rules inferred from the examples

- decorators register domain intent, not transport intent;
- transport exposure is explicit;
- dependencies are explicit;
- framework magic should be inspectable;
- capability functions remain ordinary Python callables where practical;
- no decorator stack should be required for common cases;
- agent metadata should never obscure normal Python semantics.

## 21. Create a project

```bash
agnara project create commerce
```

## 22. Create a domain app

```bash
agnara app create payments
```

## 23. Create app with multiple exposures

```bash
agnara app create payments --with http,mcp,tasks
```

## 24. MCP shortcut

```bash
agnara app-mcp tools
```

is an alias for:

```bash
agnara app create tools --profile mcp
```

Both create the same runtime app type.

## 25. Add a transport later

```bash
agnara app expose payments a2a
```

No domain/application file should require modification merely to install the adapter skeleton.

## 26. Generate a capability

```bash
agnara capability create payments refund
```

## 27. Inspect an app

```bash
agnara inspect payments
```

Example conceptual output:

```text
App: payments
Architecture: modular-hexagonal

Capabilities
  payments.create
  payments.refund

Exposures
  HTTP
  MCP
  Tasks

Dependencies
  PaymentRepository
  AuditPublisher
```

## 28. Machine-readable inspection

```bash
agnara inspect payments --json
```

This is a first-class requirement for agents and automation.

The JSON format must be versioned and deterministic and should match the data
contract consumed by Agnara Explorer. Human text output is a presentation of
the same filtered snapshot, not a separately discovered model.

## 29. Export generated OpenAPI

```bash
agnara schema openapi
```

The command exports the same deterministic projection served by the HTTP
schema endpoint and must support non-interactive file/stdout use. Exact output
flags and exit codes remain pending CLI review.

`agnara docs` is not yet accepted. Add it only if it provides framework-specific
development value beyond `agnara dev`; it must not become a second source of
documentation configuration.
