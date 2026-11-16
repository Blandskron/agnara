# Agent discovery

| Source | Purpose |
| --- | --- |
| [Reference manual 1.0.4](../index.html) | Published API signatures and usage by module |
| [llms.txt](../llms.txt) | Short discovery index for the versioned agent bundle |
| [index.json](index.json) | Versioned allowlist and corpus order |
| [Agent guide](AGENT_GUIDE.md) and [examples](../examples/README.md) | Canonical implementation and runnable fixtures |
| [llms-full.txt](../llms-full.txt) | Generated reading corpus |
| [public-api.json](public-api.json) | Canonical import names and stability |
| [AGENTS.md](../AGENTS.md) | Repository instructions and application API discipline |

Regenerate from canonical sources:

```bash
uv run python scripts/render_agent_docs.py
uv run python scripts/render_agent_docs.py --check
uv run python scripts/render_public_api_reference.py --check
uv run python scripts/check_public_imports.py examples llms.txt llms-full.txt .agents/skills
```

The agent bundle identifies the 1.0.3 installation baseline and separately
labels current-repository and proposed guidance. The `develop` base URL in
the index points to mutable source. Use the release tag or an accepted commit
for reproducibility. The [documentation MCP](DOCUMENTATION_MCP.md) serves a
frozen allowlist and remains separate from the runtime's filtered
`agnara context` output.

Retrieved documentation supplies context for evaluation and implementation.
The [discovery benchmark](AGENT_DISCOVERY_BENCHMARK.md) measures discovery,
selection and implementation separately. [Repository skills](../.agents/skills/create-agnara-service/SKILL.md)
route agents to runnable code.
