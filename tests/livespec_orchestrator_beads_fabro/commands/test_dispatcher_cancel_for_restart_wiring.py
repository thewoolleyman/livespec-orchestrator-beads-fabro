"""Coverage for the restart-preservation failure record and command route."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_restart_preservation_record import (
    RestartPreservationComment,
    append_restart_preservation_comment,
)


def test_unwritable_restart_comment_is_journaled(tmp_path: Path) -> None:
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    def _unwritable(**_: object) -> object:
        raise OSError("ledger unavailable")

    append_restart_preservation_comment(
        repo=tmp_path,
        journal=journal,
        comment=RestartPreservationComment(
            work_item_id="bd-ib-adcaa6",
            run_id="run-1",
            factory="petri",
            body="livespec-preserved-tree",
        ),
        resolve_config=lambda **_: object(),
        append_comment=_unwritable,
    )

    assert "restart-preserved-tree-record-error" in journal.path.read_text(encoding="utf-8")


def test_cancel_for_restart_command_reaches_its_dispatcher_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _run(*, args: Namespace) -> int:
        calls.append(str(args.factory))
        return 0

    monkeypatch.setattr(dispatcher, "run_cancel_for_restart_command", _run)

    assert dispatcher.main(argv=["cancel-for-restart", "--factory", "petri"]) == 0
    assert calls == ["petri"]
