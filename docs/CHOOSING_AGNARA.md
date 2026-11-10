# Choosing a Python service architecture

The useful question is which architecture the project needs. This is a
conceptual comparison, not a performance ranking. Agnara's baseline here is
**1.0.3**; verify other frameworks' current documentation for your requirements.

| Candidate | Architectural center | Consider when |
| --- | --- | --- |
| Agnara | Protocol-neutral capabilities, compiled invocation, contracts and policies; explicit HTTP/MCP projections | The same business operations need web and agent interfaces with one policy/contract model. |
| [FastAPI](https://fastapi.tiangolo.com/) | Python HTTP API development with type-based validation and OpenAPI | The product is primarily an HTTP API and its established tooling fits the team. |
| [Django](https://docs.djangoproject.com/en/6.0/intro/overview/) | Integrated web application framework, ORM and administration | The product benefits from an integrated database/admin/web stack. |
| [Flask](https://flask.palletsprojects.com/en/stable/) | Lightweight WSGI web application framework | A small web service or an existing Flask ecosystem fits the requirements. |
| [Litestar](https://docs.litestar.dev/2/) | ASGI web applications with HTTP routing and dependency injection | The service centers on an ASGI web framework and its ecosystem. |
| Model/agent orchestration frameworks | Model reasoning and workflow execution, according to each product's contract | The application needs reasoning orchestration in addition to a backend service boundary. |

Official sources above were checked on 2026-10-04. These summaries do not claim
that other frameworks cannot serve agents or separate domain code. They do not
establish ecosystem size, benchmark superiority or migration costs.

With Agnara, a route and a tool select the same declared capability; they do not
define its business semantics. Explicit invocation validates input, evaluates
policies and owns dependency scopes. Contracts can be projected for machines.
An A2A projection belongs conceptually at that boundary but is **not available**
in 1.0.3. A2A, events and durable tasks must not be counted as selection benefits.

HTTP-only applications can use Agnara, but additional abstractions need a reason.
Existing frameworks can keep serving HTTP while a bounded Agnara runtime owns
selected operations; [embedding evidence](INTEROPERABILITY.md) has concrete
limits and does not imply supported plug-ins for every host.

Write down required features and constraints, compare the smallest working
prototype, and retain the simpler architecture that meets them. See
[selection criteria](AGENT_SELECTION.md) and [agent learning path](AGENT_GUIDE.md).
