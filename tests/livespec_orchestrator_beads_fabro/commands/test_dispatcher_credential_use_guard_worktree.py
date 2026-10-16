"""The credential-use guard must stay invisible to the run's own git worktree.

Measured 2026-10-14 on hp-candidate canary 11, run
01M4XNM4BBMYFPQDA6X5JCBDYM (fabro 0.382.0-nightly.0 adeefec): the review
stage reported that the run's branch carried
`.livespec/credential-use-guard.sh`, 286 lines the implementer never
wrote. Checkpoint `run_prepare_33` committed it (b4a09ea4), so it landed
in draft pull request 2977's diff against master.

The cause is a LAYOUT difference and not a bug in the guard. The guard
is installed at the fixed path `/workspace/.livespec/credential-use-guard.sh`.
On the pinned engine the repository clone is `/workspace/<repo>`, so
`/workspace/.livespec` sits OUTSIDE the clone and nothing git does can
reach it. On the Petri-era engine the clone IS `/workspace`, so the same
path lands inside the repository -- and that engine runs each prepare
step as a graph node and checkpoints after it, which commits every
change the step left in the worktree.

This is the sibling of `bd-ib-dud2ww`, the gh-refresh bundle, which was
already excluded; the guard file was not covered.

THESE CASES BUILD THE PETRI LAYOUT ON PURPOSE -- a throwaway clone whose
TOP LEVEL is the sandbox root -- because that is the only layout in which
the defect exists. A fixture whose clone sits one directory below the
sandbox root reproduces the PINNED engine, where the guard was never
committable, so it would pass before the change and prove nothing.

They execute the RENDERED prepare scripts for real, as
`test_dispatcher_credential_use_projection.py` does, and for the same
reason: a presence/absence assertion over the rendered text cannot tell
an exclusion that git honours from one that was written to a path git
never reads. Only `/workspace` is rebased onto `tmp_path`.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_EXPIRY_ENV_VAR,
    CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    CREDENTIAL_USE_UNPROTECTED_ENV_VAR,
    GUARD_SCRIPT_PATH,
    guarded_acp_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_projection import (
    CredentialUseProjection,
    credential_use_env_lines,
    credential_use_guard_prepare_steps_block,
)

# The in-sandbox root the generated scripts are written against, rebased onto
# `tmp_path` so the generated text runs here unchanged in every other respect.
_SANDBOX_ROOT = "/workspace"
_DEFAULT_BRANCH = "master"
_RUN_BRANCH = "fabro/run/01M4XNM4BBMYFPQDA6X5JCBDYM"
# The worktree-relative spelling of the guard, derived from the production
# constant rather than written out, so a path change cannot leave this file
# measuring a path no dispatch installs.
_GUARD_RELPATH = GUARD_SCRIPT_PATH.removeprefix(f"{_SANDBOX_ROOT}/")
_GUARD_TOP_SEGMENT = _GUARD_RELPATH.split("/")[0]
_STEP_TIMEOUT_SECONDS = 60


def test_no_checkpoint_of_the_prepare_chain_can_stage_the_credential_use_guard(
    tmp_path: Path,
) -> None:
    """Every prepare step is a checkpoint, so EVERY step must be covered.

    The engine checkpoints after each graph node rather than once at the
    end of the chain, so staging is measured after every step. The
    `--allow-empty` commit keeps one fixture shape in both arms: once the
    guard is invisible that checkpoint stages nothing, which is what the
    engine logs as "checkpoint skipped: no staged changes".
    """
    repo = _git_repo(root=tmp_path / "workspace")
    scripts = _rendered_prepare_scripts(sandbox_root=repo)
    env = _rendered_env(sandbox_root=repo)
    _git("checkout", "-b", _RUN_BRANCH, repo=repo)

    for index, script in enumerate(scripts):
        _run_prepare_step(script=script, env=env, repo=repo)
        _git("add", "-A", repo=repo)

        assert _guard_paths(_git_stdout("diff", "--cached", "--name-only", repo=repo)) == []

        _git("commit", "--allow-empty", "-m", f"fabro checkpoint run_prepare_{index}", repo=repo)

    # Positive controls: the staging instrument was pointed at a worktree
    # where the guard really was installed, so the empty results above are
    # measurements rather than a vacuously clean fixture.
    assert (repo / _GUARD_RELPATH).is_file()
    assert _guard_paths(_git_stdout("ls-files", repo=repo)) == []


def test_a_run_branch_rebase_is_not_blocked_by_the_credential_use_guard(
    tmp_path: Path,
) -> None:
    """`publish_draft`'s refresh must replay the run onto the default tip.

    The collision the sibling incident recorded needs two things at once:
    a replayed commit that ADDS the guard, and the guard PRESENT and
    untracked in the worktree the rebase runs in. Both are ordinary -- the
    first is an engine checkpoint, the second is what the prepare chain
    leaves behind in every sandbox -- so the fixture builds exactly that
    and asserts the refresh completes.
    """
    repo = _git_repo(root=tmp_path / "workspace")
    scripts = _rendered_prepare_scripts(sandbox_root=repo)
    env = _rendered_env(sandbox_root=repo)

    _git("checkout", "-b", _RUN_BRANCH, repo=repo)
    _run_prepare_chain(scripts=scripts, env=env, repo=repo)
    _git("add", "-A", repo=repo)
    _git("commit", "--allow-empty", "-m", "fabro checkpoint run_prepare_33", repo=repo)
    _commit_file(repo=repo, name="product.txt", body="the run's own work\n")

    # The default branch moves while the run is in flight, so the refresh
    # has something to replay onto.
    _git("checkout", _DEFAULT_BRANCH, repo=repo)
    _commit_file(repo=repo, name="default.txt", body="a later default-branch commit\n")
    # And the prepare chain has installed the guard into the worktree the
    # refresh rebases in.
    _run_prepare_chain(scripts=scripts, env=env, repo=repo)

    rebase = subprocess.run(
        ["git", "rebase", _DEFAULT_BRANCH, _RUN_BRANCH],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=_STEP_TIMEOUT_SECONDS,
        check=False,
    )

    assert rebase.returncode == 0, rebase.stderr


def test_the_installed_guard_still_starts_a_coding_agent(tmp_path: Path) -> None:
    """Hiding the guard from git must not hide it from the launch.

    This is the preservation half of the change, and it cannot fail before
    the change: the guard already launched agents. It is asserted here so a
    later edit that hides the guard by MOVING or REMOVING it -- which would
    satisfy the invisibility assertions just as well -- is caught.
    """
    repo = _git_repo(root=tmp_path / "workspace")
    scripts = _rendered_prepare_scripts(sandbox_root=repo)
    env = _rendered_env(sandbox_root=repo)
    marker = tmp_path / "agent-ran"
    _run_prepare_chain(scripts=scripts, env=env, repo=repo)

    guard_on_disk = repo / _GUARD_RELPATH
    assert guard_on_disk.stat().st_size > 0
    # The launch route the engine execs, with only the sandbox root rebased:
    # the agent stand-in starts through the guard or not at all.
    argv = [
        _rebased(text=token, sandbox_root=repo)
        for token in guarded_acp_command(
            argv=["/bin/sh", "-c", f"printf done > {marker}"],
        )
    ]
    launched = subprocess.run(
        argv,
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=_STEP_TIMEOUT_SECONDS,
        env=env,
        check=False,
    )

    assert launched.returncode == 0, launched.stderr
    assert marker.read_text(encoding="utf-8") == "done"


def _projection() -> CredentialUseProjection:
    """A protected dispatch with ample runway on both quantities.

    Both figures are future and the requirement is well under the
    credential's remaining lifetime, so the startup check admits. A refusal
    in any case here would therefore be about the exclusion rather than
    about a shortfall the guard is right to report.
    """
    now = int(time.time())
    return CredentialUseProjection(
        deadline_epoch=now + 3600,
        credential_expiry_epoch=now + 7200,
        required_remaining_seconds=60,
    )


def _rendered_prepare_scripts(*, sandbox_root: Path) -> list[str]:
    """Every prepare-step script the credential-use block emits, in order."""
    document = tomli.loads(credential_use_guard_prepare_steps_block(projection=_projection()))
    steps = document.get("run", {}).get("prepare", {}).get("steps", [])
    assert steps
    return [_rebased(text=str(step["script"]), sandbox_root=sandbox_root) for step in steps]


def _rendered_env(*, sandbox_root: Path) -> dict[str, str]:
    """The child environment the rendered `[...env]` table declares.

    Read through a real TOML parser from the production renderer, so the
    transport the guard reads its inputs through is the one under test. The
    four names the guard reads are scrubbed from the inherited environment
    first: a factory stage running this suite carries its OWN projection of
    them, and inherited they would grade the stage's credential rather
    than this case's. The unprotected DECLARATION is the one no rendered
    table here replaces, so inherited from a dispatch that routed no Codex
    credential it stands beside this case's deadline and the guard refuses
    the pair.
    """
    child = dict(os.environ)
    for name in (
        CREDENTIAL_USE_DEADLINE_ENV_VAR,
        CREDENTIAL_EXPIRY_ENV_VAR,
        CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
        CREDENTIAL_USE_UNPROTECTED_ENV_VAR,
    ):
        child.pop(name, None)
    table = tomli.loads(credential_use_env_lines(projection=_projection()))
    child.update(
        {key: _rebased(text=str(value), sandbox_root=sandbox_root) for key, value in table.items()}
    )
    return child


def _rebased(*, text: str, sandbox_root: Path) -> str:
    """Point the generated text at this case's sandbox root."""
    return text.replace(_SANDBOX_ROOT, str(sandbox_root))


