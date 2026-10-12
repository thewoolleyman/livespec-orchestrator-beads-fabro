"""The gh-refresh bundle must stay invisible to the run's own git worktree.

Measured 2026-10-12 on hp-candidate run 01M4Q45S5AGK (fabro
0.382.0-nightly.0): every stage through `janitor` succeeded and
`publish_draft` then failed in five seconds. Its `git rebase
origin/master` stopped at pick 26 -- the engine's checkpoint commit for
prepare step `run_prepare_25` -- with `error: The following untracked
working tree files would be overwritten by merge:
.livespec-gh-refresh/_vendor/livespec_runtime/__init__.py`.

The Petri-era engine runs the prepare steps as GRAPH NODES and
checkpoints after each one, so the bundle the steps write into
`/workspace/.livespec-gh-refresh` -- inside the run's worktree, ignored
by nothing -- is committed into the run branch. The refresh then meets
its own committed copy as an untracked file on disk and refuses.

These tests execute the RENDERED prepare scripts for real inside a
throwaway git clone, because the rendering is where the repair lives and
a test that asserts the text a renderer emits has never been shown to
repair anything. The lever `LIVESPEC_SANDBOX_GH_REFRESH_ROOT` points the
bundle root into that clone, which is what makes the fixture faithful:
in production the root IS inside the run's worktree.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    SANDBOX_GH_REFRESH_ROOT_ENV_VAR,
    refreshing_gh_prepare_steps_block,
)

_BUNDLE_DIRNAME = ".livespec-gh-refresh"
_DEFAULT_BRANCH = "master"
_RUN_BRANCH = "fabro/run/01M4Q45S5AGK"


def test_a_run_branch_rebase_is_not_blocked_by_the_gh_refresh_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`publish_draft`'s refresh must replay the run onto the default tip.

    The collision the incident recorded needs two things at once: a
    replayed commit that ADDS the bundle, and the bundle PRESENT and
    untracked in the worktree the rebase runs in. Both are ordinary --
    the first is an engine checkpoint, the second is what the prepare
    steps leave behind in every sandbox -- so the fixture builds exactly
    that and asserts the refresh completes.
    """
    repo = _git_repo(root=tmp_path / "clone")
    bundle_root = repo / _BUNDLE_DIRNAME
    scripts = _rendered_prepare_scripts(monkeypatch=monkeypatch, bundle_root=bundle_root)
    bin_dir = _stub_path_dir(root=tmp_path / "bin", capture=tmp_path / "gh-calls.txt")

    _git("checkout", "-b", _RUN_BRANCH, repo=repo)
    _run_prepare_chain(scripts=scripts, repo=repo, bin_dir=bin_dir, tmp_path=tmp_path)
    # The engine checkpoints after every node: it stages every change in
    # the worktree and commits. `--allow-empty` so the fixture has one
    # shape in both arms -- once the bundle is invisible this checkpoint
    # stages nothing, which is what the engine logs as "checkpoint
    # skipped: no staged changes".
    _git("add", "-A", repo=repo)
    _git("commit", "--allow-empty", "-m", "fabro checkpoint run_prepare_25", repo=repo)
    _commit_file(repo=repo, name="product.txt", body="the run's own work\n")

    # The default branch moves while the run is in flight, so the refresh
    # has something to replay onto.
    _git("checkout", _DEFAULT_BRANCH, repo=repo)
    _commit_file(repo=repo, name="default.txt", body="a later default-branch commit\n")
    # And the prepare steps have written the bundle into the worktree the
    # refresh rebases in.
    _run_prepare_chain(scripts=scripts, repo=repo, bin_dir=bin_dir, tmp_path=tmp_path)

    rebase = subprocess.run(
        ["git", "rebase", _DEFAULT_BRANCH, _RUN_BRANCH],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert rebase.returncode == 0, rebase.stderr


def test_the_installed_gh_wrapper_still_runs_the_bundles_mint_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hiding the bundle from git must not hide it from the wrapper.

    This is the preservation half of the change, and it cannot fail
    before the change: the bundle already worked. It is asserted here so
    a later edit that hides the bundle by MOVING or REMOVING it -- which
    would satisfy the invisibility assertions just as well -- is caught.
    """
    repo = _git_repo(root=tmp_path / "clone")
    bundle_root = repo / _BUNDLE_DIRNAME
    scripts = _rendered_prepare_scripts(monkeypatch=monkeypatch, bundle_root=bundle_root)
    capture = tmp_path / "gh-calls.txt"
    bin_dir = _stub_path_dir(root=tmp_path / "bin", capture=capture)

    _run_prepare_chain(scripts=scripts, repo=repo, bin_dir=bin_dir, tmp_path=tmp_path)

    # Only now: the unpack step needs the REAL python3 to extract the
    # archive, so the logging stub cannot be on PATH before the chain.
    mint_log = tmp_path / "mint-args.txt"
    _write_executable(
        path=bin_dir / "python3",
        source="#!/usr/bin/env bash\n"
        "set -eu\n"
        'printf "%s\\n" "$1" >> "$MINT_ARG_LOG"\n'
        "printf minted-token\n",
    )
    subprocess.run(
        ["gh", "auth", "status"],
        cwd=repo,
        env=_chain_env(bin_dir=bin_dir, capture=capture, mint_log=mint_log),
        capture_output=True,
        text=True,
        check=True,
    )

    mint_helper = bundle_root / "bin" / "mint_app_token.py"
    assert mint_helper.is_file()
    assert (bundle_root / "_vendor" / "livespec_runtime" / "__init__.py").is_file()
    # The wrapper ran THAT helper, and the token it minted reached the
    # real `gh` -- which is the whole job of the bundle.
    assert mint_log.read_text(encoding="utf-8").splitlines() == [str(mint_helper)]
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "args=auth status",
        "GH_TOKEN=minted-token",
        "GITHUB_TOKEN=minted-token",
    ]


def _rendered_prepare_scripts(
    *,
    monkeypatch: pytest.MonkeyPatch,
    bundle_root: Path,
) -> list[str]:
    """Every prepare-step script the gh-refresh block emits, in order."""
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    monkeypatch.setenv(SANDBOX_GH_REFRESH_ROOT_ENV_VAR, str(bundle_root))
    found = re.findall(
        r"script = '''\n(.*?)\n'''",
        refreshing_gh_prepare_steps_block(),
        re.DOTALL,
    )
    assert found
    return list(found)


def _git_repo(*, root: Path) -> Path:
    """A throwaway clone with one commit on the default branch."""
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


def _commit_file(*, repo: Path, name: str, body: str) -> None:
    (repo / name).write_text(body, encoding="utf-8")
    _git("add", name, repo=repo)
    _git("commit", "-m", f"add {name}", repo=repo)


def _stub_path_dir(*, root: Path, capture: Path) -> Path:
    """A PATH directory whose `gh` records how it was called.

    The unpack step MOVES the `gh` it finds on PATH aside and writes the
    wrapper over it, so this stub becomes `gh.livespec-real` and is what
    the wrapper execs.
    """
    root.mkdir(parents=True)
    _write_executable(
        path=root / "gh",
        source="#!/usr/bin/env bash\n"
        "set -eu\n"
        "{\n"
        '  printf "args=%s\\n" "$*"\n'
        '  printf "GH_TOKEN=%s\\n" "${GH_TOKEN:-}"\n'
        '  printf "GITHUB_TOKEN=%s\\n" "${GITHUB_TOKEN:-}"\n'
        '} >> "$GH_CAPTURE"\n'
        "exit 0\n",
    )
    assert capture.parent.is_dir()
    return root


def _write_executable(*, path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _chain_env(*, bin_dir: Path, capture: Path, mint_log: Path) -> dict[str, str]:
    return {
        **os.environ,
        "GH_CAPTURE": str(capture),
        "MINT_ARG_LOG": str(mint_log),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }


def _run_prepare_chain(
    *,
    scripts: list[str],
    repo: Path,
    bin_dir: Path,
    tmp_path: Path,
) -> None:
    """Execute the rendered prepare steps for real, in order, in `repo`."""
    env = _chain_env(
        bin_dir=bin_dir,
        capture=tmp_path / "gh-calls.txt",
        mint_log=tmp_path / "mint-args.txt",
    )
    for index, script in enumerate(scripts):
        step = tmp_path / f"prepare-{index}.sh"
        step.write_text(script, encoding="utf-8")
        subprocess.run(
            ["/bin/bash", str(step)],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
