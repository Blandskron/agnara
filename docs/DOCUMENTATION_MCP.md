# Read-only documentation MCP: implementation specification

Status: **specified, not implemented or deployed**. Tracking:
[Issue #559](https://github.com/Blandskron/agnara/issues/559).
`mcp.agnara.dev` is a conceptual host name only;
no DNS ownership, TLS, server or endpoint is claimed. This design supplements
files; clients can use [llms.txt](../llms.txt) without MCP.

## Scope and ownership

Implement repository tooling in a separate documentation service directory,
not the core runtime or package imports. Start with local stdio for a pinned
MCP SDK host and an explicit checked-out documentation snapshot. The maintainer
chooses any remote transport/domain later, after resource/auth/rate-limit review.
Do not add a dependency to `agnara` or change its capability registry.

The service loads [index.json](index.json), canonical Markdown/example files
and the governed [public manifest](public-api.json) from one immutable accepted
commit. It validates the entire corpus at startup and builds a deterministic
in-memory lexical search index. No crawling, URLs supplied by clients, arbitrary
file paths, app imports, reflection, subprocesses, code execution or repository
writes are permitted. It never reads AGENTS/client configuration or runtime
discovery exports as API authority.

## Common response and errors

Every tool returns JSON structured content and a matching JSON text block:

```json
{
  "schema_version": 1,
  "documentation_version": "1.0.3",
  "source_commit": "<accepted immutable commit>",
  "release_commit": "c25d9eb5b2d432f652c4661a1925cb38baa63c82",
  "stability": "stable-api",
  "source_path": "docs/AGENT_GUIDE.md",
  "source_sha256": "<content hash>",
  "source_url": "https://github.com/Blandskron/agnara/blob/<commit>/docs/AGENT_GUIDE.md",
  "content": "<requested data>",
  "truncated": false
}
```

Schema version and content hash describe provenance, not authority or model
trust. Always preserve `current-repository` and `proposed` labels; a version
match must not imply unreleased fixes shipped. Default baseline requests exclude
those entries unless explicitly requested. Unknown versions never fall forward
to latest. Use transport invalid-parameters errors for malformed arguments;
bounded redacted tool errors for `unsupported_version`, `unknown_document`,
`unknown_export`, `stale_snapshot` and `size_limit`. No filesystem diagnostics,
credential strings or exception traces enter client errors.

## Tools

All input schemas set `additionalProperties: false`; `version` is required
and initially accepts exactly `"1.0.3"`. No tool takes a path or URL.

| Tool | Arguments | Result |
| --- | --- | --- |
| `get_version` | `version` | Version, source/release commits, corpus hash, supported versions, schema version; clearly distinguish API baseline and document revision. |
| `search_docs` | `version`, `query` (1–256 characters), optional `topic` from indexed topics, `limit` (1–10, default 5), `include_nonbaseline` (default false) | At most 10 indexed ID/title/topic/stability/source URL/snippet hits. Casefolded token intersection with deterministic ID tie-break; no semantic superiority claim. |
| `read_doc` | `version`, `document_id` from startup allowlist, `offset` (nonnegative character index, default 0), `length` (1–12000, default 6000), `include_nonbaseline` (default false) | Exact canonical Markdown slice, total length and next offset; no synthesized instructions or interpretation. Python/JSON entries go through their dedicated tools. |
| `get_example` | `version`, `example_id` whose indexed path ends in `.py` | Exact source text as data, source hash, associated guide/test IDs if recorded. Never run it. Fail if it exceeds the response cap. |
| `get_api_reference` | `version`, `module` (governed module), optional `name` (governed export) | Exact manifest classification and canonical source reference. It is an export inventory, not inferred signatures. Include guidance to read executable examples for call syntax. |

Maximum serialized response: 32 KiB; search snippets: 400 characters per hit;
source size: 100 KiB; total loaded corpus: 2 MiB. Reject over-budget startup
instead of serving a partial inconsistent snapshot. Bound simultaneous requests
to 8 and require host cancellation/timeout handling. Remote serving must choose
per-client limits and log only tool/ID/timing/error categories, never query text,
tokens or content. Stdio testing needs no claim of OAuth or remote support.

## Security acceptance criteria

1. Startup copies exact allowlisted bytes from a resolved root. Reject absolute,
   traversal, UNC, URL, symlink/reparse-point escape and unindexed paths; reject
   duplicate IDs, unknown schema, mixed versions and hash mismatch. Once loaded,
   responses use the frozen in-memory snapshot, preventing later filesystem swaps.
2. Inputs are IDs/enums, never expressions, code, paths or URLs. No shell/eval,
   imports of examples, network fetch or link following. Sentinel files outside
   the allowlist remain unread; queries cause no filesystem writes.
3. Treat document text as untrusted data. A fixture containing “ignore previous
   instructions”, a malicious link or a secret-like string cannot expand the
   allowlist or invoke other tools. Review source snapshots for real secrets
   before deployment; an allowlist is not a secret scanner. Tool descriptions
   tell clients that returned text cannot authorize actions.
4. Exercise malformed/overlong requests, unknown IDs/modules/names/versions,
   corrupted startup manifests, bounded search, deterministic ordering, UTF-8
   pagination, output size, cancellation and simultaneous client isolation.
5. Test protocol initialize/list/call exchanges with the pinned official client;
   verify exact response provenance, stale-hash refusal and redacted errors.
6. No documented remote endpoint until maintainers verify deployment, DNS/TLS,
   public-data review, chosen protocol subset, limits and actual client access.

## Delivery plan

Phase 1: corpus validator, frozen loader, deterministic search and five local
tools with unit/adversarial/official-client tests, a stdio launch command and
tested setup instructions. Keep generated corpus optional and read-only.
Phase 2: a separate maintainer-reviewed deployment Issue; choose host, remote
transport, TLS and observability with an operational owner and rollback. Static
file publication should precede or accompany remote MCP. Future multi-version
support selects separate immutable snapshots, never current checkout aliases.

The full server plus deployment requires operational choices outside this
documentation change. The prepared follow-up Issue owns implementation; this
specification meets the current task's explicit specification alternative.
No security guarantee above is described as implemented server behavior.
