"""Refuse publication unless an annotated version tag names reviewed main history."""

from __future__ import annotations

import argparse
import subprocess


def verify(tag: str) -> None:
    if not tag.startswith("v") or any(character.isspace() for character in tag):
        raise ValueError("release tag must start with v and contain no whitespace")
    ref = f"refs/tags/{tag}"

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments], check=True, capture_output=True, text=True
        ).stdout.strip()

    if git("cat-file", "-t", ref) != "tag":
        raise ValueError("release tag must be annotated")
    commit = git("rev-parse", "--verify", f"{ref}^{{commit}}")
    if commit != git("rev-parse", "HEAD"):
        raise ValueError("checkout does not match the release tag")
    git("merge-base", "--is-ancestor", commit, "refs/remotes/origin/main")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    arguments = parser.parse_args()
    try:
        verify(arguments.tag)
    except (ValueError, subprocess.CalledProcessError) as error:
        print(f"release tag refused: {error}")
        return 1
    print(f"verified annotated {arguments.tag} at HEAD in origin/main history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
