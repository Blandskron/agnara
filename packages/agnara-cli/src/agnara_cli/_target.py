"""Resolve a compiled Agnara application from a command-line target.

There is no project manifest yet (E0A.2), so the target is explicit:
``package.module:attribute``, the convention `uvicorn` and `gunicorn` already
established, resolved with the ordinary import system.

Importing a target runs the user's module. That is inherent — a compiled
application only exists once its declarations have executed — and it is the
reason a malformed target is rejected before anything is imported.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from agnara import Agnara
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan

__all__ = ["ResolvedTarget", "TargetError", "resolve_target"]


class TargetError(Exception):
    """A command-line target cannot be resolved into a compiled application.

    Carries a caller-facing diagnostic. The CLI prints it; it never lets an
    import failure reach the operator as a traceback.
    """


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    """One application, its compiled plans and its dependency registry."""

    app: Agnara
    plans: tuple[ExecutionPlan, ...]
    dependencies: DIRegistry | None


def _split(target: str) -> tuple[str, str]:
    if not isinstance(target, str) or not target.strip():
        raise TargetError("target must be given as 'module:attribute'")
    module_name, separator, attribute = target.partition(":")
    if not separator or not module_name.strip() or not attribute.strip():
        raise TargetError(
            f"invalid target {target!r}: expected 'module:attribute', "
            "for example 'billing.bootstrap:app'"
        )
    module_name = module_name.strip()
    attribute = attribute.strip()
    for part in module_name.split("."):
        if not part.isidentifier():
            raise TargetError(f"invalid target {target!r}: {module_name!r} is not a module path")
    if not attribute.isidentifier():
        raise TargetError(f"invalid target {target!r}: {attribute!r} is not an attribute name")
    return module_name, attribute


def _import(module_name: str, search_path: Sequence[str]) -> object:
    """Import the target module, with the requested paths ahead of the rest."""
    added = [str(Path(entry).resolve()) for entry in search_path]
    original = list(sys.path)
    sys.path[:0] = added
    try:
        return importlib.import_module(module_name)
    except ImportError as error:
        raise TargetError(f"cannot import {module_name!r}: {error}") from error
    except Exception as error:
        # A module that raises while executing is the user's code failing, not
        # a CLI failure, and the operator needs the reason rather than a stack.
        raise TargetError(f"importing {module_name!r} failed: {error}") from error
    finally:
        sys.path[:] = original


def _registry(module: object, name: str | None) -> DIRegistry | None:
    if name is None:
        return None
    registry = getattr(module, name, None)
    if registry is None:
        raise TargetError(f"the target module defines no attribute {name!r}")
    if not isinstance(registry, DIRegistry):
        raise TargetError(f"attribute {name!r} is a {type(registry).__name__}, not a DIRegistry")
    return registry


def resolve_target(
    target: str,
    *,
    search_path: Iterable[str] = (),
    dependencies: str | None = None,
) -> ResolvedTarget:
    """Import ``module:attribute`` and compile every declared capability.

    ``dependencies`` names a `DIRegistry` in the same module. Without it the
    application is compiled against an empty registry, which succeeds only
    when no capability declares a dependency — a capability that needs one
    fails with the reason rather than being described as if it had none.
    """
    module_name, attribute = _split(target)
    module = _import(module_name, tuple(search_path))
    app = getattr(module, attribute, None)
    if app is None:
        raise TargetError(f"the target module defines no attribute {attribute!r}")
    if not isinstance(app, Agnara):
        raise TargetError(
            f"attribute {attribute!r} is a {type(app).__name__}, not an Agnara application"
        )
    registry = _registry(module, dependencies)
    compile_against = DIRegistry() if registry is None else registry
    try:
        plans = tuple(
            ExecutionPlan.compile(app.capabilities[capability_id], compile_against)
            for capability_id in app.capabilities
        )
    except Exception as error:
        raise TargetError(f"compiling {app.name!r} failed: {error}") from error
    return ResolvedTarget(app, plans, registry)
