from collections.abc import Callable
from typing import Any, get_type_hints

from .registry import DIRegistry


class DependencyCycleError(Exception):
    """Raised when a dependency cycle is detected."""

    pass


class DependencyResolutionError(Exception):
    """Raised when a dependency cannot be resolved."""

    pass


def _get_dependencies(func: Callable[..., Any]) -> dict[str, type]:
    """Get the type hints of a function, ignoring return type."""
    hints = get_type_hints(func)
    if "return" in hints:
        del hints["return"]
    return hints


def compile_dag(
    registry: DIRegistry, target_funcs: list[Callable[..., Any]]
) -> dict[Callable[..., Any], list[type]]:
    """
    Compile the Dependency DAG for a set of target functions (e.g., capabilities).

    Verifies that all required dependencies are bound in the registry and that no cycles exist.
    A dependency is assumed to be a DI dependency if it exists in the registry.
    If it is not in the registry, it is assumed to be a payload parameter and ignored
    by the DAG compiler.

    Returns a mapping from the target function to a list of DI dependencies it requires.
    """
    # Graph representing which type depends on which other types
    # type -> list[type]
    graph: dict[type, list[type]] = {}

    # We need to explore all providers starting from the target functions
    types_to_explore = set()

    target_deps = {}

    # Extract root types
    for func in target_funcs:
        deps = _get_dependencies(func)
        di_deps = []
        for _name, typ in deps.items():
            if registry.is_bound(typ):
                di_deps.append(typ)
                types_to_explore.add(typ)
        target_deps[func] = di_deps

    explored = set()

    # Explore the graph
    while types_to_explore:
        current_type = types_to_explore.pop()
        if current_type in explored:
            continue

        provider = registry.get_provider(current_type)
        if not provider:
            # This shouldn't happen because we only add bound types
            raise DependencyResolutionError(f"Type {current_type} is not bound.")

        deps = _get_dependencies(provider.func)
        di_deps = []
        for name, typ in deps.items():
            if registry.is_bound(typ):
                di_deps.append(typ)
                if typ not in explored:
                    types_to_explore.add(typ)
            else:
                # For providers, ALL parameters MUST be bound in the registry.
                # A provider cannot take a request payload directly.
                raise DependencyResolutionError(
                    f"Provider for {current_type} requires unbound parameter '{name}' "
                    f"of type {typ}. Providers can only depend on other registered providers."
                )

        graph[current_type] = di_deps
        explored.add(current_type)

    # Detect cycles using DFS
    visiting = set()
    visited = set()

    def dfs(node: type, path: list[type]) -> None:
        if node in visiting:
            cycle = [*path[path.index(node) :], node]
            cycle_str = " -> ".join(n.__name__ for n in cycle)
            raise DependencyCycleError(f"Dependency cycle detected: {cycle_str}")
        if node in visited:
            return

        visiting.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            dfs(neighbor, path)

        path.pop()
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        if node not in visited:
            dfs(node, [])

    return target_deps
