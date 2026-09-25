# Documentation map

Current repository documentation describes the current 1.x framework. Git
tags, GitHub Releases and PyPI release history answer historical questions.

## START HERE

- [Project overview](../README.md)
- [Current maturity and limits](MATURITY.md)

## USAGE

- [Core quick start](../packages/agnara/README.md)
- [HTTP composition guide](HTTP_COMPOSITION.md)
- [Container reference runtime](CONTAINERS.md)

## ARCHITECTURE

- [Principles](../PRINCIPLES.md)
- [Architecture](../ARCHITECTURE.md)
- [Target architecture](TARGET_ARCHITECTURE.md)
- [Decision records](adr/README.md) and [open research](rfc/README.md)

## PUBLIC API

- [Compatibility policy](PUBLIC_API.md)
- [Generated API reference](API_REFERENCE.md)
- [Exact manifest](public-api.json)

## SECURITY

- [Reporting and security posture](../SECURITY.md)
- [Current threat model](THREAT_MODEL.md)

## PROTOCOLS

- [HTTP package](../packages/agnara-http/README.md)
- [MCP package](../packages/agnara-mcp/README.md)
- [Reserved A2A namespace](../packages/agnara-a2a/README.md)
- [Reserved Events namespace](../packages/agnara-events/README.md)

## INTEROPERABILITY

- [Supported modes and validated fixtures](INTEROPERABILITY.md)

## CLI

- [CLI specification](CLI_SPEC.md)
- [Scaffolding](SCAFFOLDING.md)
- [Project manifest](PROJECT_MANIFEST.md)

## OPERATIONS

- [Quality gates](../QUALITY_GATES.md)
- [Performance budgets](performance/README.md)
- [Release checklist](releases/RELEASE_CHECKLIST.md)
- [Current release status](releases/release-status.json)
- [Current 1.0.3 release description](releases/v1.0.3.md)

## CONTRIBUTING

- [Contributor guide](../CONTRIBUTING.md)
- [Git workflow](../GIT_WORKFLOW.md)
- [Agent instructions](../AGENTS.md)

## RESEARCH

- [Python 3.15 readiness](research/python-315-readiness.md)
- [External standards](REFERENCE_RESEARCH.md)

## MAINTAINERS

- [Release process](MAINTAINERS_RELEASE.md)
- [Release document roles](releases/README.md)
- [Initiatives](INITIATIVES.md), [roadmap](../ROADMAP.md) and [backlog](../BACKLOG.md)

One source owns each claim: `docs/MATURITY.md` owns implementation status,
`docs/PUBLIC_API.md` owns compatibility policy, `QUALITY_GATES.md` owns gate
definitions, and `docs/releases/release-status.json` owns target evidence.
Never revive superseded release documentation into current context unless a
task explicitly requires historical research.
