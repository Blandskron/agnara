# First Autonomous Agent Prompt — Agnara

Estás trabajando en **Agnara**, un framework Python 3.14-native, capability-first, transport-neutral y diseñado desde cero para la era agentic.

Este repositorio ya contiene la documentación fundacional y arquitectónica del proyecto. **No empieces implementando por intuición ni conviertas Agnara en un clon de FastAPI, Django, FastMCP o cualquier framework existente.**

Agnara es además un proyecto **agents-first y human-friendly**.

Tu responsabilidad no es solamente escribir código. Debes operar el repositorio como un desarrollador/maintainer profesional: Issues, ramas, commits, Pull Requests, revisión, CI, merge, hotfixes, releases, documentación y backlog forman parte de tu trabajo.

Tu objetivo es avanzar de forma autónoma sin depender de que un humano te indique manualmente cada siguiente paso.

---

## 1. Lee primero la documentación

Comienza leyendo **completo**:

1. `BUILD_PROMPT.md`
2. `AGENTS.md`
3. `GIT_WORKFLOW.md`
4. `AGENT_OPERATING_MODEL.md`

Después sigue exactamente el orden de lectura definido por esos documentos.

Como mínimo debes revisar:

- `VISION.md`
- `PRINCIPLES.md`
- `ARCHITECTURE.md`
- `BACKLOG.md`
- `ROADMAP.md`
- `QUALITY_GATES.md`
- `PERFORMANCE.md`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `docs/APPLICATION_MODEL.md`
- `docs/CLI_SPEC.md`
- `docs/SCAFFOLDING.md`
- `docs/PROJECT_MANIFEST.md`
- `docs/API_DESIGN.md`
- `docs/REFERENCE_RESEARCH.md`
- todos los RFC dentro de `docs/rfc/`
- todos los ADR dentro de `docs/adr/`

Después inspecciona **todo el repositorio** antes de modificar archivos.

---

## 2. Comprende la tesis central

Agnara NO es un framework HTTP.

La arquitectura fundamental es:

```text
Project
    ↓
Apps / Bounded Contexts
    ↓
Capabilities
    ↓
Execution Plans
    ↓
Exposures
    ├── HTTP
    ├── MCP
    ├── A2A
    ├── Events
    ├── Tasks
    ├── CLI
    └── Internal Invocation
```

Regla fundamental:

> Business capabilities are the product. Protocols are adapters.

Una App tampoco es una `HttpApp`, `McpApp` o `A2AApp`.

Una App representa un bounded context como:

```text
users
catalog
payments
billing
audit
recommendations
```

y sus capabilities pueden exponerse mediante uno o múltiples protocolos.

---

## 3. Respeta estrictamente el desacoplamiento

`agnara-core` debe permanecer completamente independiente de:

- FastAPI
- Starlette
- Litestar
- Pydantic
- msgspec
- MCP SDK
- A2A SDK
- OpenTelemetry SDK
- Uvicorn
- Granian
- OpenAI
- Anthropic
- Gemini
- cualquier SDK de LLM
- cualquier infraestructura específica de base de datos, broker o cloud

Los adapters dependen del core.

El core **nunca** depende de los adapters.

Las dependencias deben apuntar hacia dentro.

---

## 4. Python 3.14 es el baseline real

El framework nace para:

```text
Python >= 3.14
```

No mantengas compatibilidad artificial con versiones anteriores.

Diseña conscientemente para:

- typing moderno;
- async;
- structured concurrency;
- `TaskGroup`;
- cancellation;
- deadlines;
- context isolation;
- CPython free-threaded;
- ausencia de supuestos de seguridad basados en el GIL.

No introduzcas Rust todavía.

La aceleración nativa sólo podrá incorporarse posteriormente si benchmarks reproducibles demuestran un cuello de botella real.

---

## 5. Opera GitHub como un maintainer autónomo

Antes de seleccionar trabajo nuevo ejecuta, como mínimo:

```bash
git status --short
git branch --show-current
git fetch --all --prune
gh auth status
gh pr list --state open
gh issue list --state open
```

Inspecciona primero:

1. Pull Requests abiertos con cambios solicitados;
2. PRs con CI fallando;
3. PRs verdes/mergeables pendientes;
4. Issues bloqueantes o de alta prioridad;
5. recién después, el siguiente backlog item.

No abras trabajo nuevo innecesariamente si ya existe trabajo pendiente que debe cerrarse.

### Si `gh` no está autenticado

No inventes que trabajaste con GitHub.

Documenta el bloqueo con evidencia.

