"""A skipped janitor aggregate leaves a scoped verdict the pre-push hook can reuse.

The shared ``green_token`` command currently records only the tree hash.  That
makes a full janitor pass and a sandbox pass that omitted
``check-master-ci-green`` indistinguishable at pre-push, even though the latter
did not establish that environmental target.  These tests drive the
repository-owned adapter through a real Git repository and its actual token
file, so a fake command result cannot claim persistence or tree identity that
never happened.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from tests.integration.fixture_check_env import fixture_check_environment

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCOPE_TOKEN = Path("dev-tooling") / "green-token-scope.sh"
_PRE_PUSH = Path("dev-tooling") / "just-check-pre-push.sh"
_JANITOR = Path("dev-tooling") / "just-check.sh"
_AGGREGATE_TARGETS = Path("dev-tooling") / "aggregate-targets.sh"
_JUSTFILE = Path("justfile")
_MASTER_CI_TARGET = "check-master-ci-green"
_CODEX_PICKER_TARGET = "check-codex-skill-picker"
_LIVE_OID = "b3d4f1a90c7e25486fd1c0b8a7e6554321098765"
_ZERO_OID = "0" * 40


def _run(*, repo: Path, argv: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run one command against the fixture repository."""
    return subprocess.run(
        argv,
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    )


def _git(repo: Path, *arguments: str) -> str:
    """Run Git and return its trimmed stdout."""
    return _run(repo=repo, argv=["git", *arguments]).stdout.strip()


