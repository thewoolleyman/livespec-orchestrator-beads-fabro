"""Tests for the pointer write on a pull request whose only counting record is a host replay.

An item declaring a `factory_captured` assertion beside a `host_captured` one can
merge with a factory `captured` record and an independent `host_verified` replay
on its pull request and no `verified` record. That used to journal
"no verified Proof of Done record for the merging run" and write NO pointer, and
because the `accept` valve reads the pull request off the pointer the item could
neither close nor be accepted by hand. The pointer now cites the latest record
that counts for a declared mode, which here is the host replay; a `captured`
record counts for no mode, so it alone still earns no pointer.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands import _dispatcher_proof_pointer_write
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_criteria import (
    CriterionCheck,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
    PROOF_MODE_HOST_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import (
    HostAssertionGrade,
    HostLeg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_leg import (
    PROOF_RECORD_EVIDENCE_LEG,
    AssertionEvidence,
    ProofLeg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import pointer_in
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer_write import (
    write_proof_pointer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_HOST_VERIFIED,
    ProofRecord,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_FACTORY = "The projection carries the parent field."
_HOST = "The released build resolves the mode on an operator host."
_CAPTURED_URL = "https://example.test/pull/7#issuecomment-1"
_HOST_URL = "https://example.test/pull/7#issuecomment-3"
_DESCRIPTION = f"## Definition of Done\n\n- {_FACTORY}\n- {_HOST}\n\nReferences: ## Something\n"
_REPLAYER = "session-b"


def _item(*, description: str = _DESCRIPTION) -> WorkItem:
    return WorkItem(
        id="bd-ib-captured",
        type="bug",
        status="acceptance",
        title="Task",
        description=description,
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-then-human",
        acceptance_criteria=None,
    )


def _outcome(*, pr_number: int | None) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-captured",
        status="green",
        stage="done",
        pr_number=pr_number,
        merge_sha="abc123",
        detail="merged",
    )


def _leg(*, replayed: bool) -> ProofLeg:
    captured = ProofRecord(
        verdict=VERDICT_CAPTURED,
        run_id="d547aa765bb3427cb43e70ebc9fd54a6",
        timestamp="2026-10-27T00:46:00Z",
        url=_CAPTURED_URL,
        body="",
    )
    replay = ProofRecord(
        verdict=VERDICT_HOST_VERIFIED,
        run_id=_REPLAYER,
        timestamp="2026-10-29T10:07:30Z",
        url=_HOST_URL,
        body="",
    )
    return ProofLeg(
        assertions=(
            AssertionEvidence(
                text=_FACTORY,
                proof_mode=PROOF_MODE_FACTORY_CAPTURED,
                leg=PROOF_RECORD_EVIDENCE_LEG,
                record_comment=None,
                check=None,
            ),
            AssertionEvidence(
                text=_HOST,
                proof_mode=PROOF_MODE_HOST_CAPTURED,
                leg="host-captured record",
                record_comment=_HOST_URL if replayed else None,
                check=CriterionCheck(text=_HOST, passed=True, reason="verified"),
            ),
        ),
        record=None,
        records=(captured, replay) if replayed else (captured,),
        reason="read",
        host=HostLeg(
            grades=(
                HostAssertionGrade(
                    text=_HOST,
                    passed=True if replayed else None,
                    reason="verified",
                    record_comment=_HOST_URL if replayed else None,
                ),
            ),
            verified_record=replay if replayed else None,
            refused=(),
        ),
    )


def _stages(*, journal: JournalFile) -> list[str]:
    text = journal.path.read_text(encoding="utf-8")
    return [str(json.loads(line)["stage"]) for line in text.splitlines() if line.strip()]


def _recorded_writes(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    written: list[str] = []

    def _record(**kwargs: object) -> None:
        written.append(str(kwargs["description"]))

    def _config(**_: object) -> Path:
        return tmp_path

    monkeypatch.setattr(_dispatcher_proof_pointer_write, "update_work_item_description", _record)
    monkeypatch.setattr(_dispatcher_proof_pointer_write, "store_config", _config)
    return written


def test_a_mixed_item_with_only_a_host_replay_gets_a_pointer_at_that_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written = _recorded_writes(monkeypatch=monkeypatch, tmp_path=tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    write_proof_pointer(
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(pr_number=7),
        proof=_leg(replayed=True),
        journal=journal,
    )

    assert len(written) == 1
    pointer = pointer_in(description=written[0])
    assert pointer is not None
    assert pointer.pull_request == 7
    assert pointer.record_url == _HOST_URL
    assert pointer.verdict == VERDICT_HOST_VERIFIED
    assert pointer.host_verified_url == _HOST_URL
    assert _stages(journal=journal) == ["proof-pointer"]


def test_a_captured_record_alone_still_earns_no_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written = _recorded_writes(monkeypatch=monkeypatch, tmp_path=tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    write_proof_pointer(
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(pr_number=7),
        proof=_leg(replayed=False),
        journal=journal,
    )

    assert written == []
    assert _stages(journal=journal) == ["proof-pointer-skipped"]


def test_a_later_dispatch_that_opened_no_pull_request_leaves_the_pointer_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written = _recorded_writes(monkeypatch=monkeypatch, tmp_path=tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    write_proof_pointer(
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(pr_number=7),
        proof=_leg(replayed=True),
        journal=journal,
    )
    assert len(written) == 1
    pointed = written[0]
    written.clear()
    write_proof_pointer(
        repo=tmp_path,
        item=_item(description=pointed),
        outcome=_outcome(pr_number=None),
        proof=_leg(replayed=True),
        journal=journal,
    )

    assert written == []
    pointer = pointer_in(description=pointed)
    assert pointer is not None
    assert pointer.pull_request == 7
