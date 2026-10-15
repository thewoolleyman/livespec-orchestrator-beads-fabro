"""The sandbox-local tmux state must stay invisible to the run's own git worktree.

Found by the same static audit on 2026-10-14 that found the Codex home, and
the mechanism is identical: on the Petri-era engine the repository clone IS
`/workspace`, so every artifact the dispatch writes at a fixed `/workspace`
path lands INSIDE the repository, and that engine runs each prepare step as a
graph node and checkpoints after it. On the pinned engine the clone is
`/workspace/<repo>` and the same paths sit outside it, which is why this was
invisible before Petri. The siblings already routed through the shared
renderer are `bd-ib-dud2ww` (the gh-refresh bundle) and `bd-ib-ccywva` (the
credential-use guard).

WHAT MAKES THIS INSTANCE DIFFERENT FROM THOSE, and why the fixture has an
extra step. The prepare step creates the socket ROOT and writes nothing into
it; tmux populates it LATER, while the agent nodes drive, and those nodes
checkpoint too. So the prepare chain alone leaves an empty directory, which
git does not track in any case -- a case that ran the chain and stopped would
report a clean worktree before the change as readily as after it, and prove
nothing. This file therefore stands in for the tmux server the way
`test_dispatcher_dual_cred.py`'s socket-root probe does, writing the
`tmux-<uid>/default` path tmux itself resolves under `TMUX_TMPDIR`, and
measures staging after that.

THIS CASE BUILDS THE PETRI LAYOUT ON PURPOSE -- a throwaway clone whose TOP
LEVEL is the sandbox root -- because that is the only layout in which the
defect exists.

It executes the RENDERED prepare scripts for real, as
`test_dispatcher_credential_use_guard_worktree.py` does, and for the same
reason: a presence/absence assertion over the rendered text cannot tell an
exclusion that git honours from one that was written to a path git never
reads. Only `/workspace` is rebased onto `tmp_path`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

# The in-sandbox root the generated scripts are written against, rebased onto
# `tmp_path` so the generated text runs here unchanged in every other respect.
_SANDBOX_ROOT = "/workspace"
_DEFAULT_BRANCH = "master"
_RUN_BRANCH = "fabro/run/01M4YDE405RJ43GDANYZA8YDMW"
_STEP_TIMEOUT_SECONDS = 60
_ENVIRONMENT_ID = "livespec-ci"
_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    f'id = "{_ENVIRONMENT_ID}"\n'
)
# Bound to locals before being passed, so ruff's hardcoded-password rules read
# them as the fixture values they are rather than as credentials.
_FAKE_TOKEN = "livespec-fixture-oauth-token"
_FAKE_GITHUB_TOKEN = "livespec-fixture-github-token"


def test_no_checkpoint_of_a_driving_run_can_stage_the_sandbox_tmux_state(
    tmp_path: Path,
) -> None:
    """Both halves are measured: every prepare step, then the live tmux state.

    The engine checkpoints after each graph node rather than once at the end,
    so staging is measured after every prepare step. The `--allow-empty`
    commit keeps one fixture shape in both arms: once the socket root is
    invisible that checkpoint stages nothing, which is what the engine logs as
    "checkpoint skipped: no staged changes".

    The reading AFTER the stand-in tmux server is the one that can fail before
    the change -- the prepare chain leaves an empty directory, which git never
    tracks -- and it is the reading that matters, because tmux writes its
    state while the agent nodes are driving and those nodes checkpoint too.
    """
    repo = _git_repo(root=tmp_path / "workspace")
    scripts = _tmux_prepare_scripts(sandbox_root=repo)
    tmux_tmpdir = _tmux_tmpdir(sandbox_root=repo)
    _git("checkout", "-b", _RUN_BRANCH, repo=repo)

    for index, script in enumerate(scripts):
        _run_prepare_step(script=script, repo=repo)
        _git("add", "-A", repo=repo)

        assert _tmux_paths(listing=_git_stdout("diff", "--cached", "--name-only", repo=repo)) == []

        _git("commit", "--allow-empty", "-m", f"fabro checkpoint run_prepare_{index}", repo=repo)

    state = _stand_in_tmux_server_state(tmux_tmpdir=tmux_tmpdir)
    _git("add", "-A", repo=repo)

    assert _tmux_paths(listing=_git_stdout("diff", "--cached", "--name-only", repo=repo)) == []

    # Positive controls: the staging instrument was pointed at a worktree where
    # the tmux state really was present, so the empty results above are
    # measurements rather than a vacuously clean fixture.
    assert state.is_file()
    assert _tmux_paths(listing=_git_stdout("ls-files", repo=repo)) == []


def _tmux_prepare_scripts(*, sandbox_root: Path) -> list[str]:
    """The rendered prepare-step scripts that concern the tmux socket root.

    Read off the PUBLIC overlay renderer through a real TOML parse, then
    narrowed to the steps naming the socket root. The narrowing is what keeps
    this case about the tmux projection rather than about the whole prepare
    chain, whose other blocks reach the forge and the plugin cache and cannot
    run here.
    """
    document = tomli.loads(_rendered_overlay())
    steps = document.get("run", {}).get("prepare", {}).get("steps", [])
    root = _tmux_tmpdir(sandbox_root=Path(_SANDBOX_ROOT))
    scripts = [str(step["script"]) for step in steps if str(root) in str(step["script"])]
    assert scripts
    return [_rebased(text=script, sandbox_root=sandbox_root) for script in scripts]


def _tmux_tmpdir(*, sandbox_root: Path) -> Path:
    """The projected socket root, read off the rendered env table's TMUX_TMPDIR.

    Derived rather than written out, so a path change cannot leave this file
    measuring a directory no dispatch projects -- and `TMUX_TMPDIR` is the
    variable tmux itself resolves its sockets under, so this is the same value
    the sandbox's tmux reads.
    """
    _, env_table = _rendered_overlay().split(f"[environments.{_ENVIRONMENT_ID}.env]", 1)
    table = tomli.loads(env_table)
    return Path(_rebased(text=str(table["TMUX_TMPDIR"]), sandbox_root=sandbox_root))


def _rendered_overlay() -> str:
    """The dispatch-time overlay, rendered by the production builder."""
    token = _FAKE_TOKEN
    github_token = _FAKE_GITHUB_TOKEN
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=Path(_SANDBOX_ROOT),
        token=token,
        github_token=github_token,
        siblings=None,
    )
    assert rendered is not None
    return rendered


def _stand_in_tmux_server_state(*, tmux_tmpdir: Path) -> Path:
    """Write the state a tmux server leaves under `TMUX_TMPDIR`.

    tmux appends `tmux-<uid>/default` below the root the prepare step created,
    which is the layout the sibling socket-root probe in
    `test_dispatcher_dual_cred.py` also stands in for. A regular file stands in
    for the socket: git stages a regular file and never a socket, so the
    regular file is the shape that can actually reach a checkpoint -- and it is
    also what tmux's server log looks like when a run enables one.
    """
    state = tmux_tmpdir / f"tmux-{os.getuid()}" / "default"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("sandbox tmux server state\n", encoding="utf-8")
    return state


def _tmux_paths(*, listing: str) -> list[str]:
    """The listed worktree-relative paths that belong to the tmux socket root.

    Keyed on the root's top path SEGMENT, because the root is a directory the
    tmux server populates rather than one file a step writes: there is no
    narrower path a step could name, and anything tmux puts under it is as
    committable as the directory itself.
    """
    segment = _tmux_tmpdir(sandbox_root=Path(_SANDBOX_ROOT)).name
    return [path for path in listing.splitlines() if path.split("/")[0] == segment]


def _rebased(*, text: str, sandbox_root: Path) -> str:
    """Point the generated text at this case's sandbox root."""
    return text.replace(_SANDBOX_ROOT, str(sandbox_root))


