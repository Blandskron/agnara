# Threat Model — 1.0 Candidate

What an attacker can reach in the `1.0.0` candidate, what Agnara itself
refuses, and what it deliberately leaves to the application or deployment.
It covers direct capability execution; the ASGI/HTTP and SSE projection; MCP;
nested composition and idempotency; embedded and side-by-side hosts; schema,
persistence and telemetry seams; the local CLI; and published distributions.

This is source-and-test-backed release evidence, not a production-security
certification. There is no penetration test, fuzzing corpus, load test,
cryptographic review or audit of an application's deployment. Every
"verified" claim below names repository evidence; everything else is written
as an assumption, residual risk or post-1.0 decision on purpose.

`SECURITY.md` owns the reporting channel and the project's security posture.
This document owns the analysis.

## 1. Assets

| Asset | Why an attacker wants it |
| --- | --- |
| Capability handlers and their effects | They do the application's real work: writes, payments, deletions. |
| The authorization decision | Reaching a capability the caller was not granted. |
| Application secrets held by dependencies | Database credentials, API keys, tokens resolved through DI. |
| Request and response content | Other callers' data, whatever the application processes. |
| Server availability | A worker held open, memory consumed, a process degraded. |
| Server-side detail | Tracebacks, internal paths, dependency names, policy internals. |
| Execution and idempotency identities | A forged execution identity, replayed key or cross-principal result can confuse effects and audit trails. |
| Schema, persistence and telemetry data | A custom adapter, store or exporter can disclose or corrupt application data outside core controls. |
| Host and release authority | A host identity mapper, local CLI operator or publisher can cause privileged effects or publish compromised artifacts. |
| The published distributions | Anything shipped to PyPI is executed by every consumer. |

## 2. Trust boundaries

```text
       untrusted / host-owned          │ Agnara owns              │ application owns
───────────────────────────────────────┼──────────────────────────┼───────────────────
 HTTP client ──▶ ASGI server ──▶ binding ──▶ policies ──▶ handler / result mapping
 MCP client ──▶ official SDK ──▶ dispatch ──▶ policies ──▶ handler / result mapping
 direct or embedded caller ──▶ value-only context bridge ──▶ policies ──▶ handler
 schema adapter / idempotency store ───────────────────────────────────────▶ selected by app
 telemetry hook ───────────────────────────────────────────────────────────▶ exporter and retention
```

Eight boundaries matter.

**B1 — the ASGI server.** Everything before the adapter's first line: TLS,
connection limits, HTTP framing, header size limits, request smuggling, and how
long a client may take to send a body. Agnara is an ASGI 3 application and
inherits whatever the deployed server enforces.

**B2 — the adapter boundary.** Where attacker bytes become a typed payload.
Agnara owns this completely and it is where most of this document lives.

**B3 — the policy boundary.** Where a principal and a payload become a
decision. Agnara supplies the pipeline and the ordering; the application
supplies the policies and, for confirmation, the verifier.

**B4 — the application boundary.** Handlers, dependency providers, telemetry
exporters and any failure message an application writes. Agnara cannot make an
application's own disclosure safe; it can keep its own out of the way.

**B5 — direct and embedded execution.** A caller that can construct an
`ExecutionContext` is a trusted composition root, not an authenticated remote
principal. The ADR 0094 host bridge passes plain values only; the host owns
request/session/transaction/span objects and must map verified identity to a
direct actor or fail closed to anonymous. Core rejects caller metadata named
`execution_id` and generates that identity itself, but it cannot authenticate
the caller that supplied a principal, confirmation evidence or idempotency
selector.

What core does enforce is the shape of that hand-off. A principal must be a
`Principal`, so a raw token or session object cannot pose as one, and the
verified authority inputs are fixed once the execution exists, so a running
capability cannot reassign the actor its own children inherit. `SECURITY.md`
owns the accepted identity vocabulary.

**B6 — schema and persistence.** Core compiles the selected schema contract
and strictly validates materialized input, but a custom schema adapter and any
durable idempotency store are application code. The bundled store is
process-local; the SQLAlchemy/SQLite exercises are fixtures in which the host
owns session, commit and rollback, not a shipped persistence integration.

**B7 — observability.** The optional telemetry bridge emits a fixed allowlist
and excludes payloads, principals, values and exception text. Tracer/meter
providers, exporter endpoint, retention, access and host propagation remain
application-owned.

