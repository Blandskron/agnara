"""The reviewed publication set, read from one file instead of retyped.

`docs/distributions.json` is the single source of truth for which
distributions Agnara ships. Before this module the same seven names were
spelled out independently in `scripts/check_distributions.py`,
`scripts/check_release_readiness.py`, `tests/architecture/boundaries.py`, the
workspace root `pyproject.toml` and twice inside `.github/workflows/`. Six
copies of a list is six chances for a release to disagree with itself about
what it is publishing, and the `0.1.0a4` incident was exactly a disagreement
about a distribution name -- between this repository and PyPI rather than
between two files here, but the class of failure is the same.

Used as a module by the other release scripts, and as a command by the
workflows so a shell step never has to retype a name or a count::

    python scripts/distributions.py --names
    python scripts/distributions.py --import-names
    python scripts/distributions.py --count
    python scripts/distributions.py --third-party
    python scripts/distributions.py --publication-order
    python scripts/distributions.py --pinned 0.1.0a5

Standard library only, like the rest of the repository's release tooling.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Where the reviewed set lives, relative to a workspace checkout.
MANIFEST_RELATIVE = Path("docs") / "distributions.json"

SCHEMA_VERSION = 1

#: Roles a distribution may declare. `reserved` names a package that ships an
#: empty public namespace on purpose; it is published so the name cannot be
#: taken, not because it has a runtime.
ROLES = frozenset({"kernel", "adapter", "reserved"})


class ManifestError(Exception):
    """The publication manifest is missing, malformed or self-contradictory."""


@dataclass(frozen=True, slots=True)
class Distribution:
    """One first-party distribution and everything a release needs about it."""

    name: str
    import_name: str
    role: str
    console_scripts: tuple[str, ...]
    third_party_requirements: tuple[str, ...]

    @property
    def artifact_stem(self) -> str:
        """The filename stem `uv build` writes, per PEP 427 and PEP 625.

        A canonical project name is dash-separated; a built artifact
        normalizes the dash to an underscore. `agnara_a2a-0.1.0a5.tar.gz` is
        therefore the correct filename for the project `agnara-a2a`, not a
        typo, and nothing in the release should "fix" it.
        """
        return re.sub(r"[-_.]+", "_", self.name).lower()


@dataclass(frozen=True, slots=True)
class Manifest:
    """The complete reviewed publication set."""

    core: str
    distributions: tuple[Distribution, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(distribution.name for distribution in self.distributions)

    @property
    def mapping(self) -> dict[str, str]:
        """Distribution name -> top-level import package, per ADR 0017."""
        return {distribution.name: distribution.import_name for distribution in self.distributions}

    @property
    def import_names(self) -> tuple[str, ...]:
        return tuple(distribution.import_name for distribution in self.distributions)

    @property
    def adapters(self) -> tuple[Distribution, ...]:
        """Everything except the kernel."""
        return tuple(
            distribution for distribution in self.distributions if distribution.name != self.core
        )

    @property
    def third_party_requirements(self) -> tuple[str, ...]:
        """Every adapter-owned third-party requirement, deduplicated.

        An installer must resolve these from the index *before* the
        first-party wheels are installed with index access closed.
        """
        seen: dict[str, None] = {}
        for distribution in self.distributions:
            for requirement in distribution.third_party_requirements:
                seen.setdefault(requirement, None)
        return tuple(seen)

    @property
    def console_scripts(self) -> tuple[str, ...]:
        return tuple(
            script for distribution in self.distributions for script in distribution.console_scripts
        )

    @property
    def publication_order(self) -> tuple[str, ...]:
        """Upload order: every sibling first, the kernel last.

        Multi-project uploads are not atomic, so some order is chosen whether
        or not anyone chooses it. Publishing `agnara` last makes the partial
        state fail closed: an adapter pins its kernel exactly, so a sibling
        published without its kernel resolves to nothing and installs for
        nobody. The reverse order -- what `0.1.0a4` did -- leaves the kernel
        advertising a version whose adapters do not exist, which installs
        cleanly and is wrong. See ADR 0079.
        """
        return (*sorted(distribution.name for distribution in self.adapters), self.core)

    def get(self, name: str) -> Distribution:
        for distribution in self.distributions:
            if distribution.name == name:
                return distribution
        raise ManifestError(f"{name!r} is not in the reviewed publication set")


def _string_tuple(value: object, *, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ManifestError(f"{where} must be a list of strings")
    return tuple(value)  # type: ignore[arg-type]


def load(workspace: Path = ROOT) -> Manifest:
    """Read and validate the reviewed publication set."""
    path = workspace / MANIFEST_RELATIVE
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ManifestError(f"cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise ManifestError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(document, dict):
        raise ManifestError(f"{path} must contain a JSON object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(
            f"{path}: unsupported schema_version {document.get('schema_version')!r}; "
            f"this tool understands {SCHEMA_VERSION}"
        )
    core = document.get("core")
    if not isinstance(core, str):
        raise ManifestError(f"{path}: 'core' must name the kernel distribution")

    entries = document.get("distributions")
    if not isinstance(entries, list) or not entries:
        raise ManifestError(f"{path}: 'distributions' must be a non-empty list")

    distributions: list[Distribution] = []
    for index, entry in enumerate(entries):
        where = f"{path}: distributions[{index}]"
        if not isinstance(entry, dict):
            raise ManifestError(f"{where} must be an object")
        name = entry.get("name")
        import_name = entry.get("import_name")
        role = entry.get("role")
        if not isinstance(name, str) or not isinstance(import_name, str):
            raise ManifestError(f"{where} must declare string 'name' and 'import_name'")
        if role not in ROLES:
            raise ManifestError(f"{where}: 'role' must be one of {sorted(ROLES)}, found {role!r}")
        distributions.append(
            Distribution(
                name=name,
                import_name=import_name,
                role=role,
                console_scripts=_string_tuple(
                    entry.get("console_scripts", []), where=f"{where}.console_scripts"
                ),
                third_party_requirements=_string_tuple(
                    entry.get("third_party_requirements", []),
                    where=f"{where}.third_party_requirements",
                ),
            )
        )

    names = [distribution.name for distribution in distributions]
    if len(names) != len(set(names)):
        raise ManifestError(f"{path}: distribution names must be unique")
    imports = [distribution.import_name for distribution in distributions]
    if len(imports) != len(set(imports)):
        raise ManifestError(f"{path}: import names must be unique")
    if names != sorted(names):
        raise ManifestError(f"{path}: distributions must be listed in canonical name order")
    if core not in names:
        raise ManifestError(f"{path}: core {core!r} is not one of the declared distributions")
    kernels = [distribution.name for distribution in distributions if distribution.role == "kernel"]
    if kernels != [core]:
        raise ManifestError(
            f"{path}: exactly one distribution may hold role 'kernel', found {kernels}"
        )

    return Manifest(core=core, distributions=tuple(distributions))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT, help=argparse.SUPPRESS)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--names", action="store_true", help="canonical project names")
    selection.add_argument("--import-names", action="store_true", help="top-level import packages")
    selection.add_argument("--artifact-stems", action="store_true", help="built filename stems")
    selection.add_argument("--count", action="store_true", help="how many distributions ship")
    selection.add_argument(
        "--third-party", action="store_true", help="adapter-owned third-party requirements"
    )
    selection.add_argument(
        "--console-scripts", action="store_true", help="installed console script names"
    )
    selection.add_argument(
        "--publication-order", action="store_true", help="upload order, kernel last"
    )
    selection.add_argument(
        "--pinned", metavar="VERSION", help="every distribution pinned to VERSION"
    )
    parser.add_argument(
        "--separator",
        default="\n",
        help="what to join the output with; defaults to one item per line",
    )
    arguments = parser.parse_args(argv)

    try:
        manifest = load(arguments.workspace.resolve())
    except ManifestError as exc:
        print(f"publication manifest refused: {exc}", file=sys.stderr)
        return 1

    if arguments.count:
        print(len(manifest.distributions))
        return 0

    items: tuple[str, ...]
    if arguments.names:
        items = manifest.names
    elif arguments.import_names:
        items = manifest.import_names
    elif arguments.artifact_stems:
        items = tuple(distribution.artifact_stem for distribution in manifest.distributions)
    elif arguments.third_party:
        items = manifest.third_party_requirements
    elif arguments.console_scripts:
        items = manifest.console_scripts
    elif arguments.publication_order:
        items = manifest.publication_order
    else:
        items = tuple(f"{name}=={arguments.pinned}" for name in manifest.names)

    separator = arguments.separator.replace("\\n", "\n").replace("\\t", "\t")
    print(separator.join(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
