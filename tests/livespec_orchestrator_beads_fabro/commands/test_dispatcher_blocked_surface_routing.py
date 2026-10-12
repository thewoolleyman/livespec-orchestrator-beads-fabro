"""The escalation's STDERR line parts company with the three endings too.

`_dispatcher_needs_human_detail` already splits the outcome DETAIL three ways.
This module is about the OTHER channel the same ending reaches an operator on,
and it exists because fixing one while leaving the other made the drive result
contradict itself in a single payload.

`drive` captures the dispatcher's stderr beside `stdout_json`, so both land in
the same result an operator reads. While `escalate_needs_human_block` emitted
one wording for every ending — `parked at a Fabro human gate ... held terminal
until a human valve moves it out` — a transport fault produced a result whose
`detail` said no agent asked anything and whose `stderr` said the run was
parked at a human gate. A reader resolving that contradiction has no reason to
prefer the correct half, and the incorrect half is the one that names an action
(answer the gate), so it is the one they act on.

THE THREE ENDINGS ARE ASSERTED TOGETHER, for the reason the detail's own tests
give: each arm alone is satisfied by a build that loses the others. The fault
arm alone is satisfied by a build that stopped mentioning the valve at all,
which would describe a state with no way out; the request arm alone is
satisfied by the undifferentiated wording this module exists to retire; and
without the unestablished arm a record that grounds neither answer gets
whichever of the two the code happens to fall through to.

WHAT THE LIFECYCLE DOES NOT DO IS CHANGE. Every arm still writes `blocked` /
`needs-human` and still names `resolve-blocked:<id>:ready`, because the item
rests in one place and leaves by one valve whatever routed it there. A
transport fault is not evidence that an agent asked a question; it is equally
not grounds for a different ledger state. The assertions below check the stored
status in all three arms so a rewording cannot quietly move it.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked import (
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    AGENT_REQUEST,
    STAGE_FAILURE,
    UNESTABLISHED,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.work_items.types import StoredBlockedReason, WorkItemStatus

_ITEM = "bd-ib-anfa5t"
_VALVE = f"`resolve-blocked:{_ITEM}:ready`"

# The field the routing reads. Named here rather than inline because the first
# assertion of every case below is that it EXISTS: the routing cannot be
# expressed without it, so a build lacking it must fail on an assertion about
# the field rather than on a TypeError raised while constructing the outcome.
_KIND_FIELD = "needs_human_kind"

# The wording the undifferentiated line always carried. It is correct for
# exactly one of the three endings and is asserted ABSENT from the other two.
_GATE_PHRASE = "parked at a Fabro human gate"
_VALVE_WAIT_PHRASE = "held terminal until a human valve"


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


def _item(
    *,
    status: WorkItemStatus = "active",
    blocked_reason: StoredBlockedReason | None = None,
) -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status=status,
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
        blocked_reason=blocked_reason,
    )


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _escalate(
    *,
    tmp_path: Path,
    kind: str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[str, WorkItem]:
    """Drive the real escalation for one ending and return its stderr line.

    The ledger write is the production store bridge over the fake tenant, so
    the stored status read back afterwards is what the escalation actually
    persisted rather than what the outcome claimed.
    """
    _write_config(tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    escalate_needs_human_block(
        repo=tmp_path,
        item=item,
        outcome=DispatchOutcome(
            work_item_id=_ITEM,
            status="blocked",
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail="rendered elsewhere; this case is about the other channel",
            **{_KIND_FIELD: kind},
        ),
        journal=_RecordingJournal(),
    )
    stored = materialize_work_items(records=read_work_items(path=_config()))[_ITEM]
    return (capsys.readouterr().err, stored)


def _assert_field_exists() -> None:
    """The routing's input, asserted before any outcome is built with it."""
    names = {entry.name for entry in dataclasses.fields(DispatchOutcome)}
    assert _KIND_FIELD in names


def test_a_stage_fault_escalation_does_not_announce_a_human_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fault arm: triage guidance, and no gate for the operator to answer."""
    _assert_field_exists()

    line, stored = _escalate(tmp_path=tmp_path, kind=STAGE_FAILURE, capsys=capsys)

    assert _GATE_PHRASE not in line
    assert _VALVE_WAIT_PHRASE not in line
    assert "no answer is owed" in line
    assert _VALVE in line
    assert (stored.status, stored.blocked_reason) == ("blocked", "needs-human")


def test_a_genuine_request_escalation_keeps_its_gate_wording(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The request arm: unchanged, because it was never the one mis-rendered."""
    _assert_field_exists()

    line, stored = _escalate(tmp_path=tmp_path, kind=AGENT_REQUEST, capsys=capsys)

    assert _GATE_PHRASE in line
    assert _VALVE_WAIT_PHRASE in line
    assert (stored.status, stored.blocked_reason) == ("blocked", "needs-human")


def test_an_unestablished_escalation_claims_neither_ending(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The third arm: says the ending is unexplained rather than picking one."""
    _assert_field_exists()

    line, stored = _escalate(tmp_path=tmp_path, kind=UNESTABLISHED, capsys=capsys)

    assert _GATE_PHRASE not in line
    assert "does not establish" in line
    assert _VALVE in line
    assert (stored.status, stored.blocked_reason) == ("blocked", "needs-human")


def test_an_unrouted_escalation_keeps_the_legacy_wording(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An outcome carrying no verdict is the legacy shape, and keeps its line.

    Every pre-existing caller builds the outcome without the field, so the
    default has to leave their wording alone. Asserting it here is what stops
    the routing from being introduced as a silent behaviour change to the
    callers that never opted into it — the dispatcher's own non-Fabro blocked
    paths among them.
    """
    _write_config(tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)

    escalate_needs_human_block(
        repo=tmp_path,
        item=item,
        outcome=DispatchOutcome(
            work_item_id=_ITEM,
            status="blocked",
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail="a legacy caller that knows nothing about the three endings",
        ),
        journal=_RecordingJournal(),
    )

    assert _GATE_PHRASE in capsys.readouterr().err