**B8 — local tooling and release.** CLI target import is local code execution,
not a sandbox. Publication crosses protected GitHub environment review,
phase-specific OIDC and package registries; their live settings need external
readback and are not established by source inspection alone.

## 3. Attacker-controlled inputs

Everything in this list is untrusted, including values the transport looks
structural: method, path, `root_path`, query string, every header name and
value, cookies, the body and its media type, multipart boundaries, part names
and filenames, the number and size of ASGI body events, an MCP tool name, its
arguments, the JSON-RPC request id and SDK access token. A direct or embedded
caller can also supply a principal, confirmation evidence, deadline,
idempotency selector, opaque correlation label and custom schema/store/exporter
configuration; those are trusted only after its application composition root
has validated them. Capability descriptions, schemas, examples, prompt text
and metadata are untrusted data when an application sends them to a human or
agent; the framework does not inspect semantic prompt/tool injection.

## 4. Verified protections

Each row is proved by the test named beside it. `tests/security/` was added by
this audit; the other paths existed already.

| Property | Evidence |
| --- | --- |
| A body over its limit is refused, and the limit is per route | `tests/http/test_dispatch.py`, `tests/http/test_request_surface.py` |
| A multipart body is bounded in parts as well as bytes | `tests/http/test_request_surface.py` |
| Malformed multipart, bad boundaries and bad encodings are structured failures, never exceptions | `tests/http/test_request_surface.py` |
| The client filename in an upload is never exposed | `tests/http/test_request_surface.py` |
| Nothing is read from the body until the media type settles | `tests/http/test_request_surface.py` |
| A duplicate header, cookie, form field or query value is refused rather than resolved | `tests/http/test_request_surface.py`, `tests/http/test_request_binding.py` |
| Duplicate JSON object keys are refused | `tests/http/test_request_binding.py` |
| A JSON body too deeply nested to decode is a 400, not an escaped exception | `tests/security/test_http_protocol_robustness.py` |
| A result too deeply nested to serialize is a redacted 500 | `tests/security/test_http_protocol_robustness.py` |
| A stream of empty body events terminates | `tests/security/test_http_protocol_robustness.py` |
| A disconnect mid-body ends the request with no response and no exception | `tests/security/test_http_protocol_robustness.py` |
| A bound header value cannot reach a response header | `tests/security/test_http_protocol_robustness.py` |
| A traversal sequence in a path parameter is data, not a path | `tests/security/test_http_protocol_robustness.py` |
| The problem document never carries the query string | `tests/http/test_dispatch.py`, `tests/security/test_http_protocol_robustness.py` |
| An unexpected handler exception becomes a fixed, redacted 500 | `tests/security/test_trust_boundaries.py`, `tests/http/test_dispatch.py` |
| Default runtime logs retain the capability identifier but exclude unexpected exception messages and tracebacks | `tests/unit/execution/test_runtime.py` |
| An unsupported ASGI scope is refused before dispatch | `tests/http/test_asgi_boundary.py` |
| The HTTP surface builds an anonymous principal and reads identity from no request field | `tests/security/test_trust_boundaries.py` |
| A confirmation requirement cannot be satisfied over HTTP, and the handler does not run | `tests/security/test_trust_boundaries.py` |
| A confirmation requirement without a verifier fails at startup | `tests/security/test_trust_boundaries.py` |
| Scopes are matched exactly: no prefix, wildcard, case fold or trim | `tests/security/test_trust_boundaries.py` |
| Runtime-owned parameters cannot be supplied by a caller, on either transport | `tests/mcp/test_tool_invocation.py`, `tests/security/test_trust_boundaries.py` |
| An MCP tool hidden by discovery filtering is still refused when named directly | `tests/security/test_trust_boundaries.py` |
| An MCP mapper failure is redacted and fails closed | `tests/mcp/test_authorization.py` |
| Task-augmented and resumed MCP calls are refused before dispatch | `tests/mcp/test_tool_invocation.py` |
| Telemetry carries no payload, principal, value or exception text | `tests/security/test_trust_boundaries.py`, `tests/integration/telemetry/test_opentelemetry_shared_host.py`, `packages/agnara-telemetry` |
| An over-long or unusable MCP request id never reaches telemetry | `tests/mcp/test_tool_invocation.py` |
| A caller cannot choose the runtime execution identity through invocation metadata | `tests/unit/execution/test_execution_identity.py` |
| A privileged parent cannot lend its authority to a child the caller lacks scope for | `tests/security/test_authority_boundary.py` |
| A running capability cannot reassign the verified actor, confirmation evidence or idempotency selector | `tests/security/test_authority_boundary.py` |
| A credential-shaped object offered as a principal is refused before execution | `tests/security/test_authority_boundary.py` |
| Principal metadata never grants authority under any claim name | `tests/security/test_authority_boundary.py` |
| A cached or replayed discovery snapshot never authorizes a later invocation | `tests/security/test_authority_boundary.py` |
| An unavailable or ambiguous confirmation verdict denies instead of approving | `tests/security/test_authority_boundary.py` |
| Interleaved executions never exchange principals between parents or children | `tests/security/test_authority_boundary.py` |
| A nested child has a detached actor, new execution identity and no inherited confirmation or idempotency selector | `tests/unit/execution/test_nested_composition.py` |
| An idempotency selector is bound to capability, principal and fingerprint, with atomic in-flight behavior | `tests/unit/execution/test_idempotency.py` |
| A streaming invocation refuses an idempotency selector instead of discarding it | `tests/security/test_trust_boundaries.py` |
| Slow SSE consumers exert pull backpressure and disconnect/cancellation close the owned stream | `tests/http/test_sse.py` |
| Host fixtures retain host identity, lifespan and transaction ownership while the core re-evaluates policy | `tests/conformance/test_host_harness.py`, `tests/integration/persistence/test_sqlalchemy_sqlite.py` |
| The optional OpenTelemetry bridge omits payloads, claims and idempotent results, including in a shared host | `tests/integration/telemetry/test_opentelemetry_shared_host.py` |
| Reviewed files and built distributions are checked for recognized credential signatures; this does not prove absence of every secret format | `tests/security/test_repository_secrets.py`, `scripts/check_distributions.py` |

