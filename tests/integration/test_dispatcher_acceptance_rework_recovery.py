"""Integration-tier acceptance for the ai-fail-auto-rework recovery routing.

Drives the under-cap FAIL route of the post-merge acceptance valve
(`SPECIFICATION/contracts.md`) through the real disposition and the real
store/client seam against the in-memory `FakeBeadsClient` (the hermetic CI
backend). Only the acceptance pass is stood in, so the routing decision, the
journal records, and the ledger writes are the production code paths.

What this binds, per the ratified rework-pending re-dispatch contract: the
under-cap FAIL parks the item `active` and STAMPS `rework:pending` in the same
disposition. The marker is what makes the park reachable — it is the drain's
selection input, and `dispatch --item` accepts a marked item — which is exactly
what an earlier `active` return lacked when it was reachable by no route at all.

- A merged failed item is parked `active` carrying the marker, and its
  disposition record names the fix-forward rework re-dispatch plus the ordering
  that the criteria defect is fixed BEFORE that re-dispatch runs. It does NOT
  name `reconcile-merged`, which refuses a marked item precisely because this
  disposition already ran.
- An unmerged failed item is parked the same way and advertises no recovery
  clause: the ordinary rework re-dispatch IS the whole route.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    """Resolve the store onto the in-memory fake, fresh per case.

    There is no shared conftest at this tier, so each case owns both halves:
    the `LIVESPEC_BEADS_FAKE` resolution the production `store_config` reader
    consults, and the process-singleton reset.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title="A dispatched slice whose AI acceptance pass fails",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _outcome(*, item_id: str, pr_number: int | None, merge_sha: str | None) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item_id,
        status="green",
        stage="done",
        pr_number=pr_number,
        merge_sha=merge_sha,
        detail="merged" if merge_sha is not None else "no merge recorded",
    )


@dataclass(frozen=True, kw_only=True)
class _FailingAcceptancePass:
    """The acceptance pass seam, standing in a dispositive FAIL verdict."""

    # The proof leg the real pass carries. `None` is what a legacy-source item
    # resolves to, and it is the right stand-in here: these cases are about the
    # DISPOSITION the verdict routes to, and the pointer write skips an item
    # with no record rather than changing which branch runs.
    proof: None = None

    verdict: str = "FAIL"
    absent_evidence: tuple[str, ...] = ()

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {
            "stage": "acceptance-ai-pass",
            "work_item_id": work_item_id,
            "verdict": self.verdict,
            "acceptance_policy": policy,
        }


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def _rework_disposition(*, journal: JournalFile) -> dict[str, object]:
    records = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    return next(
        record
        for record in records
        if record.get("stage") == "auto-disposition"
        and record.get("disposition") == "ai-fail-auto-rework"
    )


def _fail_acceptance(
    *,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    monkeypatch: pytest.MonkeyPatch,
    merge_sha: str | None,
    pr_number: int | None,
) -> None:
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        _dispatcher_completion,
        "run_acceptance_pass",
        lambda **_: _FailingAcceptancePass(),
    )
    _dispatcher_completion.complete_and_accept(
        repo=repo,
        item=item,
        outcome=_outcome(item_id=item.id, pr_number=pr_number, merge_sha=merge_sha),
        journal=journal,
    )


def test_merged_failed_acceptance_parks_marked_and_names_the_rework_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item(item_id="bd-ib-rework-merged")
    journal = JournalFile(path=repo / "merged-journal.jsonl")

    _fail_acceptance(
        repo=repo,
        item=item,
        journal=journal,
        monkeypatch=monkeypatch,
        merge_sha="feed01",
        pr_number=11,
    )

    stored = _stored()[item.id]
    # Parked `active` and MARKED: the marker is the selection input the rework
    # re-dispatch reads, so the park is visible and brief rather than stranded.
    assert (stored.status, stored.blocked_reason) == ("active", None)
    assert stored.rework_pending is True
    disposition = _rework_disposition(journal=journal)
    assert disposition["recovery"] == "rework-re-dispatch"
    ordering = disposition["recovery_ordering"]
    assert isinstance(ordering, str)
    # The record carries the ORDERING, not merely the route name: re-dispatching
    # first re-fails on the same criteria fragment.
    assert "acceptance-criteria defect" in ordering
    assert "BEFORE the rework " in ordering
    assert "acceptance_rework_cap" in ordering


def test_unmerged_failed_acceptance_parks_marked_without_a_recovery_clause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item(item_id="bd-ib-rework-unmerged")
    journal = JournalFile(path=repo / "unmerged-journal.jsonl")

    _fail_acceptance(
        repo=repo,
        item=item,
        journal=journal,
        monkeypatch=monkeypatch,
        merge_sha=None,
        pr_number=None,
    )

    stored = _stored()[item.id]
    assert (stored.status, stored.blocked_reason) == ("active", None)
    assert stored.rework_pending is True
    disposition = _rework_disposition(journal=journal)
    # Nothing has merged, so no fix-forward ordering is advertised: the ordinary
    # rework re-dispatch IS the whole recovery.
    assert "recovery" not in disposition
    assert "recovery_ordering" not in disposition
