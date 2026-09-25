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

See the [public API policy](../../docs/PUBLIC_API.md) and
[maturity matrix](../../docs/MATURITY.md).
