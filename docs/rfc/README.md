# Requests for Comment

RFCs hold design questions. An answered question points to its ADR; current
implementation status is owned by `docs/MATURITY.md`.

| RFC | Subject | Current state |
| --- | --- | --- |
| 0001 | Capability runtime | Implemented; architecture and runtime tests are authoritative. |
| 0002 | Project and app scaffolding | Implemented; ADR 0065 governs app namespace. |
| 0003 | HTTP documentation and Explorer | Implemented; ADR 0033 and ADRs 0036–0040 govern the surfaces. |
| 0004 | Transport-neutral DI | Accepted design; current shipped subset is in `docs/MATURITY.md`. |
| 0005 | Protocol-neutral delegation | Open research; no delegation support is claimed. |
| 0006 | Unified exposure model | Implemented by ADR 0070 and ADR 0071. |
| 0007 | Distribution version identity | Implemented by ADR 0069 and ADR 0095. |
| 0008 | Framework embedding | Host boundary implemented by ADR 0094; streaming, delegation and cross-application questions remain open. |
| 0009 | Protocol-neutral streaming | Kernel and HTTP SSE implemented by ADR 0084 and ADR 0086; other projections require separate decisions. |

`RFC 9457` denotes the external IETF problem-details standard, not a local
record. Local RFC identifiers are zero-padded to four digits. Historical
release reconstruction belongs to Git tags and history, not current RFC text.
