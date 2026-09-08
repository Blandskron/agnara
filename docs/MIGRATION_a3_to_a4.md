# Migrating from `0.1.0a3` to `0.1.0a4`

`0.1.0a4` is an alpha, so the public API may change without a deprecation
cycle. That is a licence to change the API, not a licence to surprise you. This
page lists every change a `0.1.0a3` user has to act on, and says plainly which
ones require no action at all.

Each entry gives the `a3` spelling, the `a4` spelling, why it changed, and a
migration example. Internal refactoring is deliberately absent: if it never
appeared in your code, it is not on this page.

The changes were derived by diffing the public surface of the published
`agnara==0.1.0a3` against the `0.1.0a4` build, not from the changelog.

Two conventions for the code below. Blocks shown as a matched `a3` / `a4` pair
are excerpts of your code, not programs — the `a3` half is expected to fail on
`a4`, which is the point. The complete programs are the ones under "Apps and
bounded contexts" and "Serving over HTTP"; both are executed against an
installed `0.1.0a4` build as part of this repository's documentation
reproduction check.

## At a glance

| Change | Breaks code? |
| --- | --- |
| `AppDescriptor` renamed to `ApplicationDescriptor` | **Yes**, an import error |
| `AppDescriptor` reused at `agnara.AppDescriptor` for a different type | **Yes**, silently, if you re-point the import carelessly |
| Six adapter distributions exist alongside `agnara` | No, additive |
| Apps and bounded contexts (`App`, `Agnara.include`) | No, additive |
| Exposure model (`agnara.exposure`) | No, additive |
| HTTP composition API (`agnara_http`) | No, new |
| MCP invocation surface (`agnara_mcp`) | No, new |
| `agnara` console script (`agnara-cli`) | No, new |
| `ConfirmationPolicy` exported from `agnara.policy` | No, additive |
| Declared `scopes=` become enforced | **Yes** — see "Pending" below |

Everything else you wrote against `0.1.0a3` keeps working. Capability
declaration, the registry, dependency injection, execution plans, policies,
canonical results, telemetry hooks and frozen value semantics are unchanged.

## 1. `AppDescriptor` is now `ApplicationDescriptor`

**`a3`**

```python
from agnara.introspection import AppDescriptor, describe_app, snapshot

described: AppDescriptor = describe_app(app, plans)
```

**`a4`**

```python
from agnara.introspection import ApplicationDescriptor, describe_app, snapshot

described: ApplicationDescriptor = describe_app(app, plans)
```

**Why.** `a4` introduces apps as a first-class concept, so "app" and
"application" stopped being synonyms. The type that describes one compiled
application acquired an `apps` field listing the bounded contexts mounted on
it, and keeping the shorter name for it would have made the two ideas
indistinguishable in the exact code that has to tell them apart.

**Migration.** Rename the import. `describe_app()` and `snapshot()` keep their
names and their argument order; only the annotation changes. The old name
raises `ImportError` rather than resolving to something else, so a missed
occurrence fails at import rather than at runtime.

### The trap worth reading twice

`AppDescriptor` still exists in `a4`, at `agnara.AppDescriptor` and
`agnara.app.AppDescriptor` — and it is **a different type**.

| | `a3` `introspection.AppDescriptor` | `a4` `agnara.AppDescriptor` |
| --- | --- | --- |
| Fields | `name`, `capabilities`, `providers` | `name`, `description`, `module` |
| Means | a compiled application's contents | one app's identity |

So this "fix" imports cleanly and is wrong:

```python
from agnara import AppDescriptor          # identity, not contents
```

The replacement for the `a3` type is `agnara.introspection.ApplicationDescriptor`.

## 2. `describe_app(exposures=...)` accepts more, not less

**`a3`** accepted a mapping of capability id to exposure descriptors, written
by hand.

**`a4`** accepts that same mapping **or** the compiled
`FrozenExposureRegistry` that the adapters now produce.

**Why.** A hand-written mapping is a second answer to "what is exposed", and it
could disagree with what the adapters actually serve. Deriving descriptors from
compiled availability makes the two impossible to separate.

**Migration.** None required — the mapping form still works and is the
transitional path. Prefer passing the compiled registry once your surfaces are
compiled, because it cannot drift.

## 3. Installing the adapters

**`a3`** published one distribution, `agnara`. HTTP and MCP support existed in
the repository but could not be installed as ordinary dependencies.

**`a4`** builds seven synchronized distributions:

| Distribution | Import package | Contains |
| --- | --- | --- |
| `agnara` | `agnara` | the kernel; standard library only |
| `agnara-http` | `agnara_http` | HTTP/ASGI composition, OpenAPI |
| `agnara-mcp` | `agnara_mcp` | MCP discovery and tool invocation |
| `agnara-cli` | `agnara_cli` | the `agnara` console script |
| `agnara-telemetry` | `agnara_telemetry` | OpenTelemetry metric and span hooks |
| `agnara-a2a` | `agnara_a2a` | reserved name, no API |
| `agnara-events` | `agnara_events` | reserved name, no API |

**Migration.** Add the adapters you use as ordinary dependencies, once the
ones you need are available on your index:

```bash
pip install agnara agnara-http
```

Availability is the thing to check first, and this page deliberately does not
assert it: at the time of writing only `agnara` resolves from PyPI, and the
command above fails on `agnara-http`. Each distribution's PyPI project page is
the authority.

Until an adapter is on your index, install it from the built wheels:

```bash
uv build --all-packages --out-dir dist/
pip install --no-index --find-links dist/ agnara agnara-http
```

Adapter versions are pinned to the exact matching kernel version, so upgrade
them together.

## 4. Apps and bounded contexts

New in `a4`, and purely additive: `Agnara` is now a project onto which apps are
mounted.

