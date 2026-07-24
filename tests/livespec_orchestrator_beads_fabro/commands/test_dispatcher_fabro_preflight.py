"""Tests for the Dispatcher's fabro engine-binary preflight (work-item bd-ib-qz7b54).

The Dispatcher resolves its `fabro` engine binary from `--fabro-bin` / env /
config / an absolute default, then REFUSES at preflight — BEFORE arming the
OTLP receiver, preparing the store, or admitting anything (ready -> active) —
when the resolved binary is not an existing executable. Refusing before
admission is the fix for bd-ib-qz7b54: a bare-name `fabro` that failed to
resolve under the fleet credential wrapper's sanitized PATH used to strand the
admitted item at active (ready -> active, assignee=fabro) before the launch
subprocess raised FileNotFoundError.

Coverage here spans the resolution helper's two arcs (explicit flag wins vs.
defer to resolution), the preflight predicate's path-vs-bare-name arms (each
resolvable and not), and the end-to-end refusal exit code for both `dispatch`
and `loop`. The end-to-end refusals need NO live store: the preflight returns
before `_prepare`, so they run purely hermetically on a bare `tmp_path`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.dispatcher import dispatch_preamble, main
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _make_executable(path: Path) -> None:
    _ = path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


_EXIT_PRECONDITION_ERROR = 3


def _git(*, repo: Path, argv: list[str]) -> None:
    subprocess.run(
        ["git", *argv],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_origin_backed_repo(*, tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    _git(repo=tmp_path, argv=["init", "--bare", str(origin)])
    _git(repo=tmp_path, argv=["clone", str(origin), str(repo)])
    _git(repo=repo, argv=["config", "user.email", "test@example.com"])
    _git(repo=repo, argv=["config", "user.name", "Test User"])
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    _git(repo=repo, argv=["add", ".livespec.jsonc"])
    _git(repo=repo, argv=["commit", "-m", "initial"])
    _git(repo=repo, argv=["push", "origin", "HEAD:master"])
    _git(repo=repo, argv=["fetch", "origin"])
    return repo


def _commit_marker(*, repo: Path, name: str, content: str) -> None:
    _ = (repo / name).write_text(content, encoding="utf-8")
    _git(repo=repo, argv=["add", name])
    _git(repo=repo, argv=["commit", "-m", f"add {name}"])


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _ready_item(*, item_id: str = "bd-ib-pums-probe") -> WorkItem:
    return WorkItem(
        id=item_id,
        title="Probe item",
        description="Dispatch preflight probe",
        status="ready",
        rank="a5",
        type="bug",
        origin="freeform",
        gap_id=None,
        assignee=None,
        depends_on=(),
        captured_at="2026-07-24T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _install_refusing_pre_push_hook(*, repo: Path) -> None:
    _git(repo=repo, argv=["config", "core.hooksPath", ".githooks"])
    hooks = repo / ".githooks"
    hooks.mkdir()
    pre_push = hooks / "pre-push"
    _ = pre_push.write_text(
        "#!/bin/sh\n"
        "echo 'livespec: refusing commit/push at primary checkout; use a worktree' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    pre_push.chmod(0o755)


def _dispatch_origin_unreachable_probe(
    *, repo: Path, tmp_path: Path, item: WorkItem
) -> tuple[int, Path]:
    exe = tmp_path / "fabro"
    _make_executable(exe)
    journal = tmp_path / "dispatch-journal.jsonl"
    rc = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--fabro-bin",
            str(exe),
            "--journal",
            str(journal),
        ]
    )
    return rc, journal


# --- dispatch_preamble resolution ------------------------------------------


def test_resolve_fabro_bin_for_explicit_flag_wins(tmp_path: Path) -> None:
    """A non-None --fabro-bin is an operator override, returned verbatim."""
    exe = tmp_path / "explicit-fabro"
    _make_executable(exe)
    args = argparse.Namespace(fabro_bin=str(exe), janitor=None)
    janitor, rc = dispatch_preamble(args=args, repo=tmp_path)
    assert (janitor, rc) == (None, None)
    assert args.fabro_bin == str(exe)


def test_resolve_fabro_bin_for_none_defers_to_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A None flag defers to resolve_fabro_bin (exercised here via the env override)."""
    exe = tmp_path / "resolved-fabro"
    _make_executable(exe)
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", str(exe))
    args = argparse.Namespace(fabro_bin=None, janitor=None)
    janitor, rc = dispatch_preamble(args=args, repo=tmp_path)
    assert (janitor, rc) == (None, None)
    assert args.fabro_bin == str(exe)


# --- _fabro_preflight_error: absolute-path arm ------------------------------


def test_preflight_absolute_missing_is_error(tmp_path: Path) -> None:
    """A path-shaped value naming no existing file refuses, naming every knob."""
    missing = tmp_path / "nope" / "fabro"
    args = argparse.Namespace(fabro_bin=str(missing), janitor=None)
    janitor, rc = dispatch_preamble(args=args, repo=tmp_path)
    assert (janitor, rc) == (None, _EXIT_PRECONDITION_ERROR)


def test_preflight_absolute_executable_is_ok(tmp_path: Path) -> None:
    """A path-shaped value naming an existing executable file is resolvable."""
    exe = tmp_path / "fabro"
    _make_executable(exe)
    args = argparse.Namespace(fabro_bin=str(exe), janitor=None)
    assert dispatch_preamble(args=args, repo=tmp_path) == (None, None)


