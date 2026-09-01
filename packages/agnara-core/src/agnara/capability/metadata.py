"""Agentic metadata vocabularies for capabilities.

These describe what invoking a capability *does*, in a form a policy engine
or a discovery surface can read. They are data, never enforcement:
ADR 0008 and PRINCIPLES.md P9 both require that a policy engine combine
this metadata with context to reach a decision. A capability labelled
``risk="low"`` is not thereby authorized.

Values are defined in RFC 0001 "Effects", "Risk", "Confirmation" and
"Idempotency".
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "Confirmation",
    "Idempotency",
    "Risk",
    "StandardEffect",
]


class Risk(StrEnum):
    """How much damage a wrong or malicious invocation could cause."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confirmation(StrEnum):
    """Whether a human has to approve an invocation before it proceeds."""

    #: No confirmation is ever required.
    NEVER = "never"
    #: A policy decides, per invocation and context.
    POLICY = "policy"
    #: Always require confirmation.
    REQUIRED = "required"


class Idempotency(StrEnum):
    """Whether repeating an invocation is safe.

    ``UNKNOWN`` is the default everywhere. RFC 0001 is explicit that
    claiming idempotency falsely is worse than admitting ignorance, because
    a caller retrying a non-idempotent operation can duplicate real effects.
    """

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class StandardEffect(StrEnum):
    """Effect labels Agnara gives a defined meaning.

    The effect vocabulary is deliberately open: a capability may declare any
    non-empty string, because applications have effects Agnara cannot
    anticipate. These are the values Agnara itself understands, offered so
    that common cases spell them the same way across projects.
    """

    NONE = "none"
    READ = "read"
    CACHE_WRITE = "cache-write"
    DATABASE_WRITE = "database-write"
    EXTERNAL_WRITE = "external-write"
    FINANCIAL_WRITE = "financial-write"
    DESTRUCTIVE = "destructive"
