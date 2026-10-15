"""The projected Codex home must stay invisible to the run's own git worktree.

Found by a static audit on 2026-10-14 rather than by a run, which is why
there is no incident id here and why the fixture has to build the layout
itself. On the Petri-era engine the repository clone IS `/workspace`, so
every artifact the prepare chain writes at a fixed `/workspace` path lands
INSIDE the repository -- and that engine runs each prepare step as a graph
node and checkpoints after it, which commits every change the step left in
the worktree. On the pinned engine the clone is `/workspace/<repo>`, so the
same paths sit outside it and nothing git does can reach them; that is why
this was invisible before Petri.

`$CODEX_HOME` is fixed at `/workspace/.codex` and the chain writes a
CREDENTIAL into it (`auth.json`), so this is the sharpest instance of the
class: a Petri dispatch whose routing or fallback reaches the Codex adapter
would commit a credential file into the run branch, and from there into the
draft pull request's diff against the default branch. Canary 11's branch
carried none only because no node ran on Codex.

This is the sibling of `bd-ib-dud2ww` (the gh-refresh bundle) and
`bd-ib-ccywva` (the credential-use guard), both of which were already
excluded through the same shared renderer; the Codex home was not covered.

THE WHOLE DIRECTORY IS THE SUBJECT, not `auth.json` alone, and the
measurement is keyed on its top path SEGMENT for that reason. The chain's
own telemetry step writes `config.toml` into the same directory, and the
codex-acp child populates it further while the run drives, so an exclusion
written for the credential file alone leaves the identical defect one path
over -- which is the mistake the shared renderer's own docstring records as
the one its callers keep making.

THESE CASES BUILD THE PETRI LAYOUT ON PURPOSE -- a throwaway clone whose TOP
LEVEL is the sandbox root -- because that is the only layout in which the
defect exists. A fixture whose clone sits one directory below the sandbox
root reproduces the PINNED engine, where the Codex home was never
committable, so it would pass before the change and prove nothing.

They execute the RENDERED prepare scripts for real, as
`test_dispatcher_credential_use_guard_worktree.py` does, and for the same
reason: a presence/absence assertion over the rendered text cannot tell an
exclusion that git honours from one that was written to a path git never
reads. Only `/workspace` is rebased onto `tmp_path`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth_projection import (
    codex_auth_env_lines,
    codex_auth_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_otel_config import (
    codex_otel_config_toml,
    codex_otel_env_lines,
    codex_otel_prepare_steps_block,
)

# The in-sandbox root the generated scripts are written against, rebased onto
# `tmp_path` so the generated text runs here unchanged in every other respect.
_SANDBOX_ROOT = "/workspace"
_DEFAULT_BRANCH = "master"
_RUN_BRANCH = "fabro/run/01M4YDE405RJ43GDANYZA8YDMW"
_STEP_TIMEOUT_SECONDS = 60
# A projected snapshot shaped like the real one: a JSON object carrying the
# non-rotatable sentinel, so the written file is a plausible credential and
# the read-back below is reading something a Codex adapter would accept.
_SNAPSHOT = json.dumps(
    {
        "tokens": {
            "access_token": "livespec-fixture-access-token",
            "refresh_token": "livespec-non-rotatable-sentinel",
        },
    }
)


def test_no_checkpoint_of_the_prepare_chain_can_stage_the_projected_codex_home(
    tmp_path: Path,
) -> None:
    """Every prepare step is a checkpoint, so EVERY step must be covered.

    The engine checkpoints after each graph node rather than once at the
    end of the chain, so staging is measured after every step. The
    `--allow-empty` commit keeps one fixture shape in both arms: once the
    Codex home is invisible that checkpoint stages nothing, which is what
    the engine logs as "checkpoint skipped: no staged changes".
    """
    repo = _git_repo(root=tmp_path / "workspace")
    scripts = _rendered_prepare_scripts(sandbox_root=repo)
    env = _rendered_env(sandbox_root=repo)
    codex_home = _codex_home(sandbox_root=repo)
    _git("checkout", "-b", _RUN_BRANCH, repo=repo)

    for index, script in enumerate(scripts):
        _run_prepare_step(script=script, env=env, repo=repo)
        _git("add", "-A", repo=repo)

        assert _codex_paths(_git_stdout("diff", "--cached", "--name-only", repo=repo)) == []

        _git("commit", "--allow-empty", "-m", f"fabro checkpoint run_prepare_{index}", repo=repo)

    # Positive controls: the staging instrument was pointed at a worktree
    # where the credential and the telemetry config really were projected,
    # so the empty results above are measurements rather than a vacuously
    # clean fixture.
    assert (codex_home / "auth.json").is_file()
    assert (codex_home / "config.toml").is_file()
    assert _codex_paths(_git_stdout("ls-files", repo=repo)) == []


def test_the_projected_credential_is_still_readable_through_codex_home(
    tmp_path: Path,
) -> None:
    """Hiding the Codex home from git must not hide it from the adapter.

    This is the preservation half of the change, and it cannot fail before
    the change: the credential was already projected there. It is asserted
    here so a later edit that hides the credential by MOVING or REMOVING it
    -- which would satisfy the invisibility assertion just as well -- is
    caught.

    The path is taken from the rendered env table's own `CODEX_HOME`, which
    is the variable the codex-acp child resolves its credential through, so
    this reads the credential the way the adapter does rather than at a path
    written out here.
    """
    repo = _git_repo(root=tmp_path / "workspace")
    scripts = _rendered_prepare_scripts(sandbox_root=repo)
    env = _rendered_env(sandbox_root=repo)
    for script in scripts:
        _run_prepare_step(script=script, env=env, repo=repo)

    projected = _codex_home(sandbox_root=repo) / "auth.json"

    assert projected.read_text(encoding="utf-8") == _SNAPSHOT


def _rendered_prepare_scripts(*, sandbox_root: Path) -> list[str]:
    """Every prepare-step script the two Codex-home blocks emit, in order.

    Both blocks are rendered, in the order `render_run_config_overlay`
    appends them, because both write into the same directory: measuring the
    credential block alone would report a clean worktree while the telemetry
    config sat staged beside it.
    """
    document = tomli.loads(
        codex_auth_prepare_steps_block(codex_auth_snapshot=_SNAPSHOT)
        + codex_otel_prepare_steps_block(codex_otel_config=_otel_config())
    )
    steps = document.get("run", {}).get("prepare", {}).get("steps", [])
    assert steps
    return [_rebased(text=str(step["script"]), sandbox_root=sandbox_root) for step in steps]


def _rendered_env(*, sandbox_root: Path) -> dict[str, str]:
    """The child environment the rendered `[...env]` table declares.

    Read through a real TOML parser from the production renderers, so the
    transport the prepare steps read their inputs through is the one under
    test. The table is the WHOLE environment the steps are given rather than
    an overlay on this process's own: a factory stage running this suite
    carries its own `CODEX_HOME` and `CODEX_AUTH_JSON`, and inherited they
    would point the steps at the stage's credential instead of this case's.
    `PATH` is carried over because the steps shell out to git.
    """
    table = tomli.loads(
        codex_auth_env_lines(codex_auth_snapshot=_SNAPSHOT)
        + codex_otel_env_lines(codex_otel_config=_otel_config())
    )
    child = {
        key: _rebased(text=str(value), sandbox_root=sandbox_root) for key, value in table.items()
    }
    child["PATH"] = _host_path()
    return child


def _codex_home(*, sandbox_root: Path) -> Path:
    """The projected Codex home, read off the rendered env table.

    Derived rather than written out, so a path change cannot leave this file
    measuring a directory no dispatch projects.
    """
    table = tomli.loads(codex_auth_env_lines(codex_auth_snapshot=_SNAPSHOT))
    return Path(_rebased(text=str(table["CODEX_HOME"]), sandbox_root=sandbox_root))


def _codex_paths(listing: str) -> list[str]:
    """The listed worktree-relative paths that belong to the projected Codex home.

    Keyed on the home's top path SEGMENT rather than on `auth.json`, so every
    sibling the chain and the adapter project into that directory is caught
    too -- an exclusion written for the credential alone while the directory
    carries other projected artifacts is the same defect one path over.
    """
    segment = _codex_home(sandbox_root=Path(_SANDBOX_ROOT)).name
    return [path for path in listing.splitlines() if path.split("/")[0] == segment]


def _otel_config() -> str:
    """The projected `[otel]` body, rendered by its own production renderer."""
    return codex_otel_config_toml(
        endpoint="http://127.0.0.1:4318",
        work_item_id="bd-ib-5qxa5q",
        dispatch_id="livespec-fixture-dispatch",
    )


def _host_path() -> str:
    """This process's `PATH`, so the rendered steps can resolve `git`.

    The engine's own container carries a PATH the overlay does not declare;
    supplying this process's is the local stand-in for it.
    """
    completed = subprocess.run(
        ["/bin/sh", "-c", 'printf %s "$PATH"'],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _rebased(*, text: str, sandbox_root: Path) -> str:
    """Point the generated text at this case's sandbox root."""
    return text.replace(_SANDBOX_ROOT, str(sandbox_root))


def _git_repo(*, root: Path) -> Path:
    """A throwaway clone whose TOP LEVEL is the sandbox root.

    This is the Petri-era layout, and building it is the whole point of this
    file: on the pinned engine the clone sits one directory below the sandbox
    root and the Codex home was never inside it.
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
