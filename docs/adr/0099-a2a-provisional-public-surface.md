# ADR 0099 — Provisional A2A public surface

- Status: Proposed
- Date: 2026-10-30
- Tracking: GitHub Issue #701 (A2A-04a)
- Related: ADR 0010, ADR 0070, ADR 0073, ADR 0098, RFC 0010

## Context

[ADR 0098](0098-a2a-complete-result-projection.md) fixed the wire contract of
the first A2A profile and left names, signatures, exports and the exact SDK
pin to A2A-04 (D11). The A2A-03 fixture proved that contract in an isolated
experiment against `a2a-sdk[http-server]==1.3.0`. RFC 0010 requires separate
approval for exports, dependencies, installed-wheel consumers, examples and
maturity.

The maintainer decided on 2026-10-30 to split A2A-04 in two. This record
covers A2A-04a: the importable surface and its dependency. A2A-04b covers a
runnable example, installed-wheel consumers, network hosting and
cross-platform CI before any support or maturity promotion.

## Decision

### D1 — Stability: provisional

Every `agnara_a2a` export is classified `provisional` in
[public-api.json](../public-api.json), the first use of that term. A
provisional name is governed, importable and checked like a stable one, but
its signature and behaviour may change in a minor release after a reviewed
decision. It is not part of the 1.x compatibility promise. A module is either
entirely provisional or entirely stable; promotion to `stable` needs its own
record after A2A-04b evidence.

### D2 — Exports

| Name | Kind | Mirrors |
| --- | --- | --- |
| `A2a(app, *, surface="default")` | Exposure declaration at the composition root | `Mcp` |
| `A2a.skill(capability, /, *, id, name, description, tags)` | Publishes the surface's single capability | `Mcp.tool` |
| `A2a.compile()` / `A2a.compile_surface()` | Returns the `A2aSkillExposure`, or it with its ADR 0070 record | `Mcp.compile*` |
| `A2aSkillExposure` | Frozen capability plus explicit skill metadata | `McpToolExposure` |
| `A2aAgentCard(name, description, version)` | Explicit agent-level card metadata | — |
| `A2aDefinitionError` | Composition refusals, a `DefinitionError` | `McpToolDefinitionError` |
| `build_a2a_app(exposure, plans, di_container, *, card, url, principals, challenge, timeout=30.0, max_body_bytes=1048576, card_cache_control=None)` | Returns an ASGI 3 application | `build_mcp_server` |
| `A2A_PROTOCOL_VERSION`, `SUPPORTED_A2A_PROTOCOL_VERSIONS`, `A2A_PYTHON_SDK_VERSION` | Exact identities | MCP constants |

A surface serves exactly one capability (ADR 0098 D2): a second `skill` call
fails, and so does compiling an empty surface. Skill and card fields are
required, non-empty and never derived from definition text (ADR 0098 D8). A
capability declared with `Confirmation.REQUIRED` is refused at `skill` time
(ADR 0098 D5). Unlike `Mcp`, there is no tool-name table to freeze, so
`compile()` returns the single exposure rather than a mapping.

### D3 — Principal resolver and challenge

`principals` is a required `Callable[[Mapping[str, Any]], Principal | None]`
over the ASGI scope, the same shape as the HTTP discovery and Explorer
resolvers. The host authenticates in front of the application and leaves its
result in the scope; the resolver maps it to a `Principal`. Returning `None`
answers `401` with `challenge` as the `WWW-Authenticate` value before the body
is read, which is the ADR 0098 D5 refusal. A surface that should be anonymous
returns an explicit anonymous principal; there is no default. Any other return
type is a programming error and raises `TypeError`.

### D4 — Mounting and lifecycle

`build_a2a_app` returns an ASGI application that answers JSON-RPC at its root
and the public card at `/.well-known/agent-card.json`. The host mounts it at
`url`, which the card publishes verbatim. The application owns no background
work, no task state and no SDK resource needing shutdown; the host owns the DI
container and closes it after the application's lifespan (ADR 0098 D10).
`card_cache_control` passes the host's `Cache-Control` choice to the SDK's card
route, which already emits an `ETag`.

### D5 — Dependency pin

`agnara-a2a` declares `a2a-sdk[http-server]==1.3.0`, under ADR 0010's exact-pin
rule, and `docs/distributions.json` records it as the adapter's third-party
requirement. The workspace lock resolves it jointly with every other member
and adds protobuf 7.36.2, the runtime the ADR 0098 D7 ceilings were measured
on. The adapter imports Starlette's `Router` and `Request` directly, because
the SDK's route factories return Starlette routes; Starlette arrives through
the `http-server` extra and is not declared separately. The kernel imports
nothing new.

## Consequences

- Applications can compose an A2A surface from governed imports, but every
  name may still change before promotion.
- Installing `agnara-a2a` from this checkout pulls the SDK, protobuf, Pydantic,
  Starlette and Google API core libraries. An SDK advisory reaches every
  consumer until a new pin is published.
- The release gate imports provisional names from installed wheels like stable
  ones, so a provisional name cannot disappear unnoticed.
- `agnara-a2a` changes role from `reserved` to `adapter` in the publication
  set. Only `agnara-events` remains reserved.

## Alternatives

- **Classify the exports `stable`:** rejected by the maintainer. The profile is
  one week old, its ADR is still Proposed, and no installed-wheel or
  cross-platform evidence exists yet.
- **Return a Starlette application instead of a plain ASGI callable:** rejected.
  It would make Starlette part of the published return type.
- **Accept a mapping of skills per surface:** rejected by ADR 0098 D2.
- **Take a token verifier instead of a principal resolver:** rejected.
  Authentication stays at the host boundary, as for HTTP and MCP.

## Remaining evidence (A2A-04b)

[A2A-04b1](https://github.com/Blandskron/agnara/issues/705) adds the
[runnable guide](../A2A_SERVICE.md) and an exact-example installed-wheel
consumer to the existing cross-platform CI gate. It changes no decision above
and keeps the surface provisional and experimental. A network server with
real-disconnect evidence and any later maturity promotion remain separate work.
