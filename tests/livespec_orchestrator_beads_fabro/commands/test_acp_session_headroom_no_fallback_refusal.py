"""What a below-floor reading COSTS a repository that declares no chain.

Binds the two consequences the headroom clause of `SPECIFICATION/contracts.md`
section "Dispatcher admission, WIP cap, and post-merge acceptance" attaches to
an emptied node, for the population `test_acp_session_headroom_no_fallback_
repository.py` establishes is covered: "If headroom skips leave an
admission-required node with no eligible candidate, a ready item remains ready
without a claim or blocked reason", and the per-node selection record must name
the skipped candidate. It is the no-fallback counterpart of
`test_acp_session_headroom_containment.py`, which binds the same two for a
repository whose chains are declared and enabled.

THE EXPENSIVE HALF IS THE ABSENCE OF A WRITE, so it is asserted by RECORDING
every ledger write the pass attempts and finding none. A refusal that also
claimed the item, or marked it blocked, leaves work stranded `active` with no
run behind it, and nothing in the refusal record itself would say so.

THE VERDICT IS RESOLVED FOR REAL, off a repository fixture that declares no ACP
configuration at all, and only the PROVIDER READ is injected. The admission
pass's own `session_headroom_policy` call is wrapped rather than replaced, so
the floor, the horizon and the at-most-once memo are the production builder's.
Substituting a hand-built verdict here -- as the containment module must, since
its chains are synthetic -- would assert this module's own fixture and say
nothing about the resolution a dispatch takes.

BOTH CASES READ ONE ADMISSION RUN, deliberately: the refusal and the assessment
record are two journal rows of the SAME evaluation, and asserting them against
two runs would let a build that wrote each correctly in isolation disagree about
which nodes one evaluation emptied.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as candidate
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import _dispatcher_admission as admission_module
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission_eligibility as eligibility_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import ANTHROPIC_DOMAIN
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    ACP_PREFLIGHT_REFUSAL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_NOW = "2026-10-17T16:46:00Z"
_FLOOR = 20
_ITEM_ID = "bd-ib-ready"
_CREDENTIAL = "cred-no-fallback"


@dataclass(frozen=True, kw_only=True)
class _Accounting:
    active_count: int = 0
    live_lock_active_ids: tuple[str, ...] = ()
    journal_unreadable_active_ids: tuple[str, ...] = ()
    green_terminal_active_ids: tuple[str, ...] = ()
    rework_pending_active_ids: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class _Pass:
    """One admission run's verdict, its journal rows, and its ledger writes."""

    admission: admission_module.Admission
    records: list[dict[str, Any]]
    writes: list[dict[str, object]]
    reads: list[str | None]


def _item() -> WorkItem:
    fields: dict[str, object] = {
        "id": _ITEM_ID,
        "type": "task",
        "status": "ready",
        "title": "Task",
        "description": "Do it.",
        "origin": "freeform",
        "gap_id": None,
        "rank": "a1",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-07-16T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
        "admission_policy": None,
        "acceptance_policy": None,
    }
    return WorkItem(**fields)  # pyright: ignore[reportArgumentType]


def _run_admission(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Pass:
    """One admission evaluation over a repository declaring no ACP chain."""
    repo = tmp_path / "governed"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text("{}\n", encoding="utf-8")
    reads: list[str | None] = []
    reading = headroom.session_headroom_reading(
        credential_identity=_CREDENTIAL, observed_at=_NOW, utilization=95
    )

    def counting_read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        _ = observed_at
        reads.append(token)
        return reading

    def wrapped_policy(**kwargs: Any) -> headroom.SessionHeadroomPolicy:
        return headroom_gate.session_headroom_policy(**kwargs, read=counting_read)

    writes: list[dict[str, object]] = []
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "projected-token")
    monkeypatch.setattr(admission_module, "session_headroom_policy", wrapped_policy)
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(
        admission_module,
        "update_work_item_status",
        lambda **kwargs: writes.append(dict(kwargs)),
    )
    monkeypatch.setattr(admission_module, "claimed_active_accounting", lambda **_: _Accounting())
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    journal_path = tmp_path / "journal.jsonl"

    admission = admission_module.admit_and_select(
        repo=repo,
        items=[],
        candidates=[_item()],
        journal=JournalFile(path=journal_path),
        enforce_cap=False,
    )

    records = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return _Pass(admission=admission, records=records, writes=writes, reads=reads)


def _one(*, records: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    [record] = [record for record in records if record["stage"] == stage]
    return record


def test_a_below_floor_reading_leaves_the_ready_item_ready_without_a_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal, and the ledger write that must not accompany it."""
    outcome = _run_admission(tmp_path=tmp_path, monkeypatch=monkeypatch)

    # The population, established rather than assumed: this fixture declares no
    # fallback-enabled chain, and its one provider read was taken.
    assert outcome.admission.verdict.fallback_enabled is False
    assert outcome.reads == ["projected-token"]

    # The item stays ready with no dispatch claim and no blocked_reason: the
    # pass attempted NO ledger write at all.
    assert outcome.admission.admitted == []
    assert outcome.writes == []
    assert [refused.work_item_id for refused in outcome.admission.refused] == [_ITEM_ID]

    refusal = _one(records=outcome.records, stage=ACP_PREFLIGHT_REFUSAL_STAGE)
    assert refusal["work_item_id"] == _ITEM_ID
    assert refusal["governing_condition"] == candidate.HEADROOM_SKIP
    assert refusal["session_headroom_floor_percent"] == _FLOOR
    assert refusal["exhausted"] == list(outcome.admission.verdict.admission_required)
    assert [entry["credential_identity"] for entry in refusal["session_headroom_assessments"]] == [
        _CREDENTIAL
    ]


def test_the_assessment_record_names_the_skipped_builtin_candidate_per_emptied_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every admission-required node the reading emptied names its own skip.

    The skipped candidate is the node's BUILT-IN single candidate, so the entry
    carries the built-in identity the resolution rendered -- which is how a
    reader joins the skip to the adapter that would have run, and how this case
    distinguishes an assessment that reached the node from a record that merely
    listed it.
    """
    outcome = _run_admission(tmp_path=tmp_path, monkeypatch=monkeypatch)
    verdict = outcome.admission.verdict

    assessment = _one(records=outcome.records, stage=SESSION_HEADROOM_STAGE)
    emptied = set(verdict.exhausted)
    # The reading governs every admission-required node here, because each one
    # resolves to exactly one covered built-in candidate.
    assert emptied == set(verdict.admission_required)
    assert emptied <= set(assessment["node_selections"])

    for node in sorted(emptied):
        selection = assessment["node_selections"][node]
        assert selection["selected_availability_key"] is None
        assert selection["selected_candidate_key"] is None
        [skip] = selection["headroom_skipped"]
        assert skip["availability_key"] == ANTHROPIC_DOMAIN
        assert str(skip["candidate_key"]).startswith("builtin-anthropic-")
        assert skip["session_headroom_floor_percent"] == _FLOOR
        assert skip["headroom_skip_kind"] == candidate.FLOOR_SKIP_KIND
        assert skip["headroom"]["credential_identity"] == _CREDENTIAL
