"""The helper-delivery prepare step is executable in a governed sandbox."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_stage_scripts as stage_scripts
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stage_scripts import (
    stage_scripts_prepare_steps_block,
)

from tests.prepare_step_support import runnable_script, steps_in

_PLUGIN_ROOT = Path(dispatcher.__file__).resolve().parents[3]
_WORKFLOW_DIR = _PLUGIN_ROOT / ".fabro" / "workflows" / "implement-work-item"
_STAGES = _WORKFLOW_DIR / "stages"
_SHA = "a" * 40
_UPSTREAM = "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git"


def test_stage_script_prepare_step_fetches_committed_files_without_plugin_import(
    tmp_path: Path,
) -> None:
    """A plain shell plus Git delivers byte-identical files to a clean sandbox."""
    source = tmp_path / "source"
    _ = subprocess.run(["git", "init", "-q", str(source)], check=True)
    target = source / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "stages"
    target.mkdir(parents=True)
    for committed in _STAGES.glob("*.sh"):
        _ = (target / committed.name).write_bytes(committed.read_bytes())
    _ = subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    _ = subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "stage scripts",
        ],
        check=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, check=True, text=True
    ).stdout.strip()
    bare = tmp_path / "source.git"
    _ = subprocess.run(["git", "clone", "-q", "--bare", str(source), str(bare)], check=True)
    rendered = render_run_config_overlay(
        committed_text=(_WORKFLOW_DIR / "workflow.toml").read_text(),
        workflow_dir=_WORKFLOW_DIR,
        token=sha,
        github_token="",
        siblings=None,
        stage_scripts_build_sha=sha,
    )
    assert rendered is not None
    assert len(rendered.encode()) <= 471_859
    step = next(
        step for step in steps_in(block=rendered) if "/livespec-stage-scripts.git" in step.script
    )
    script = runnable_script(step=step).replace(_UPSTREAM, bare.as_uri())
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    done = subprocess.run(
        ["sh", "-c", script], cwd=sandbox, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    for committed in _STAGES.glob("*.sh"):
        assert (
            Path("/livespec-stage-scripts") / committed.name
        ).read_bytes() == committed.read_bytes()


def test_stage_script_prepare_step_refuses_an_unresolved_build() -> None:
    """No fallback to master can silently mismatch the graph and stage files."""
    assert stage_scripts_prepare_steps_block(build_sha=None) is None
    assert stage_scripts_prepare_steps_block(build_sha="bad") is None


def test_full_overlay_refuses_when_the_build_cannot_be_resolved() -> None:
    """A dispatch never silently fetches stage files from an unrelated ref."""
    assert (
        render_run_config_overlay(
            committed_text=(_WORKFLOW_DIR / "workflow.toml").read_text(),
            workflow_dir=_WORKFLOW_DIR,
            token="",
            github_token="",
            siblings=None,
            stage_scripts_build_sha=None,
        )
        is None
    )


def test_stage_scripts_build_sha_comes_from_the_matching_installed_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cache entry pins helper delivery to the build that rendered the graph."""
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    home = tmp_path / "home"
    registry = home / ".claude" / "plugins" / "installed_plugins.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "plugins": {
                    "livespec-orchestrator-beads-fabro@test": [
                        {"installPath": str(plugin), "gitCommitSha": _SHA}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(stage_scripts, "plugin_root", lambda: plugin)
    monkeypatch.setattr(stage_scripts.Path, "home", lambda: home)

    assert stage_scripts.resolve_stage_scripts_build_sha() == _SHA
