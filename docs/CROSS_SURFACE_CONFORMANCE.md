# Schema, Policy and Failure Conformance

This is the `0.1.0a4` semantic matrix for direct runtime, HTTP/OpenAPI and MCP.
It records equivalence, not byte identity. Executable evidence lives in
`tests/conformance/test_a4_schema_policy_failure_consistency.py`; adapter suites
retain their protocol-specific cases.

## Schemas

| Contract shape | Direct runtime | HTTP / OpenAPI | MCP |
| --- | --- | --- | --- |
| `bool`, `int`, `float`, `str` | exact Python type; `bool` is not `int` | scalar text bindings convert strictly; JSON preserves JSON scalars | decoded JSON scalar, then common strict validation |
| `T | None` | exact matching union member | `anyOf` including `null`; decoded JSON is materialized against a matching member | same compiled `anyOf` fragment and materialization |
| `Enum` | exact enum instance | underlying JSON scalar is materialized to the enum member | same as HTTP; the tool schema publishes the underlying scalar values |
| `Literal` | exact type and value | JSON `const`/`enum` | identical compiled fragment |
| dataclass | exact instance | closed JSON object becomes the declared instance recursively | same closed object schema and recursive materialization |
| `list[T]` | exact list | JSON array; nested values materialized | same |
| `dict[str, T]` | exact string-keyed dict | JSON object; nested values materialized | same |
| tuple | exact tuple | JSON array materializes to tuple | same; fixed tuples use `prefixItems` and length bounds |
| defaults | omitted Python argument uses handler/dataclass default | omitted optional input/field uses the same default | omitted optional argument/field uses the same default |
| required input/field | missing value is `invalid_input` | `required` is projected and runtime enforces it | tool `required` preserves compiled declaration order and runtime enforces it |

HTTP and MCP call `invoke_result(..., input_materializer=materialize_json)`.
Materialization occurs after policy and before validation. Direct calls omit
the helper: a dictionary is not silently accepted where Python declared a
dataclass. Custom schema implementations receive decoded JSON unchanged and
retain their own validation/coercion behavior.

Binary values are not a general JSON shape. HTTP upload/scalar bindings have
the bounded behavior documented in `HTTP_COMPOSITION.md`. MCP rejects a tool
whose standard schema graph contains `bytes` at startup instead of publishing
an impossible JSON contract; no binary tool-input extension or encoding is
claimed.

## Policies

| Concern | Common enforcement | Surface note |
| --- | --- | --- |
| allowed principal | `ScopePolicy` compares the context principal's granted scopes | direct and authenticated MCP can supply an identified principal |
| denied/anonymous principal | denial is canonical `forbidden` before input diagnostics or effects | HTTP a4 dispatch is anonymous, so a scoped capability fails closed |
| declared scopes | compiled once as the first plan policy | discovery filtering is visibility only and never replaces invocation policy |
| application business rule | explicit capability policies run after the declared-scope guard, in declaration order | a business rule is not framework authorization metadata |
| confirmation | `required` compiles a verifier-backed policy; missing evidence is `interaction_required`, invalid evidence is `forbidden` | HTTP maps 428; MCP maps one-way input-required and trusts no submitted boolean |
| risk/effects | preserved in declarations/introspection | metadata only: neither grants nor denies authority by itself |

The fixed execution order is:

```text
plan/context and protected-key checks
→ telemetry/deadline
→ declared scopes
→ application policies
→ confirmation declaration policy
→ explicit wire materialization
→ strict schema validation
→ dependency construction
→ handler
```

## Structured failures

| Situation | Canonical Agnara outcome | HTTP | MCP | Caller exposure |
| --- | --- | --- | --- | --- |
| validation | `invalid_input` | 400 problem | tool error | safe message; HTTP path, no submitted value |
| policy denial | `forbidden` | 403 problem | tool error | caller-safe policy reason |
| confirmation required | `interaction_required` | 428 problem | input-required form | reviewed title/message only; no evidence or verifier diagnostics |
| target/capability absent before invocation | no capability outcome | routing 404 problem | `INVALID_PARAMS` protocol error | target name only where the protocol requires it; no internals |
| dependency resolution failure | `internal_failure` | 500 problem | internal tool error | fixed redacted text, no details |
| application/domain failure | explicit `Failure` code chosen by application | reviewed status/problem | tool error | application must provide caller-safe non-internal text; MCP omits details |
| unexpected exception | `internal_failure` | 500 problem | internal tool error | fixed redacted text, no traceback/details |
| deadline | `timeout` | 504 problem | timeout tool error | stable deadline message |

HTTP also has transport-only failures before a capability exists: 405, 413 and
415. They do not enlarge `FailureCode`. MCP task-augmented, unknown and forged
resumption calls are protocol errors because no supported capability
invocation occurs.

For every `internal_failure`, both adapters discard the canonical message and
details. Tests use credential-shaped data, a private filesystem path and an
unexpected object to prove that serialized payloads contain no secret,
traceback, raw credential, object representation, dependency graph or private
path. Cancellation propagates as control flow and is not classified as a
failure.

## Deferred

Output schemas/validation, HTTP authentication, MCP MRTR resumption, A2A,
streaming and additional schema libraries are not `0.1.0a4` behavior. Their
absence is not papered over by a parallel schema or application workaround.
