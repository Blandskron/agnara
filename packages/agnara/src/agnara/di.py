"""Public dependency-injection API.

This is the deliberate 1.0 spelling for Agnara's dependency-injection
contracts.  The implementation remains under ``agnara.core.di``; consumers
must import this module instead so the public path does not look internal.
"""

from agnara.core.di import (
    DependencyCycleError,
    DependencyResolutionError,
    DIContainer,
    DIRegistry,
    ProviderDefinition,
    ProviderType,
    Scope,
    compile_dag,
    provider,
)

__all__ = [
    "DIContainer",
    "DIRegistry",
    "DependencyCycleError",
    "DependencyResolutionError",
    "ProviderDefinition",
    "ProviderType",
    "Scope",
    "compile_dag",
    "provider",
]