def test_preflight_absolute_non_executable_is_error(tmp_path: Path) -> None:
    """A path that exists but is not executable (no +x) refuses."""
    plain = tmp_path / "fabro"
    _ = plain.write_text("not executable\n", encoding="utf-8")
    plain.chmod(0o644)
    args = argparse.Namespace(fabro_bin=str(plain), janitor=None)
    assert dispatch_preamble(args=args, repo=tmp_path) == (
        None,
        _EXIT_PRECONDITION_ERROR,
    )


# --- _fabro_preflight_error: bare-name arm ----------------------------------


def test_preflight_bare_name_not_on_path_is_error() -> None:
    """A bare name absent from PATH refuses (the original bare-`fabro` failure mode)."""
    args = argparse.Namespace(fabro_bin="definitely-not-a-real-binary-xyz", janitor=None)
    assert dispatch_preamble(args=args, repo=Path.cwd()) == (
        None,
        _EXIT_PRECONDITION_ERROR,
    )


def test_preflight_bare_name_on_path_is_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare name found on PATH (shutil.which) is resolvable."""
    exe = tmp_path / "myfabro"
    _make_executable(exe)
    monkeypatch.setenv("PATH", str(tmp_path))
    args = argparse.Namespace(fabro_bin="myfabro", janitor=None)
    assert dispatch_preamble(args=args, repo=tmp_path) == (None, None)


# --- origin reachability preflight ------------------------------------------


def test_dispatch_preamble_admits_origin_reachable_head(tmp_path: Path) -> None:
    """HEAD equal to an origin ref passes the source-checkout preflight."""
    repo = _init_origin_backed_repo(tmp_path=tmp_path)
    exe = tmp_path / "fabro"
    _make_executable(exe)
    args = argparse.Namespace(fabro_bin=str(exe), janitor=None, journal=None)
    assert dispatch_preamble(args=args, repo=repo) == (None, None)


def test_dispatch_preamble_admits_head_behind_origin_ref(tmp_path: Path) -> None:
    """A behind-but-pushed checkout is still safe because origin contains HEAD."""
    repo = _init_origin_backed_repo(tmp_path=tmp_path)
    _commit_marker(repo=repo, name="pushed.txt", content="pushed\n")
    _git(repo=repo, argv=["push", "origin", "HEAD:master"])
    _git(repo=repo, argv=["reset", "--hard", "HEAD~1"])
    exe = tmp_path / "fabro"
    _make_executable(exe)
    args = argparse.Namespace(fabro_bin=str(exe), janitor=None, journal=None)
    assert dispatch_preamble(args=args, repo=repo) == (None, None)


def test_dispatch_refuses_unpushed_head_with_journaled_terminal_outcome(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An origin-unreachable HEAD refuses before admission and names the remedy."""
    repo = _init_origin_backed_repo(tmp_path=tmp_path)
    _commit_marker(repo=repo, name="local.txt", content="local-only\n")
    _install_refusing_pre_push_hook(repo=repo)
    item = _ready_item()
    append_work_item(item=item, path=_config())

    rc, journal = _dispatch_origin_unreachable_probe(repo=repo, tmp_path=tmp_path, item=item)

    err = capsys.readouterr().err
    assert rc == _EXIT_PRECONDITION_ERROR
    assert "source checkout HEAD is not reachable from any origin ref" in err
    assert "add local.txt" in err
    assert "livespec: refusing commit/push at primary checkout; use a worktree" in err
    assert "preserve the unpushed commit(s) on a branch/worktree" in err
    assert "reset the primary checkout to origin/master" in err
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert [record["stage"] for record in records] == ["source-checkout-origin-reachability"]
    assert records[0]["terminal"] is True
    assert records[0]["reason"] == "source-head-not-origin-reachable"
    assert records[0]["push_outcome"]["exit_code"] == 1
    assert next(iter(read_work_items(path=_config()))).status == "ready"

    _git(repo=repo, argv=["branch", "preserve-local-work"])
    _git(repo=repo, argv=["reset", "--hard", "origin/master"])
    exe = tmp_path / "fabro"
    args = argparse.Namespace(fabro_bin=str(exe), janitor=None, journal=None)
    assert dispatch_preamble(args=args, repo=repo) == (None, None)


# --- end-to-end refusal before admission ------------------------------------


def test_loop_refuses_before_admission_on_unresolvable_fabro(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`loop` with an unresolvable explicit --fabro-bin refuses at preflight (exit 3).

    The refusal is before `_prepare`, so no live store / `.livespec.jsonc` is
    needed on `tmp_path`; the explicit flag overrides the hermetic env stub.
    """
    rc = main(
        argv=[
            "loop",
            "--repo",
            str(tmp_path),
            "--budget",
            "1",
            "--fabro-bin",
            "/nonexistent/fabro",
            "--json",
        ]
    )
    assert rc == _EXIT_PRECONDITION_ERROR
    assert "not resolvable" in capsys.readouterr().err


def test_dispatch_refuses_before_admission_on_unresolvable_fabro(tmp_path: Path) -> None:
    """`dispatch` with an unresolvable explicit --fabro-bin refuses at preflight (exit 3)."""
    rc = main(
        argv=[
            "dispatch",
            "--repo",
            str(tmp_path),
            "--item",
            "any-id",
            "--fabro-bin",
            "/nonexistent/fabro",
        ]
    )
    assert rc == _EXIT_PRECONDITION_ERROR
