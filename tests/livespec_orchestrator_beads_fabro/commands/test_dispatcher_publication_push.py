"""The materialized exact-object leased push used by scripted refresh.

The program's whole contract is that ONE push happens and that it carries an
explicit lease against a named object, so the cases below EXECUTE it against a
real local bare remote rather than reading its text. A text assertion cannot
tell `--force-with-lease=<ref>:<sha>` from `--force-with-lease=<ref>:` — and
that second form is accepted by git and means "the ref does not exist", so it
does not fail, it silently becomes a much weaker assertion.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_path_expansion,
    publication_push_program_prepare_steps_block,
    publication_push_program_source,
)

_BRANCH = "feat/publication-push"


def test_the_prepare_step_materializes_the_single_safe_push_recipe() -> None:
    """One push, one lease, no bypass — and the step writes exactly those bytes."""
    source = publication_push_program_source()
    path = publication_push_program_path_expansion()
    block = publication_push_program_prepare_steps_block()
    parsed = tomli.loads(block)
    [step] = parsed["run"]["prepare"]["steps"]
    script = step["script"]

    assert source.startswith("#!/bin/sh\nset -eu\n")
    assert source.count("git push") == 1
    assert '--force-with-lease="refs/heads/$branch:$expected"' in source
    assert 'origin "HEAD:refs/heads/$branch"' in source
    assert "--no-verify" not in source
    assert path.endswith(f"/{PUBLICATION_PUSH_PROGRAM_FILENAME}")
    assert f"cat > \"{path}\" <<'LIVESPEC_PUBLICATION_PUSH_PROGRAM'" in script
    assert source in script
    assert f'chmod 700 "{path}"' in script


def _git(*, repo: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """One fixture git command, raising its own captured stderr on failure.

    `check=True` rather than a hand-rolled branch: every call here is fixture
    setup that must succeed, so a tolerated-failure arm would be a branch no
    case takes — which this tier's per-file coverage gate reads exactly as it
    reads a never-taken branch in the product.
    """
    return subprocess.run(["git", *argv], cwd=repo, check=True, text=True, capture_output=True)


def _program(*, root: Path) -> Path:
    path = root / PUBLICATION_PUSH_PROGRAM_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(publication_push_program_source(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _repository(*, root: Path) -> tuple[Path, Path, str]:
    """A clone on the publish branch, its bare origin, and the published head."""
    root.mkdir(parents=True)
    remote = root / "remote.git"
    work = root / "work"
    _git(repo=root, argv=["init", "--bare", str(remote)])
    _git(repo=root, argv=["init", "-b", "master", str(work)])
    _git(repo=work, argv=["config", "user.name", "Publication Push Test"])
    _git(repo=work, argv=["config", "user.email", "push@example.com"])
    _ = (work / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo=work, argv=["add", "base.txt"])
    _git(repo=work, argv=["commit", "-m", "base"])
    _git(repo=work, argv=["remote", "add", "origin", str(remote)])
    _git(repo=work, argv=["switch", "-c", _BRANCH])
    _git(repo=work, argv=["push", "-u", "origin", _BRANCH])
    published = _git(repo=work, argv=["rev-parse", "HEAD"]).stdout.strip()
    return work, remote, published


def _remote_head(*, remote: Path) -> str:
    listed = _git(
        repo=remote.parent, argv=["ls-remote", "--heads", str(remote), f"refs/heads/{_BRANCH}"]
    )
    return listed.stdout.split()[0] if listed.stdout.strip() else ""


def _rewritten(*, work: Path) -> str:
    """This clone's HEAD after a rewrite origin does not carry."""
    _ = (work / "next.txt").write_text("next\n", encoding="utf-8")
    _git(repo=work, argv=["add", "next.txt"])
    _git(repo=work, argv=["commit", "--amend", "--no-edit"])
    return _git(repo=work, argv=["rev-parse", "HEAD"]).stdout.strip()


def test_a_rewrite_against_the_recorded_object_lands(tmp_path: Path) -> None:
    """The success path, executed: the ref moves to this clone's HEAD."""
    work, remote, published = _repository(root=tmp_path / "match")
    program = _program(root=tmp_path / "plugins")
    rewritten = _rewritten(work=work)

    completed = subprocess.run(
        [str(program), _BRANCH, published],
        cwd=work,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert rewritten != published
    assert _remote_head(remote=remote) == rewritten


def test_a_rewrite_against_a_stale_object_is_rejected_and_moves_nothing(tmp_path: Path) -> None:
    """The lease is real: a wrong expected object leaves origin exactly as it was.

    This is the case a text assertion cannot reach. The clone genuinely CAN push
    — the success case above proves it against the same fixture shape — so a
    rejection here is the lease acting rather than a broken fixture.
    """
    work, remote, published = _repository(root=tmp_path / "stale")
    program = _program(root=tmp_path / "plugins")
    _ = _rewritten(work=work)

    completed = subprocess.run(
        [str(program), _BRANCH, "0" * 40],
        cwd=work,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0
    assert _remote_head(remote=remote) == published


_UNUSABLE: tuple[tuple[str, list[str], str], ...] = (
    ("no-arguments", [], "expected <branch> <expected-object>"),
    ("one-argument", [_BRANCH], "expected <branch> <expected-object>"),
    ("three-arguments", [_BRANCH, "a" * 40, "extra"], "expected <branch>"),
    ("empty-branch", ["", "a" * 40], "branch is empty"),
    ("empty-object", [_BRANCH, ""], "not a full lowercase sha"),
    ("short-object", [_BRANCH, "abc123"], "not a full lowercase sha"),
    ("uppercase-object", [_BRANCH, "A" * 40], "not a full lowercase sha"),
    ("non-hex-object", [_BRANCH, "z" * 40], "not a full lowercase sha"),
)


def test_every_unusable_invocation_refuses_before_any_push(tmp_path: Path) -> None:
    """Eight malformed invocations, each refusing with its own stated cause.

    The EMPTY expected object is the one that matters most: git accepts
    `--force-with-lease=<ref>:` as "the ref does not exist", so an unvalidated
    empty value would not fail — it would push under a lease that asserts
    nothing. Origin is asserted unmoved after every arm, which is what shows the
    refusal happened before the exec rather than after a push nobody looked for.

    EIGHT ARMS IN ONE CASE, against ONE repository, deliberately. They are eight
    readings of a single argument-validation contract whose whole claim is that
    the repository is never reached, so a fixture per arm would build eight
    repositories — some sixty real `git` processes — to assert the same unmoved
    ref eight times. This suite runs inside `pr_refresh`'s own gate on a loaded
    box, where that cost is paid against every other test's timing.
    """
    work, remote, published = _repository(root=tmp_path / "invalid")
    program = _program(root=tmp_path / "plugins")

    for name, argv, cause in _UNUSABLE:
        completed = subprocess.run(
            [str(program), *argv], cwd=work, check=False, text=True, capture_output=True
        )

        assert completed.returncode == 2, (name, completed.stdout, completed.stderr)
        assert cause in completed.stderr, (name, completed.stderr)
        assert _remote_head(remote=remote) == published, name
