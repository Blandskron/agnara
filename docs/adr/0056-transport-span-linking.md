# ADR 0056 — Transport Span Linking Is the Application's Responsibility

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #223 (E9.4)

## Context

ADR 0055 gave a capability one span, parented by the ambient OpenTelemetry
context, and scoped remote parenting out: E9.3 "creates no remote parent,
injects and extracts no propagation headers, and makes no claim about a span
produced by an HTTP or MCP adapter".

E9.4 has to answer whether a capability span joins a caller's distributed
trace, and who is responsible for making that happen. The two candidate
answers are that Agnara reads `traceparent` itself, or that Agnara reads
nothing and inherits whatever context the application established.

## Decision

**Security amendment (2026-11-16).** The official MCP SDK now extracts W3C
trace context from request metadata. `agnara-mcp` requires a patched
`opentelemetry-api` for that existing middleware, including when installed
without the telemetry bridge. Agnara transport code still imports no
OpenTelemetry and implements no propagation.
[GHSA-mf5v-w3w3-f6cg](https://github.com/advisories/GHSA-mf5v-w3w3-f6cg)

**Agnara implements no context propagation.** Transport adapter code does
not read or write propagation fields. The host or its protocol SDK can
establish the incoming trace context. A capability span joins that trace
because ADR 0055 starts it from the ambient context.

The HTTP dispatcher and direct MCP `tools/call` invoker tests exercise both
ambient context cases.

| Ambient parent span | Result |
| --- | --- |
| yes | capability span carries the caller's trace ID, parented by the caller's span |
| no | capability span is a root span in its own trace |

A `traceparent` header alone leaves the HTTP capability span unlinked when
the host has no instrumentation extracting that header.

`tests/architecture/test_package_boundaries.py` enforces the boundary.
`agnara-telemetry` imports the API for its hooks. The MCP adapter declares
the patched API floor for its SDK. Transport code may not import it.

## Why not parse the header in the adapter

**It is a trust decision, not a plumbing detail.** A `traceparent` is
caller-supplied. Honouring it lets a caller choose the trace identity their
operation is recorded under: they can join an unrelated trace, or reuse one
identifier across many requests so an operator's view of them collapses. That
is usually acceptable inside a trusted perimeter and rarely acceptable at an
untrusted edge. A framework default would make that judgment for every
deployment; an application makes it once, knowingly.

**The ecosystem already does it, better.** ASGI and client instrumentation for
this exists, is maintained alongside the SDK, and handles far more than
extraction. Reimplementing a subset inside `agnara-http` would add a dependency
to a transport package to duplicate something the application probably already
runs.

**It would not be transport-neutral.** MCP has no header. Its context arrives
from whatever transport carries the JSON-RPC frames, or not at all. An
adapter-level header parser would give HTTP a capability MCP could not have,
and the ambient-context approach gives both the same one.

## Consequences

Without an ambient span, the capability span is a root. The direct MCP
invoker tests exercise that case outside the SDK middleware. A served MCP
request can inherit a span established by the SDK.

An unknown `traceparent` version links. The W3C specification requires forward
compatibility for future versions and forbids only `ff`, and the propagator
implements that. This was written expecting `99` to be rejected; the
specification agrees with the propagator, so the expectation was wrong and the
behaviour is pinned by test instead of being left as a surprise.

Malformed values are inert. An empty, truncated, non-hexadecimal, all-zero or
`ff`-versioned header produces an unlinked root span and no error, so a
hostile header degrades linking rather than the request.

Nothing about span content changes. A linked span carries the same two
attributes an unlinked one does; joining a caller's trace is not a back door
for transport data, and a test asserts the attribute set and the absence of the
header value in the exported span.

In-process nesting from ADR 0055 survives remote parenting: a nested
invocation is still a child of its caller's span, inside the caller's trace.

## Alternatives considered

**Extract `traceparent` in `agnara-http`.** Rejected above: it moves a trust
decision into the framework, duplicates maintained instrumentation and cannot
be offered to MCP.

**Read trace context from MCP `_meta`.** Rejected for now. It would be an
Agnara-specific convention layered on the protocol, and it inherits the same
trust problem without the W3C specification's backing. Revisit if the MCP
specification adopts a propagation field.

**Emit an OpenTelemetry `Link` instead of a parent.** A link expresses
association between causally-related traces rather than containment. A remote
caller invoking a capability is containment: the invocation happens because of
and during the caller's operation. Using a link would model it as a sibling and
lose the latency relationship an operator wants.

**Ship an ASGI middleware in `agnara-telemetry`.** It would import no sibling
adapter and so is permitted, but it would be a worse copy of an existing,
maintained package, and it would put a transport concept in the telemetry
adapter for no gain.

## Scope

This ADR adds no runtime code. Semantic convention compatibility remains E9.5:
the span name and attributes stay custom Agnara names and are not asserted to
satisfy any OpenTelemetry protocol or GenAI convention. No-op cost evidence
remains E9.6. Outbound header injection for calls a capability makes is out of
scope entirely and belongs to whatever client the capability uses.

Proposed status does not claim maintainer architectural approval.

## Evidence

`tests/telemetry/test_transport_linking.py` — 17 cases over the real
dispatchers: HTTP and MCP linking under propagation, both unlinked without it,
an unextracted header changing nothing, seven malformed headers, three unknown
versions, fifteen concurrent requests across two remote traces and five
unpropagated ones without contamination, attribute containment, and nested
invocation inside a remote trace.

`tests/architecture/test_package_boundaries.py` prohibits OpenTelemetry imports
outside the telemetry adapter and allows only the MCP SDK's patched API floor
as a transport dependency. `tests/security/test_dependency_security.py`
exercises the SDK's metadata extraction with valid and over-limit values.

Primary sources checked on 2026-09-05:

- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [Context propagation](https://opentelemetry.io/docs/specs/otel/context/api-propagators/)
- [Python propagators](https://opentelemetry-python.readthedocs.io/en/latest/api/propagate.html)
- [Published API baseline](https://pypi.org/project/opentelemetry-api/1.44.0/)
