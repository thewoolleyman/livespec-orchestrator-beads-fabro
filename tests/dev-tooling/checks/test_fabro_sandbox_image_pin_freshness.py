"""Tests for the Fabro sandbox image pin lockstep check."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "fabro_sandbox_image_pin_freshness.py"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "fabro_sandbox_image_pin_freshness_under_test", _CHECK_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CHECK = _load_check()


def _write_repo(*, root: Path, dev_tooling_tag: str, image_tag: str) -> None:
    _ = (root / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item").mkdir(
        parents=True
    )
    _ = (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.uv.sources]",
                (
                    "livespec-dev-tooling = { git = "
                    '"https://github.com/thewoolleyman/livespec-dev-tooling.git", '
                    f'tag = "{dev_tooling_tag}" }}'
                ),
            ]
        ),
        encoding="utf-8",
    )
    _ = (
        root / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
    ).write_text(
        "\n".join(
            [
                "[environments.livespec-ci.image]",
                f'docker = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:{image_tag}"',
            ]
        ),
        encoding="utf-8",
    )


def test_matching_dev_tooling_and_sandbox_image_tags_passes(monkeypatch, tmp_path: Path) -> None:
    _write_repo(root=tmp_path, dev_tooling_tag="v0.33.5", image_tag="v0.33.5")
    monkeypatch.chdir(tmp_path)
    assert _CHECK.main() == 0


def test_mismatched_tags_fail_and_report_lockstep(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _write_repo(root=tmp_path, dev_tooling_tag="v0.33.5", image_tag="sha-ea684ad")
    monkeypatch.chdir(tmp_path)
    assert _CHECK.main() == 1
    record = json.loads(capsys.readouterr().err.splitlines()[-1])
    assert record["event"] == (
        "fabro sandbox image tag is out of lockstep with the livespec-dev-tooling pin"
    )
    assert "does not verify release shipped or factory rollout" in record["scope"]
