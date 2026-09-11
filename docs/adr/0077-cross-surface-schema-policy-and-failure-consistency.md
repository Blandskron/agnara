# ADR 0077 — Cross-Surface Schema, Policy and Failure Consistency

- Status: Proposed
- Date: 2026-09-07
- Tracking: GitHub Issue #307
- Amends: ADRs 0008, 0025, 0044 and 0075

## Context

The baseline HTTP and MCP adapters both projected compiled core schemas, but
they did not consume them equivalently. HTTP materialized decoded JSON into
dataclasses, tuples and enums before entering the runtime. MCP published the
same JSON Schema and then passed decoded JSON directly to strict Python
validation, making valid published tool inputs fail. HTTP materialization also
ran dataclass constructors before policy, contrary to ADR 0025's security
order.

Declared scopes were enforced by an MCP-only guard while direct and HTTP
invocation depended on an application attaching `ScopePolicy` manually. An
adapter therefore decided whether the same declaration was executable.

Finally, HTTP redacted every `internal_failure`, including an explicit one,
while MCP serialized its message. A handler could return an internal failure
containing a path or credential and expose it only through MCP.

## Decision

### JSON materialization is explicit and ordered by core

`agnara.schema.materialize_json(schema, value)` converts decoded JSON into the
standard schema values JSON cannot carry: dataclasses, enum members and
tuples, recursively through lists, string-keyed mappings and unions. Unknown
schema implementations receive the decoded value unchanged.

`invoke_result` accepts an explicit `input_materializer`. The runtime calls it
after all policies and before strict schema validation. HTTP and MCP pass
`materialize_json`; direct Python invocation passes nothing and remains
strict. A materializer `ValidationError` receives the ordinary input path and
the same canonical `invalid_input` classification. An unexpected constructor
or materializer exception becomes a redacted `internal_failure`.

This is a schema-boundary helper, not implicit coercion. Core never examines a
transport name and never turns a direct dictionary into a domain object.

### Declared scopes compile into the common plan

When a capability declares scopes, `ExecutionPlan.compile` prepends one
`ScopePolicy` to its policy sequence. Application policies follow in declared
order; required confirmation remains the final compiled declaration policy.
Consequently identity/scope denial precedes application business rules,
materialization, validation, dependency construction and handler effects on
every surface.

Scopes restrict authority; they never grant it. Risk and effects remain
machine-readable metadata with no independent allow/deny semantics.

Baseline HTTP capability dispatch has no authentication bridge and therefore
runs as anonymous. A scoped HTTP capability fails closed with `forbidden`.
Adding an HTTP principal resolver is separate authentication work, not part of
this consistency fix.

### Internal failure text is adapter-owned and always redacted

HTTP retains its RFC 9457 redacted detail. MCP emits the stable
`"capability invocation failed"` message for every `internal_failure`, whether
core produced it from an exception or an application returned it explicitly.
MCP continues to omit all canonical failure details. Other failure messages
are caller-safe by the canonical `Failure` contract; HTTP may publish their
immutable details while MCP deliberately does not.

## Protocol-specific transformations

- HTTP represents canonical failures as RFC 9457 documents and statuses; MCP
  represents capability failures as tool-error content.
- A target missing before invocation is an HTTP routing `404` or MCP
  `INVALID_PARAMS`, not a fabricated capability failure.
- HTTP includes caller-safe canonical details; MCP omits them.
- Confirmation is HTTP `428`; MCP returns one input-required form. The form
  response is not confirmation evidence and no resumption is implemented.
- JSON arrays materialize as Python tuples only when the compiled schema says
  tuple. Direct Python callers must supply a tuple themselves.
- MCP rejects a standard schema graph containing `bytes` at startup because
  the supported JSON tool contract defines no reversible binary encoding.
  HTTP retains its explicit raw upload and scalar byte bindings.

## Threat analysis

**Pre-policy construction.** A dataclass `__post_init__` can perform arbitrary
application work. Moving materialization into the runtime after policy ensures
an unauthorized input cannot trigger it. Tests use an observable constructor
and prove scope and business-policy denial precede construction and handler.

**Scope bypass.** An adapter can no longer omit or reorder declared-scope
enforcement. The immutable plan owns the policy; MCP's duplicate adapter guard
is removed. Anonymous HTTP dispatch fails closed.

**Secret and path disclosure.** Both adapters replace internal messages and
discard internal details. Regression fixtures include a credential-shaped
value and private Windows path and assert neither serialized representation
contains them. Tracebacks and object representations are never serialized.

**Malformed JSON objects.** Materialization follows only the already compiled
schema graph, rejects unknown and missing dataclass fields, imports no
request-selected type and preserves body/part limits. Expected construction
errors become `invalid_input`; unexpected exceptions become a redacted 500 or
MCP internal tool error.

**Residual application responsibility.** An application may deliberately
return a non-internal `Failure` with caller-safe text and details. Agnara cannot
infer whether arbitrary application strings contain secrets. The canonical
contract therefore continues to require those fields to be safe for callers.

## Consequences

- Published JSON shapes are invocable through both shipped transports.
- One security-sensitive order is tested rather than reproduced by adapters.
- `materialize_json` adds one provisional export in each of
  `agnara.schema` and `agnara.schema.standard`; nothing is promoted stable.
- Existing HTTP dataclass field errors now use canonical `details.path`
  beginning with the capability input name instead of transport
  `details.location` beginning with `body`.
- Output schema compilation, HTTP authentication, MRTR resumption and a second
  schema implementation remain out of scope.
