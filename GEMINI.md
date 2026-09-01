# Instrucciones Específicas para Gemini

Este documento contiene directrices y políticas aplicables exclusivamente al agente de inteligencia artificial **Gemini** (operando a través de Google Antigravity o entornos similares). Si eres Gemini y se te ha pedido contribuir a este repositorio, debes cumplir estas reglas obligatoriamente.

## 1. Identidad de Atribución Oficial

Toda contribución material al código, documentación o infraestructura en este repositorio realizada por Gemini debe quedar registrada con el siguiente trailer de Git al final del mensaje del commit:

```text
Co-authored-by: gemini-cli <218195315+gemini-cli@users.noreply.github.com>
```

### Reglas estrictas de identidad
- **NO** utilices `antigravity@google.com`, `gemini@google.com`, ni otras combinaciones de prueba.
- **NO** inventes seudónimos como `antigravity[bot]` o `google-antigravity`.
- Usa exclusivamente la identidad de `gemini-cli` definida arriba, pues esta garantiza la correcta vinculación del ID numérico `218195315` con el sistema de noreply de GitHub.

## 2. Aplicación del Trailer (Regla Obligatoria antes de cada commit)

Cuando vayas a preparar un commit (`git commit`), debes:
1. **Verificar autoría material**: Comprueba mediante `git diff` si realmente escribiste o diseñaste los cambios que se incluyen. No te atribuyas commits que sean 100% de humanos u otros agentes.
2. **Formato**: El trailer `Co-authored-by` debe ir siempre al final del cuerpo del mensaje del commit, precedido por una línea en blanco.
3. **Multi-Agente**: Si el commit consolida trabajo tuyo y de otros agentes (ej. Codex, Claude), incluye ambos trailers en líneas separadas. Nunca borres la atribución legítima de otro agente.
4. **No reescribas la historia**: Esta política se aplica "hacia adelante". No debes modificar commits pasados (históricos) para agregar tu nombre de forma retroactiva.

## 3. Coordinación en Agnara

- Recuerda que Agnara es un repositorio concurrente multi-agente. 
- Utiliza la CLI de coordinación para descubrir tareas (`python scripts/agent.py next`), reservar tu trabajo (`python scripts/agent.py claim`), y asegurar aislamiento de entornos (mediante `git worktree`).
- Para las directrices arquitectónicas globales, dirígete siempre a `AGENTS.md`.
