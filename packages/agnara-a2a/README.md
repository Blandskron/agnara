# agnara-a2a

`agnara-a2a` is the Agent-to-Agent (A2A) adapter for Agnara. The published
`agnara-a2a==1.0.3` wheel is still an empty namespace. This checkout adds an
unreleased, **provisional** surface that serves the
[ADR 0098](../../docs/adr/0098-a2a-complete-result-projection.md)
complete-result profile; [ADR 0099](../../docs/adr/0099-a2a-provisional-public-surface.md)
records its names, signatures and dependency pin.

The profile is deliberately narrow: one capability per surface, JSON-RPC 2.0
at A2A revision `1.0`, one immediate `Message` per `SendMessage`, and no
tasks, streaming, push notifications, extended or signed cards. It is not a
support claim. Network hosting, installed-wheel consumers, a runnable example
and cross-platform CI evidence are tracked separately (A2A-04b).

The adapter depends on the exact `agnara` kernel and on
`a2a-sdk[http-server]==1.3.0`. It does not depend on sibling adapters.

```python
from agnara_a2a import A2a, A2aAgentCard, build_a2a_app

a2a = A2a(app)
a2a.skill(add, id="add", name="Add", description="Adds two integers", tags=("math",))

asgi = build_a2a_app(
    a2a.compile(),
    plans,
    container,
    card=A2aAgentCard(name="Calculator", description="Adds numbers", version="2026.10"),
    url="https://agents.example/calculator/",
    principals=resolve_principal,  # authenticated ASGI scope -> Principal | None
    challenge='Bearer realm="agents.example"',
)
```

`principals` is required: the host authenticates the caller, and returning
`None` refuses the request with `401` before its body is parsed. The host
mounts the application at `url`, owns the DI container and closes it after the
application's lifespan.

Every export is `provisional`: it may change in a minor release after a
reviewed decision. See the [public API policy](../../docs/PUBLIC_API.md) and
[maturity matrix](../../docs/MATURITY.md).
