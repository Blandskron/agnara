# Roadmap

The [maturity matrix](docs/MATURITY.md) (`docs/MATURITY.md`) records current behavior and support
boundaries. The [backlog](BACKLOG.md) orders the work, and GitHub Issues hold
its acceptance criteria and evidence.

## November 14, 2026 presentation

Show one business capability declared once, invoked directly and through HTTP
and MCP, with a visible trace and a reproducible CLI setup. Use the presentation
to show how the packages work together and where each protocol boundary sits.

| Window | Focus | Exit evidence |
| --- | --- | --- |
| Nov 3–8 | MCP interoperability first, followed by CLI adoption | Exercise one host-owned MCP transport with the pinned SDK. Rehearse the CLI setup and diagnostics in a clean project. |
| Nov 9–11 | A2A scope and rehearsal | Record the host and compatibility decision for the provisional complete-result profile. Rehearse the stable path from installed candidate wheels. |
| Nov 12–14 | Freeze the demo commit and rehearse | Record the exact commit, package source, versions and commands. Reserve the final window for regressions that block the demo. |

If the MCP transport experiment misses the freeze, demonstrate the verified
in-process SDK flow. Include A2A as an explicitly experimental segment only
if the pinned client and host path can be reproduced. Present Events through
its feasibility question and reserved namespace status.

The presentation may use candidate wheels from a reviewed `develop` commit.
Label them separately from the published 1.0.3 artifacts and keep support
claims within the evidence recorded for each package.

## After the presentation

Continue reference application and interoperability maintenance. Review
transport and diagnostics changes using the presentation evidence. Consider
new hosts, stores and protocol projections once their contracts, tests and
ownership are defined. The [initiatives index](docs/INITIATIVES.md) tracks the
longer-term programs.

Per maintainer direction on 2026-09-28, publication remains paused until
approximately March 2027, a planning reference. Work continues on `develop`
under `[Unreleased]`. Publication requires a separate maintainer decision
and release gates.
