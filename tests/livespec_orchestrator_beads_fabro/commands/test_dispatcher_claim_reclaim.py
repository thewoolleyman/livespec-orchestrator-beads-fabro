"""Tests for dispatch-claim WIP-cap accounting."""

import importlib
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim import (
    claimed_active_accounting,
    claimed_active_count,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem


def test_claimed_active_count_reclaims_non_green_terminal_outcome(tmp_path: Path) -> None:
    item = _item(item_id="bd-failed", status="active")
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": item.id})
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {"work_item_id": item.id, "status": "failed", "stage": "fabro-run"},
        }
    )

    count = claimed_active_count(repo=tmp_path, items=[item], journal=journal)

    assert count == 0
    records = _records(path=journal.path)
    abandoned = records[-1]
    assert abandoned["stage"] == "dispatch-claim-abandoned"
    assert abandoned["work_item_id"] == item.id
    assert abandoned["reason"] == "terminal-outcome-non-green"


def test_claimed_active_count_reclaims_when_latest_admit_has_no_outcome(
    tmp_path: Path,
) -> None:
    item = _item(item_id="bd-killed", status="active")
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {"work_item_id": item.id, "status": "green", "stage": "done"},
        }
    )
    journal.append(record={"stage": "ledger-admit", "work_item_id": item.id})

    count = claimed_active_count(repo=tmp_path, items=[item], journal=journal)

    assert count == 0
    last_record = json.loads(journal.path.read_text(encoding="utf-8").splitlines()[-1])
    assert last_record["reason"] == "no-outcome-since-ledger-admit"


def test_claimed_active_count_reclaims_active_claim_with_missing_journal(
    tmp_path: Path,
) -> None:
    item = _item(item_id="bd-missing-journal", status="active")
    journal = JournalFile(path=tmp_path / "missing-journal.jsonl")

    count = claimed_active_count(repo=tmp_path, items=[item], journal=journal)

    assert count == 1
    assert not journal.path.exists()


def test_claimed_active_count_counts_active_claim_with_unreadable_journal(
    tmp_path: Path,
) -> None:
    item = _item(item_id="bd-unreadable-journal", status="active")
    journal = JournalFile(path=tmp_path)

    count = claimed_active_count(repo=tmp_path, items=[item], journal=journal)

    assert count == 1


def test_claimed_active_count_counts_null_run_terminal_claim_with_unreadable_journal(
    tmp_path: Path,
) -> None:
    item = _item(item_id="bd-unreadable-terminal", status="active")
    journal = JournalFile(path=tmp_path)

    count = claimed_active_count(repo=tmp_path, items=[item], journal=journal)

    assert count == 1


def test_claimed_active_count_tolerates_malformed_journal_for_active_items(
    tmp_path: Path,
) -> None:
    item = _item(item_id="bd-malformed-active", status="active")
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal_text = "\n".join(
        (
            "not-json",
            "[]",
            json.dumps({"stage": "ledger-admit", "work_item_id": 7}),
            json.dumps({"stage": "outcome", "outcome": "not-an-object"}),
            json.dumps({"stage": "outcome", "outcome": {"work_item_id": item.id}}),
        )
    )
    _ = journal.path.write_text(journal_text + "\n", encoding="utf-8")

    count = claimed_active_count(repo=tmp_path, items=[item], journal=journal)

    assert count == 0
    last_record = json.loads(journal.path.read_text(encoding="utf-8").splitlines()[-1])
    assert last_record["reason"] == "no-outcome-since-ledger-admit"


def test_claimed_active_count_reclaims_green_terminal_claim_and_failed_claim(
    tmp_path: Path,
) -> None:
    green = _item(item_id="bd-green-park", status="active")
    failed = _item(item_id="bd-failed-claim", status="active")
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": green.id})
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {"work_item_id": green.id, "status": "green", "stage": "done"},
        }
    )
    journal.append(record={"stage": "ledger-admit", "work_item_id": failed.id})
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {"work_item_id": failed.id, "status": "failed", "stage": "fabro-run"},
        }
    )

    count = claimed_active_count(repo=tmp_path, items=[green, failed], journal=journal)

    assert count == 0
    abandoned = [
        record
        for record in _records(path=journal.path)
        if record["stage"] == "dispatch-claim-abandoned"
    ]
    assert [record["work_item_id"] for record in abandoned] == [green.id, failed.id]
    assert [record["reason"] for record in abandoned] == [
        "green-terminal-active-reclaimed",
        "terminal-outcome-non-green",
    ]


