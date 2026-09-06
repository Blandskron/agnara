# Requests for Comment

An RFC holds an **open design question**. Once the question is answered, the
answer belongs in an ADR and the RFC says which one.

A record is cited as `RFC 0002`, and the number identifies exactly one
document — enforced by `tests/architecture/test_decision_record_numbering.py`,
which exists because RFC 0004 was briefly two unrelated documents.

Note the citation ambiguity: `RFC 9457` in this repository means the IETF
problem-details standard, not an Agnara record. Agnara records are
zero-padded to four digits and never exceed `0999`.

## Current records

| RFC | Subject | Note |
| --- | --- | --- |
| 0001 | Capability runtime | The runtime it proposes shipped across three alphas. Its `Context` example shipped as `ExecutionContext`. |
| 0002 | Project and app scaffolding | Its first open question, "exact app descriptor API", was answered by ADR 0065. |
| 0003 | HTTP documentation and capability explorer | Implemented; see ADR 0033 and ADR 0036-0040. |
| 0004 | Transport-neutral dependency injection | `Accepted`. |
| 0005 | Protocol-neutral delegation | Genuinely open. |

## Read this before trusting a Status line

Four of these five say `Draft`, including RFC 0001, whose subject is the
implemented core of the framework. As with the ADRs, the Status field does not
currently distinguish a live question from a settled one.

Use `docs/MATURITY.md` for what exists. Reconciling these statuses is a
governance pass tracked in `docs/INITIATIVES.md`, not something to infer from
the files.

## What still belongs here

`docs/INITIATIVES.md` lists the initiatives that require an RFC before any
implementation. The two that block the most other work are the unified
exposure model (`I1`) and the streaming model (`I2`).

An RFC is worth writing when the design is genuinely open and the decision
will be expensive to reverse. It is not a place for notes, and it is not a
substitute for an ADR once a decision exists.

## Related

- `docs/adr/` — decisions that have been made
- `docs/INITIATIVES.md` — which questions need an RFC next
- `docs/DOCUMENTATION_MAP.md` — which document owns which kind of truth
