"""`dispatcher.py reseed` publishes a reseed and rules it as the item's next seed.

The diff-apply itself is covered against a real origin beside this module
(`test_dispatcher_diff_apply_reseed`). This module observes what that one cannot: the
command's two durable outputs (one ledger comment and one journal record), that the
ruling it writes routes the item's next dispatch seeded from the reseed ref at the
reseed commit's full id, and that every refusal leaves the ledger and the journal alone.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_reseed_command, dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_diff_apply_reseed import (
    Reseeded,
    ReseedRefusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_ruled_seed import (
    ruled_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reseed_command import (
    run_reseed_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ruling_currency import (
    current_ruling,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import SeedRuling
from livespec_orchestrator_beads_fabro.types import StoreConfig

_ITEM = "bd-ib-5xihdt"
_SEED_REF = "refs/heads/needs-human/abc"
_SEED = "5" * 40
_TIP = "7" * 40
_COMMIT = "c" * 40
_REF = f"refs/livespec/reseed/{_ITEM}/{_COMMIT}"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


class _Runner:
    """Answers every call with one fixed result, recording the argvs it was asked."""

    def __init__(self, *, exit_code: int = 0, stdout: str = "") -> None:
        self.result = CommandResult(exit_code=exit_code, stdout=stdout, stderr="")
        self.calls: list[list[str]] = []

    def run(self, **kwargs: object) -> CommandResult:
        self.calls.append([str(one) for one in cast("list[object]", kwargs["argv"])])
        return self.result


@pytest.fixture
def ledger(monkeypatch: pytest.MonkeyPatch) -> FakeBeadsClient:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM,
            issue_type="task",
            title=_ITEM,
            description="d",
            priority=2,
            assignee=None,
            created_at="2026-11-14T00:00:00Z",
            labels=[],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    return client


def _args(
    *, tmp_path: Path, branch: str | None = "master", reason: str | None = None
) -> argparse.Namespace:
    return argparse.Namespace(
        item=_ITEM,
        seed_ref=_SEED_REF,
        default_branch=branch,
        reason=reason,
        invoker="coordinator",
        repo=str(tmp_path),
        journal=str(tmp_path / "journal.jsonl"),
    )


def _reseeded(*, branch: str = "master") -> Reseeded:
    return Reseeded(
        ref=_REF,
        commit=_COMMIT,
        source_ref=_SEED_REF,
        source_commit=_SEED,
        tip_commit=_TIP,
        default_branch=branch,
    )


def _journal(*, tmp_path: Path) -> list[dict[str, object]]:
    path = tmp_path / "journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _reseed_returns(
    *, monkeypatch: pytest.MonkeyPatch, answer: Reseeded | ReseedRefusal
) -> list[dict[str, object]]:
    """Replace the diff-apply with a canned answer, recording the branch it was asked for."""
    asked: list[dict[str, object]] = []

    def fake(**kwargs: object) -> Reseeded | ReseedRefusal:
        asked.append(dict(kwargs))
        return answer

    monkeypatch.setattr(_dispatcher_reseed_command, "diff_apply_reseed", fake)
    return asked


def test_a_published_reseed_is_ruled_so_the_next_dispatch_is_seeded_from_it(
    tmp_path: Path,
    ledger: FakeBeadsClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asked = _reseed_returns(monkeypatch=monkeypatch, answer=_reseeded())

    exit_code = run_reseed_command(args=_args(tmp_path=tmp_path), runner=_Runner(), ledger=ledger)

    assert exit_code == 0
    assert asked[0]["seed_ref"] == _SEED_REF
    assert asked[0]["default_branch"] == "master"
    assert asked[0]["work_item_id"] == _ITEM
    comments = [str(one["text"]) for one in ledger.list_comments(issue_id=_ITEM)]
    assert len(comments) == 1
    assert comments[0].splitlines()[0] == "livespec-seed-ruling"
    for fact in (_REF, _COMMIT, _SEED_REF, _SEED, _TIP, "coordinator"):
        assert fact in comments[0]
    (record,) = _journal(tmp_path=tmp_path)
    assert (record["stage"], record["preservation_ref"], record["commit_sha"]) == (
        "seed-ruling",
        _REF,
        _COMMIT,
    )
    assert f"RESEEDED  {_ITEM}  {_REF} at {_COMMIT}" in capsys.readouterr().out
    ruling = current_ruling(comments=tuple(comments))
    assert isinstance(ruling, SeedRuling)
    origin = _Runner(stdout=f"{_COMMIT}\t{_REF}\n")
    seed = ruled_seed(runner=origin, repo=tmp_path, ruling=ruling, earlier_run_ids=("run-1",))
    assert isinstance(seed, RecoverySeed)
    assert (seed.preservation_ref, seed.commit_sha) == (_REF, _COMMIT)
    assert len(seed.commit_sha) == 40


def test_the_default_branch_is_resolved_when_none_is_named_and_an_operator_reason_is_kept(
    tmp_path: Path, ledger: FakeBeadsClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _reseed_returns(monkeypatch=monkeypatch, answer=_reseeded(branch="main"))

    exit_code = run_reseed_command(
        args=_args(tmp_path=tmp_path, branch=None, reason="the coordinator's call"),
        runner=_Runner(stdout="origin/main\n"),
        ledger=ledger,
    )

    assert exit_code == 0
    assert asked[0]["default_branch"] == "main"
    (comment,) = [str(one["text"]) for one in ledger.list_comments(issue_id=_ITEM)]
    assert "reason: the coordinator's call" in comment


def test_a_refusal_publishes_and_records_nothing(
    tmp_path: Path,
    ledger: FakeBeadsClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    detail = "the diff does not apply cleanly; conflicting paths: a.txt, b.txt"
    _ = _reseed_returns(monkeypatch=monkeypatch, answer=ReseedRefusal(detail=detail))

    exit_code = run_reseed_command(args=_args(tmp_path=tmp_path), runner=_Runner(), ledger=ledger)

    assert exit_code == 3
    assert f"reseed refused: {detail}" in capsys.readouterr().err
    assert ledger.list_comments(issue_id=_ITEM) == []
    assert _journal(tmp_path=tmp_path) == []


def test_an_unknown_work_item_is_refused_before_anything_is_read(
    tmp_path: Path,
    ledger: FakeBeadsClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asked = _reseed_returns(monkeypatch=monkeypatch, answer=_reseeded())
    args = _args(tmp_path=tmp_path)
    args.item = "bd-ib-nothere"

    exit_code = run_reseed_command(args=args, runner=_Runner(), ledger=ledger)

    assert exit_code == 3
    assert "no work-item bd-ib-nothere" in capsys.readouterr().err
    assert asked == []


def test_an_unresolvable_default_branch_is_refused_before_the_reseed(
    tmp_path: Path,
    ledger: FakeBeadsClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asked = _reseed_returns(monkeypatch=monkeypatch, answer=_reseeded())

    exit_code = run_reseed_command(
        args=_args(tmp_path=tmp_path, branch=None), runner=_Runner(exit_code=1), ledger=ledger
    )

    assert exit_code == 3
    assert "default branch could not be resolved" in capsys.readouterr().err
    assert asked == []


def test_a_published_reseed_whose_ruling_is_refused_says_the_ref_stands_unruled(
    tmp_path: Path,
    ledger: FakeBeadsClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _reseed_returns(monkeypatch=monkeypatch, answer=_reseeded())

    exit_code = run_reseed_command(
        args=_args(tmp_path=tmp_path, reason="{{ not a literal }}"),
        runner=_Runner(),
        ledger=ledger,
    )

    assert exit_code == 3
    err = capsys.readouterr().err
    assert f"reseed published {_REF} but could not rule it" in err
    assert "template opener present" in err
    assert ledger.list_comments(issue_id=_ITEM) == []


@pytest.mark.parametrize("with_repo", [True, False])
def test_the_subcommand_is_registered_and_binds_the_production_seams(
    tmp_path: Path,
    ledger: FakeBeadsClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    with_repo: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    flags = [
        "reseed",
        "--item",
        _ITEM,
        "--seed-ref",
        _SEED_REF,
        "--default-branch",
        "master",
        "--invoker",
        "coordinator",
        "--journal",
        str(tmp_path / "journal.jsonl"),
    ]
    argv = [*flags, "--repo", str(tmp_path)] if with_repo else flags

    exit_code = dispatcher.main(argv=argv)

    assert exit_code == 3
    err = capsys.readouterr().err
    assert "reseed refused" in err
    assert "refs/heads/master" in err
    assert ledger.list_comments(issue_id=_ITEM) == []