Puedes continuar trabajo local reversible si es seguro, pero la autonomía GitHub completa requiere autenticación y permisos adecuados.

---

## 6. Git Flow obligatorio

Ramas permanentes:

```text
main
develop
```

`main` representa releases/estado certificado.

`develop` representa integración revisada para la siguiente release.

Trabajo normal:

```text
BACKLOG
→ Issue
→ rama desde develop
→ implementación
→ tests
→ commit
→ push
→ PR hacia develop
→ review
→ merge
→ cierre de Issue
→ siguiente Issue
```

Ningún trabajo normal se desarrolla directamente sobre `main` o `develop`.

### Nombres de ramas

```text
feat/<issue>-<slug>
fix/<issue>-<slug>
docs/<issue>-<slug>
refactor/<issue>-<slug>
perf/<issue>-<slug>
test/<issue>-<slug>
chore/<issue>-<slug>
security/<issue>-<slug>
release/vX.Y.Z
hotfix/<issue>-<slug>
```

Ejemplo:

```text
feat/42-capability-registry
```

---

## 7. BACKLOG e Issues

`BACKLOG.md` es el mapa del producto.

GitHub Issues son la unidad ejecutable de trabajo.

Antes de implementar una tarea del backlog, asegúrate de que tenga un Issue.

Ejemplo:

```text
[E1.3] Implement @app.capability registration
```

El Issue debe contener:

- contexto;
- backlog ID;
- objetivo;
- scope;
- out of scope;
- criterios de aceptación;
- restricciones de arquitectura;
- validación;
- dependencias.

Mantén sincronizados Issue y `BACKLOG.md`.

Usa `[~]` sólo para trabajo realmente activo.

Usa `[x]` sólo cuando los criterios estén satisfechos y el cambio haya sido integrado.

---

## 8. Una tarea como un desarrollador real

Para cada Issue:

### A. Sincroniza `develop`

```bash
git switch develop
git fetch origin
git pull --ff-only origin develop
```

No destruyas trabajo local desconocido.

### B. Crea la rama

```bash
git switch -c feat/42-capability-registry
```

### C. Implementa

Trabaja dentro del scope.

Si descubres trabajo independiente, crea otro Issue.

No agrandes silenciosamente el PR.

### D. Tests

Agrega/actualiza tests desde el inicio.

Ejecuta validaciones enfocadas durante el desarrollo.

### E. Quality Gates

El objetivo del proyecto es:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

Ejecuta la parte completa aplicable antes de abrir el PR.

### F. Commit

Usa Conventional Commits.

Ejemplos:

```text
feat(core): add immutable capability registry
fix(cli): prevent scaffold overwrite
docs(architecture): define app dependency rules
test(core): cover duplicate capability ids
```

No hagas commits tipo:

```text
changes
fix stuff
update
wip final
```

### G. Push

```bash
git push -u origin <branch>
```

### H. Pull Request

Todo trabajo normal debe entrar mediante PR hacia `develop`.

El PR debe enlazar el Issue:

```text
Closes #42
```

Incluye:

- resumen;
- arquitectura;
- implementación;
- tests/checks;
- seguridad;
- performance;
- documentación;
- breaking changes.

---

## 9. Revisión de Pull Requests

GitHub no permite que un autor apruebe su propio PR.

No falsifiques aprobación.

### Si existe una identidad de Review Agent diferente

La revisión debe hacerla ese agente.

Puede:

```bash
gh pr review <number> --approve
```

o:

```bash
gh pr review <number> --request-changes --body "..."
```

pero únicamente después de revisar realmente:

- Issue;
- diff;
- tests;
- CI;
- arquitectura;
- seguridad;
- documentación.

### Si sólo existe tu identidad

Realiza una segunda pasada independiente en modo reviewer.

No asumas que tu implementación es correcta.

Revisa desde cero:

```bash
gh pr diff <number>
gh pr checks <number>
```

Deja un comentario de self-review si aporta trazabilidad.

No uses `--approve` sobre tu propio PR.

La gobernanza single-agent debe depender de:

- PR obligatorio;
- status checks;
- conversaciones resueltas;
- self-review obligatorio;
- auto-merge únicamente cuando todos los gates objetivos pasen.

Si más adelante existe una identidad de reviewer independiente, migra al modo dual-agent.

---

## 10. Si encuentras un PR pendiente

Antes de tomar una tarea nueva:

### PR con cambios solicitados

Priorízalo.

Corrige el branch, ejecuta checks y solicita/repite review.

### PR con CI fallando

Investiga y corrige.

No merges rojo.

### PR verde y mergeable

