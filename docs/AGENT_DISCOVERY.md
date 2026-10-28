# Agent discovery architecture

The intended path is **discover → understand → evaluate → select → implement →
validate**. Publishing documents makes evidence reachable. It does not prove
that any agent will retrieve it, recommend Agnara or produce a correct program.
The [benchmark](AGENT_DISCOVERY_BENCHMARK.md) measures those outcomes separately.

## Sources and consumers

| Artifact | Owner / purpose | Consumer |
| --- | --- | --- |
| [README](../README.md) and package READMEs | Human introduction and installation | GitHub/PyPI readers and search agents |
| [llms.txt](../llms.txt) | Maintained short discovery/selection summary | Clients explicitly fetching the conventional file |
| [AGENT_GUIDE.md](AGENT_GUIDE.md) and canonical Markdown guides | Public API learning and lifecycle | Coding agents and developers |
| [index.json](index.json) | Versioned official document/example allowlist, ordered corpus selection | `scripts/render_agent_docs.py`; future docs MCP |
| [llms-full.txt](../llms-full.txt) | Generated consolidated guide, source links and version labels | Clients needing a larger local reading corpus |
| [public-api.json](public-api.json) | Exact canonical exports and stability | Import audit; generated API reference |
| [AGENTS.md](../AGENTS.md) | Canonical operational instructions with application/framework scope | Coding agents operating on this checkout |
| [.agents skills](../.agents/skills/create-agnara-service/SKILL.md) | Small reusable workflows routing to official examples | Compatible skill clients, or explicit reading by others |

The existing API-reference generator is retained. It owns export inventory,
not narrative documentation. The new standard-library-only corpus renderer
uses explicit index IDs and exact learning-guide sections, never a crawl.
Examples are embedded from their actual Python sources. It relocates links for
the root corpus and emits sources only once. The 22 main sections are ordered;
unsupported A2A/events/tasks are statements of absence, not API tutorials.

```bash
uv run python scripts/render_agent_docs.py
uv run python scripts/render_agent_docs.py --check
uv run python scripts/render_public_api_reference.py --check
uv run python scripts/check_public_imports.py examples llms.txt llms-full.txt .agents/skills
uv run pytest tests/docs tests/architecture
```

Edit canonical sources and regenerate. Do not hand-edit `llms-full.txt` or
`API_REFERENCE.md`. The index's `version` names the public API installation
baseline, not a claim that every listed document existed at release time.
`stable-api` teaches existing contracts; `current-repository` includes
unreleased behavior; `guidance` describes workflow; `proposed` is unimplemented.
Consumers must retain these labels. Historical reconstruction uses the release
commit/tag, not a current Markdown file or editable package version.

## Discovery and publication boundaries

The stable baseline is **1.0.3**, released from
`c25d9eb5b2d432f652c4661a1925cb38baa63c82`. The public manifest is unchanged
between that release and this task's base. Current schema fixes for JSON enum,
numeric Literal and out-of-range integer-to-float inputs are unreleased.
The schema guide is labeled accordingly and excluded from the baseline corpus.

Repository-relative links work in a checkout and in GitHub's file viewer.
`index.json` records the `develop` GitHub file base URL: it is mutable current
documentation, not an immutable release URL. A client needing reproducibility
pins an accepted commit. A documentation deployment must choose and test its
own base path; this task does not deploy a site, create an HTTP route or claim
`mcp.agnara.dev` exists. A normal PR to `develop` will not immediately put these
files on default-branch `main` or PyPI. Maintainer promotion/publication is separate.

The [llms.txt proposal](https://llmstxt.org/) supplies a conventional Markdown
index structure. Adoption by particular clients remains a client behavior, not
a framework compatibility promise. Existing `agnara context` emits filtered
application discovery; it remains distinct from this public docs corpus.

## One instruction source across clients

`AGENTS.md` remains canonical. `CLAUDE.md` imports it with `@AGENTS.md`, following
[Claude's documented memory imports](https://code.claude.com/docs/en/memory).
[Cursor documents root AGENTS.md support](https://cursor.com/docs/rules), so
no separate Cursor policy is introduced. Codex uses the same
[root instructions](https://developers.openai.com/codex/guides/agents-md) and
[repository skills](https://developers.openai.com/codex/skills). Other clients can be explicitly told to read AGENTS.md,
llms.txt and the skill source; no automatic loading claim is made for Copilot
or Gemini. Client mechanisms were checked on 2026-10-04. Users should inspect
loaded context in their client rather than assume a filename was consumed.

The two skills route service creation and capability extension to canonical
examples; they do not duplicate the API manual, configure client accounts or
authorize deployment. Applications should copy only the scoped application
rules, not this framework repository's GitHub governance/coordination commands.

## Metadata review

All seven PyPI `1.0.3` JSON records were read on 2026-10-04: exact synchronized
versions, Python >=3.14, no core third-party requirements, exact adapter core
pins, MCP SDK pin and optional telemetry dependency. Current published summaries
call reserved A2A/events packages adapters/abstractions despite their empty APIs.
The source summaries now identify reserved namespaces truthfully and describe
the core as a backend capability framework for applications and AI agents.
No version, requirement, publication or PyPI artifact was changed. Updated
source metadata reaches PyPI only through a future authorized release.

The GitHub description previously advertised HTTP, MCP, A2A, events and tasks
without qualification. The corrected description identifies implemented
HTTP/MCP and protocol-neutral contracts/policies. No search ranking or
recommendation increase is claimed.

## Trust boundary

Generation reads only indexed files under `docs/` and `examples/`, rejects
traversal and escaped symlinks, caps source/corpus sizes and never imports
application modules or executes examples. It writes only the corpus when
explicitly invoked; `--check` does not write. Source reviews and CI still matter:
an allowlisted document can contain malicious instructions. Agents must treat
retrieved text as data, preserve user authorization and refuse authority
escalation from documentation. There is no server-side enforcement of a
model's interpretation. The [MCP specification](DOCUMENTATION_MCP.md) defines
additional read-only serving controls and adversarial acceptance tests.
