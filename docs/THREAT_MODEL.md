# Threat Model — 0.1.0a4

What an attacker can reach in the surface `0.1.0a4` publishes, what Agnara
itself refuses, and what it does not attempt. It covers the a4-owned surface:
the ASGI/HTTP adapter, the MCP adapter, the policy pipeline, error mapping,
observability and the published distributions.

This is not the beta security program. There is no penetration test, no fuzzing
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
| No credential lives in the repository or in a built distribution | `tests/security/test_repository_secrets.py`, `scripts/check_distributions.py` |

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
| H-1 | P1 | Fixed. A JSON body nested beyond the decoder's stack raised `RecursionError` out of the dispatcher. 80 KB — well inside the 1 MiB default — was enough, from an unauthenticated client, before any capability ran. The dispatcher sent nothing and the ASGI server decided what the client and the operator's log received, bypassing the reviewed problem mapping and its redaction. Now a 400 naming the reason without echoing the body. |
| H-2 | P1 | Fixed. The same class at the other end: a value nested deeper than the interpreter can walk raised `RecursionError` out of response serialization, reachable by a capability that echoes an accepted-but-deep body. Now the existing last-resort redacted 500. |
| H-3 | P1 | **Open — recorded, not fixed.** `scopes=` on a capability is enforced over MCP and ignored over HTTP. See below. |
| H-4 | P2 | Fixed. `_read_body` bounded total bytes but not the number of events. An empty chunk moves `max_body_bytes` no closer to its limit, so a client sending them with `more_body` set held a worker open indefinitely and grew a list without bound. Empty events are now capped. |
| H-5 | P3 | Fixed. `request_timeout` was documented as a per-request deadline. It starts after binding, so it bounds execution and not how long a client may take to send a body. The documentation now says which. |

### H-3 — declared scopes are enforced on one transport only

`@app.capability(scopes={"records:read"})` compiles to metadata. `agnara-mcp`
turns that metadata into a core `ScopePolicy` and evaluates it before any
effect. `agnara-http` does not: the same capability, declared once, is
authorization-checked when reached as an MCP tool and runs unchecked when
reached over HTTP.

Both halves are recorded by `tests/security/test_trust_boundaries.py`, which
asserts the current behaviour on both transports so that a fix must change the
test deliberately rather than pass in silence.

This is not a bug in either adapter taken alone. ADR 0008 says metadata is
never authorization by itself, which is exactly why HTTP ignores it; the MCP
dispatcher documents the opposite reading for its own surface. The security
problem is the asymmetry: an author who declares a scope, sees it enforced
through an agent, and then publishes the same capability over HTTP loses the
check without any diagnostic.

For the release thesis — can Agnara be consumed as a framework from outside
this repository — this is the more serious half. HTTP is the surface an
application is most likely to expose publicly.

Resolving it is an architectural decision rather than an adapter patch, and it
has no safe default. Making core attach a `ScopePolicy` from declared scopes
would enforce the declaration everywhere, but the a4 HTTP surface authenticates
nobody, so every scoped capability would become permanently unreachable over
HTTP — a breaking change for any application relying on today's behaviour.
Making MCP stop enforcing it would remove a real check. Either direction needs
an ADR and the authentication design that `0.1.0a4` deliberately does not have.

Until then the honest statement for an application author is: **treat
`scopes=` as metadata, and attach an explicit policy for anything that must be
enforced over HTTP.**

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

`SECURITY.md` lists the agent threats the project intends to model. Their a4
status:

| Threat | a4 status |
| --- | --- |
| Confused deputy, over-broad delegated authority | Partially addressed. MCP maps a verified token to a principal through an application mapper and never trusts caller-supplied identity. H-3 is the gap. |
| Tool name and schema spoofing | Addressed. Names and schemas come from one frozen startup snapshot; discovery and invocation cannot disagree. |
| Approval bypass | Addressed for confirmation: no evidence channel exists on either transport, resumed calls are refused, and a missing verifier fails at startup. |
| Prompt and tool injection across trust boundaries | Not addressed. Agnara does not inspect argument content. |
| Automated destructive invocation, replay of non-idempotent operations | Not addressed. `risk`, `effects` and `idempotent` are metadata, and idempotency is not enforced. |
| Cross-tenant context leakage | Not applicable in a4: no tenant concept, and no per-request state is shared between invocations. |
| Unbounded tool recursion | Not addressed. Nothing bounds a capability invoking another. |
| SSRF through generic HTTP capabilities | Application's own concern; Agnara makes no outbound call. |

## 8. What this audit did not do

No fuzzing, no penetration test, no load or denial-of-service testing under
real concurrency, no dependency vulnerability scan (the repository configures
no such tool; the lockfile currency check is not one), no review of the
vendored documentation bundles' own code, no analysis of git history for
previously committed credentials, and no review of the A2A, events or CLI
packages, which `0.1.0a4` does not publish as part of this surface.
