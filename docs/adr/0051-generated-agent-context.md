# ADR 0051 — Generated Agent Context

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #200 (E8.13)

## Context

Agnara's premise is that agents are first-class consumers. Everything built so
far serves that indirectly: a model can read `agnara inspect --json` or the
discovery endpoint, but both are shaped for a program. An agent deciding which
capability to call spends its context window parsing a structure rather than
understanding capabilities.

E8.13 asks for generated agent context. The risk is that such a document reads
as an offer. A model given a list of capabilities will reasonably assume it may
call them, which is precisely the inference ADR 0008 forbids and precisely the
inference no amount of filtering prevents — a capability can be visible and
still be denied at invocation.

## Decision

`agnara context TARGET` renders the filtered snapshot as Markdown, from the
shared view `agnara inspect` and `agnara graph` already use. There is no second
discovery path, so it cannot describe a capability those commands would hide
from the same viewer.

**The document states what it is not.** Every rendering, including an empty
one, carries the sentence that seeing a capability is not permission to invoke
it and that every invocation is authorized independently at call time. It is in
the empty rendering too, because a model must not read "no capabilities listed"
as "nothing is restricted".

**A withheld field is named, never defaulted.** Risk, confirmation and
idempotency always carry a value in the descriptor, so an unpublished one
arrives as the declared default. Printing it would tell a model "risk: low"
about a capability whose real risk was withheld — the single most
consequential thing it could be wrong about. The renderer takes the visibility
decision, omits what was not published, and lists the withheld field names once
under a "This view is partial" line so absence is legible as withholding rather
than as absence of the fact.

**Provenance travels with the document.** The snapshot's format and version
appear in the header, so a stale context pasted into a prompt six months later
is identifiable as stale rather than merely wrong.

Output is deterministic and carries no ANSI. `--output` writes a file and
refuses to replace one without `--overwrite`, matching
`agnara schema openapi`; the two now share one writer, so the refusal reads
the same whichever command produced it.

This is not `llms.txt`. E8.12 is still research, and the backlog is explicit
that `llms.txt` must not be treated as an authorization or canonical discovery
format. This command produces a document at a path the operator chooses, for a
prompt the operator assembles.

## Alternatives

- Emit JSON shaped for a model: rejected. `agnara inspect --json` already
  exists; the value here is prose a model reads without parsing.
- Reuse the `agnara inspect` text renderer: rejected because its audience is a
  terminal — dense, indented, no explanation of what the document is or is not.
- Render from the snapshot alone: rejected for the same reason ADR 0047 gives.
  Without the visibility decision the renderer cannot tell a withheld risk from
  a declared `low` one, and would assert the wrong one confidently.
- Omit the "not authorization" statement as obvious: rejected. It is obvious to
  the operator and not to the model, and the model is the reader.
- Emit an `llms.txt` at a well-known path: rejected. E8.12 has not concluded,
  and a well-known path invites treating the document as canonical discovery.
- Include dependency and provider detail by default: rejected. It is
  implementation detail a caller cannot act on, and it is what `--visibility`
  already governs for anyone who wants it.

## Evidence and limits

`tests/cli/test_context.py` covers the rendered content, the safety statement
including in an empty result, provenance, a withheld field being named rather
than defaulted, "no inputs" appearing only when inputs are published,
determinism, parity with `agnara inspect` for one viewer, `--output` with and
without `--overwrite`, the shared failure contract, and that every view command
offers the same visibility controls.

Limits: no `llms.txt`, no HTTP serving, no prompt template, no model-specific
format, no token budgeting, and no claim that the document is a security
boundary. Exposures are still absent from a CLI-built snapshot, so the
"Reachable through" line only appears once a composition contributes them.