def _guard_paths(listing: str) -> list[str]:
    """The listed worktree-relative paths that belong to the guard.

    Keyed on the guard's top path SEGMENT rather than on its full
    spelling, so a sibling file projected into the same directory is
    caught too -- an exclusion written for the guard alone while the
    directory carries other projected artifacts is the same defect one
    path over.
    """
    return [path for path in listing.splitlines() if path.split("/")[0] == _GUARD_TOP_SEGMENT]


def _git_repo(*, root: Path) -> Path:
    """A throwaway clone whose TOP LEVEL is the sandbox root.

    This is the Petri-era layout, and building it is the whole point of
    this file: on the pinned engine the clone sits one directory below the
    sandbox root and the guard was never inside it.
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
    _commit_file(repo=root, name="tracked.txt", body="the repository's own content\n")
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


def _commit_file(*, repo: Path, name: str, body: str) -> None:
    (repo / name).write_text(body, encoding="utf-8")
    _git("add", name, repo=repo)
    _git("commit", "-m", f"add {name}", repo=repo)


def _run_prepare_chain(*, scripts: list[str], env: dict[str, str], repo: Path) -> None:
    """Execute the rendered prepare steps for real, in order, in `repo`."""
    for script in scripts:
        _run_prepare_step(script=script, env=env, repo=repo)


def _run_prepare_step(*, script: str, env: dict[str, str], repo: Path) -> None:
    """Execute ONE rendered prepare step the way the engine's shell does."""
    step = subprocess.run(
        ["/bin/sh", "-c", script],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=_STEP_TIMEOUT_SECONDS,
        env=env,
        check=False,
    )

    assert step.returncode == 0, f"{script}\n{step.stdout}\n{step.stderr}"
