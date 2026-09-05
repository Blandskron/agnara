# ADR 0057 — Semantic Convention Compatibility for Capability Telemetry

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #225 (E9.5)

## Context

ADR 0054 and ADR 0055 both shipped custom `agnara.*` names and disclaimed any
semantic convention claim, deferring the question to E9.5. This is that
decision.

The available conventions were read out of the installed
`opentelemetry-semantic-conventions` 0.65b0 rather than quoted from a
specification page, so the classification below is reproducible with
`uv run python`:

| Namespace | Status | Relevant entries |
| --- | --- | --- |
| `opentelemetry.semconv.attributes` | stable | `error.type` |
| `..._incubating...gen_ai_attributes` | incubating | `gen_ai.operation.name` (`execute_tool`), `gen_ai.tool.name`, `gen_ai.tool.type`, `gen_ai.tool.call.id`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result` |
| `..._incubating...mcp_attributes` | incubating | `mcp.method.name`, `mcp.protocol.version`, `mcp.resource.uri`, `mcp.session.id` |

Stable metric conventions exist only for `db` and `http`; none describes a
capability invocation.

## Decision

**Adopt `error.type`, and nothing else.** Every other attribute Agnara emits
stays in the `agnara.` namespace.

On a span whose outcome is `failure` or `timeout`, `error.type` carries that
same outcome word. The convention asks for a low-cardinality error identifier,
and Agnara's closed vocabulary is exactly that. It deliberately does not carry
an exception type or message: ADR 0055 forbids exporting exception text, and
that prohibition outranks a more descriptive attribute value. A `cancellation`
carries no `error.type`, consistent with ADR 0055 leaving its status `UNSET` —
the caller withdrew, and the capability did not fail.

**Reject the GenAI vocabulary on a capability span.** Three independent
reasons, any one of which is sufficient:

1. AGENTS.md states that a capability is not intrinsically a tool and that MCP
   must never be the semantic source of truth. `gen_ai.operation.name` with the
   value `execute_tool` on every capability span would assert the opposite for
   an HTTP request made by a human.
2. `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` are payload
   attributes. ADR 0054 and ADR 0055 forbid exporting arguments and results.
3. It is incubating. Adopting an unstable vocabulary means inheriting its
   renames, and documentation discipline forbids claiming compatibility that
   evidence does not support.

Reason 1 is the one that would still hold if the vocabulary stabilised
tomorrow. The others are timing.

**Reject the MCP vocabulary in `agnara-telemetry`** for the same first reason,
and because the telemetry adapter has no MCP identity to report: it observes a
capability invocation, which may have arrived over MCP, HTTP, or a direct
in-process call. `mcp.method.name` belongs where the method name exists.

**Leave metric attributes unchanged.** `error.type` was considered for
`agnara.invocation.count` and rejected: `agnara.invocation.outcome` already
carries the same information on every measurement, so a second attribute
present only on failures would fragment existing time series without adding
signal. Spans and metrics therefore have deliberately different attribute sets,
which is recorded by a test rather than left to be noticed.

## Making the boundary enforceable

A sentence in an ADR does not survive contact with a future patch. Two rules in
`tests/telemetry/test_semantic_conventions.py` check every attribute the two
hooks actually emit, across all four outcomes, against the installed
conventions package:

1. every emitted attribute is either `agnara.`-namespaced or a **stable**
   convention name;
2. no incubating convention name is emitted.

A third asserts both directions of the adoption list, so nothing can be adopted
silently and nothing can be recorded here while absent from the output. Two
more name the `gen_ai.` and `mcp.` prefixes specifically, and each first
asserts that the installed package actually declares them, so the rule cannot
pass because a namespace disappeared.

Verified non-vacuous: a temporary `gen_ai.tool.name` attribute failed four of
these rules.

## Consequences

Adding `error.type` changes the exported attribute set of an error span from
two attributes to three. That is a visible change for anyone matching on the
exact set, and it is recorded in the changelog. The E9.2 and E9.3 assertions
were updated to expect it explicitly rather than relaxed to tolerate extras.

Agnara telemetry will not be recognised by a backend's GenAI-specific views. An
application that genuinely serves capabilities as MCP tools, and wants those
views, should add the `mcp.*` and `gen_ai.*` attributes at its MCP layer, where
a tool identity and a method name actually exist, rather than expecting a
transport-neutral capability span to claim them.

The conventions package remains a development dependency only, reached through
the pinned SDK. `agnara-telemetry` still declares `opentelemetry-api` alone, and
`error.type` is a string literal in the adapter rather than an import, so
adopting a convention name did not add a runtime dependency.

## Alternatives considered

**Adopt the GenAI vocabulary behind a flag.** A constructor option to emit
`gen_ai.*` would keep the default honest, but it makes the framework offer a
claim it believes is wrong for most invocations, and the flag's correct value
depends on the transport — which the hook, by ADR 0056, does not know.

**Emit `error.type` as the exception class name.** More informative and what
much instrumentation does. Rejected: ADR 0055 forbids exception text, class
names leak internal structure, and cardinality becomes unbounded across a
codebase's exception hierarchy.

**Wait for the conventions to stabilise before adopting anything.** Rejected
for `error.type` specifically, which is already stable, applicable, and
low-cardinality. Waiting would forgo a real interoperability gain for no
reduction in risk.

## Scope

No performance claim; no-op cost evidence is E9.6. No protocol version support
claim of any kind. Proposed status does not claim maintainer architectural
approval.

## Evidence

`tests/telemetry/test_semantic_conventions.py` — 7 cases over both hooks and
all four outcomes. `tests/telemetry/test_tracing.py` — updated attribute
assertions naming `error.type` on error outcomes and asserting its absence
otherwise.

Verified locally on 2026-09-05 against `opentelemetry-semantic-conventions`
0.65b0, `opentelemetry-api` 1.44.0 and `opentelemetry-sdk` 1.44.0.

Primary sources checked on 2026-09-05:

- [Semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
- [General attributes, `error.type`](https://opentelemetry.io/docs/specs/semconv/attributes-registry/error/)
- [GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [Published conventions baseline](https://pypi.org/project/opentelemetry-semantic-conventions/0.65b0/)
