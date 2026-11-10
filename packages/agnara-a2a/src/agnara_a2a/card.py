"""Explicit public Agent Card metadata (ADR 0098 D8)."""

from __future__ import annotations

from dataclasses import dataclass

from .exposure import _required_text

__all__: list[str] = []


@dataclass(frozen=True, slots=True)
class A2aAgentCard:
    """The agent-level fields of the public, unsigned Agent Card.

    The card is identical for every caller. Interface, capability flags and
    content modes are fixed by the profile and are not configurable here.
    """

    name: str
    description: str
    version: str

    def __post_init__(self) -> None:
        for field in ("name", "description", "version"):
            _required_text(f"card {field}", getattr(self, field))
