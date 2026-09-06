# ADR 0050 — Exporting OpenAPI Without Importing an Adapter

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #198 (E8.7)

## Context

E8.7 asks for `agnara schema openapi` over "the same OpenAPI projection served
by `agnara-http`". The direct implementation is forbidden twice over:
`agnara-cli` must not import a sibling adapter (`ARCHITECTURE.md` sections 3
and 4, enforced by an architecture test), and core must not depend on OpenAPI
tooling (`AGENTS.md`).

That is not merely a rule to route around. A second projection living in the
CLI could disagree with the one an HTTP surface serves — a different version, a
different set of published operations, a description the projection withheld —
and nobody would notice until a client trusted the wrong document.

## Decision

The CLI exports the document the composition already produced. It does not
project one.

`agnara schema openapi MODULE:ATTRIBUTE` resolves an attribute the user's own
module exposes, and reads it structurally: the serialized bytes an HTTP surface
would serve, the mapping those bytes came from, or a zero-argument callable
returning either. The user's module imports `agnara-http`; the CLI stays on the
other side of the boundary.

**When the target supplies bytes, they are emitted unchanged.** The export is
byte-identical to what is served, not merely equivalent to it. Re-serializing
would silently normalize whatever the projection chose, and the difference
would be invisible in a diff of parsed documents.

**When the target supplies a mapping, the CLI serializes it with the same
arguments `_serialize_openapi` uses** — compact, key-sorted, UTF-8, no NaN,
no ASCII escaping. Those arguments are duplicated rather than imported, which
is a promise; `tests/integration/test_openapi_export.py` keeps it one by
projecting the same application, serializing the mapping through the CLI and
the bytes through the adapter, and asserting the two are equal.

**The target is validated as an OpenAPI document**: a JSON object with a
non-empty string `openapi` version. That is deliberately shallow. Deeper
validation would be the CLI forming its own opinion about a contract it did
not produce, and E6.11 already owns structural conformance.

`--output FILE` writes the document and prints nothing, and refuses to replace
an existing file without `--overwrite`. `--pretty` indents for a human reader
and says in its own help text that the result is no longer byte-identical to
what a server sends.

The entry point now accepts `str | bytes | None` from a handler. Bytes go to
`sys.stdout.buffer` unchanged: a document another surface already serialized
must reach a pipe exactly as that surface would send it, and encoding it
through the text layer would let the platform's newline translation rewrite
it. `None` means the command produced no stdout, as when it wrote a file.

`resolve_attribute` is the generic half of target resolution, split out of
`resolve_target`. A command that needs an application narrows the result
itself; this one cannot narrow it to a type at all, because the type belongs
to a package it must not import.

## Alternatives

- Import `agnara_http` from `agnara-cli`: forbidden by the architecture, and
  it would make the CLI carry an HTTP dependency to export a document.
- Move the projection into core: forbidden — core must not depend on OpenAPI
  tooling — and it would make an HTTP contract a kernel concern.
- Rebuild the document from the introspection snapshot: rejected. RFC 0003 is
  explicit that inspection must not infer its model from OpenAPI, and the
  inverse is worse: the snapshot has no HTTP exposures, so a document built
  from it would describe a different application.
- Define a document-provider protocol in core: rejected because a protocol
  named around OpenAPI is an OpenAPI concept in the kernel regardless of
  whether it imports one.
- Accept only bytes: rejected because a composition that keeps the mapping and
  serializes at request time is legitimate, and refusing it would push
  composers toward keeping bytes they do not otherwise need.
- Re-serialize bytes for consistency: rejected. Byte-identity to the served
  document is the property worth having, and normalization would destroy it
  while looking like a no-op.

## Evidence and limits

`tests/cli/test_schema.py` covers exact byte emission, mapping serialization,
callable targets, non-ASCII, `--pretty`, `--output` with and without
`--overwrite`, an unwritable destination, seven ways a target can fail to be
an OpenAPI document, a producer that raises, an absent attribute, the usage
exit code, and an AST check that the export module imports no adapter.
`tests/integration/test_openapi_export.py` projects a real application through
`agnara-http` and asserts the CLI's export equals the adapter's bytes, from
both the bytes and the mapping.

Limits: no YAML, no validation beyond the document being a JSON object with a
version, no `agnara.toml` discovery of a default target, and no `agnara docs`.
The CLI cannot tell whether the document it exports is the one a running
server actually serves — only that it is the one the named attribute holds.