def test_claimed_active_count_ignores_malformed_journal_for_inactive_items(
    tmp_path: Path,
) -> None:
    item = _item(item_id="bd-ready", status="ready")
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal_text = "\n".join(
        (
            "not-json",
            "[]",
            json.dumps({"stage": "ledger-admit", "work_item_id": 7}),
            json.dumps({"stage": "outcome", "outcome": "not-an-object"}),
            json.dumps({"stage": "outcome", "outcome": {"work_item_id": item.id}}),
        )
    )
    _ = journal.path.write_text(journal_text, encoding="utf-8")

    count = claimed_active_count(repo=tmp_path, items=[item], journal=journal)

    assert count == 0
    assert journal.path.read_text(encoding="utf-8") == journal_text


def test_claimed_active_projection_is_side_effect_free_with_matching_classification(
    tmp_path: Path,
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim"
    )
    assert hasattr(module, "claimed_active_projection")

    live = _item(item_id="bd-live", status="active")
    green = _item(item_id="bd-green", status="active")
    failed = _item(item_id="bd-failed", status="active")
    journal_unreadable = _item(item_id="bd-unreadable", status="active")
    ready = _item(item_id="bd-ready", status="ready")
    items = [live, green, failed, journal_unreadable, ready]
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    _ = write_dispatch_lock(repo=tmp_path, work_item_id=live.id, dispatch_id="live-dispatch")
    journal.append(record={"stage": "ledger-admit", "work_item_id": green.id})
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {"work_item_id": green.id, "status": "green", "stage": "done"},
        }
    )
    journal.append(record={"stage": "ledger-admit", "work_item_id": failed.id})
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {"work_item_id": failed.id, "status": "failed", "stage": "fabro-run"},
        }
    )
    original_bytes = journal.path.read_bytes()

    projection = module.claimed_active_projection(repo=tmp_path, items=items, journal=journal)
    second_projection = module.claimed_active_projection(
        repo=tmp_path, items=items, journal=journal
    )

    assert projection == second_projection
    assert journal.path.read_bytes() == original_bytes

    mutating_journal_path = tmp_path / "mutating-journal.jsonl"
    _ = mutating_journal_path.write_bytes(original_bytes)
    mutating = claimed_active_accounting(
        repo=tmp_path,
        items=items,
        journal=JournalFile(path=mutating_journal_path),
    )

    assert projection == mutating
    assert journal.path.read_bytes() == original_bytes
    mutating_records = _records(path=mutating_journal_path)
    assert [
        record["work_item_id"]
        for record in mutating_records
        if record["stage"] == "dispatch-claim-abandoned"
    ] == [green.id, failed.id, journal_unreadable.id]


def test_claimed_active_projection_counts_unreadable_journal_without_writing(
    tmp_path: Path,
) -> None:
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim"
    )
    assert hasattr(module, "claimed_active_projection")
    item = _item(item_id="bd-unreadable", status="active")
    journal = JournalFile(path=tmp_path)

    projection = module.claimed_active_projection(repo=tmp_path, items=[item], journal=journal)

    assert projection.active_count == 1
    assert projection.journal_unreadable_active_ids == (item.id,)
    assert tmp_path.is_dir()


def test_rework_pending_active_row_is_exposed_not_counted_and_not_abandoned(
    tmp_path: Path,
) -> None:
    """The sanctioned park is its own readable class, not a silent exclusion.

    A caller composing capacity truth must consume THIS verdict; exposing the
    class is what keeps it from re-deriving the rework class from the raw
    ledger label and becoming a second authority on the same question.
    """
    marked = _item(item_id="bd-rework-park", status="active", rework_pending=True)
    failed = _item(item_id="bd-failed-claim", status="active")
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": failed.id})
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {"work_item_id": failed.id, "status": "failed", "stage": "fabro-run"},
        }
    )

    accounting = claimed_active_accounting(repo=tmp_path, items=[marked, failed], journal=journal)

    assert accounting.rework_pending_active_ids == (marked.id,)
    assert accounting.active_count == 0
    abandoned = [
        record
        for record in _records(path=journal.path)
        if record["stage"] == "dispatch-claim-abandoned"
    ]
    # The unmarked failed sibling IS recorded abandoned, which is what proves
    # the marked row's absence here is the marker's doing and not a no-op.
    assert [record["work_item_id"] for record in abandoned] == [failed.id]


def test_rework_pending_marker_never_pre_empts_a_live_dispatch_lock(tmp_path: Path) -> None:
    """The double-selection guard is the lock, never the marker."""
    marked = _item(item_id="bd-rework-locked", status="active", rework_pending=True)
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    _ = write_dispatch_lock(repo=tmp_path, work_item_id=marked.id, dispatch_id="live-rework")

    accounting = claimed_active_accounting(repo=tmp_path, items=[marked], journal=journal)

    assert accounting.live_lock_active_ids == (marked.id,)
    assert accounting.rework_pending_active_ids == ()
    assert accounting.active_count == 1


