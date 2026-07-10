"""Edge tests for the Fabro sandbox image pin lockstep check."""

from __future__ import annotations

import importlib.util
import runpy
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "fabro_sandbox_image_pin_freshness.py"
_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "fabro_sandbox_image_pin_freshness_edges_under_test", _CHECK_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CHECK = _load_check()


def _write_pyproject(*, root: Path, text: str) -> None:
    _ = (root / "pyproject.toml").write_text(text, encoding="utf-8")


def _write_workflow(*, root: Path, image_tag: str) -> None:
    workflow_dir = root / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
    _ = workflow_dir.mkdir(parents=True)
    _ = (workflow_dir / "workflow.toml").write_text(
        f'docker = "{_IMAGE}:{image_tag}"', encoding="utf-8"
    )


def test_missing_workflow_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_pyproject(
        root=tmp_path,
        text=(
            "[tool.uv.sources]\n"
            'livespec-dev-tooling = { git = "https://github.com/thewoolleyman/livespec-dev-tooling.git", tag = "v0.33.5" }'
        ),
    )
    monkeypatch.chdir(tmp_path)
    assert _CHECK.main() == 1


def test_missing_pyproject_pin_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_pyproject(root=tmp_path, text="[tool.uv.sources]\n")
    _write_workflow(root=tmp_path, image_tag="v0.33.5")
    monkeypatch.chdir(tmp_path)
    assert _CHECK.main() == 1


def test_main_guard_exits_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_pyproject(
        root=tmp_path,
        text=(
            "[tool.uv.sources]\n"
            'livespec-dev-tooling = { git = "https://github.com/thewoolleyman/livespec-dev-tooling.git", tag = "v0.33.5" }'
        ),
    )
    _write_workflow(root=tmp_path, image_tag="v0.33.5")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as raised:
        _ = runpy.run_path(str(_CHECK_PATH), run_name="__main__")
    assert raised.value.code == 0
