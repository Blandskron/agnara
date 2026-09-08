"""The HTTP adapter's contribution to the unified exposure model.

This is the one supported way to compile HTTP capability exposures. It returns
the frozen route registry that dispatch needs *and* the neutral records the
project aggregates, in one value, so the two cannot be produced separately and
drift (RFC 0006 section 9).

The records are derived from the compiled route table rather than from the
declarations that produced it. That ordering is the whole point: a record
cannot describe a route the registry does not hold, and a route cannot exist
without a record, because both are read out of the same compiled artifact.

Naming note: ``surface`` here is the RFC 0006 sense -- one named deployment of
this adapter, such as ``http:public``. It is unrelated to ``_HTTPSurface`` in
``_surfaces``, which is a static documentation response. Keeping both words is
deliberate for now; the public spelling is settled when the composition API
lands, and inventing a private synonym today would leave two vocabularies for
one concept.
"""

from __future__ import annotations

from collections.abc import Iterable

from agnara.exposure import CompiledExposure, SurfaceCompilation, SurfaceId
from agnara_http._dispatch import _compile_exposures, _CompiledExposure, _HTTPExposure
from agnara_http._routing import _FrozenRouteRegistry

#: The adapter kind this package contributes, and the ``transport`` value its
#: exposures carry into introspection.
ADAPTER = "http"

#: Surface name used when a project does not name one. A single-surface
#: deployment is the common case and should not have to invent a word for it.
DEFAULT_SURFACE = "default"

type _HTTPRoutes = _FrozenRouteRegistry[_CompiledExposure]


def _http_surface(name: str = DEFAULT_SURFACE) -> SurfaceId:
    """The identity of one named HTTP surface."""
    return SurfaceId(ADAPTER, name)


def _local_name(method: str, path_template: str) -> str:
    """The adapter-local name of one HTTP target.

    A method and path pair, which is how an HTTP route is named everywhere a
    developer already reads one. The kernel treats it as opaque text.
    """
    return f"{method} {path_template}"


def _derive_exposures(
    surface: SurfaceId,
    routes: _HTTPRoutes,
) -> tuple[CompiledExposure, ...]:
    """Read neutral records out of the compiled route table itself."""
    return tuple(
        CompiledExposure.of(
            surface,
            _local_name(route.method, route.path_template),
            route.target.plan.definition.id,
            {"method": route.method, "path": route.path_template},
        )
        for route in routes
    )


def _compile_exposure_surface(
    exposures: Iterable[_HTTPExposure],
    *,
    surface: str = DEFAULT_SURFACE,
) -> SurfaceCompilation[_HTTPRoutes]:
    """Compile one named HTTP surface into dispatch truth and neutral records.

    ``exposures`` are ``_HTTPExposure`` declarations. Route grammar, template
    parsing, binding compilation and collision detection stay in
    ``_compile_exposures``: the kernel never learns any of them, and this
    function adds no validation of its own beyond what the route table
    already enforced.
    """
    routes = _compile_exposures(exposures)
    identity = _http_surface(surface)
    return SurfaceCompilation(identity, routes, _derive_exposures(identity, routes))