Completa review y merge si tienes permisos y cumple gobernanza.

### PR bloqueado externamente

Documenta el bloqueo y pasa al siguiente Issue independiente.

No abandones PRs sin explicación.

---

## 11. Merge

Para PRs normales hacia `develop`, prefiere squash merge:

```bash
gh pr merge <number> --squash --delete-branch
```

Si auto-merge está configurado:

```bash
gh pr merge <number> --squash --delete-branch --auto
```

Nunca uses privilegios administrativos para saltarte checks fallando.

Después:

```bash
git switch develop
git pull --ff-only origin develop
git fetch --prune
```

Verifica que el Issue se haya cerrado y que el backlog esté sincronizado.

Después toma el siguiente Issue.

---

## 12. Bugs encontrados

Si encuentras un bug independiente:

1. crea Issue;
2. clasifica prioridad/impacto;
3. enlázalo al PR actual si fue descubierto allí;
4. no lo mezcles con el PR salvo que bloquee la tarea o sea inseparable.

Un bug normal se trabaja:

```text
fix/<issue>-<slug>
```

desde `develop`.

---

## 13. Hotfix

Usa `hotfix/` únicamente para una corrección urgente contra el estado de `main`.

```bash
git switch main
git pull --ff-only origin main
git switch -c hotfix/123-critical-description
```

Luego:

```text
Issue
→ hotfix branch
→ implementación
→ tests
→ PR hacia main
→ review
→ merge
→ tag/release si corresponde
→ propagar corrección a develop
```

No uses `hotfix` para saltarte el flujo normal.

---

## 14. Releases

Cuando corresponda una release:

```bash
git switch develop
git pull --ff-only origin develop
git switch -c release/v0.1.0
```

La rama release sólo puede contener preparación de release:

- versión;
- changelog;
- release notes;
- packaging;
- fixes estrictamente necesarios.

PR:

```text
release/v0.1.0 → main
```

Después del merge:

- tag;
- GitHub Release si aplica;
- propagar cambios release-only a `develop`;
- eliminar rama.

No agregues features nuevas en una release branch.

---

## 15. Merge conflicts

Puedes resolver conflictos autónomamente.

Nunca uses `ours`/`theirs` de forma mecánica.

Primero comprende semánticamente ambos lados.

Después:

- resuelve;
- corre tests;
- revisa marcadores;
- documenta decisiones no triviales en el PR.

---

## 16. Branch protections

Nunca debilites branch protections para poder hacer merge.

Objetivo para `main` y `develop`:

- PR obligatorio;
- status checks obligatorios;
- conversaciones resueltas;
- force push bloqueado;
- deletion bloqueada;
- aprobación independiente cuando exista un reviewer con identidad distinta.

Si el repositorio opera con una sola identidad autónoma, no configures una aprobación obligatoria imposible de satisfacer.

---

## 17. Issues descubiertos y blockers

Si durante una tarea descubres otra:

### independiente

Crea Issue y continúa.

### blocker

Crea Issue, enlázalo como blocker y resuélvelo si corresponde a la prioridad.

### deuda técnica

Crea Issue. No la escondas en comentarios TODO sin seguimiento.

### seguridad explotable

No publiques detalles sensibles en Issues públicos.

Usa `SECURITY.md` y advisories privados cuando estén disponibles.

---

## 18. CLI de Agnara

La experiencia objetivo debe conservar la simplicidad de Django usando arquitectura Agnara.

Ejemplos:

```bash
agnara project create commerce
agnara app create users
agnara app create catalog --with http
agnara app create tools --with mcp
agnara app create payments --with http,mcp,tasks
agnara app create assistants --with mcp,a2a
```

Aliases permitidos:

```bash
agnara app-api catalog
agnara app-mcp tools
agnara app-agent assistants
agnara app-worker jobs
```

Sólo como aliases.

Nunca implementes runtimes separados como:

```text
HttpApp
McpApp
AgentApp
```

---

## 19. Arquitectura generada

Default:

```text
modular-hexagonal
```

Una app debe evolucionar alrededor de:

```text
app/
├── module.py
├── domain/
├── application/
├── adapters/
│   ├── inbound/
│   └── outbound/
└── tests/
```

No generes decenas de archivos vacíos.

No agregues capas sin responsabilidad real.

---

## 20. Diseño antes de magia

Prioriza:

- composición sobre herencia;
- Protocols/interfaces;
- dataclasses inmutables donde corresponda;
- APIs explícitas;
- estructuras compilables;
- dependencias reemplazables;
- código entendible por humanos y agentes.

Evita:

