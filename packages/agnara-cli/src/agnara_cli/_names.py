"""One rule for every name a generator turns into a Python identifier.

``agnara project create`` and ``agnara app create`` both take a name that
becomes a package directory, an import path and a manifest key. They used to
validate it separately, and both accepted anything `str.isidentifier` did --
including ``class`` and ``import``, which are identifiers to that method and
syntax errors to the interpreter. One rule, here, so the two cannot drift.
"""

from __future__ import annotations

import keyword
from collections.abc import Collection

from agnara_cli._generate import GenerationError

__all__ = ["validated_identifier"]


def validated_identifier(
    name: str,
    *,
    subject: str,
    reserved: Collection[str] = (),
    reserved_because: str = "",
) -> str:
    """Refuse a name that could not become a package, a module or an import.

    Args:
        name: the candidate.
        subject: what to call it in a diagnostic, such as ``"project name"``.
        reserved: names that are syntactically fine but would collide with
            something the generated code already binds or imports.
        reserved_because: the reason, completing "it is reserved: ...".
    """
    if not name.isidentifier():
        raise GenerationError(
            f"invalid {subject} {name!r}: it becomes a package and an import "
            "path, so it must be a single Python identifier"
        )
    if keyword.iskeyword(name):
        raise GenerationError(
            f"invalid {subject} {name!r}: it is a Python keyword, so the generated "
            "code could not import it"
        )
    if name != name.lower():
        raise GenerationError(
            f"invalid {subject} {name!r}: use lower_case, so the package name "
            "matches the import path on case-insensitive filesystems"
        )
    if name in reserved:
        raise GenerationError(f"invalid {subject} {name!r}: it is reserved; {reserved_because}")
    return name
