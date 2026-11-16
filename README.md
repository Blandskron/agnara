# Agnara

Agnara is a Python 3.14+ capability runtime. Define a business operation
once, then call it from Python or expose it through HTTP and MCP. The
standard-library kernel compiles contracts, policies and dependencies before
invocation.

[Manual de referencia de Agnara 1.0.4](index.html) ·
[Release 1.0.4](https://github.com/Blandskron/agnara/releases/tag/v1.0.4)

```bash
python -m pip install "agnara==1.0.4"
```

Run the [minimal capability](examples/minimal_capability.py) or see the
[same capability over Python, HTTP and MCP](examples/http_mcp.py). The
[example index](examples/README.md) links each runnable guide and its tests.
Use synchronized package versions when adding adapters.

| I need | Start here |
| --- | --- |
| Public imports and stability | [API policy](docs/PUBLIC_API.md) and [manifest](docs/public-api.json) |
| Supported surfaces and limits | [Maturity](docs/MATURITY.md) |
| Coding-agent resources | [llms.txt](llms.txt) and [machine index](docs/index.json) |
| Architecture and current work | [Architecture](ARCHITECTURE.md) and [backlog](BACKLOG.md) |
| Contributing | [Contribution guide](CONTRIBUTING.md), [quality gates](QUALITY_GATES.md) and [agent instructions](AGENTS.md) |
| Reporting a vulnerability | [Security policy](SECURITY.md) |

The manual documents the published tag. Checkout changes are recorded in
[the changelog](CHANGELOG.md). To serve the manual with GitHub Pages, select
**Deploy from a branch → develop → /(root)** after the manual reaches `develop`.

Apache-2.0. See [LICENSE](LICENSE).
