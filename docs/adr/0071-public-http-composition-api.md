# ADR 0071 — Public HTTP Composition API

- Status: Proposed
- Date: 2026-09-07
- Initiative: I1 Unified exposure model (RFC 0006 phase 3)
- Tracking: GitHub Issue #295
- Related: ADR 0005, ADR 0026, ADR 0035, ADR 0041, ADR 0067, ADR 0068, ADR 0070

## Context

`agnara_http.__all__` was empty across three published releases. Sixteen
submodules, every one underscore-prefixed. An application that wanted HTTP had
to import `agnara_http._dispatch`, `_binding`, `_routing`, `_surfaces` and
`_asgi` — which is what the baseline gate
`reference-apps-no-internal-imports` forbids, and which this repository's own
integration tests do, being the clearest evidence that no supported path
existed.

The stated reason was correct: the composition API could not be settled while
the exposure model beneath it was unsettled. ADR 0070 settled that model in
#294. This is RFC 0006 phase 3.

Two mandatory baseline gates are blocked on this and nothing else:
`reference-apps-no-internal-imports` and `http-exposure-from-application`.

## Decision

### Seven public names, in one public module

`agnara_http.composition`, re-exported from the package root:

| Name | Concept |
| --- | --- |
| `Http` | Declare and compile one named HTTP surface. |
| `HttpApplication` | The compiled, immutable ASGI 3 application. |
| `Binding` | Read one capability input from one place in the request. |
| `BindingSource` | Which place: `PATH`, `QUERY`, `HEADER`, `BODY`. |
| `OpenApiInfo` | Document metadata. |
| `OpenApiOperation` | The per-operation decision to publish, and its metadata. |
| `HttpDefinitionError` | One composition mistake, at startup. |

All `provisional`. Nothing is `stable`; ADR 0067 reserves that for a decision
the `1.0.0` release gates.

Not exposed: `_RouteRegistry`, `_HTTPBindingPlan`, `_HTTPDispatcher`,
`_SurfaceDispatcher`, `_ASGIBoundary`, `_DocumentationProvider`,
`_OpenAPIPublication`, and the other twenty-odd internal types. A router, a
binder and a renderer are implementation details; an application composes
against concepts.

### Public value types are translated, not aliased

`Binding` is a new class that produces an `_InputBinding`; `OpenApiInfo`
produces an `_OpenAPIInfo`; `BindingSource` is a new `StrEnum` mapped onto
`_BindingSource`. Aliasing the private classes would have been three lines
shorter and would have put `agnara_http._binding._InputBinding` in every
traceback and every editor tooltip, and frozen the internal shape.

The translation layer is the thing that lets routing, binding and projection
change without breaking an application — which is the reason this package
declared no public surface for three releases. Paying for it once is the point.

### The composition root owns the lifecycle, and there is no global state

```text
Agnara("shop")            → the application
@app.capability           → declarations
app.compile()             → frozen capabilities        (the application's call)
http.get(...) / .post(...)→ route declarations
http.compile(...)         → HttpApplication            (the startup step)
asgi(scope, receive, send)→ one request                (the server's call)
```

`Http.compile` takes the **frozen** registry from `Agnara.compile()` rather
than the application object. The builder therefore holds no reference to an
`Agnara`, two surfaces in one process share nothing, and no module-level
registry exists to be mutated behind a caller's back. It also keeps the freeze
visible in the application's own code instead of happening as a side effect
inside an adapter.

The builder is single-use: `compile()` closes it and a later declaration
raises (ADR 0005).

Capabilities are resolved at `compile()`, not at declaration. That is what
keeps `Http` independent of the application object; the cost is that an
undeclared capability is reported at compile time, and the diagnostic names the
method and path so the declaration is still identifiable.

### `Http.compile` returns one object that is three things

`HttpApplication` is the ASGI 3 callable, carries `exposures` for
`agnara.exposure.compile_exposures`, and carries `plans` so an application
does not compile execution plans twice to build an introspection snapshot.

`plans` covers the capabilities *this surface exposes*. `describe_app` wants a
plan for every declared capability, so an application with unexposed
capabilities compiles those itself. Documented rather than papered over: the
alternative was for `Http.compile` to compile plans for capabilities it does
not serve, which is work the surface has no reason to do.

### Bindings stay explicit

No inference from the path template. ADR 0026 already decided this, and the
public API does not quietly reverse it: renaming a capability parameter fails
at startup with `required input 'order_id' has no HTTP binding` rather than
becoming a confusing validation error on the first request.

### Publication is opt-in, per operation, with no default path

An exposure without an `OpenApiOperation` is served and appears nowhere in the
document (ADR 0035). `openapi_path` has no default, because publishing an API
description is a deliberate act rather than something a framework should do
because nobody said otherwise.

### One error class

`HttpDefinitionError(DefinitionError)`, matching `McpToolDefinitionError` in
the sibling adapter. Adapter-internal failures — `_BindingDefinitionError`,
`_RouteDefinitionError`, `_SurfaceDefinitionError`, `_OpenAPIDefinitionError`,
`_ProblemDefinitionError`, `_RouteRegistryFrozenError` — are translated, with
the original kept on `__cause__`.

Core's `DefinitionError` and `SchemaError` pass through unchanged. A capability
that is not declared, or whose plan will not compile, is a capability mistake
and should not be re-labelled as an HTTP one.

