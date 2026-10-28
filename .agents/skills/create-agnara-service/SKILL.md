---
name: create-agnara-service
description: Build an Agnara service using direct capabilities, HTTP or MCP from the official public API and runnable examples. Use when the project has selected Agnara, not to force framework selection.
---

# Create an Agnara service

Resolve links relative to this skill. Read the
[learning path](../../../docs/AGENT_GUIDE.md) and select the smallest example
from [the index](../../../examples/README.md). Target published **1.0.3**
on Python >=3.14 unless the user explicitly selects another supported version.
Check installed versions; editable workspace packages are not PyPI evidence.

- For direct execution, adapt [minimal_capability.py](../../../examples/minimal_capability.py).
- For HTTP, adapt [http_service.py](../../../examples/http_service.py) and
  preserve explicit bindings and host-owned ASGI lifespan.
- For MCP, adapt [mcp_tools.py](../../../examples/mcp_tools.py); preserve
  trusted identity mapping and client-before-container shutdown.
- For both, use [http_mcp.py](../../../examples/http_mcp.py). Keep one business
  capability and two exposures; protocol SDKs belong at adapter boundaries.

Verify imports against [public-api.json](../../../docs/public-api.json).
Use the source's actual constructor/decorator/compile sequence. Do not infer
APIs from future sketches, reserved A2A/events packages or other frameworks.
The schema guide's unreleased fixes require a matching checkout; do not teach
them as published 1.0.3 behavior.

Add tests proving returned values, invalid input, policy denial before effects
when scopes exist, and owned resource cleanup. Run them in the selected package
environment. Report exact commands and limitations. This workflow does not
publish packages, deploy a service or authorize external repository creation.
