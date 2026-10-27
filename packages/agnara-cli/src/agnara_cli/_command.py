"""Private command output for diagnostics with an explicit exit status."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandResult:
    output: str
    exit_code: int
