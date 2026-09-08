"""The CLI writes what it computed, whatever the console's encoding is.

`docs/CLI_SPEC.md` calls the JSON output deterministic. On Windows a piped
stdout is ``cp1252`` and translates ``\\n`` to ``\\r\\n``, so a description
containing an arrow used to end the command in a `UnicodeEncodeError`
traceback and the "deterministic" document differed by platform.
"""

from __future__ import annotations

import io
import sys

import pytest

from agnara_cli._main import _emit


def _console(encoding: str) -> tuple[io.TextIOWrapper, io.BytesIO]:
    raw = io.BytesIO()
    return io.TextIOWrapper(raw, encoding=encoding, newline="\r\n", write_through=True), raw


def test_text_is_written_as_utf8_with_lf_regardless_of_the_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console, raw = _console("cp1252")
    monkeypatch.setattr(sys, "stdout", console)

    _emit('{\n  "description": "Adds two numbers \u2192 result \u2713"\n}')

    assert raw.getvalue() == (
        b'{\n  "description": "Adds two numbers \xe2\x86\x92 result \xe2\x9c\x93"\n}\n'
    )


def test_bytes_are_written_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    console, raw = _console("cp1252")
    monkeypatch.setattr(sys, "stdout", console)

    _emit(b'{"a":1}')

    assert raw.getvalue() == b'{"a":1}'


def test_nothing_is_written_for_no_output(monkeypatch: pytest.MonkeyPatch) -> None:
    console, raw = _console("utf-8")
    monkeypatch.setattr(sys, "stdout", console)

    _emit(None)

    assert raw.getvalue() == b""


def test_a_stdout_without_a_binary_layer_still_receives_the_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)

    _emit("answer")

    assert stream.getvalue() == "answer\n"
