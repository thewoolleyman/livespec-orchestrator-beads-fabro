"""A janitor refresh onto the default branch re-takes the sandbox's sibling clones.

Work-item `bd-ib-rzkhqv`, `SPECIFICATION/contracts.md` section "Self-contained
plugin dispatch" paragraph "A sandbox runs its tools from pinned clones and works
in the latest clones" (work clones are the default branch's latest commit).

MEASURED CAUSE. Run 01M6Y1Q7ZFWZ of work-item bd-ib-bacahf checked a tree taken
from a moved default branch against a `livespec` sibling cloned at run start,
before that sibling's fix released, and failed with a RecursionError the released
sibling no longer had. The prepare chain clones each sibling once; nothing
re-cloned it when the janitor refreshed the tree.

The shipped `janitor` node bytes (taken through `parse_dot_graph`) are EXECUTED by
`sh` against real throwaway repositories, because the re-clone is shell and a
substring assertion cannot tell a step that runs from one behind an earlier
`exit`. Siblings are real git repositories reached through `file://` URLs (a
plain path makes git ignore `--depth`). Three controls carry the module: a
sibling whose release landed AFTER the clone is the positive case, an
unreachable or un-cloneable sibling must keep its previous clone while the
output names it and the reason, and a janitor that never refreshes must leave
every sibling at its run-start commit.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_DEFAULT_BRANCH = "master"
_SIBLING = "livespec"
_OTHER_SIBLING = "livespec-dev-tooling"


def _git(*argv: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        check=True,
        capture_output=True,
        cwd=cwd,
        text=True,
    )


def _head(*, cwd: Path) -> str:
    return _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()


def _commit(*, cwd: Path, path: str, text: str, subject: str) -> str:
    target = cwd / path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")
    _ = _git("add", path, cwd=cwd)
    _ = _git("commit", "-m", subject, cwd=cwd)
    return _head(cwd=cwd)


def _janitor_script() -> str:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script: str = graph.nodes["janitor"]["script"]
    return (
        script.replace("{{ inputs.default_branch }}", _DEFAULT_BRANCH)
        .replace("{{ inputs.sandbox_check_suite }}", "true")
        .replace(r"\"", '"')
    )


def _identified(*, cwd: Path) -> None:
    _ = _git("config", "user.name", "Test", cwd=cwd)
    _ = _git("config", "user.email", "test@example.invalid", cwd=cwd)


def _origin_with_seed(*, root: Path, name: str) -> tuple[Path, Path]:
    """A bare origin plus the working clone that publishes to it."""
    origin = root / f"{name}-origin.git"
    _ = _git("init", "--bare", f"--initial-branch={_DEFAULT_BRANCH}", str(origin), cwd=root)
    seed = root / f"{name}-seed"
    seed.mkdir()
    _ = _git("init", f"--initial-branch={_DEFAULT_BRANCH}", cwd=seed)
    _identified(cwd=seed)
    _ = _commit(cwd=seed, path="base.txt", text="base\n", subject="chore: seed")
    _ = _git("remote", "add", "origin", str(origin), cwd=seed)
    _ = _git("push", "-u", "origin", _DEFAULT_BRANCH, cwd=seed)
    return origin, seed


def _advance(*, seed: Path, text: str) -> str:
    sha = _commit(cwd=seed, path="release.txt", text=text, subject=f"release: {text.strip()}")
    _ = _git("push", "origin", _DEFAULT_BRANCH, cwd=seed)
    return sha


def _sandbox_sibling(*, root: Path, clones: Path, name: str) -> tuple[Path, Path, Path]:
    """A sibling origin, its run-start clone under `clones`, and its publishing seed."""
    origin, seed = _origin_with_seed(root=root, name=name)
    clone = clones / name
    _ = _git("clone", "--quiet", "--depth", "1", origin.as_uri(), str(clone), cwd=root)
    return origin, seed, clone


def _run_world(*, root: Path) -> Path:
    """The run's own clone, behind a default branch that has since moved."""
    origin, seed = _origin_with_seed(root=root, name="target")
    run = root / "run"
    _ = _git("clone", str(origin), str(run), cwd=root)
    _identified(cwd=run)
    _ = _git("switch", "-c", "fabro/run/test", cwd=run)
    _ = _commit(cwd=run, path="run.txt", text="run\n", subject="feat: run work")
    _ = _advance(seed=seed, text="target moved\n")
    return run


def _plugins(*, root: Path) -> Path:
    plugins = root / "plugins"
    plugins.mkdir()
    gate = plugins / "livespec-run-plugin-gate.py"
    _ = gate.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    _ = gate.chmod(gate.stat().st_mode | stat.S_IXUSR)
    return plugins


def _janitor(
    *, run: Path, plugins: Path, clones: Path, path_prefix: Path | None = None
) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
    }
    if path_prefix is not None:
        environment["PATH"] = f"{path_prefix}{os.pathsep}{environment['PATH']}"
    return subprocess.run(
        ["sh", "-c", _janitor_script()],
        check=False,
        capture_output=True,
        cwd=run,
        env=environment
        | {
            "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins),
            "LIVESPEC_SIBLING_CLONES_ROOT": str(clones),
        },
        text=True,
    )


