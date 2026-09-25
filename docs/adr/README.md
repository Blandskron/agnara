# Architecture Decision Records

One decision per file, numbered and never renumbered. A record is cited as
`ADR 0065`; `tests/architecture/test_decision_record_numbering.py` enforces
unique numbers.

Most older ADRs still say `Proposed`, including some decisions implemented in
code. The following records explicitly declare `Accepted`: ADR 0023, ADR 0068,
ADR 0069, ADR 0073, ADR 0084, ADR 0085, ADR 0086, ADR 0087,
ADR 0088, ADR 0089, ADR 0091, ADR 0092, ADR 0093, ADR 0094 and ADR 0095.
The index and record statuses are checked together. `docs/MATURITY.md`, not an
ADR status alone, describes current implementation.

## Vocabulary

| Status | Meaning |
| --- | --- |
| `Proposed` | Written; status does not itself prove implementation or acceptance. |
| `Accepted` | Decided; the codebase is expected to comply. |
| `Superseded by ADR NNNN` | Replaced by a named decision. |
| `Rejected` | Considered and declined. |

An ADR records a technical or governance decision. An open question belongs
in an RFC. Current repository documentation describes the current framework;
use Git history, tags or GitHub Releases for historical reconstruction.

See [maturity](../MATURITY.md), [target architecture](../TARGET_ARCHITECTURE.md)
and the [documentation map](../DOCUMENTATION_MAP.md).