The repository generally favours granular errors (`DuplicateAppError`,
`DuplicateCapabilityError`). Here one class wins because all of these abort
startup, nothing catches them selectively in production, and a taxonomy is
easier to add later than to narrow.

### Documentation UI, Explorer and discovery stay internal

Deliberate, and not because exposing them is hard.

`_compile_publication` compiles **placeholder** routes. Its own comment says
"provider rendering, CSP and assets are downstream work", and
`_DocumentationProvider.render` is called from nothing outside tests. There is
no product code path from a publication configuration to a served
documentation page; the browser tests assemble one by hand in
`tests/http/browser/_host.py`.

Publishing an API for that would publish an API for something that does not
work end to end. Their configuration is also security-sensitive — content
security policy, asset policy, principal resolution, discovery redaction — and
each deserves its own review rather than arriving as a keyword argument.

`docs/MATURITY.md` records documentation UI publication as `DESIGNED` instead
of `IMPLEMENTED`, which is what it actually is.

## Threat analysis

**A published document could promise an operation that cannot succeed.** It
does, today, for a dataclass-typed body: `DataclassSchema.json_schema()`
projects a correct object schema and `DataclassSchema.validate` then rejects
the decoded `dict`. Found through this API, recorded as Issue #296, pinned by a
test, and stated in the guide. Not fixed here: coercion policy belongs to
ADR 0004 and ADR 0025 and changes direct invocation for every transport.

**An exposure could be published by accident.** Publication requires an
explicit `OpenApiOperation` per route, and serving the document requires an
explicit `openapi_path`. Both absent by default, so a deployment that has not
decided publishes nothing.

**A document route could shadow a capability.** The document is registered
through the same application-wide collision boundary as any other static
surface, so `openapi_path="/ping"` over a `GET /ping` capability fails at
startup rather than shadowing it.

**A capability could be reachable without its policy.** It cannot: dispatch is
unchanged and still evaluates the compiled plan's policies. Every HTTP
invocation runs as the anonymous principal, so a `ScopePolicy` denies it with
`403`. Nothing here can produce a `401`, and the guide says so rather than
implying authentication exists.

**An error could leak internal detail.** Handler exception messages are
already redacted into `internal_failure` by `_problem`. The new translation
layer copies an internal *composition* diagnostic into
`HttpDefinitionError`; those are startup messages about the application's own
declarations, containing paths and input names the author wrote, and they never
reach a response body.

**An unbounded body could exhaust memory.** The existing per-route limit is
reachable and overridable through `max_body_bytes`; the default is unchanged.

**A `problem_base_uri` could be hostile.** It is validated by the existing
`_compile_problem_types` — absolute, no query, no fragment, trailing slash —
and a rejection now surfaces as `HttpDefinitionError` at startup.

## Consequences

### Positive

- An external application can compose and serve Agnara HTTP with no private
  import and no monkey patch, which is what two baseline gates ask for.
- The exposure model gets its first public producer, so HTTP and MCP compose
  into one availability registry from application code.
- The first genuine dogfooding defect surfaced (#296), from a shape every HTTP
  test had missed because they all use `dict[str, Any]` bodies.

### Negative

- Seven more `provisional` names to keep or break deliberately.
- The translation layer is real code with no behaviour of its own, and it must
  be kept in step with the internal types it wraps. Tests pin both directions.
- The word "surface" now means three things in this package: an RFC 0006
  adapter surface, `_HTTPSurface` (a static response, ADR 0034), and loosely
  "the public API". ADR 0070 already recorded the first collision as a hazard.
  This ADR does not fix it — renaming a shipped internal to suit a new public
  name is churn, and `Http` does not force an application to meet either
  private spelling.
- `docs/API_DESIGN.md` section 4 showed `http.get("/users/{user_id}",
  get_user)` with no bindings. The real API needs them, and the sketch is now
  corrected rather than the API bent to match a sketch.

## Alternatives considered

**Expose the internal classes directly.** Rejected: it publishes a router, a
binder and a dispatcher as the contract, and freezes internal shape at the
moment it is least understood.

**Infer bindings from the path template and the signature.** Rejected: ADR 0026
decided explicit binding, and inference makes a renamed parameter a runtime
surprise rather than a startup failure. The convenience is real and it can be
added later as sugar over an explicit core; the reverse is not true.

**Take the `Agnara` app instead of the frozen registry, and freeze inside.**
Rejected: it hides the freeze in an adapter, couples the builder to the
application object, and makes two-adapter composition ambiguous about who
froze what.

**Return a bare ASGI callable from `compile()`.** Rejected: the caller then has
no way to reach the exposure records or the OpenAPI document, and would be back
to private imports for both.

**Ship a documentation UI keyword now.** Rejected on evidence: no product path
renders a provider into a served route, so the keyword would configure
something that does not happen.

**A granular error hierarchy.** Rejected for now, in favour of matching the
MCP adapter. Adding `DuplicateRouteError` later is compatible; removing one is
not.

**Also expose `Explorer` and discovery.** Rejected: both need a principal
resolver and a visibility policy in the public signature, which is the security
review this task is not.

## Revisit when

I7 lands cookies, forms, multipart and uploads — `BindingSource` gains members
and this ADR should be checked for whether `Binding` still reads well. Also at
`1.0.0`, when the embedding contract (RFC 0008) needs to say what an external
host calls: `HttpApplication` is the obvious answer and has not been designed
against that question yet.

Promotion of any of these seven names to `stable` is a separate decision.
