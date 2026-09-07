"""The archive sweep's gitignore resolution, at its two defensive edges.

Both are exercised through the PUBLIC sweep rather than the private helper, so
these assert the behaviour an archiving session actually gets.

Both edges fail toward REPORTING a reference rather than hiding one, which is
the direction that matters: a sweep that silently dropped hits when git was
unavailable would let a real red-pull-request reference through unseen.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_MODULE = "livespec_orchestrator_beads_fabro.commands._plan_archive_gates"


def _write(*, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def test_a_tree_with_nothing_to_sweep_reports_no_references(tmp_path: Path) -> None:
    gates = importlib.import_module(_MODULE)
    _write(path=tmp_path / "plan" / "some-plan" / "research" / "001.md", text="notes\n")

    assert gates.outside_plan_path_references(project_root=tmp_path, slug="some-plan") == ()


def test_an_unavailable_git_still_reports_a_real_reference(
    tmp_path: Path, monkeypatch: Any
) -> None:
    gates = importlib.import_module(_MODULE)
    _write(path=tmp_path / "plan" / "some-plan" / "research" / "001.md", text="notes\n")
    _write(path=tmp_path / "workflows" / "w.toml", text="# see plan/some-plan/research/001.md\n")

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise OSError("git not found")

    monkeypatch.setattr(gates.subprocess, "run", _raise)

    hits = gates.outside_plan_path_references(project_root=tmp_path, slug="some-plan")

    assert hits == ("workflows/w.toml",), hits
