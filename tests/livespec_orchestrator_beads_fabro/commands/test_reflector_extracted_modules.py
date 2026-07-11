from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _reflector_runtime as runtime
from livespec_orchestrator_beads_fabro.commands._reflector_lessons import (
    _lesson_slug,  # pyright: ignore[reportPrivateUsage]
)


def test_runtime_resolve_claude_path_covers_override_and_found_binary(
    monkeypatch,
) -> None:
    assert (
        runtime.resolve_claude_path(environ={"LIVESPEC_REFLECTOR_CLAUDE_PATH": "/opt/claude"})
        == "/opt/claude"
    )
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: "/usr/bin/claude")
    assert runtime.resolve_claude_path(environ={}) == "/usr/bin/claude"


def test_runtime_resolve_claude_path_covers_local_bin_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: None)
    fake_claude = tmp_path / "claude"
    _ = fake_claude.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(runtime, "_CLAUDE_LOCAL_BIN_FALLBACK", str(fake_claude))
    assert runtime.resolve_claude_path(environ={}) == str(fake_claude)


def test_lesson_slug_is_stable_and_normalizes_body_whitespace(tmp_path: Path) -> None:
    first = _lesson_slug(title="t", repo=tmp_path, body="Body   Text")
    second = _lesson_slug(title="t", repo=tmp_path, body="body text")
    assert first == second
    assert len(first) == 12
    assert all(ch in "0123456789abcdef" for ch in first)