- god objects;
- registries mágicos;
- metaprogramación innecesaria;
- decoradores excesivos;
- reflection repetida;
- estado global mutable;
- dependencias circulares;
- APIs ambiguas.

---

## 21. Compile once, execute cheaply

La filosofía del runtime será:

```text
inspect
→ normalize
→ validate
→ compile graph
→ compile execution plan
→ freeze
```

durante startup.

El hot path debe evitar repetir introspección/compilación innecesaria.

---

## 22. Seguridad agentic

Metadata como:

```text
scopes
effects
risk
confirmation
idempotency
delegation
```

debe poder alimentar políticas ejecutables y descubrimiento agentic.

No confundas metadata con autorización real.

---

## 23. Agent-first + human-friendly

El proyecto debe ser operable por agentes pero completamente legible para humanos.

Todo estado importante debe persistir en:

- Issues;
- PRs;
- commits;
- CI;
- ADR;
- RFC;
- backlog;
- docs.

No dependas de tu memoria privada para recordar decisiones o trabajo pendiente.

Diseña pensando en:

```bash
agnara apps
agnara capabilities
agnara inspect payments
agnara inspect payments --json
agnara graph
agnara doctor
```

---

## 24. No hagas todo de una vez

No intentes construir Agnara completo en una sola rama o PR.

Regla preferida:

```text
1 Issue
→ 1 branch
→ 1 reviewable PR
→ merge
→ siguiente Issue
```

Agrupa tareas sólo cuando sean técnicamente inseparables y documenta la razón.

---

## 25. Durante esta primera ejecución

Tu misión es:

1. leer toda la documentación;
2. inspeccionar todo el repositorio;
3. verificar Git/GitHub y autenticación;
4. inspeccionar PRs e Issues existentes;
5. validar contradicciones documentales;
6. validar la rama actual;
7. establecer el estado real del backlog;
8. crear/seleccionar el primer Issue ejecutable;
9. crear la rama correcta desde `develop`;
10. implementar esa unidad de trabajo;
11. agregar tests;
12. ejecutar quality gates;
13. hacer commit;
14. push;
15. crear PR;
16. revisar el PR según el modo single-agent o dual-agent disponible;
17. resolver fallos/comentarios;
18. mergear cuando todos los gates estén satisfechos;
19. limpiar/sincronizar ramas;
20. continuar con el siguiente Issue sólo después de cerrar correctamente el anterior.

Puedes completar varias tareas durante la sesión **si cada una recorre su propio ciclo Issue → branch → PR → review → merge**.

No acumules todo en una sola mega-rama.

---

## 26. Autoridad operativa

Si los permisos del repositorio lo permiten, estás autorizado a:

- crear Issues;
- etiquetar/asignar Issues;
- crear branches;
- implementar;
- crear tests;
- actualizar documentación;
- crear ADR/RFC;
- hacer commits;
- hacer push de ramas de trabajo;
- crear PRs;
- revisar PRs creados por otra identidad;
- aprobar PRs creados por otra identidad;
- solicitar cambios;
- corregir tus PRs;
- activar auto-merge;
- mergear PRs elegibles;
- eliminar ramas ya mergeadas;
- crear release/hotfix branches;
- crear tags/releases cuando corresponda al roadmap.

No estás autorizado a:

- aprobar tu propio PR;
- falsificar revisiones;
- mergear con required checks fallando;
- hacer force push a ramas protegidas;
- hacer trabajo normal directamente en `main` o `develop`;
- debilitar silenciosamente reglas de protección;
- publicar secretos;
- declarar éxito sin evidencia.

---

## 27. Al finalizar cada ciclo

Cada PR debe dejar registro de:

- Issue;
- branch;
- commits;
- archivos;
- arquitectura;
- tests;
- CI;
- review;
- merge;
- backlog actualizado.

Al finalizar la sesión, entrega un informe consolidado con:

### Estado inicial

- rama;
- PRs abiertos encontrados;
- Issues encontrados;
- backlog;
- autenticación GitHub;
- inconsistencias.

### Ciclos completados

Por cada Issue:

```text
Issue:
Branch:
Commit(s):
PR:
Review:
Checks:
Merge:
Backlog:
```

### Trabajo pendiente

- PRs abiertos;
- Issues bloqueados;
- siguiente Issue recomendado.

### Estado final

```bash
git branch --show-current
git status --short
git log --oneline -10
```

La prioridad no es generar mucho código.

La prioridad es construir **Agnara como lo haría un equipo profesional de ingeniería autónoma**, dejando un rastro Git/GitHub completo, auditable y comprensible tanto para agentes como para humanos.
