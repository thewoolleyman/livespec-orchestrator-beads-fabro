"""Integration-tier acceptance for the enumerated wait set and its handoffs.

Binds two `SPECIFICATION/scenarios.md` headings through one composed snapshot,
because the second is a property OF the first and cannot be checked apart from
it:

- "Scenario 85 — Every enumerated orchestrator-owned wait composes with its
  unblock": all six waits are seeded into ONE tenant and one snapshot is
  composed, so the assertion is completeness rather than six independent
  presence checks. A per-lane test cannot fail the way this one can — a lane
  that composes correctly in isolation and is never wired into the snapshot
  passes it.
- "Scenario 80 — Every advertised handoff is executable as advertised": each
  drive-kind handoff the composed envelope advertises is then SUBMITTED to the
  real `drive.run_action` enforcer. Asserting that a handoff exists proves
  nothing about whether the enforcer would take it; only executing it does.

The negative leg of each is what makes them load-bearing. The healthy admitted
item must produce no wait, and a state drive refuses by construction must never
be advertised — checked against the same envelope, so the advertiser and the
enforcer are compared rather than each being asked about itself.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.attention_item import AttentionItem
from livespec_runtime.needs_attention import SpecNextOutput

_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"
_CRITERIA = "The change is verified green by the check suite."


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    # Keep build_attention composition independent of this host's plugin build:
    # the currency-staleness lane reads the provisioned build vs the marketplace
    # release clone, and a mid-session release makes those diverge and leaks a
    # hygiene row into the snapshot. The lane keeps its own dedicated coverage in
    # test_needs_attention_currency_staleness.py and its build_attention wiring in
    # test_dispatcher_plugin_currency_scenario95.py.
    monkeypatch.setattr(needs_attention, "currency_staleness_items", lambda **_kwargs: [])
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed(*, id_: str, status: str, rank: str, **overrides: object) -> None:
    base = WorkItem(
        id=id_,
        type="task",
        status="active",
        title=f"{id_} title",
        description="d",
        origin="freeform",
        gap_id=None,
        rank=rank,
        assignee=None,
        depends_on=(),
        captured_at="2026-08-24T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria=_CRITERIA,
    )
    append_work_item(path=_config(), item=replace(base, status=status, **overrides))  # pyright: ignore[reportArgumentType]


def _write_project(*, root: Path, wip_cap: int = 1) -> None:
    (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {"wip_cap": wip_cap, "auto_approve_ready": True},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_journal(*, root: Path, records: list[dict[str, object]]) -> None:
    journal = root / _JOURNAL
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _provider_exhaustion_record() -> dict[str, object]:
    return {
        "stage": "provider-exhaustion-observed",
        "work_item_id": "bd-prior",
        "provider": "codex",
        "governing_condition": "provider_usage_limit",
        "record_expires_at": "2099-01-01T00:00:00Z",
    }


def _needs_attention_park_records(*, work_item_id: str) -> list[dict[str, object]]:
    return [
        {
            "stage": "acceptance-ai-pass",
            "work_item_id": work_item_id,
            "verdict": "NEEDS_ATTENTION",
            "acceptance_policy": "human-only",
            "diff": {"observed": False, "reason": "missing-merge-evidence"},
            "criteria": {"observed": True, "checks": []},
            "telemetry": {"observed": False, "reason": "missing-run-turn"},
        },
        {
            "stage": "acceptance-parked",
            "work_item_id": work_item_id,
            "policy": "human-only",
            "advisory": True,
            "acceptance_verdict": "NEEDS_ATTENTION",
        },
    ]


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def _snapshot(*, root: Path, monkeypatch: pytest.MonkeyPatch) -> list[AttentionItem]:
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    return build_attention(project_root=root, repo_name="repo", include_hygiene=False)


def _seed_every_wait(*, root: Path) -> None:
    """Seed one instance of each enumerated wait plus one healthy admitted item.

    `bd-healthy` is the admitted item: `active` and holding a live dispatch
    lock. It is what fills the WIP cap, which is what makes `bd-deferred` a
    capacity-deferred hold — the two facts are the same fact seen from the two
    ends, so they are seeded together deliberately.
    """
    _write_project(root=root, wip_cap=1)
    _seed(id_="bd-healthy", status="active", rank="a1")
    _seed(id_="bd-deferred", status="active", rank="a2")
    _seed(id_="bd-parked", status="acceptance", rank="a3", acceptance_policy="human-only")
    _seed(id_="bd-blocked", status="blocked", rank="a4", blocked_reason="needs-human")
    _seed(id_="bd-approval", status="pending-approval", rank="a5", admission_policy="manual")
    _seed(id_="bd-host", status="ready", rank="a6", factory_safety="needs-host-secrets")
    _seed(id_="bd-held", status="ready", rank="a7")
    _ = write_dispatch_lock(repo=root, work_item_id="bd-healthy", dispatch_id="run-healthy")
    _write_journal(
        root=root,
        records=[
            _provider_exhaustion_record(),
            *_needs_attention_park_records(work_item_id="bd-parked"),
        ],
    )


def test_all_six_enumerated_waits_compose_and_the_admitted_item_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_every_wait(root=tmp_path)

    attention = _snapshot(root=tmp_path, monkeypatch=monkeypatch)

    assert {item.id for item in attention} == {
        # 1. capacity-deferred eligible item, reported as its own hold
        "hygiene:capacity:repo",
        "hygiene:capacity-hold:bd-deferred",
        # 2. NEEDS_ATTENTION-parked acceptance
        "valve:accept:bd-parked",
        # 3. blocked on a needs-human reason
        "valve:resolve-blocked:bd-blocked",
        # 4. pending-approval under an effective manual admission policy
        "valve:approve:bd-approval",
        # 5. factory-unsafe ready work awaiting host routing
        "host-only:needs-host-secrets:bd-host",
        # 6. ready work held by an unexpired provider-exhaustion record
        "hygiene:provider-exhaustion:codex:bd-held",
    }
    # Every wait carries an unblock: a drive action a human can take, or a
    # runnable shell handoff. A wait with nothing to do about it is the
    # failure this clause exists to prevent.
    for item in attention:
        assert (item.handoff.action_id or item.handoff.command).strip() != "", item.id
    # The healthy admitted item is not a wait: nothing in the snapshot names it.
    assert "bd-healthy" not in {item.source_ref.work_item for item in attention}


def test_the_parked_acceptance_is_one_item_naming_both_reject_dispositions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_every_wait(root=tmp_path)

    attention = _snapshot(root=tmp_path, monkeypatch=monkeypatch)

    [parked] = [item for item in attention if item.source_ref.work_item == "bd-parked"]
    assert parked.handoff.action_id == "accept:bd-parked"
    assert "reject:bd-parked:rework" in parked.summary
    assert "reject:bd-parked:regroom" in parked.summary


def test_every_advertised_drive_handoff_is_accepted_by_drive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_every_wait(root=tmp_path)
    attention = _snapshot(root=tmp_path, monkeypatch=monkeypatch)
    advertised = [item for item in attention if item.handoff.kind == "drive"]
    assert [item.handoff.action_id for item in advertised] == [
        "accept:bd-parked",
        "resolve-blocked:bd-blocked:ready",
        "approve:bd-approval",
    ]

    results: dict[str, dict[str, Any]] = {
        item.handoff.action_id: run_action(repo=tmp_path, action_id=item.handoff.action_id)
        for item in advertised
    }

    # Submitted to the enforcer, not merely inspected: every advertised action
    # is one drive takes.
    assert {action: result["status"] for action, result in results.items()} == {
        "accept:bd-parked": "green",
        "resolve-blocked:bd-blocked:ready": "green",
        "approve:bd-approval": "green",
    }


def test_a_state_drive_refuses_by_construction_is_never_advertised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(root=tmp_path)
    # `auto_approve_ready` makes this item's effective admission policy `auto`,
    # so the Dispatcher owns it and the human approve valve refuses it by
    # construction.
    _seed(id_="bd-auto", status="pending-approval", rank="a1")

    attention = _snapshot(root=tmp_path, monkeypatch=monkeypatch)
    refusal = run_action(repo=tmp_path, action_id="approve:bd-auto")

    assert refusal["status"] == "failed"
    assert refusal["summary"] == "approve requires an effective-manual pending-approval item."
    assert "approve:bd-auto" not in {item.handoff.action_id for item in attention}
    # It is surfaced — just not as an action the enforcer would reject. The
    # awaiting-admission lane is selected by id rather than by referent, because
    # an auto-admissible item on an idle factory is also the idle-factory fact's
    # first ranked dispatch, and that row names the same work-item.
    [awaiting] = [item for item in attention if item.id.startswith("hygiene:awaiting-admission:")]
    assert awaiting.id == "hygiene:awaiting-admission:bd-auto"
    assert awaiting.handoff.kind == "shell"
    assert awaiting.source_ref.work_item == "bd-auto"
