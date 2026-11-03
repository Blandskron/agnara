"""Writing a generated document to a file, without destroying one.

Shared by every command that takes ``--output``. A command destined for a
build script must not replace a file nobody authorized it to replace, and the
refusal has to read the same way whichever command produced it.
"""

from __future__ import annotations

from pathlib import Path

from agnara_cli._target import TargetError

__all__ = ["write_document"]


def write_document(destination: str, body: bytes, *, overwrite: bool) -> None:
    """Write ``body`` to ``destination``, refusing an unauthorized replacement."""
    path = Path(destination)
    try:
        with path.open("wb" if overwrite else "xb") as stream:
            stream.write(body)
    except FileExistsError as error:
        raise TargetError(
            f"{destination!r} already exists; pass --overwrite to replace it"
        ) from error
    except OSError as error:
        raise TargetError(f"cannot write {destination!r}: {error}") from error
