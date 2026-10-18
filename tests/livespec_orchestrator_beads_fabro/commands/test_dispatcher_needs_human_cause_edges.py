"""The causal record's partial-evidence arms, and its ledger-write failure.

Separate from `test_dispatcher_needs_human_cause.py` because these shapes were
found by a coverage measurement taken after that module's Red was authored, and
a Red's test bytes are fixed across its Red-to-Green pair.

WHAT THESE ARMS HAVE IN COMMON is that the engine recorded a stage failure and
then supplied LESS than the full account of it. Each of them is the record's
chance to invent the missing half, and the reason they get their own module is
that the full-evidence case cannot distinguish a build that reports what it
measured from one that fills gaps with plausible values — the full case has no
gaps. A record naming a stage the verdict never attributed, or a command the
engine never quoted, is worse than one that stays quiet: it is append-only, so
nothing downstream can retract it, and it reads exactly like a measured one.

The write-failure arm is here for a different reason. The record is an ACCOUNT
of an ending that has already happened, so losing it must not convert a
finished dispatch into a failed one — but it must not pass silently either, or
an operator finding no record cannot tell a build that never wrote one from a
tenant that refused the write.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import _dispatcher_needs_human_cause as record_mod
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    NEEDS_HUMAN_CAUSE_MARKER,
    needs_human_cause_body,
    record_needs_human_cause,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_detail import (
    NEEDS_HUMAN_CAUSE_ABSENT,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import STAGE_FAILURE
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-anfa5t"
_RUN = "01M44F9E56XCEWZNMVJX4M14Z6"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _write_config(project_root: Path) -> None:
    _ = (project_root / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
""",
        encoding="utf-8",
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status="active",
        title="Preserve causal ACP transport faults through needs_human terminals",
        description="A transport fault is not a question.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason=None,
    )


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _fault_outcome(
    *,
    stages: tuple[str, ...] | None,
    cause: str | None,
    category: str | None = None,
    signature: str | None = None,
) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="rendered elsewhere",
        fabro_run_id=_RUN,
        fabro_failure_cause=cause,
        fabro_failure_category=category,
        fabro_failure_signature=signature,
        needs_human_kind=STAGE_FAILURE,
        needs_human_stages=stages,
    )


def test_a_stage_failure_with_no_attributed_stage_names_none() -> None:
    """The verdict said stage-failure but attributed no stage, so none is named.

    Reachable because the two are independent fields on the terminal
    checkpoint: a node can be recorded failed while the outcome map the stage
    list is read from is unreadable. The cause is still reported, because that
    was measured.
    """
    body = needs_human_cause_body(
        outcome=_fault_outcome(stages=(), cause="ACP adapter exited before protocol completed")
    )

    assert "failed stage" not in body
    assert "innermost cause: ACP adapter exited before protocol completed" in body
    assert "transport fault: adapter-exited" in body


def test_a_stage_failure_with_no_cause_states_the_absence_and_classifies_nothing() -> None:
    """A failed stage the engine classified no cause for SAYS the cause is absent.

    This is the `publish_draft` refusal shape: the node writes its whole
    diagnosis to its own output and the engine records no cause chain at all.
    A classification here would be invented from nothing, so none is made —
    but the missing cause is itself reported (`bd-ib-3nu5vv`), because this
    kind has already claimed a fault and omitting the clause made this record
    identical to one for an ending that genuinely had no cause.
    """
    body = needs_human_cause_body(outcome=_fault_outcome(stages=("publish_draft",), cause=None))

    assert "failed stage: publish_draft" in body
    assert NEEDS_HUMAN_CAUSE_ABSENT in body
    assert "transport fault" not in body
    assert "no answer is owed" in body


def test_a_backgrounded_cause_naming_no_command_invents_one() -> None:
    """A cause that classifies but quotes no command names the family only.

    The engine owns that wording, so a cause carrying the marker without the
    parenthesised command yields the family and nothing else — the same
    restraint `TransportFault` applies, asserted here at the record it reaches.
    """
    body = needs_human_cause_body(
        outcome=_fault_outcome(
            stages=("pr",),
            cause="the ACP tool call continued in background and the turn ended",
        )
    )

    assert "transport fault: backgrounded-tool" in body
    assert "backgrounded command" not in body
    assert "backgrounded task" not in body


def test_a_refused_ledger_write_is_journaled_and_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tenant that refuses the append leaves a journal row, not an exception.

    Both halves matter. Raising would convert an ending that already completed
    into a dispatch failure after the fact; staying silent would leave an
    operator unable to tell a build that writes no record from a write the
    tenant refused. The row names the error type, which is what says which.
    """
    _write_config(tmp_path)
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()

    def _refuse(**_kwargs: object) -> None:
        raise BeadsCommandError(
            command="bd comment bd-ib-anfa5t", exit_code=1, stderr="tenant refused the append"
        )

    monkeypatch.setattr(record_mod, "append_work_item_comment", _refuse)

    record_needs_human_cause(
        repo=tmp_path,
        item=_item(),
        outcome=_fault_outcome(stages=("pr",), cause=None),
        journal=journal,
    )

    assert {
        "stage": "needs-human-cause-record-error",
        "work_item_id": _ITEM,
        "needs_human_kind": STAGE_FAILURE,
        "reason": "BeadsCommandError",
    } in journal.records
    assert not any(
        NEEDS_HUMAN_CAUSE_MARKER in comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM)
    )
