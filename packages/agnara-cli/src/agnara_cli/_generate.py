"""The plan-then-apply mechanism every Agnara generator uses.

AGENTS.md requires generators to support dry-run, be deterministic, refuse
overwrite by default, run non-interactively, expose machine-readable output and
never silently delete modified files. Those properties are hard to retrofit onto
code that writes as it decides, so generation is split in two: a plan built
without touching the filesystem, and an apply step that writes it.

Everything a caller needs to review a run — what will be created, what already
exists, whether anything conflicts — is answerable from the plan alone. That is
what makes ``--dry-run`` honest rather than a second code path that might
disagree with the real one. See ADR 0060.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

__all__ = [
    "FileAction",
    "GenerationError",
    "GenerationPlan",
    "apply_plan",
    "build_plan",
    "plan_json",
    "render_plan",
]

#: The declared JSON shape of a plan, so automation can detect a change rather
#: than discover one.
FORMAT_VERSION = 1


class GenerationError(Exception):
    """A generator cannot proceed.

    Carries a caller-facing diagnostic. The CLI prints it as one line; it never
    lets a filesystem failure reach the operator as a traceback.
    """


@dataclass(frozen=True, slots=True)
class FileAction:
    """One file a plan would write, and whether something is already there.

    ``intended_update`` separates the two reasons a file can already exist. A
    generator that means to edit project metadata — ``agnara app create``
    adding a table to ``agnara.toml`` — declares that intent, and the existing
    file is not a conflict. A file the generator meant to create and found
    already there is a conflict, and is refused.
    """

    path: PurePosixPath
    contents: str
    exists: bool
    intended_update: bool = False

    @property
    def verb(self) -> str:
        """`docs/CLI_SPEC.md` renders a plan as CREATE and UPDATE lines."""
        return "UPDATE" if self.exists or self.intended_update else "CREATE"

    @property
    def is_conflict(self) -> bool:
        """An existing file this action was not authorized to replace."""
        return self.exists and not self.intended_update


@dataclass(frozen=True, slots=True)
class GenerationPlan:
    """Everything one generator run would write, in deterministic order."""

    root: Path
    actions: tuple[FileAction, ...]

    @property
    def conflicts(self) -> tuple[FileAction, ...]:
        """Actions that would replace an existing file without authorization."""
        return tuple(action for action in self.actions if action.is_conflict)

    def resolve(self, action: FileAction) -> Path:
        """The absolute path one action writes to."""
        return self.root.joinpath(*action.path.parts)


def build_plan(
    root: Path,
    files: dict[str, str],
    *,
    updates: Iterable[str] = (),
) -> GenerationPlan:
    """Turn rendered file contents into a plan, sorted for determinism.

    Sorting by path is what makes two runs with the same inputs produce the
    same plan, the same rendering and the same JSON, regardless of the order a
    template happened to build its mapping in.

    ``updates`` names the paths the generator intends to rewrite, so an edit to
    project metadata is not reported as a conflict with itself.
    """
    intended = set(updates)
    unknown = sorted(intended - set(files))
    if unknown:
        raise GenerationError(f"declared an update for a file it does not write: {unknown}")
    actions = []
    for relative in sorted(files):
        path = PurePosixPath(relative)
        if path.is_absolute() or any(part == ".." for part in path.parts):
            raise GenerationError(f"refusing to generate outside the target: {relative!r}")
        target = root.joinpath(*path.parts)
        actions.append(
            FileAction(
                path=path,
                contents=files[relative],
                exists=target.exists(),
                intended_update=relative in intended,
            )
        )
    return GenerationPlan(root=root, actions=tuple(actions))


def render_plan(plan: GenerationPlan) -> str:
    """Render a plan the way `docs/CLI_SPEC.md` shows a dry run."""
    lines = [f"{action.verb} {plan.root.name}/{action.path}" for action in plan.actions]
    conflicts = plan.conflicts
    if conflicts:
        lines.append("")
        lines.append(
            f"{len(conflicts)} existing file(s) would be replaced; pass --overwrite to allow it"
        )
    return "\n".join(lines)


def plan_json(plan: GenerationPlan) -> dict[str, object]:
    """The same plan, for automation rather than a reader."""
    return {
        "format_version": FORMAT_VERSION,
        "root": plan.root.as_posix(),
        "files": [
            {
                "path": str(action.path),
                "action": action.verb.lower(),
                "exists": action.exists,
                "intended_update": action.intended_update,
            }
            for action in plan.actions
        ],
        "conflicts": [str(action.path) for action in plan.conflicts],
    }


def apply_plan(plan: GenerationPlan, *, overwrite: bool = False) -> GenerationPlan:
    """Write a plan, or refuse before writing anything.

    Conflicts are checked against the whole plan first. A run that would
    replace a file the operator did not authorize must leave the directory
    exactly as it was, not half-written, so the refusal happens before the
    first ``write_text``.
    """
    conflicts = plan.conflicts
    if conflicts and not overwrite:
        listed = ", ".join(str(action.path) for action in conflicts)
        raise GenerationError(
            f"refusing to replace existing file(s) in {plan.root}: {listed}. "
            "Pass --overwrite to allow it."
        )
    for action in plan.actions:
        target = plan.resolve(action)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # newline="\n" so a generated file is byte-identical on every
            # platform; a project is shared, and its line endings are its own
            # decision rather than that of the machine that created it.
            target.write_text(action.contents, encoding="utf-8", newline="\n")
        except OSError as error:
            raise GenerationError(f"cannot write {target}: {error}") from error
    return plan
