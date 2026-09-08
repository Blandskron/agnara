"""Small, deterministic formatting helpers for generated Python source.

Project and app names are valid Python identifiers, so their length is not
fixed. Templates therefore cannot assume that an interpolated import,
docstring opening or Sphinx comment still fits the generated project's
100-character Ruff limit.

This is deliberately not a general Python formatter. It handles only the
three generated constructs whose width depends on an identifier, without
adding a runtime dependency on Ruff or changing already-short output.
"""

from __future__ import annotations

from textwrap import wrap

__all__ = ["format_python_template"]

_LINE_LENGTH = 100


def _wrapped_import(line: str) -> list[str]:
    indent = line[: len(line) - len(line.lstrip())]
    statement = line.strip()
    module, imported = statement.split(" import ", 1)
    names = [name.strip() for name in imported.split(",")]
    return [
        f"{indent}{module} import (",
        *(f"{indent}    {name}," for name in names),
        f"{indent})",
    ]


def _wrapped_docstring_opening(line: str) -> list[str]:
    return wrap(
        line[3:],
        width=_LINE_LENGTH,
        initial_indent='"""',
        subsequent_indent="",
        break_long_words=False,
        break_on_hyphens=False,
    )


def _wrapped_comment(line: str) -> list[str]:
    return wrap(
        line[3:],
        width=_LINE_LENGTH,
        initial_indent="#: ",
        subsequent_indent="#: ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def format_python_template(source: str) -> str:
    """Wrap name-dependent constructs while preserving short source exactly."""
    formatted: list[str] = []
    for line in source.splitlines():
        if len(line) <= _LINE_LENGTH:
            formatted.append(line)
        elif line.lstrip().startswith("from ") and " import " in line:
            formatted.extend(_wrapped_import(line))
        elif line.startswith('"""') and not line.endswith('"""'):
            formatted.extend(_wrapped_docstring_opening(line))
        elif line.startswith("#: "):
            formatted.extend(_wrapped_comment(line))
        else:
            formatted.append(line)
    return "\n".join(formatted) + "\n"