def test_a_refresh_retakes_each_sibling_at_its_default_branch_tip_as_of_the_refresh(
    *, tmp_path: Path
) -> None:
    """A sibling released after the run started is at its new tip once the janitor refreshed."""
    run = _run_world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    clones = tmp_path / "siblings"
    clones.mkdir()
    _, seed, clone = _sandbox_sibling(root=tmp_path, clones=clones, name=_SIBLING)
    _, other_seed, other_clone = _sandbox_sibling(root=tmp_path, clones=clones, name=_OTHER_SIBLING)
    at_run_start = _head(cwd=clone)
    released = _advance(seed=seed, text="0.47.1\n")
    other_released = _advance(seed=other_seed, text="0.9.9\n")
    assert released != at_run_start
    assert _head(cwd=clone) == at_run_start

    result = _janitor(run=run, plugins=plugins, clones=clones)

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_JANITOR_REFRESH:" in result.stderr
    assert _head(cwd=clone) == released
    assert _head(cwd=other_clone) == other_released
    assert (clone / "release.txt").read_text(encoding="utf-8") == "0.47.1\n"
    assert sorted(entry.name for entry in clones.iterdir()) == sorted((_SIBLING, _OTHER_SIBLING))


def test_a_sibling_the_refresh_cannot_reach_keeps_its_clone_and_is_named(*, tmp_path: Path) -> None:
    """An unreachable sibling is named with its reason; its neighbour is still re-taken."""
    run = _run_world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    clones = tmp_path / "siblings"
    clones.mkdir()
    origin, _, clone = _sandbox_sibling(root=tmp_path, clones=clones, name=_SIBLING)
    _, other_seed, other_clone = _sandbox_sibling(root=tmp_path, clones=clones, name=_OTHER_SIBLING)
    kept = _head(cwd=clone)
    other_released = _advance(seed=other_seed, text="0.9.9\n")
    _ = origin.rename(tmp_path / "gone.git")

    result = _janitor(run=run, plugins=plugins, clones=clones)

    assert result.returncode == 0, result.stderr
    assert _head(cwd=clone) == kept
    assert (clone / ".git").is_dir()
    assert _head(cwd=other_clone) == other_released
    skipped = [line for line in result.stderr.splitlines() if "sibling re-clone skipped" in line]
    assert len(skipped) == 1, result.stderr
    assert f"for {_SIBLING}: repository not reachable (nonexistent or no access)" in skipped[0]


def test_a_sibling_whose_clone_fails_after_a_reachable_probe_keeps_its_clone(
    *, tmp_path: Path
) -> None:
    """The transient arm reads as the run-start step's does, and leaves no scratch directory."""
    run = _run_world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    clones = tmp_path / "siblings"
    clones.mkdir()
    _, seed, clone = _sandbox_sibling(root=tmp_path, clones=clones, name=_SIBLING)
    kept = _head(cwd=clone)
    _ = _advance(seed=seed, text="0.47.1\n")
    shim = tmp_path / "shim"
    shim.mkdir()
    real_git = subprocess.run(
        ["sh", "-c", "command -v git"], check=True, capture_output=True, text=True
    ).stdout.strip()
    wrapper = shim / "git"
    _ = wrapper.write_text(
        f'#!/bin/sh\ntest "$1" = clone && exit 1\nexec {real_git} "$@"\n',
        encoding="utf-8",
    )
    _ = wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)

    result = _janitor(run=run, plugins=plugins, clones=clones, path_prefix=shim)

    assert result.returncode == 0, result.stderr
    assert _head(cwd=clone) == kept
    skipped = [line for line in result.stderr.splitlines() if "sibling re-clone skipped" in line]
    assert len(skipped) == 1, result.stderr
    assert (
        f"for {_SIBLING}: clone failed after a successful reachability probe (transient)"
        in skipped[0]
    )
    assert [entry.name for entry in clones.iterdir()] == [_SIBLING]


def test_a_janitor_that_never_refreshes_keeps_the_run_start_sibling_clones(
    *, tmp_path: Path
) -> None:
    """When the default branch cannot be fetched there is no refresh and no re-clone."""
    run = _run_world(root=tmp_path)
    plugins = _plugins(root=tmp_path)
    clones = tmp_path / "siblings"
    clones.mkdir()
    _, seed, clone = _sandbox_sibling(root=tmp_path, clones=clones, name=_SIBLING)
    kept = _head(cwd=clone)
    released = _advance(seed=seed, text="0.47.1\n")
    assert released != kept
    _ = _git("remote", "set-url", "origin", str(tmp_path / "nowhere.git"), cwd=run)

    result = _janitor(run=run, plugins=plugins, clones=clones)

    assert result.returncode != 0
    assert "LIVESPEC_JANITOR_REFRESH_FAILED" in result.stderr
    assert _head(cwd=clone) == kept
    assert "sibling re-clone" not in result.stderr
