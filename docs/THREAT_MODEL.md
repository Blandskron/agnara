# Threat Model — A8 Baseline

What an attacker can reach in the baseline surface, what Agnara
itself refuses, and what it does not attempt. It covers the retained baseline surface:
the ASGI/HTTP adapter, the MCP adapter, the policy pipeline, error mapping,
observability and the published distributions.

This is not the complete `1.0.0` security program. There is no penetration test, no fuzzing
corpus and no cryptographic review behind it. Every "verified" claim below
names the test that proves it; everything else is written as an assumption or a
gap on purpose.

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
| The published distributions | Anything shipped to PyPI is executed by every consumer. |

## 2. Trust boundaries

```text
       untrusted                     │ Agnara owns          │ application owns
─────────────────────────────────────┼──────────────────────┼───────────────────
 HTTP client ──▶ ASGI server ──▶ ASGI events ──▶ binding ──▶ policies ──▶ handler
 MCP client ──▶ official SDK ──▶ tools/call ──▶ dispatch ──▶ policies ──▶ handler
                                     │                      │
                              telemetry hooks ──▶ exporter (application owns)
```

Four boundaries matter.

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

## 3. Attacker-controlled inputs

Everything in this list is untrusted, including values the transport looks
structural: method, path, `root_path`, query string, every header name and
value, cookies, the body and its media type, multipart boundaries, part names
and filenames, the number and size of ASGI body events, an MCP tool name, its
arguments, the JSON-RPC request id, and any OAuth token the SDK verifies.

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
| Telemetry carries no payload, principal, value or exception text | `tests/security/test_trust_boundaries.py`, `packages/agnara-telemetry` |
| An over-long or unusable MCP request id never reaches telemetry | `tests/mcp/test_tool_invocation.py` |
| Reviewed files and built distributions are checked for recognized credential signatures; this does not prove absence of every secret format | `tests/security/test_repository_secrets.py`, `scripts/check_distributions.py` |

Two structural properties are worth stating separately, because they remove
whole classes rather than one case.

**No filesystem, no subprocess, no outbound network.** The a4 request path
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

The a4 HTTP surface still has no authentication or principal-mapping contract.
Consequently, a declared scope fails closed there rather than being silently
ignored. Applications needing authenticated scoped HTTP calls must wait for or
provide the future authentication integration; the framework does not infer
authority from headers, cookies, query parameters or capability arguments.

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
| Authentication and principal issuance over HTTP | Not designed in a4; no HTTP path produces a `401` |
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

`SECURITY.md` lists the agent threats the project intends to model. Their baseline
status:

| Threat | baseline status |
| --- | --- |
| Confused deputy, over-broad delegated authority | Declared scopes are enforced transport-neutrally before effects. MCP maps a verified token to a principal through an application mapper; HTTP remains anonymous and fails closed for scoped capabilities. Broader authentication and delegation design remains `1.0.0` work. |
| Tool name and schema spoofing | Addressed. Names and schemas come from one frozen startup snapshot; discovery and invocation cannot disagree. |
| Approval bypass | Addressed for confirmation: no evidence channel exists on either transport, resumed calls are refused, and a missing verifier fails at startup. |
| Prompt and tool injection across trust boundaries | Not addressed. Agnara does not inspect argument content. |
| Automated destructive invocation, replay of non-idempotent operations | Not addressed. `risk`, `effects` and `idempotent` are metadata, and idempotency is not enforced. |
| Cross-tenant context leakage | Not applicable in the baseline: no tenant concept, and no per-request state is shared between invocations. |
| Unbounded tool recursion | Not addressed. Nothing bounds a capability invoking another. |
| SSRF through generic HTTP capabilities | Application's own concern; Agnara makes no outbound call. |

## 8. CLI and reserved distribution boundaries

All seven distributions, including `agnara-cli`, `agnara-a2a` and
`agnara-events`, belong to the reviewed a4 publication set (ADR 0073).
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
protection and Dependabot alerts/security updates. Settings must be read back
from GitHub; a successful update request alone is not evidence of activation.
Non-provider-pattern scanning remained disabled after the enable request;
secret validity checks were not enabled. These limitations remain visible in
the release closure record.

Required CI includes CodeQL for Python and GitHub Actions, with immutable
action references and security-result upload permission limited to that job.
The analysis runs without building or executing the application. A completed
scan is not a claim that no vulnerability exists: maintainers must triage
reported alerts before release. See `SECURITY.md` for the operating procedure.

The locked runtime dependency audit recorded in the release closure is
separate evidence; it does not cover development tools or future advisory
database updates.

## 10. What this audit did not do

No fuzzing, no penetration test, no load or denial-of-service testing under
real concurrency, no review of the
vendored documentation bundles' own code, no analysis of git history for
previously committed credentials. The CLI review is bounded to section 8;
there is no hostile-local-filesystem or plugin-execution audit. Reserved A2A
and events distributions have no implemented protocol behavior to review.
Native secret scanning and static analysis supplement these limits; they do
not replace a full historical credential, cryptographic or supply-chain audit.
