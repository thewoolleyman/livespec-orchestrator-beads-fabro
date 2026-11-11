"""Consumer-tier acceptance for Scenario 336's helper-fetch blocks, run for real.

Binds the helper blocks of "## Scenario 336 — A sandbox checks a tree with the
tooling release that tree pins, and works in the latest clones": "The setup step
writes every helper program from the pinned commit and verifies its digest" and
"A helper the setup step cannot verify fails the run before dod_gate". The setup
step's OWN script is executed under `sh`, against a local repository standing in
for the forge (`file://`), holding this checkout's plugin tree as one commit and
two variants of it, so the fetch, the sparse shallow checkout and the checkout's
own materializer are all the shipped ones. Nothing reaches the network.

The fixture repository is built once per module: copying the plugin tree and
committing it is most of this file's cost.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_build import HelperSource
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_fetch import (
    helper_fetch_prepare_step,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_registry import (
    HELPER_ROOTS,
    helper_registry,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMANDS = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_CAUSE = "LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH"
# Every child runs with the repository-selecting `GIT_*` variables and the coverage
# hooks removed: this suite can itself run under a commit hook, whose
# `GIT_INDEX_FILE` would point a fixture's commits at the outer repository.
_SCRUBBED_PREFIXES = ("GIT_", "COVERAGE_PROCESS_START", "COV_CORE_")
_GIT_ENV = {
    **{
        name: value for name, value in os.environ.items() if not name.startswith(_SCRUBBED_PREFIXES)
    },
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


@dataclass(frozen=True, kw_only=True)
class _Forge:
    url: str
    pristine: str
    edited_red: str
    without_green: str


def _git(*args: str, cwd: Path) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, env=_GIT_ENV, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def _commit(*, repository: Path, message: str) -> str:
    _ = _git("add", "-A", cwd=repository)
    _ = _git("commit", "-q", "-m", message, cwd=repository)
    return _git("rev-parse", "HEAD", cwd=repository)


@pytest.fixture(scope="module", name="forge")
def _forge(tmp_path_factory: pytest.TempPathFactory) -> _Forge:
    """This checkout's plugin tree as one commit, plus a tampered and a truncated variant."""
    repository = tmp_path_factory.mktemp("forge") / "orchestrator"
    ignored = shutil.ignore_patterns("__pycache__", "*.pyc")
    for tree in (".claude-plugin/scripts", ".claude-plugin/.fabro"):
        _ = shutil.copytree(_REPO_ROOT / tree, repository / tree, ignore=ignored)
    _ = _git("init", "-q", "-b", "master", str(repository), cwd=repository.parent)
    _ = _git("config", "uploadpack.allowFilter", "true", cwd=repository)
    pristine = _commit(repository=repository, message="the installed build")
    red = repository / _COMMANDS / "_dispatcher_commit_red_program.sh"
    _ = red.write_text(red.read_text(encoding="utf-8") + "# drifted\n", encoding="utf-8")
    _ = _git("checkout", "-q", "-b", "edited-red", cwd=repository)
    edited_red = _commit(repository=repository, message="a commit whose Red program differs")
    _ = _git("checkout", "-q", "-b", "without-green", pristine, cwd=repository)
    (repository / _COMMANDS / "_dispatcher_commit_green_program.sh").unlink()
    without_green = _commit(repository=repository, message="a commit missing the Green program")
    return _Forge(
        url=f"file://{repository}",
        pristine=pristine,
        edited_red=edited_red,
        without_green=without_green,
    )


def _run_step(*, forge: _Forge, commit: str, sandbox: Path) -> subprocess.CompletedProcess[str]:
    """The setup step's own script under `sh`, with only its own env and a scratch HOME."""
    roots = {name: str(sandbox / name) for name in HELPER_ROOTS}
    step = helper_fetch_prepare_step(
        source=HelperSource(repository=forge.url, commit=commit), roots=roots
    )
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(sandbox / "home"),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        **step.env,
    }
    return subprocess.run(
        ["sh", "-c", step.script], cwd=sandbox, env=env, capture_output=True, text=True, check=False
    )


def _landed(*, sandbox: Path) -> list[Path]:
    return [
        path
        for name in HELPER_ROOTS
        if (sandbox / name).is_dir()
        for path in (sandbox / name).rglob("*")
        if path.is_file()
    ]


def test_every_helper_lands_byte_identical_with_its_mode_and_again_on_resume(
    forge: _Forge, tmp_path: Path
) -> None:
    """The setup step writes every helper program from the pinned commit and verifies its digest."""
    first = _run_step(forge=forge, commit=forge.pristine, sandbox=tmp_path)
    assert first.returncode == 0, first.stderr
    helpers = helper_registry()
    for helper in helpers:
        target = tmp_path / helper.root / helper.path
        assert target.read_bytes() == helper.compose(), helper.name
        assert target.stat().st_mode & 0o7777 == helper.mode, helper.name
    assert len(_landed(sandbox=tmp_path)) == len(helpers)
    (tmp_path / "plugins" / helpers[0].path).unlink()
    resumed = _run_step(forge=forge, commit=forge.pristine, sandbox=tmp_path)
    assert resumed.returncode == 0, resumed.stderr
    assert (tmp_path / "plugins" / helpers[0].path).read_bytes() == helpers[0].compose()


def test_a_commit_the_forge_does_not_serve_fails_naming_the_commit(
    forge: _Forge, tmp_path: Path
) -> None:
    """A helper the setup step cannot verify: commit C cannot be fetched."""
    absent = "0123456789abcdef0123456789abcdef01234567"
    done = _run_step(forge=forge, commit=absent, sandbox=tmp_path)
    assert done.returncode != 0
    assert (
        f"{_CAUSE}: helper-manifest: commit {absent} cannot be fetched from {forge.url}"
        in done.stderr
    )
    assert _landed(sandbox=tmp_path) == []


def test_a_helper_whose_digest_differs_at_the_commit_fails_naming_it(
    forge: _Forge, tmp_path: Path
) -> None:
    """A helper the setup step cannot verify: one helper composed at C has a different digest."""
    done = _run_step(forge=forge, commit=forge.edited_red, sandbox=tmp_path)
    assert done.returncode == 1
    assert f"{_CAUSE}: commit-red: composed digest " in done.stderr
    assert f"at commit {forge.edited_red} differs from the manifest's" in done.stderr
    assert _landed(sandbox=tmp_path) == []


def test_a_helper_whose_source_is_missing_at_the_commit_fails_naming_it(
    forge: _Forge, tmp_path: Path
) -> None:
    """A helper the setup step cannot verify: one helper's source path is missing at C."""
    done = _run_step(forge=forge, commit=forge.without_green, sandbox=tmp_path)
    assert done.returncode == 1
    assert (
        f"{_CAUSE}: commit-green: source path missing at commit {forge.without_green}: "
        in done.stderr
    )
    assert _landed(sandbox=tmp_path) == []