def _git_repo(*, root: Path) -> Path:
    """A throwaway clone whose TOP LEVEL is the sandbox root.

    This is the Petri-era layout, and building it is the whole point of this
    file: on the pinned engine the clone sits one directory below the sandbox
    root and the socket root was never inside it.
    """
    root.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--initial-branch", _DEFAULT_BRANCH],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    _git("config", "user.email", "fixture@example.invalid", repo=root)
    _git("config", "user.name", "Fixture", repo=root)
    (root / "tracked.txt").write_text("the repository's own content\n", encoding="utf-8")
    _git("add", "tracked.txt", repo=root)
    _git("commit", "-m", "add tracked.txt", repo=root)
    return root


def _git(*argv: str, repo: Path) -> None:
    subprocess.run(["git", *argv], cwd=repo, capture_output=True, text=True, check=True)


def _git_stdout(*argv: str, repo: Path) -> str:
    completed = subprocess.run(
        ["git", *argv],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _run_prepare_step(*, script: str, repo: Path) -> None:
    """Execute ONE rendered prepare step the way the engine's shell does."""
    step = subprocess.run(
        ["/bin/sh", "-c", script],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=_STEP_TIMEOUT_SECONDS,
        check=False,
    )

    assert step.returncode == 0, f"{script}\n{step.stdout}\n{step.stderr}"
