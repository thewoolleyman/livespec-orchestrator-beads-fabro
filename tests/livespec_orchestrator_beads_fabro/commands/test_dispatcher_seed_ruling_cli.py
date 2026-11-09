"""`dispatcher.py seed-ruling` driven through the real supervisor.

The command function is covered on its own beside this module; this one
observes the wiring that function cannot: the subcommand is registered, its
flags parse, and the production seams (the tenant ledger and the shell runner)
are the ones bound. The shell runner reads a directory that is not a git
repository, so the remote read finds no ref and the command must refuse.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.types import StoreConfig

_ITEM = "bd-ib-cbcdrp"
_REF = "refs/heads/needs-human/ruled"
_COMMIT = "a" * 40


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


@pytest.fixture
def ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeBeadsClient:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
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


def _argv(*, tmp_path: Path, with_repo: bool) -> list[str]:
    flags = [
        "seed-ruling",
        "--item",
        _ITEM,
        "--ref",
        _REF,
        "--commit",
        _COMMIT,
        "--reason",
        "retain the checked tree",
        "--invoker",
        "coordinator",
        "--journal",
        str(tmp_path / "journal.jsonl"),
    ]
    return [*flags, "--repo", str(tmp_path)] if with_repo else flags


@pytest.mark.parametrize("with_repo", [True, False])
def test_the_subcommand_refuses_a_ref_origin_does_not_hold_and_writes_nothing(
    tmp_path: Path,
    ledger: FakeBeadsClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    with_repo: bool,
) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = dispatcher.main(argv=_argv(tmp_path=tmp_path, with_repo=with_repo))

    assert exit_code == 3
    assert f"{_REF} expected {_COMMIT} but origin observed absent" in capsys.readouterr().err
    assert ledger.list_comments(issue_id=_ITEM) == []
    assert not (tmp_path / "journal.jsonl").exists()
