"""A hold over an unattributable published head names its own measurement.

`SPECIFICATION/contracts.md` "Recovery from the failed run's preserved work" and
Scenario 323: when a published head and a competing preserved ref both exist and
the publishing run cannot be established, the item is routed held with a
recovery-held record naming the measurement `publishing-run-unobservable`, and no
publish branch is reclaimed.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

import pytest

# Import order is load-bearing; see `test_dispatcher_recovery_routing_resume.py`
# for the cycle this leading import breaks.
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission as _admission,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_recovery_routing as routing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

from tests.livespec_orchestrator_beads_fabro.commands._recovery_tip_reads import tip_read_answer

_ = _admission

_ITEM_ID = "bd-ib-so6fef"
_RUN = "01M6S5B67ANM2BE1DX8YFN305M"
_DISPATCH = "c1d2e3f405968788a9babbcbddcedfe0"
_TERMINAL = "a" * 40
_HEAD = "b" * 40
_HELD_STAGE = "recovery-held"
_MEASUREMENT = "publishing-run-unobservable"


class _Shell:
    answers: ClassVar[dict[str, CommandResult]] = {}
    calls: ClassVar[list[str]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        joined = " ".join(argv)
        _Shell.calls.append(joined)
        for needle, result in _Shell.answers.items():
            if needle in joined:
                return result
        if (tip := tip_read_answer(argv=argv)) is not None:
            return tip
        return CommandResult(exit_code=0, stdout="", stderr="")


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A released item with a head and a competing ref",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _journal(*, tmp_path: Path, records: Sequence[dict[str, object]]) -> JournalFile:
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
    )
    return journal


def _rows(*, journal: JournalFile, stage: str) -> tuple[dict[str, Any], ...]:
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return tuple(record for record in written if record.get("stage") == stage)


def test_an_unattributable_head_against_a_competing_ref_is_held_under_its_own_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _journal(
        tmp_path=tmp_path,
        records=(
            {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": _DISPATCH},
            {"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": _RUN},
            {"stage": "provider-limit-release", "work_item_id": _ITEM_ID, "run_id": _RUN},
        ),
    )
    _Shell.answers = {
        "gh pr list": CommandResult(exit_code=0, stdout="[]", stderr=""),
        "refs/heads/needs-human/": CommandResult(
            exit_code=0, stdout=f"{_TERMINAL}\trefs/heads/needs-human/{_RUN}\n", stderr=""
        ),
        f"refs/heads/feat/{_ITEM_ID}": CommandResult(
            exit_code=0, stdout=f"{_HEAD}\trefs/heads/feat/{_ITEM_ID}\n", stderr=""
        ),
    }
    _Shell.calls = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)

    routed = routing.route_recovery(
        args=argparse.Namespace(
            repo=str(tmp_path),
            journal=str(journal.path),
            workflow_name="implement-work-item",
            fabro_bin="/usr/local/bin/fabro",
        ),
        repo=tmp_path,
        candidates=[_work_item()],
        journal=journal,
    )

    assert routed.route_for(work_item_id=_ITEM_ID).route == "held"
    held = _rows(journal=journal, stage=_HELD_STAGE)
    assert [row["measurements"] for row in held] == [[_MEASUREMENT]]
    assert "publishing-run-unobservable" in held[0]["details"][0]
    assert not any("--delete" in call or " -d " in call for call in _Shell.calls)