```python
from agnara import Agnara, App

payments = App("payments")


@payments.capability
def get_record(record_id: str) -> str:
    return record_id


project = Agnara("shop")
project.include(payments)
capabilities = project.compile()
# the capability id is payments.get_record, whichever project mounts it
```

**Why.** An app keeps its own namespace, so two apps from the same scaffold can
declare the same names and still coexist in one project.

**Migration.** None. `Agnara("name")` with `@app.capability` on it works exactly
as in `a3`; `App` and `include` are there when a project outgrows one namespace.
Mounting two apps of the same name raises the new `DuplicateAppError`.

## 5. The exposure model

New in `a4`: `agnara.exposure` gives every adapter one neutral identity and one
frozen availability registry — `ExposureId`, `SurfaceId`, `CompiledExposure`,
`SurfaceCompilation`, `FrozenExposureRegistry`, `compile_exposures`,
`ExposureError`.

**Why.** In `a3` each adapter kept a private table, and an introspection
snapshot could report exposures that no adapter served — in practice it
reported none at all.

**Migration.** None unless you build your own adapter or pass compiled
exposures to `describe_app`. Composing HTTP or MCP through their own public
APIs uses this underneath without naming it.

## 6. Serving over HTTP

New in `a4`. `agnara_http` exposes exactly seven public names: `Http`,
`HttpApplication`, `Binding`, `BindingSource`, `OpenApiInfo`,
`OpenApiOperation`, `HttpDefinitionError`.

```python
from agnara import Agnara
from agnara_http import Binding, BindingSource, Http, OpenApiInfo

app = Agnara("shop")


@app.capability
def show(order_id: str) -> dict[str, str]:
    return {"id": order_id}


http = Http("public")
http.get("/orders/{order_id}", show, Binding("order_id", BindingSource.PATH))
asgi = http.compile(app.compile(), openapi=OpenApiInfo("Shop API", "1.0.0"))
```

`asgi` is an ASGI 3 application; hand it to any ASGI server. Every input is
bound explicitly — `PATH`, `QUERY`, `HEADER`, `BODY`, `COOKIE`, `FORM`,
`UPLOAD` — because `a4` refuses to guess where a value came from. A route
declares one body reading, since one request has one body.

`docs/HTTP_COMPOSITION.md` is the guide, including what `0.1.0a4` does not
expose yet: the documentation UI providers, the Explorer and the authorized
discovery endpoint remain internal.

## 7. Serving over MCP

New in `a4`. `a3` had no invocation surface; `a4` adds `tools/call` dispatch
over the same frozen snapshot discovery uses, so no tool name is invocable
without being discoverable. See `packages/agnara-mcp/README.md` and
`docs/MCP_CONFORMANCE.md` for the bounded evidence behind that.

## 8. The CLI

New in `a4`: installing `agnara-cli` provides an `agnara` console script with
`project create`, `app create`, `inspect`, `graph`, `schema openapi` and
`context`. Nothing in `a3` used it, so there is nothing to migrate.

## 9. Compilation and freezing

Unchanged in shape: declaration stays open until `compile()`, and compilation
freezes. `a4` adds project-wide freezing over mounted apps — an `App` has no
`compile()` of its own, because freezing is a project-wide decision.

**Migration.** None. Registering after a freeze still raises, as in `a3`.

## Pending: declared scopes become enforced

> This change is **not merged at the time of writing**. It is tracked by
> [#309](https://github.com/Blandskron/agnara/issues/309) and implemented in
> [#307](https://github.com/Blandskron/agnara/issues/307). Treat this section
> as advance notice, and re-check it against the released `0.1.0a4`.

**`a3` and `0.1.0a4` before that change.** `@app.capability(scopes={...})` is
metadata. Nothing evaluates it unless the application attaches a policy, except
`agnara-mcp`, which compiles its own `ScopePolicy` per tool.

**`0.1.0a4` after that change.** `ExecutionPlan.compile` attaches a
`ScopePolicy` built from the declared scopes, so the declaration is enforced on
every transport and by direct invocation.

**Why.** One capability was authorization-checked when reached as an MCP tool
and unchecked over HTTP, with no diagnostic telling the author which they had.

**Migration.** Any invocation of a capability that declares scopes must carry a
principal holding them. An invocation with no principal runs as
`AnonymousPrincipal`, which holds none, and returns
`Failure(FailureCode.FORBIDDEN)`.

```python
from agnara.policy import Principal

outcome = await invoke_result(
    plan,
    ExecutionContext(
        invocation,
        DIContainer(dependencies),
        principal=Principal("service-account", scopes={"billing:write"}),
    ),
)
```

Passing a principal is already valid before the change, so adding it now is
safe either way. Scopes are matched exactly: no prefix, wildcard, case fold or
trimming, so `billing` does not satisfy `billing:write`.

`docs/THREAT_MODEL.md` records the security reasoning.

## What did not change

Worth stating, because most `a3` code is in this list:

- `Agnara`, `@app.capability` and the returned function staying directly
  callable;
- capability identity, `effects`, `risk`, `idempotent` and `confirmation`
  metadata;
- `ExecutionPlan.compile`, `invoke`, `invoke_result`, `ExecutionContext`,
  `Invocation` and monotonic deadlines;
- `Success` / `Failure` and every `FailureCode`;
- dependency injection, provider scopes and teardown;
- `TelemetryHook`, `InvocationStartEvent`, `InvocationTerminalEvent` — the
  `invocation_id` field they gained arrived in `a3`, not here;
- frozen value semantics on `CapabilityId` and `CapabilityDefinition`;
- the confirmation boundary and `ConfirmationVerifier`, with
  `ConfirmationPolicy` now importable from `agnara.policy` for applications
  that attach it themselves;
- Python 3.14 as the minimum runtime.
