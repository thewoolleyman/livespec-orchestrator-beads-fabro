"""`dispatcher.py seed-ruling` records, verifies and refuses an operator's ruled seed.

Scenario 185 lets an operator name the preserved tree a released item's next
dispatch starts from. The command is the only writer of that instruction, so
its two durable outputs (one ledger comment, one journal record) are asserted
together, and every refusal is read off both surfaces: an append-only comment
cannot be repaired afterwards, so a refusal must leave neither behind.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling_command import (
    run_seed_ruling_command,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_ITEM = "bd-ib-cbcdrp"
_REF = "refs/heads/needs-human/ruled"
_COMMIT = "a" * 40
_OTHER = "b" * 40
_REASON = "retain the checked Red-Green tree"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


class _Origin:
    """The one remote read the command performs, answered from a fixed listing."""

    def __init__(self, *, stdout: str) -> None:
        self.stdout = stdout
        self.calls: list[list[str]] = []

    def run(self, **kwargs: object) -> CommandResult:
        argv = kwargs["argv"]
        assert isinstance(argv, list)
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


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
            created_at="2026-11-09T00:00:00Z",
            labels=[],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    return client


def _args(*, tmp_path: Path, item: str = _ITEM, reason: str = _REASON) -> argparse.Namespace:
    return argparse.Namespace(
        item=item,
        ref=_REF,
        commit=_COMMIT,
        reason=reason,
        invoker="coordinator",
        repo=str(tmp_path),
        journal=str(tmp_path / "journal.jsonl"),
    )


def _journal(*, tmp_path: Path) -> list[dict[str, object]]:
    path = tmp_path / "journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_ruling_naming_a_ref_at_its_commit_is_recorded_on_both_surfaces(
    tmp_path: Path, ledger: FakeBeadsClient, capsys: pytest.CaptureFixture[str]
) -> None:
    origin = _Origin(stdout=f"{_COMMIT}\t{_REF}\n")

    exit_code = run_seed_ruling_command(args=_args(tmp_path=tmp_path), runner=origin, ledger=ledger)

    assert exit_code == 0
    assert origin.calls == [["git", "ls-remote", "origin", _REF]]
    comments = [str(one["text"]) for one in ledger.list_comments(issue_id=_ITEM)]
    assert len(comments) == 1
    lines = comments[0].splitlines()
    assert lines[0] == "livespec-seed-ruling"
    for fact in (_REF, _COMMIT, "coordinator", _REASON):
        assert fact in comments[0]
    instant = next(one for one in lines if one.startswith("instant: ")).removeprefix("instant: ")
    assert instant.endswith("Z")
    records = _journal(tmp_path=tmp_path)
    assert len(records) == 1
    record = records[0]
    assert {key: record[key] for key in ("stage", "work_item_id", "preservation_ref")} == {
        "stage": "seed-ruling",
        "work_item_id": _ITEM,
        "preservation_ref": _REF,
    }
    assert (record["commit_sha"], record["reason"], record["instant"]) == (
        _COMMIT,
        _REASON,
        instant,
    )
    assert record["invoker"] == "coordinator"
    assert _REF in capsys.readouterr().out


@pytest.mark.parametrize(
    ("listing", "observed"),
    [("", "absent"), (f"{_OTHER}\t{_REF}\n", _OTHER)],
)
def test_a_ref_that_is_absent_or_moved_is_refused_with_exit_3_and_nothing_written(
    tmp_path: Path,
    ledger: FakeBeadsClient,
    capsys: pytest.CaptureFixture[str],
    *,
    listing: str,
    observed: str,
) -> None:
    exit_code = run_seed_ruling_command(
        args=_args(tmp_path=tmp_path), runner=_Origin(stdout=listing), ledger=ledger
    )

    assert exit_code == 3
    err = capsys.readouterr().err
    assert f"{_REF} expected {_COMMIT} but origin observed {observed}" in err
    assert ledger.list_comments(issue_id=_ITEM) == []
    assert _journal(tmp_path=tmp_path) == []


def test_a_body_the_template_opener_detector_flags_is_refused_and_nothing_is_written(
    tmp_path: Path, ledger: FakeBeadsClient, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = run_seed_ruling_command(
        args=_args(tmp_path=tmp_path, reason="{{ not allowed }}"),
        runner=_Origin(stdout=f"{_COMMIT}\t{_REF}\n"),
        ledger=ledger,
    )

    assert exit_code == 3
    assert "template opener present: {{" in capsys.readouterr().err
    assert ledger.list_comments(issue_id=_ITEM) == []
    assert _journal(tmp_path=tmp_path) == []


def test_an_item_the_tenant_does_not_hold_is_refused_before_the_remote_read(
    tmp_path: Path, ledger: FakeBeadsClient, capsys: pytest.CaptureFixture[str]
) -> None:
    origin = _Origin(stdout=f"{_COMMIT}\t{_REF}\n")

    exit_code = run_seed_ruling_command(
        args=_args(tmp_path=tmp_path, item="bd-ib-absent"), runner=origin, ledger=ledger
    )

    assert exit_code == 3
    assert "no work-item bd-ib-absent" in capsys.readouterr().err
    assert origin.calls == []
    assert _journal(tmp_path=tmp_path) == []