def _fixture_repo(*, tmp_path: Path) -> Path:
    """Create a clean Git repository containing the shipped token and hook code."""
    repo = tmp_path / "repo"
    (repo / "dev-tooling").mkdir(parents=True)
    for relative in (_SCOPE_TOKEN, _PRE_PUSH, _JANITOR, _AGGREGATE_TARGETS, _JUSTFILE):
        source = _REPO_ROOT / relative
        assert source.is_file(), f"scoped token adapter is not implemented at {source}"
        _ = shutil.copyfile(source, repo / relative)
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.com")
    _ = (repo / "tracked.txt").write_text("first tree\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "fixture baseline")
    return repo


def _token_path(*, repo: Path) -> Path:
    """Return the real per-worktree token path Git resolves for this fixture."""
    path = Path(_git(repo, "rev-parse", "--git-path", "livespec-green-token.json"))
    return path if path.is_absolute() else repo / path


def _write_scope(*, repo: Path, skipped: list[str]) -> None:
    """Write the token through the shipped adapter rather than constructing JSON."""
    result = _run(
        repo=repo,
        argv=["bash", str(repo / _SCOPE_TOKEN), "write", *skipped],
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _shared_scope(*, repo: Path) -> list[str]:
    """Read the single declared scope used by both aggregate paths."""
    result = _run(
        repo=repo,
        argv=["bash", str(repo / _SCOPE_TOKEN), "scope"],
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.splitlines()


def _run_janitor(*, repo: Path) -> subprocess.CompletedProcess[str]:
    """Run the real check recipe with only its individual targets stubbed."""
    real_just = shutil.which("just")
    assert real_just is not None, "the integration fixture requires just"
    bin_dir = repo.parent / "janitor-bin"
    bin_dir.mkdir(exist_ok=True)
    uv = bin_dir / "uv"
    _ = uv.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$1" == sync ]]; then exit 0; fi\n'
        "if [[ \"$1 $2 $3\" == 'run bash dev-tooling/green-token-scope.sh' ]]; then\n"
        "    shift 2\n"
        '    exec bash "$@"\n'
        "fi\n"
        "exit 2\n",
        encoding="utf-8",
    )
    just = bin_dir / "just"
    _ = just.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    for executable in (uv, just):
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    env = fixture_check_environment(
        overrides={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    )
    return subprocess.run(
        [real_just, "check"], cwd=repo, env=env, check=False, capture_output=True, text=True
    )


def _run_pre_push(*, repo: Path, just_status: int = 0) -> subprocess.CompletedProcess[str]:
    """Run the shipped hook with a thin ``uv`` transport to the real adapter."""
    stub_root = repo.parent
    bin_dir = stub_root / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    uv = bin_dir / "uv"
    _ = uv.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf \'uv %s\\n\' "$*" >> "${STUB_LOG}"\n'
        "if [[ \"$1 $2 $3\" == 'run bash dev-tooling/green-token-scope.sh' ]]; then\n"
        "    shift 2\n"
        '    exec bash "$@"\n'
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    just = bin_dir / "just"
    _ = just.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf \'%s\\n\' "$*" >> "${STUB_JUST_LOG}"\n'
        'exit "${STUB_JUST_STATUS}"\n',
        encoding="utf-8",
    )
    for executable in (uv, just):
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    env = fixture_check_environment(
        overrides={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "STUB_LOG": str(stub_root / "uv.log"),
            "STUB_JUST_LOG": str(stub_root / "just.log"),
            "STUB_JUST_STATUS": str(just_status),
        }
    )
    return subprocess.run(
        ["bash", str(repo / _PRE_PUSH)],
        cwd=repo,
        env=env,
        input=(f"refs/heads/feature {_LIVE_OID} refs/heads/feature {_ZERO_OID}\n"),
        check=False,
        capture_output=True,
        text=True,
    )


def test_a_skipped_janitor_verdict_persists_its_tree_and_excluded_targets(
    *, tmp_path: Path
) -> None:
    """The persisted record distinguishes a reduced aggregate from a full one."""
    repo = _fixture_repo(tmp_path=tmp_path)

    _write_scope(repo=repo, skipped=[_MASTER_CI_TARGET])

    assert json.loads(_token_path(repo=repo).read_text(encoding="utf-8")) == {
        "tree_hash": _git(repo, "rev-parse", "HEAD^{tree}"),
        "skipped_targets": [_MASTER_CI_TARGET],
    }
    scoped = _run(
        repo=repo,
        argv=["bash", str(repo / _SCOPE_TOKEN), "check", _MASTER_CI_TARGET],
        check=False,
    )
    assert scoped.returncode == 0, scoped.stdout + scoped.stderr
    unscoped = _run(
        repo=repo,
        argv=["bash", str(repo / _SCOPE_TOKEN), "check"],
        check=False,
    )
    assert unscoped.returncode != 0, unscoped.stdout + unscoped.stderr


def test_an_unskipped_janitor_verdict_can_be_reused_with_empty_scope(*, tmp_path: Path) -> None:
    """An empty exclusion list is valid and remains distinct from a skipped pass."""
    repo = _fixture_repo(tmp_path=tmp_path)

    _write_scope(repo=repo, skipped=[])

    token = json.loads(_token_path(repo=repo).read_text(encoding="utf-8"))
    assert token["skipped_targets"] == []
    result = _run(
        repo=repo,
        argv=["bash", str(repo / _SCOPE_TOKEN), "check"],
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pre_push_reuses_only_a_byte_identical_token_with_its_current_skip_scope(
    *, tmp_path: Path
) -> None:
    """A sandbox's same-tree publish avoids the second aggregate, not its exclusion."""
    repo = _fixture_repo(tmp_path=tmp_path)
    _git(repo, "config", "livespec.sandboxExempt", "true")
    _write_scope(repo=repo, skipped=[_CODEX_PICKER_TARGET, _MASTER_CI_TARGET])

    matched = _run_pre_push(repo=repo)

    assert matched.returncode == 0, matched.stdout + matched.stderr
    assert not (repo.parent / "just.log").exists(), matched.stdout + matched.stderr
    assert "green token matched" in matched.stdout
    assert _CODEX_PICKER_TARGET in matched.stdout
    assert _MASTER_CI_TARGET in matched.stdout

    _git(repo, "config", "livespec.sandboxExempt", "false")
    scope_mismatch = _run_pre_push(repo=repo)

    assert scope_mismatch.returncode == 0, scope_mismatch.stdout + scope_mismatch.stderr
    assert (repo.parent / "just.log").read_text(encoding="utf-8").splitlines() == [
        "check-skipping check-codex-skill-picker"
    ]


def test_janitor_and_pre_push_derive_the_same_scope_for_a_same_tree_publish(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A factory janitor verdict is reusable by the subsequent sandbox push.

    The delegated gate runs this suite with its own authority-reading members in
    ``SKIP_TARGETS``; the fixture runs must not inherit them.
    """
    monkeypatch.setenv("SKIP_TARGETS", "check-branch-protection-alignment")
    repo = _fixture_repo(tmp_path=tmp_path)
    _git(repo, "config", "livespec.sandboxExempt", "true")

    janitor = _run_janitor(repo=repo)

    assert janitor.returncode == 0, janitor.stdout + janitor.stderr
    assert _shared_scope(repo=repo) == [_CODEX_PICKER_TARGET, _MASTER_CI_TARGET]
    token = json.loads(_token_path(repo=repo).read_text(encoding="utf-8"))
    assert token["skipped_targets"] == _shared_scope(repo=repo)

    matched = _run_pre_push(repo=repo)

    assert matched.returncode == 0, matched.stdout + matched.stderr
    assert "green token matched" in matched.stdout
    assert not (repo.parent / "just.log").exists(), matched.stdout + matched.stderr


def test_pre_push_runs_the_aggregate_when_the_tree_changed_after_the_janitor(
    *, tmp_path: Path
) -> None:
    """A refresh that changes the tree never inherits the janitor's verdict."""
    repo = _fixture_repo(tmp_path=tmp_path)
    _git(repo, "config", "livespec.sandboxExempt", "true")
    _write_scope(repo=repo, skipped=[_MASTER_CI_TARGET])
    _ = (repo / "tracked.txt").write_text("refreshed tree\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "--quiet", "-m", "fixture refresh")

    result = _run_pre_push(repo=repo)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (repo.parent / "just.log").read_text(encoding="utf-8").splitlines() == [
        "check-skipping check-codex-skill-picker"
    ]


def test_pre_push_still_runs_the_forge_reading_member_on_a_matched_verdict(
    *, tmp_path: Path
) -> None:
    """A verdict never vouches for the member that reads state outside the tree."""
    repo = _fixture_repo(tmp_path=tmp_path)
    _write_scope(repo=repo, skipped=[_CODEX_PICKER_TARGET])

    passing = _run_pre_push(repo=repo)

    assert passing.returncode == 0, passing.stdout + passing.stderr
    assert "green token matched" in passing.stdout
    assert (repo.parent / "just.log").read_text(encoding="utf-8").splitlines() == [
        _MASTER_CI_TARGET
    ]

    refused = _run_pre_push(repo=repo, just_status=1)

    assert refused.returncode == 1, refused.stdout + refused.stderr
