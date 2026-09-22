# Migrar de A8 a 1.0

Esta guía es para una aplicación que parte de la publicación sincronizada
`0.1.0a8` y se prepara para Agnara 1.0. No cambia el registro histórico de A8:
consulta `CHANGELOG.md` para saber qué se publicó entonces. La fuente exacta
del contrato 1.0 es `docs/public-api.json`, y `docs/PUBLIC_API.md` explica su
política de compatibilidad.

1.0 todavía es un candidato en este repositorio, no una instrucción para
instalar una versión inexistente. Valida una aplicación contra las ruedas del
candidato o, después de la publicación, contra el conjunto sincronizado 1.0.
No mezcles distribuciones ni conserves `0.1.0a8` como destino de compatibilidad.

## Cambios de API y de comportamiento

| Área | Comportamiento A8 | Contrato 1.0 | Acción de migración |
| --- | --- | --- | --- |
| Importaciones | Algunos módulos hoja y rutas de implementación eran importables. | Hay 166 nombres estables en 13 módulos canónicos; las 171 rutas alias de módulos hoja no forman parte del contrato. | Sustituye cada importación por la ruta de `docs/public-api.json`; no importes módulos con `_`. |
| DI | `agnara.core.di` aparecía en código de consumidores. | `agnara.di` es la única entrada DI estable. | `from agnara.di import DIRegistry, Scope, provider`. |
| Introspección | El consumidor podía esperar `apps` en la instantánea serializada. | `IntrospectionSnapshot.applications` y el miembro JSON superior son `applications`. `ApplicationDescriptor.apps` no cambia. | Rechaza una versión de formato no reconocida en vez de adivinar el nombre del campo. |
| Contexto y autoridad | Una forma similar a principal o una asignación posterior podía entrar al contexto. | `principal` debe ser `Principal`; `principal`, `confirmation_evidence` e `idempotency` no se pueden reasignar. | Autentica en la raíz de composición y crea el contexto una vez. Conserva sólo `tracking_id` o `state` para estado no autoritativo. |
| Identidad e idempotencia | Metadatos de llamada podían confundirse con identidad de ejecución. | El runtime genera `execution_id`; sólo la invocación directa completa opta por `IdempotencyInvocation`. HTTP y MCP no aceptan clave de idempotencia. El almacén en memoria es local al proceso. | No envíes `execution_id`, un request ID o metadatos como prueba de identidad/idempotencia; elige y opera un almacén durable fuera del núcleo si lo necesitas. |
| Composición | Llamar al manejador Python omitía políticas y el plan compilado. | `CapabilityRuntime` y `CapabilityInvoker` invocan sólo resultados completos del mismo snapshot congelado, con política, validación, cancelación y límites de profundidad normales. | Inyecta `CapabilityInvoker`; no llames a otro manejador ni compiles un segundo runtime durante una llamada. |
| Streaming | Un resultado stream no tiene representación JSON completa. | Declara `streaming=True` y `output=...`; usa `open_stream`. Un destino stream se rechaza para composición y no admite selector de idempotencia. `Http.sse` es la proyección HTTP soportada. | Trata `StreamTerminal` y `StreamInterrupted` como resultado explícito; no asumas WebSocket, replay SSE, MCP streaming ni cuerpos de solicitud en streaming. |
| Embedding | Un host podía tender a pasar objetos de framework a la aplicación. | El host conserva routing, ciclo de vida, sesión, transacción, respuesta y telemetría; Agnara recibe sólo valores y un `Principal` mapeado. El puente es async y de resultado completo. | Mantén un `CapabilityRuntime` explícito por event loop, usa `await invoke_result()`, y no pases request, sesión, ORM, credenciales ni spans a metadatos, DI o manejadores. |
| HTTP | La composición HTTP se describía como provisional. | Las 14 exportaciones de `agnara_http` son estables; extensiones de proveedores de terceros y el endpoint de discovery siguen internos. | Importa desde `agnara_http`, declara bindings explícitos y compila una vez. No uses `agnara_http.composition` como segunda ruta pública. |

## Ejemplos mínimos

### DI, ejecución directa e identidad

```python
from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry
from agnara.execution import ExecutionContext, ExecutionPlan, Invocation, invoke_result

app = Agnara("billing")


@app.capability(scopes=("billing:read",))
def invoice(invoice_id: str) -> dict[str, str]:
    return {"id": invoice_id}


async def read_invoice() -> object:
    registry = app.compile()
    dependencies = DIRegistry()
    plan = ExecutionPlan.compile(registry["billing.invoice"], dependencies)
    context = ExecutionContext(
        Invocation(plan.definition.id, {"invoice_id": "inv-7"}, {}),
        DIContainer(dependencies),
        principal=Principal("reader", scopes={"billing:read"}),
    )
    return await invoke_result(plan, context)
```

The runtime, not `Invocation.metadata`, creates the execution identity. When a
direct complete-result call needs explicit idempotency, use the governed
`IdempotencyInvocation` type from `agnara.execution`; do not adapt an HTTP or
MCP request key into this API.

### Stream output and HTTP SSE

```python
from collections.abc import AsyncIterator

from agnara import Agnara
from agnara_http import Binding, BindingSource, Http

app = Agnara("reports")


@app.capability(streaming=True, output=dict[str, int])
async def rows(report_id: int) -> AsyncIterator[dict[str, int]]:
    yield {"line": report_id}


http = Http("public")
http.sse("/reports/{report_id}", rows, Binding("report_id", BindingSource.PATH))
asgi = http.compile(app.compile())
```

The consumer must pull the stream and examine its terminal outcome. An ordinary
`get`/`post` route is deliberately refused for this capability; streaming is
not silently collapsed into a complete JSON value.

## Security and interoperability checklist

- Map a host-authenticated caller to `Principal` (or anonymous) before
  invocation; missing or ambiguous mapping must fail closed for scoped work.
- Preserve normal policy evaluation in embedded and side-by-side hosts. A
  framework's authentication or route visibility is not capability authority.
- Keep external resource ownership outside Agnara. A SQLAlchemy session,
  transaction and host lifespan are host-owned ports, not handler inputs.
- Use the same frozen application and plans for nested calls. Child work has a
  fresh execution identity, cannot expand a deadline, and receives no parent
  idempotency or confirmation selector.
- Treat HTTP `agnara-execution-id` and MCP request identifiers as correlation,
  never as caller-chosen authority or idempotency proof.

The four clean-room consumer modes — standalone, host with SQLite, embedded
FastAPI and FastAPI side-by-side — are executable evidence in
`docs/releases/1.0-dogfooding.md`. They demonstrate the supported boundary,
not a framework plugin, automatic retry, durable persistence, OpenAPI merging
or a broader framework-support claim.

## Validate before upgrading

Run the public-import audit over the application after replacing imports:

```bash
python scripts/check_public_imports.py path/to/application
```

For a candidate release, repeat the installed-artifact consumer gate:

```bash
uv run pytest tests/release/test_integrated_dogfooding.py
```

Then run the repository quality commands in `QUALITY_GATES.md`. Release
readiness remains a separate, SHA-bound assessment:

```bash
python scripts/check_release_readiness.py --verbose
```

It cannot turn pending CI, protected publication, or maintainer security and
architecture review into a pass. See `docs/releases/release-status.json` for
the recorded target status.
