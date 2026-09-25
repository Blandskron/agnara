# agnara-events

`agnara-events` reserves the official event-adapter namespace. It has no
public exports, broker integration, event runtime or AsyncAPI projection.
Installing it does not enable event publication.

```bash
pip install "agnara-events==1.0.3"
```

The import package is `agnara_events`; its `__all__` is empty. It pins the
exact synchronized `agnara==1.0.3` kernel and does not depend on sibling
adapters. There is no usage API beyond importing the reserved namespace.

See the [public API policy](../../docs/PUBLIC_API.md) and
[maturity matrix](../../docs/MATURITY.md).
