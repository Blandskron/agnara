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

The **Lifecycle** column is the reviewed classification, not the file's own
`Status` line. `OPEN` means the question is still live. `IMPLEMENTED` means the
question was answered and built, and the record is retained because ADRs, code
and tests still cite its numbered sections as the normative statement of the
problem -- deleting it would break the decision chain that ADR 0069, ADR 0070
and ADR 0071 depend on.

| RFC | Subject | Lifecycle | Note |
| --- | --- | --- | --- |
| 0001 | Capability runtime | `IMPLEMENTED` | The runtime it proposes shipped across three alphas. Its `Context` example shipped as `ExecutionContext`. Cited by the core capability modules. |
| 0002 | Project and app scaffolding | `IMPLEMENTED` | Its first open question, "exact app descriptor API", was answered by ADR 0065. |
| 0003 | HTTP documentation and capability explorer | `IMPLEMENTED` | See ADR 0033 and ADR 0036-0040. The most heavily cited record in `agnara-http`. |
| 0004 | Transport-neutral dependency injection | `ACCEPTED` | `Accepted`; not yet fully implemented. |
| 0005 | Protocol-neutral delegation | `OPEN` | Genuinely open. Required by `I8` before any delegation work. |
| 0006 | Unified exposure model | `PARTLY OPEN` | Answered by ADR 0070 and implemented. Phase 3, the public composition API, is ADR 0071. |
| 0007 | Distribution version identity and dependency constraints | `IMPLEMENTED` | Answered by ADR 0069: exact synchronized pins plus `<target>.dev0` on `develop`. |
| 0008 | Framework embedding and ecosystem composition | `OPEN` | `Proposed`. Fifteen open questions; decides none. Implementation belongs to `1.0.0` per ADR 0068. |
| 0009 | Protocol-neutral streaming model | `PARTLY OPEN` | Q1-Q9 answered for the kernel by ADR 0084; ADR 0086 adds the implemented declared output contract. Every transport projection is still open. |

An `IMPLEMENTED` record is not historical noise and is not a candidate for
deletion while anything still cites it. Before removing one, check
`docs/adr/`, `packages/` and `tests/` for citations of its number, and move
whatever they rely on into the ADR that answers it.

## Read this before trusting a Status line

Four of these eight say `Draft`, including RFC 0001, whose subject is the
implemented core of the framework. As with the ADRs, the Status field does not
currently distinguish a live question from a settled one.

Use `docs/MATURITY.md` for what exists. Reconciling these statuses is a
governance pass tracked in `docs/INITIATIVES.md`, not something to infer from
the files.

## What still belongs here

`docs/INITIATIVES.md` lists the initiatives that require an RFC before any
implementation. The unified exposure model (`I1`) and the kernel half of the
streaming model (`I2`, answered by ADR 0084 and ADR 0086) have both been
answered and built. What RFC 0009 still owes is one projection record per
transport.

RFC 0008 is deliberately the largest open record in the directory and answers
nothing. Several of its questions depend on I1, I2, I3, I8 and I10; writing an
answer before those exist would be inventing an implementation rather than
recording a decision.

An RFC is worth writing when the design is genuinely open and the decision
will be expensive to reverse. It is not a place for notes, and it is not a
substitute for an ADR once a decision exists.

## Related

- `docs/adr/` — decisions that have been made
- `docs/INITIATIVES.md` — which questions need an RFC next
- `docs/DOCUMENTATION_MAP.md` — which document owns which kind of truth
