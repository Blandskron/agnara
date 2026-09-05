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

**Agnara does not participate in context propagation.** No transport adapter
reads, writes, validates or forwards a propagation header, and no transport
adapter depends on OpenTelemetry. An application propagates incoming context —
in practice with the instrumentation its server or client library already
ships — and the capability span joins the caller's trace because ADR 0055
starts it from the ambient context.

This was verified rather than assumed, over the real HTTP dispatcher and the
real MCP `tools/call` invoker:

| Application propagates | Result |
| --- | --- |
| yes | capability span carries the caller's trace ID, parented by the caller's span |
| no | capability span is a root span in its own trace |

The second row matters as much as the first. A request may carry a
`traceparent` header and still produce an unlinked span, because Agnara never
looks at it. Linking is something an application opts into.

`tests/architecture/test_package_boundaries.py` enforces the boundary: only
`agnara-telemetry` may import or declare OpenTelemetry. That rule is what keeps
this a decision rather than a temporary state — the moment `agnara-http` could
import OpenTelemetry, a header parser and the trust decision below would
follow it in.

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

An application that configures no propagation gets per-invocation traces that
are correct but unlinked. That is a visible gap for anyone expecting linking to
work out of the box, and the package README states the composition explicitly
so the gap is documented rather than discovered.

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

`tests/architecture/test_package_boundaries.py` — six distributions asserted
free of any OpenTelemetry import or declared dependency. Verified non-vacuous:
a temporary `import opentelemetry.trace` in `agnara-http` failed the rule with
the offending file and line.

Primary sources checked on 2026-09-05:

- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [Context propagation](https://opentelemetry.io/docs/specs/otel/context/api-propagators/)
- [Python propagators](https://opentelemetry-python.readthedocs.io/en/latest/api/propagate.html)
- [Published API baseline](https://pypi.org/project/opentelemetry-api/1.44.0/)
