# Read-only documentation MCP: implementation specification

Status: **local implementation; no remote deployment**. Tracking:
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

Repository tooling lives in `tools/documentation_mcp`; it never imports the
Agnara runtime. The official SDK and types are pinned to 2.1.1 in its
`requirements.txt`. The five tools are exercised through the official client,
including an actual stdio initialize/list/call exchange. These bounded tests
are evidence for this local subset, not complete protocol certification.

## Local setup and launch

Use Python >=3.14 and a clean documentation checkout from an accepted immutable
commit. Review that commit's corpus for publishable data before creating the
lock. The loader verifies byte hashes, not Git history or maintainer approval:
the operator must verify that the selected root contains the accepted commit's
exact files. Never label a modified working tree with its old commit SHA.
For byte reproducibility across platforms, use a Git archive extraction or a
checkout with `core.autocrlf=false`; the loader preserves UTF-8 bytes, including
line endings, and pagination counts decoded characters.

From this repository, install the existing development environment with
`uv sync`, or install only `tools/documentation_mcp/requirements.txt` into a
separate Python 3.14 environment. No Agnara distribution is required by the host.

Prepare the lock offline; replace the root and SHA with the reviewed snapshot.
`prepare` prints JSON to stdout and its SHA-256 to stderr and performs no writes.
Shell redirection is an explicit operator setup action. It does not belong to
the query service. Preserve the output bytes; use UTF-8 without a BOM or an
added newline. This Python setup example avoids shell encoding differences:

```python
from pathlib import Path
from tools.documentation_mcp.corpus import digest, make_lock

root = Path("/absolute/path/to/accepted-snapshot")
lock = make_lock(root, "<40-character accepted commit SHA>")
Path("snapshot.json").write_bytes(lock)
print(digest(lock))
```

Launch from the tooling repository with the same interpreter/environment:

```text
python -m tools.documentation_mcp serve --root /absolute/path/to/accepted-snapshot --lock /absolute/path/to/snapshot.json --lock-sha256 <printed SHA-256>
```

Configure a local MCP client with that Python executable as `command`, the
tokens after `python` as `args`, and the tooling repository as its working
directory. Stdio stdout carries protocol messages only. A refused snapshot
exits with a fixed redacted message on stderr. The host has no query logging.
Stop the client to close its owned stdio process.

The lock has schema version 1, documentation version, source and release
commits, and an exact path-to-SHA-256 map including `docs/index.json` itself.
Pin its digest separately in client configuration. Altering a source or lock
requires a new operator-reviewed snapshot and explicit digest change; it never
falls forward silently. An index entry is an allowlist grant, so the lock and
index are trusted setup inputs. Document bodies remain untrusted query data.
The corpus hash reported by `get_version` is the digest of this lock.

Startup rejects all symlinks and Windows reparse points within the root and
document paths, even links to other allowlisted files. Prepare snapshots in a
trusted directory: hash checking is integrity verification, not protection
against an attacker controlling the operator's setup process or directories.
No filesystem access occurs during queries, so later swaps cannot affect data.

Every full serialized MCP tool result, including its matching JSON text and
structured data, fits 32 KiB. A large Markdown page can return `size_limit`;
retry with a smaller `length`. Examples are returned whole or refused. Search
requires every casefolded word token, orders hits by document ID and reports
`truncated` when its limit omits hits. Punctuation-only queries return no hits.
There is no search cursor; Markdown uses character offsets and `next_offset`.
An offset beyond the document returns an empty final slice.

Unknown IDs/versions/exports return the specified fixed tool error categories;
wrong types, extra fields, unknown topics, invalid pagination and unknown tools
return redacted invalid-parameters protocol errors. Examples classified as
nonbaseline are excluded because `get_example` has no opt-in argument.
API results retain the manifest's per-export classifications exactly.

One event loop owns the server and its admission semaphore. At most eight
queries execute concurrently; a five-second deadline includes admission.
Cancellation propagates and releases admission slots. Queries are synchronous
bounded in-memory work after a cancellation checkpoint, without background tasks.
The response cap excludes the SDK's JSON-RPC envelope. The local SDK transport
owns parsing; these query limits are not a remote ingress/body-size policy.

Validation:

```text
uv run pytest tests/documentation_mcp tests/architecture
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

The symlink creation test skips on Windows hosts lacking that permission;
the loader's Windows reparse refusal is separately tested without requiring
privilege. Linux/macOS CI exercises the actual symbolic link fixture.
