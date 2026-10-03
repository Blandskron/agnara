# Publishing filtered capability discovery

Build a protocol-neutral snapshot from compiled capabilities and exposures,
then decide what each viewer may discover before serializing it. Discovery
visibility and invocation authorization are independent decisions.

## Run the example

From the repository root with Python 3.14:

```bash
uv sync
uv run python examples/introspection.py
```

The complete [example](../examples/introspection.py) uses the workspace packages,
including HTTP and MCP for exposure compilation. It starts no server, makes no
network calls and requires no credentials. Its output is:

```text
anonymous: ['catalog.health']; transports=['http']
reader: ['catalog.health', 'catalog.lookup']; transports=['http', 'mcp']
identity_only: ['catalog.health', 'catalog.lookup']; transports=[]
disabled: []; transports=[]
listed_without_authority: ['catalog.health', 'catalog.lookup', 'catalog.refresh']; transports=['http', 'mcp']
denied: forbidden
hidden: refreshed
allowed: Item A-1
discovery_effects: []
denied_effects: []
effects: ['resource.open', 'refresh', 'resource.close', 'resource.open', 'lookup:A-1', 'resource.close']
```

## Describe compiled truth

`health` has an HTTP exposure. `lookup` and `refresh` have MCP exposures;
`lookup` declares `catalog:read`. The composition root freezes capabilities,
compiles their plans and obtains neutral exposure records from the adapter
compilers. It supplies that one frozen exposure registry to `describe_app`:

```python
from agnara.exposure import compile_exposures
from agnara.introspection import describe_app, snapshot

asgi = http.compile(capabilities, dependencies=dependencies)
exposures = compile_exposures(capabilities, [asgi.exposures, mcp.compile_surface()])
source = snapshot([describe_app(app, plans, dependencies=dependencies, exposures=exposures)])
```

The application, plans, dependency registry and adapter builders are defined
explicitly in the example. This path derives exposures from the compiled
adapter artifacts. A handwritten mapping can become stale and remains only a
transitional interface.

`source` holds immutable descriptors: declared inputs, dependency types,
provider structure, policy type names and exposure metadata. It contains no
handler, resource instance or credential. Building it does not instantiate
`Ledger` or execute a capability. It is still an **unfiltered** model intended
for trusted composition, not a ready-to-serve publication.

## Filter each viewer before serialization

The application selects an explicit visibility rule and publication profile:

```python
from agnara.introspection import DiscoveryVisibility, Hiding, ScopeVisible, filter_snapshot

visibility = DiscoveryVisibility.agent_safe(Hiding({"catalog.refresh"}, ScopeVisible()))
published = filter_snapshot(source, visibility, principal)
document = published.json_data()
```

`Hiding` excludes `refresh` for every viewer. `ScopeVisible` requires the
viewer to hold all declared scopes, so anonymous discovery excludes `lookup`.
The reader fixture holds `catalog:read` and sees it. Each view is derived from
the original snapshot; filtering an already restricted view cannot restore
information for another viewer.

`agent_safe` publishes descriptions, effects, declared scopes, safety metadata,
inputs and exposure names. It suppresses dependency/provider structure, policy
names, type modules and exposure detail such as deployment surface names.
The JSON shape retains empty collections or neutral defaults for suppressed
fields. Those placeholders do not establish facts about the omitted metadata.

The anonymous view reports only `http`: transport availability is derived from
surviving exposures, so a hidden MCP capability leaves no MCP availability in
that view. `identity_only` publishes capability identity while suppressing
metadata and exposures. `NoCapabilityVisible` removes all capabilities and
also their containing application and project disclosure.

The `filtered` flag records that a decision was applied. It does not certify
that the decision is appropriate. `agent_safe` is a starting profile: review
every published description, schema, effect and exposure name yourself. A
secret deliberately placed in a publishable description or schema is not
automatically scrubbed. `unrestricted` is for trusted local inspection.

Serialize only the filtered model. Deleting entries from serialized JSON can
leave derived transports or other references behind. `json_data()` returns
detached containers; changing them does not mutate either the source or a
filtered view. Store any published response per viewer and publication policy;
this example implements no response cache.

## Keep authorization independent

The example also explicitly lists every capability for an anonymous fixture
using `AllCapabilitiesVisible`. That viewer still receives `forbidden` when
calling scoped `lookup`: the compiled execution plan re-evaluates scope policy
before dependency creation or handler effects.

Conversely, `refresh` stays registered and callable even though the ordinary
discovery rule hides it. Its unscoped demonstration plan succeeds. If an
operation needs protection, declare and enforce its authorization policy;
discovery hiding cannot provide it.

`Principal("demo-reader", scopes={"catalog:read"})` is a trusted local fixture.
In a deployment, the host authenticates callers and assigns verified scopes.
Caller input, a displayed scope label or a discovery document never grants
those scopes. The example implements no identity verification.

## Own execution and state

Each permitted invocation opens an invocation-owned provider and closes it
after the handler. Denial creates no dependency and produces no effect. The
application closes its direct-invocation `DIContainer` in `finally`, and an
overall timeout bounds the demonstration. Compiling the HTTP artifact here
does not start its lifespan or execute HTTP requests.

The [behavioral tests](../tests/docs/test_introspection_example.py) verify
viewer filtering, detached JSON, preservation of source descriptors, no
discovery/denial effects, provider cleanup, no surviving tasks and execution
from outside the checkout.

This tutorial exercises compiled exposure descriptions and direct execution.
It does not serve a discovery endpoint, OpenAPI document, Explorer UI or MCP
session. It adds no network, browser, authentication or thread-safety evidence.
The [HTTP guide](HTTP_COMPOSITION.md), [MCP guide](MCP_TOOLS.md) and
[maturity matrix](MATURITY.md) describe their separate supported boundaries.