def test_counted_claim_total_is_identical_from_every_checkout_of_one_tenant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTROL reproducing the 2026-08-22 measurement behind `bd-ib-snyquw.6`.

    Two checkouts of ONE tenant, one of them holding a live dispatch lock, both
    queried in the same second. Before the fix they reported DISJOINT
    counted-claim totals (the lock-holder 1, its peer 0), because both counting
    inputs resolved from the invoking `--repo` path rather than from the tenant
    — so N checkouts admitted up to N x `wip_cap`. `SPECIFICATION/contracts.md`
    requires that bound to be TENANT-scoped, which is this equality.

    Both journals are READABLE and both carry the row's `ledger-admit`, which is
    what isolates the lock term: a peer that counted the row only because its
    own journal was missing would pass this by the wrong mechanism.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    dispatching = _tenant_checkout(root=tmp_path, name="dispatching-checkout")
    peer = _tenant_checkout(root=tmp_path, name="peer-checkout")
    item = _item(item_id="bd-tenant-wide-claim", status="active")
    _ = write_dispatch_lock(repo=dispatching, work_item_id=item.id, dispatch_id="disp-tenant")
    dispatching_journal = _admitted_journal(repo=dispatching, item_id=item.id)
    peer_journal = _admitted_journal(repo=peer, item_id=item.id)

    from_dispatching = claimed_active_count(
        repo=dispatching, items=[item], journal=dispatching_journal
    )
    from_peer = claimed_active_count(repo=peer, items=[item], journal=peer_journal)

    assert from_dispatching == 1
    assert from_peer == from_dispatching


def test_a_merge_held_items_green_terminal_run_is_reclaimed_and_counts_no_claim(
    tmp_path: Path,
) -> None:
    """A held item holds NO capacity slot, by the ORDINARY green-terminal rule.

    This is a regression lock rather than a new mechanism, and the distinction is
    the point. An earlier draft of the ratified hold kept the claim counted
    against `wip_cap`, which contradicts the green-terminal reclamation rule and
    was discharged; the settled contract says a held item's run is reclaimed
    "exactly as every green terminal outcome is". So the item stays `active` with
    its hold, its run terminates green at the pr stage, and the accounting must
    classify it green-terminal — uncounted — with no held-item special case
    anywhere in the reclamation path. A hold that silently consumed a slot would
    starve the queue for as long as the maintainer's merge window lasted.
    """
    item = _item(item_id="bd-held", status="active")
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": item.id})
    journal.append(
        record={
            "stage": "outcome",
            "outcome": {"work_item_id": item.id, "status": "green", "stage": "pr"},
        }
    )

    accounting = claimed_active_accounting(repo=tmp_path, items=[item], journal=journal)

    assert accounting.active_count == 0
    assert accounting.green_terminal_active_ids == (item.id,)
    assert accounting.live_lock_active_ids == ()
    assert _records(path=journal.path)[-1]["reason"] == "green-terminal-active-reclaimed"


def test_a_budget_rested_item_is_not_a_counted_claim_and_is_not_reclaimed(
    tmp_path: Path,
) -> None:
    """An item resting at `blocked` after a budget cancel holds no `wip_cap` slot.

    Scenario 175, "A run resting for a person blocks no admission". The journal
    still carries the item's `ledger-admit` and `run-wall-budget-exceeded` rows,
    which is what a count keyed on the journal rather than on status would read
    as a claim. It is also not an abandoned claim: reclamation writes a
    `dispatch-claim-abandoned` row for an `active` item only, and a row written
    for the rested item would mark a sanctioned rest as a leak.
    """
    rested = _item(item_id="bd-budget-rested", status="blocked")
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": rested.id})
    journal.append(
        record={
            "stage": "run-wall-budget-exceeded",
            "work_item_id": rested.id,
            "bound_exceeded": "ceiling",
        }
    )

    accounting = claimed_active_accounting(repo=tmp_path, items=[rested], journal=journal)

    assert accounting.active_count == 0
    assert accounting.live_lock_active_ids == ()
    assert [record["stage"] for record in _records(path=journal.path)] == [
        "ledger-admit",
        "run-wall-budget-exceeded",
    ]


def _tenant_checkout(*, root: Path, name: str) -> Path:
    """A checkout of one shared tenant, declared the way a real one declares it."""
    checkout = root / name
    checkout.mkdir(parents=True)
    _ = (checkout / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"tenant": "control-tenant", "prefix": "bd-ib"}
                }
            }
        ),
        encoding="utf-8",
    )
    return checkout


def _admitted_journal(*, repo: Path, item_id: str) -> JournalFile:
    journal = JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": item_id})
    return journal


def _item(*, item_id: str, status: str, rework_pending: bool = False) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status=status,
        rework_pending=rework_pending,
        title="Claim",
        description="Dispatch claim fixture.",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-26T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _records(*, path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
