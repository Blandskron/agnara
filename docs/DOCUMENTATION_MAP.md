# Documentation Map

## Canonical reading path

```text
README.md → VISION.md → ARCHITECTURE.md → ROADMAP.md → BACKLOG.md
```

The [README](../README.md) introduces the current product. The
[vision](../VISION.md) explains its long-term purpose. The
[architecture](../ARCHITECTURE.md) defines current invariants and package
boundaries. The [roadmap](../ROADMAP.md) owns provisional future programs. The
[backlog](../BACKLOG.md) contains only work still open.

## Other current references

| Question | Owner |
| --- | --- |
| Which subsystem is actually implemented? | `docs/MATURITY.md` |
| Which imports are supported and stable? | `docs/PUBLIC_API.md`, `docs/public-api.json`, `docs/API_REFERENCE.md` |
| Which rule constrains a design? | `PRINCIPLES.md`, `AGENTS.md` |
| How is quality measured? | `QUALITY_GATES.md` |
| How are vulnerabilities and releases handled? | `SECURITY.md`, `docs/MAINTAINERS_RELEASE.md` |
| How do CLI, project scaffolding and HTTP composition work? | `docs/CLI_SPEC.md`, `docs/SCAFFOLDING.md`, `docs/HTTP_COMPOSITION.md` |
| What is the Python 3.15 compatibility program? | `docs/research/python-315-readiness.md` |

The supported API reference and maturity table should be checked against code
and tests when edited. `docs/API_DESIGN.md` contains design examples; use
`docs/API_REFERENCE.md` for the supported public spelling.

## Historical evidence, not active plans

| Record | Why it remains |
| --- | --- |
| `docs/adr/` and `docs/rfc/` | Architectural decision and design provenance; individual examples may predate current APIs. |
| `docs/releases/`, `CHANGELOG.md`, `docs/MIGRATION_A8_TO_1_0.md` | Published release, security, migration and audit evidence. Pre-1.0 targets in these files are historical. |
| `docs/INITIATIVES.md`, `docs/TARGET_ARCHITECTURE.md` | Historical 1.0 construction plans. Current future work is in `ROADMAP.md`. |
| `docs/THREAT_MODEL.md`, `docs/INTEROPERABILITY.md` | Point-in-time 1.0 security and integration evidence. Revalidate before making a new release claim. |
| `experiments/` | Unshipped research, not product integrations. |

Do not turn a completed planning checkbox or an old release gate into a new
task without checking the current code and tests. ADRs/RFCs justify decisions;
they do not supersede the current API or roadmap. Keep historical evidence
reachable while removing it from the active onboarding path.

## Automated checks

`tests/architecture/test_documentation_consistency.py` verifies package and
public-name counts, status vocabulary, cited paths and decision records.
`tests/architecture/test_repository_encoding.py` guards UTF-8 text integrity.