Two structural properties are worth stating separately, because they remove
whole classes rather than one case.

**No filesystem, no subprocess, no outbound network.** The Agnara HTTP/SSE request path
opens no file, spawns nothing and makes no outbound call. Multipart is parsed
in memory, so there is no temporary upload to leak or clean up, and no static
file route exists for a traversal to reach.

**No decompression.** `Content-Encoding` is not honoured, so a compressed body
is refused as malformed rather than expanded. There is no decompression bomb
because there is no decompression.

## 5. Findings from this audit

| ID | Severity | Status |
| --- | --- | --- |
| H-1 | P1 | Fixed. A JSON body nested beyond the decoder's stack raised `RecursionError` out of the dispatcher. 80 KB — well inside the 1 MiB default — was enough, from an unauthenticated client, before any capability ran. The dispatcher sent nothing and the ASGI server decided what the client and the operator's log received, bypassing the reviewed problem mapping and its redaction. A platform-independent ceiling now rejects nesting beyond 128 levels with a 400 before decoding or capability execution, naming the reason without echoing the body. |
| H-2 | P1 | Fixed. The same class at the other end: a value nested deeper than the interpreter can walk raised `RecursionError` out of response serialization, reachable by a capability that echoes an accepted-but-deep body. Now the existing last-resort redacted 500. |
| H-3 | P1 | Fixed by [#312](https://github.com/Blandskron/agnara/pull/312). Declared scopes compile into the common execution plan, so HTTP and MCP enforce the same policy before materialization, validation or effects. Anonymous HTTP calls to scoped capabilities now fail closed. |
| H-4 | P2 | Fixed. `_read_body` bounded total bytes but not the number of events. An empty chunk moves `max_body_bytes` no closer to its limit, so a client sending them with `more_body` set held a worker open indefinitely and grew a list without bound. Empty events are now capped. |
| H-5 | P3 | Fixed. `request_timeout` was documented as a per-request deadline. It starts after binding, so it bounds execution and not how long a client may take to send a body. The documentation now says which. |
| H-6 | P3 | Fixed. Unexpected capability exceptions were redacted on the wire but logged with `exc_info`, so exception-carried credentials, dependency values or payload fragments could reach the application's default log sink. The runtime now logs only the capability identifier; a regression test proves that exception text and traceback are absent. |
| S-2 | P2 | Fixed. `ExecutionContext.principal` was an ordinary mutable attribute, and nested composition derives a child's authority from it. A capability that received its `ExecutionContext` could therefore assign a principal of its choosing and invoke a child with scopes the authenticated caller never held — privilege amplification reachable by an ordinary handler bug, not only by malicious code. The verified authority inputs (`principal`, `confirmation_evidence`, `idempotency`) are now fixed for the lifetime of an execution and refuse assignment; the attempt fails closed as a redacted canonical failure and the child never runs. The same repair validates the principal's type, so a duck-typed token or session object can no longer stand in for a verified identity. |
| S-1 | P2 | Fixed. A streaming invocation silently discarded an `IdempotencyInvocation`. The refusal existed in `_execute_with_idempotency`, but its only caller is the complete-result path, which rejects a streaming plan several frames earlier, so the guard could never fire; `open_stream` consulted `context.idempotency` nowhere. A caller asking for exactly-once effects got the producer rerun on every attempt, with the store never consulted and nothing reported. `open_stream` now refuses the selector before the producer can start. |

### H-3 — declared scopes are enforced transport-neutrally

[#312](https://github.com/Blandskron/agnara/pull/312) resolved the asymmetry.
`@app.capability(scopes={"records:read"})` now compiles a core `ScopePolicy`
into the common `ExecutionPlan`. Every transport invokes that plan, and the
policy runs before transport materialization, validation, dependencies and
handler effects. Neither HTTP nor MCP adds its own interpretation.

`tests/security/test_trust_boundaries.py` proves an anonymous HTTP call is
forbidden without executing the handler and that MCP refuses the same scoped
capability. The broader cross-surface ordering is fixed by
`tests/conformance/test_a4_schema_policy_failure_consistency.py`.

The native HTTP surface still constructs an anonymous principal and has no
general authentication or principal-mapping contract. Consequently, a declared
scope fails closed there rather than being silently ignored. An embedded host
may map a verified identity through the value-only ADR 0094 bridge, but that is
the host application's security boundary, not an HTTP adapter feature. The
framework does not infer authority from headers, cookies, query parameters or
capability arguments.

## 6. Delegated assumptions

These are not protections Agnara offers. Each belongs to a layer named beside
it, and none is verified by this repository's tests.

| Concern | Owner |
| --- | --- |
| TLS termination, certificate handling | Deployment |
| Request smuggling, HTTP framing, duplicate `Content-Length`, HTTP/2 and /3 | ASGI server and any proxy |
| Header count and size limits, request line length | ASGI server |
| How long a client may take to send a body (slowloris) | ASGI server or proxy; `request_timeout` does not cover it |
| Connection and concurrency limits, backpressure | ASGI server |
| Rate limiting, quotas, abuse detection | Application or proxy |
| Authentication and principal issuance over native HTTP | Not implemented; native HTTP invocation is anonymous and does not produce a `401` |
| OAuth token verification, JSON-RPC framing, MCP session and transport handling | Official MCP SDK |
| Correctness and disclosure of application policies, handlers and failure messages | Application |
| Telemetry exporter destination, retention and access | Application |
| CORS, security headers, caching for non-documentation routes | Not implemented; proxy or future work |

A residual worth naming: a body at the size limit sent in very small chunks
allocates roughly forty times its own size in per-chunk objects before the
limit is reached. It is bounded and freed with the request, but it is an
amplification, and the mitigation is the ASGI server's chunking rather than
anything Agnara does.

## 7. Agent-specific threats

`SECURITY.md` lists the agent threats the project intends to model. Their
current candidate status:

| Threat | candidate status |
| --- | --- |
| Confused deputy, over-broad delegated authority | Addressed at the implemented boundary, with a dedicated regression suite in `tests/security/test_authority_boundary.py`. A caller that may invoke a privileged parent gains nothing the parent can lend: the child re-evaluates the caller's own actor. The verified authority inputs are immutable for the execution, so a handler cannot escalate its own children, and a credential-shaped object is refused as a principal. Declared scopes run before effects. ADR 0093's implemented same-snapshot nested boundary re-evaluates child policy/confirmation and refuses ambient context, scope union, inherited confirmation and raw delegation evidence. The child receives a detached direct actor plus at most a bounded correlation label; parent state, idempotency and raw invocation metadata do not cross. Delegation is deliberately unimplemented. MCP maps a verified SDK token through an application mapper; native HTTP remains anonymous and fails closed for scoped capabilities. |
| Tool name and schema spoofing | Addressed. Names and schemas come from one frozen startup snapshot; discovery and invocation cannot disagree. |
| Approval bypass | Addressed for confirmation: no evidence channel exists on either transport, resumed calls are refused, and a missing verifier fails at startup. |
| Prompt and tool injection across trust boundaries | Residual application/agent risk. Agnara does not inspect argument content or decide whether untrusted descriptions, schemas, examples or retrieved text may authorize a tool. Applications must keep untrusted prompt data separate from authority and confirmation decisions. |
| Automated destructive invocation, replay of non-idempotent operations | Partially addressed. A streaming invocation now refuses an idempotency selector rather than discarding it (S-1), so a caller cannot believe it has exactly-once effects on a path that never had them. ADR 0091 makes an explicit direct `Idempotency.YES` selector claim atomically before dependencies or handler work and reuses only a bound completed success. It re-evaluates policy and confirmation, rejects scope/principal mismatch, and fails closed on store or stale-codec errors without logging opaque result bytes. Inclusive lease/result expiry is a liveness boundary, never proof the former handler stopped; automatic retries remain absent. It neither authenticates callers nor adds HTTP/MCP selector fields; anonymous HTTP and unreviewed protocol metadata remain untrusted. |
| Cross-tenant context leakage | No tenant model is supplied. Per-invocation context, nested ancestry and idempotency namespaces are isolated in the reviewed runtime; tenant isolation, host caches and application stores remain application-owned. |
| Unbounded tool recursion | Partially addressed for nested capabilities. `CapabilityRuntime` keeps private immutable ancestry per child, refuses direct and indirect repeated identities and applies a finite `1..32` runtime depth limit before the next child policy, dependencies or effects. Ordinary application Python recursion remains application-owned; a streaming child is refused before producer start, and streams and cross-app composition are not part of this boundary. |
| SSRF through generic HTTP capabilities | Application's own concern; Agnara makes no outbound call. |

### Embedded-host bridge

ADR 0094 defines the host adapter as a trust boundary rather than a source of
ambient authority. Its principal mapper may pass a verified direct actor into
an ExecutionContext, but must not manufacture scopes, confirmation, delegation,
execution identity or idempotency state from request data. Raw host
request/session/transaction, telemetry and exception objects remain outside
kernel state and normal handler parameters; the host maps canonical results and
owns its own resources. The Starlette 1.6.0, FastAPI 0.141.1, Django 6.1.1 and
Litestar 2.24.0 fixtures exercise fail-closed identity mapping, redacted
canonical failure, fixed trusted idempotency selection and disconnect
cancellation; their evidence is in `tests/integration/starlette/`,
`tests/integration/fastapi/`, `tests/integration/django/` and
`tests/integration/litestar/`. The
FastAPI fixture also keeps its dependency verifier, middleware and exception
handler outside the capability boundary, and explicitly joins a mounted
ASGI-child lifespan rather than assuming FastAPI propagates it. These remain
bounded fixture checks, not a framework support claim or completed release
security review.

## 8. CLI and reserved distribution boundaries

All seven distributions, including `agnara-cli`, `agnara-a2a` and
`agnara-events`, belong to the reviewed candidate publication set (ADR 0073).
The latter two expose empty `__all__` lists and implement no protocol runtime;
their current security evidence is package-boundary, archive and installed
metadata validation, not A2A or event-protocol conformance.

The CLI is a local developer tool with the caller's filesystem and Python
execution authority. Introspection imports the selected application module;
module initialization and dotted attribute access can execute application
code. A valid target is not a sandbox. Only run CLI targets and search paths
from projects you trust, and treat generated introspection output as local
data until an application applies its publication policy.

The bounded safeguards reviewed here are:

| Property | Evidence |
| --- | --- |
| Malformed targets are rejected before import; import errors become diagnostics | `tests/cli/test_inspect.py` |
| Manifest paths that lexically escape the project are rejected | `tests/cli/test_manifest.py` |
| Project dry-run writes nothing; existing output is refused without explicit overwrite | `tests/cli/test_project_create.py` |
| Schema/context output requires explicit overwrite of an existing file | `tests/cli/test_schema.py`, `tests/cli/test_context.py` |

These checks do not establish safety against a malicious local process racing
filesystem changes or replacing directories with symlinks. `--overwrite` is
an explicit grant to replace output, not a merge or preservation guarantee.
The no-filesystem/no-subprocess statement in section 4 applies only to the
transport request path, not to this developer tool or application handlers.

## 9. Repository security controls

The Cycle 3 follow-up in Issue #326 enables GitHub secret scanning, push
protection and Dependabot alerts/security updates. On 2026-09-20, a GitHub API
readback for the repository reported Dependabot security updates, secret
scanning and push protection enabled, and returned zero open Dependabot and
secret-scanning alerts. This is a point-in-time observation, not proof that a
future candidate or every historical revision is clean. Non-provider-pattern
scanning and secret validity checks were reported disabled. These limitations
remain visible in the release closure record.

Required CI includes CodeQL for Python and GitHub Actions, with immutable
action references and security-result upload permission limited to that job.
The analysis runs without building or executing the application. A completed
scan is not a claim that no vulnerability exists: maintainers must triage
reported alerts before release. See `SECURITY.md` for the operating procedure.

The locked runtime dependency audit recorded in the release closure is
separate evidence; it does not cover development tools or future advisory
database updates.

## 10. Adversarial review for 1.0.0

A second adversarial pass covered authorization and principal handling, direct
and embedded host bridges, nested capability invocation, execution identity,
idempotency, streaming and SSE, schema/persistence seams, documentation UIs,
supply-chain controls and telemetry.

It produced findings S-1 and S-2 above. The following were probed directly and
behaved correctly; they are recorded so a later reviewer knows they were tried
rather than assumed:

| Probe | Result |
| --- | --- |
| A stored idempotent result read back by a different principal using the same key | Refused. The selector binds capability, principal and key, and the two principals received their own results. |
| An idempotency scope naming a different capability than the compiled plan | Refused before the claim, as a redacted canonical failure. |
| A nested child inheriting the parent's idempotency selector | Does not happen; the child's execution adds no store record. |
| Caller metadata attempting to select a runtime execution identity | Refused before policy or effects; the runtime generates the execution identity. |
| A caller invoking a privileged parent whose child needs a scope it lacks | Refused at the child boundary; the privileged effect never ran and the parent still returned a canonical result. |
| A handler reassigning `context.principal` before invoking a child | Refused. This was a real finding (S-2); the authority inputs are now immutable and the attempt fails closed as a redacted canonical failure. |
| A verified-token object passed where a principal belongs | Refused at construction, although it was duck-type compatible with scope evaluation. |
| Forged `scopes`, `scp`, `roles` or `permissions` entries in principal metadata | Inert. Only granted scopes authorize. |
| Invocation metadata asserting `subject`, `on_behalf_of`, `act_as` or `delegation` | Inert. No subject or delegation surface exists to read. |
| A discovery snapshot filtered for a privileged viewer, replayed by an unprivileged one | Discloses descriptions only; authorization is re-decided from the invoking principal. |
| A host fixture passing raw request/session/transaction state into the kernel | Out of contract: the value-only bridge fixtures retain those objects and lifecycle ownership in the host. |
| An idempotency selector on a capability not declared `Idempotency.YES` | Refused, fail-closed, as a redacted canonical failure. |
| A stream unit containing SSE frame separators | Cannot inject a frame: every unit goes through the same JSON value rule, so separators are escaped. Covered by `tests/http/test_sse.py`. |
| Unbounded buffering or a slow SSE consumer | Structurally prevented: the pump performs one pull per completed send with no queue between them, so ASGI send demand is the producer's demand. |
| A telemetry hook receiving payload, principal, result or exception text | Refused by the adapter's fixed attribute allowlist; exporter routing and retention remain application-owned. |
| GitHub Actions pinned to mutable references, or default write permissions | Enforced by `tests/architecture/test_ci_workflow.py` and `test_release_workflow.py`. |

The probes are not a substitute for the limits in section 11. In particular,
none of them is a concurrency or load test.

## 11. What this audit did not do

No fuzzing, no penetration test, no load or denial-of-service testing under
real concurrency, no review of the
vendored documentation bundles' own code, no analysis of git history for
previously committed credentials. The CLI review is bounded to section 8;
there is no hostile-local-filesystem or plugin-execution audit. Reserved A2A
and events distributions have no implemented protocol behavior to review.
Native secret scanning and static analysis supplement these limits; they do
not replace a full historical credential, cryptographic or supply-chain audit.
