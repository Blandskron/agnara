# Architecture Decision Records

One decision per file, numbered, never renumbered. A record is cited as
`ADR 0065` and the number identifies exactly one document —
`tests/architecture/test_decision_record_numbering.py` enforces that, after
RFC 0004 was briefly two different documents.

## Read this before trusting a Status line

Most older ADRs still say `Status: Proposed`, including records whose decisions
govern shipped code. ADR 0001 fixes the Python 3.14 baseline that CI enforces,
and ADR 0005 fixes the startup freeze the runtime implements. A smaller set
does explicitly say `Accepted`: ADR 0021, ADR 0068, ADR 0069, ADR 0073,
ADR 0081, ADR 0084 and ADR 0085.

An explicit `Accepted` status is meaningful, but an older `Proposed` status is
not reliable evidence that its decision is open or unused. Readers therefore
cannot infer implementation status from that field alone.

Until the maintainer runs a governance pass over these statuses, use
`docs/MATURITY.md` to find out what is actually implemented. That file is
verified against code and is checked by
`tests/architecture/test_documentation_consistency.py`.

This is recorded rather than fixed here because moving a record from
`Proposed` to `Accepted` is a governance act, not an editorial one. The
proposal is tracked with the documentation initiative in
`docs/INITIATIVES.md`.

## Intended vocabulary

| Status | Meaning |
| --- | --- |
| `Proposed` | Written, not yet accepted. |
| `Accepted` | Decided. The codebase is expected to comply. |
| `Superseded by ADR NNNN` | Replaced. Kept, because the history of a decision is part of it. |
| `Rejected` | Considered and declined, with the reasoning kept for the next person who has the idea. |

## Conventions

An ADR records a decision **after** it has been made. An open question belongs
in an RFC until it is answered; the RFC then names the ADR that answered it.

Most ADRs here record a technical decision. A few record a governance one —
ADR 0021 fixes how versions are chosen, ADR 0068 fixes which release owns
ecosystem interoperability. Both kinds bind, and both are recorded here rather
than in a planning document, because a planning document is rewritten and a
decision record is not.

A superseded ADR is never deleted or edited to match the new decision. The
reasoning that turned out to be wrong is the most useful part of the record.

Every ADR states its number in its own first heading, and cites the issue it
came from.

## Related

- `docs/rfc/` — open design questions, before a decision exists
- `docs/MATURITY.md` — what is implemented
- `docs/TARGET_ARCHITECTURE.md` — where the structure is going
- `docs/DOCUMENTATION_MAP.md` — which document owns which kind of truth
