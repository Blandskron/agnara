# agnara-a2a

`agnara-a2a` reserves the official Agent-to-Agent adapter namespace. It has no
public exports, Agent Card, task handling, streaming or A2A runtime. Installing
it does not enable an A2A endpoint.

```bash
pip install "agnara-a2a==1.0.3"
```

The import package is `agnara_a2a`; its `__all__` is empty. It pins the exact
synchronized `agnara==1.0.3` kernel and does not depend on sibling adapters.
There is no usage API beyond importing the reserved namespace. Protocol work
requires a separate reviewed contract and implementation.

[RFC 0010](../../docs/rfc/0010-a2a-initial-projection.md) compares candidate
first projections and defines a future feasibility gate. It is open research,
not a usage guide or an implementation/support commitment.
[ADR 0098](../../docs/adr/0098-a2a-complete-result-projection.md) proposes the
first profile's projection contract; it adds no API or runtime.

See the [public API policy](../../docs/PUBLIC_API.md) and
[maturity matrix](../../docs/MATURITY.md).
