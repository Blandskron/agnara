"""The HTTP adapter has a public surface, and the examples prove it is enough.

`agnara-http` exported nothing for three releases, so an application composing
HTTP had to import `agnara_http._dispatch` and friends. That is what the
`0.1.0a4` gate `reference-apps-no-internal-imports` forbids, and it is what
these rules keep from coming back.

They must fail when:

- the package's declared surface drifts from what the documentation promises;
- an example, the README or the composition guide reaches into a private
  module;
- a public module of the adapter re-exports a private name;
- the maturity table's count stops matching the package.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.architecture.boundaries import WORKSPACE_ROOT, package_source_root

HTTP_DISTRIBUTION = "agnara-http"
HTTP_IMPORT_NAME = "agnara_http"

#: The exact surface `0.1.0a4` promises, in `__all__` order.
#:
#: Written out rather than imported so that adding an export is a deliberate
#: edit here as well as in the package. A count would not catch a rename.
PUBLIC_SURFACE = (
    "Binding",
    "BindingSource",
    "Http",
    "HttpApplication",
    "HttpDefinitionError",
    "OpenApiInfo",
    "OpenApiOperation",
)

#: Files an application is invited to copy. A private import in one of these
#: is worse than a private import in a test: it teaches the wrong thing.
EXEMPLARY = (
    "examples",
    "docs/HTTP_COMPOSITION.md",
    "README.md",
)

PRIVATE_IMPORT = re.compile(r"\bfrom\s+agnara(?:_\w+)?\._|\bimport\s+agnara(?:_\w+)?\._")


def literal_all(path: Path) -> tuple[str, ...] | None:
    """Read a module's ``__all__`` without importing it.

    Only the plain ``__all__ = [...]`` form is recognized, which is what both
    public modules of this adapter use. An annotated or computed ``__all__``
    returns ``None`` and fails the assertions below rather than being guessed
    at, because a surface nobody can read statically is not a governed one.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List | ast.Tuple):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if "__all__" in targets:
            return tuple(
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
    return None


def http_root() -> Path:
    return package_source_root(HTTP_DISTRIBUTION)


def public_modules() -> list[Path]:
    """Modules of the adapter an application may import."""
    return [
        path
        for path in sorted(http_root().rglob("*.py"))
        if not any(part.startswith("_") for part in path.relative_to(http_root()).parts)
        or path.name == "__init__.py"
    ]


def test_the_adapter_declares_the_documented_surface() -> None:
    declared = literal_all(http_root() / "__init__.py")

    assert declared == PUBLIC_SURFACE


def test_the_composition_module_declares_the_same_surface() -> None:
    """The package re-exports one module, so the two must not diverge."""
    assert literal_all(http_root() / "composition.py") == PUBLIC_SURFACE


def test_no_public_name_is_underscore_prefixed() -> None:
    for name in PUBLIC_SURFACE:
        assert not name.startswith("_"), name


def test_every_other_module_stays_private() -> None:
    """A new public module is a governance decision, not an accident."""
    public = {path.name for path in public_modules()}

    assert public == {"__init__.py", "composition.py"}


def test_the_maturity_table_reports_the_real_count() -> None:
    """`docs/MATURITY.md` says how many names each distribution exports."""
    maturity = (WORKSPACE_ROOT / "docs" / "MATURITY.md").read_text(encoding="utf-8")
    row = next(
        line for line in maturity.splitlines() if line.startswith(f"| `{HTTP_DISTRIBUTION}` |")
    )

    assert f"| {len(PUBLIC_SURFACE)} |" in row, row


@pytest.mark.parametrize("target", EXEMPLARY)
def test_nothing_exemplary_imports_a_private_module(target: str) -> None:
    """An example that needs a private import is a public API that is missing."""
    root = WORKSPACE_ROOT / target
    if not root.exists():
        pytest.fail(f"{target} does not exist; the composition guide is part of the contract")
    paths = sorted(root.rglob("*")) if root.is_dir() else [root]
    offenders = [
        f"{path.relative_to(WORKSPACE_ROOT).as_posix()}:{index}"
        for path in paths
        if path.is_file() and path.suffix in {".py", ".md"}
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if PRIVATE_IMPORT.search(line)
    ]

    assert not offenders, (
        "an example or guide must compose Agnara through public API only; "
        f"private imports at: {offenders}"
    )


def test_the_composition_guide_shows_the_supported_path() -> None:
    """The guide is the answer to "how do I serve a capability over HTTP?"."""
    guide = (WORKSPACE_ROOT / "docs" / "HTTP_COMPOSITION.md").read_text(encoding="utf-8")

    for name in PUBLIC_SURFACE:
        assert f"`{name}`" in guide or f"{name}(" in guide, name


def test_the_guide_states_what_this_release_does_not_expose() -> None:
    """A guide that omits its limits is how a framework earns distrust."""
    guide = (WORKSPACE_ROOT / "docs" / "HTTP_COMPOSITION.md").read_text(encoding="utf-8")

    for limitation in ("Explorer", "discovery", "WebSocket", "#296"):
        assert limitation in guide, limitation


def test_the_public_module_re_exports_no_private_name() -> None:
    """`composition` may import privately; it must not hand one back."""
    import agnara_http

    for name in agnara_http.__all__:
        exported = getattr(agnara_http, name)
        module = getattr(exported, "__module__", "")
        assert not module.rsplit(".", 1)[-1].startswith("_"), f"{name} comes from {module}"
