"""The `reconcile-runs` command EMITS what its claim lane did.

The claim lane graded, journaled and disposed of claims correctly from the
day it landed, and reported none of it: `_emit` read `summary.held` and
`summary.reconciled` alone, so every pass printed `"held": []` and
`"reconciled": []` and a pass that had just released a stranded claim printed
`(no orphaned fabro runs found)`. The dispatch journal under the running
checkout's `tmp/` tree was the only surface carrying a claim's disposition,
and that tree is gone the moment the checkout is pruned.

These cases drive the COMMAND rather than the summary, which is the whole
point: `test_dispatcher_reconcile_runs_claim_lane.py` asserts on
`ReconcileRunsSummary` directly and therefore cannot observe the emission at
all — which is why a complete claim lane shipped behind a silent surface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs_command as cli
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_grace import HeldRun
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_records import (
    ReconciledRun,
    ReconcileRunsSummary,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    HeldClaim,
    RecoveredClaim,
)
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.types import WorkItem

_HP = FactoryTarget(name="hp", server="https://hp.example:32276", dev_token=None)


def test_a_held_claim_is_listed_in_the_json_held_lane(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The clause's own words: stranded claims JOIN `held` rather than replace it."""
    _ = _stub(
        monkeypatch=monkeypatch,
        summary=_summary(held=(_held_run(),), held_claims=(_held_claim(),)),
    )

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert [entry["work_item_id"] for entry in payload["held"]] == [
        "bd-ib-parked",
        "bd-ib-attribution",
    ]
    # Both lanes, in one array, each naming which KIND it is: a run holds a
    # park measurement and a claim holds a dispatching host, so a reader
    # discriminating them by which keys happen to be present is reading a
    # shape-dependent listing rather than a labelled one.
    assert [entry.get("kind") for entry in payload["held"]] == ["run", "claim"]
    claim = payload["held"][1]
    assert claim["hold_reason"] == "attribution-pending"
    assert claim["dispatching_host"] == "hp-xubuntu"
    assert claim["remedy"] == "move it with drive --action"


def test_a_recovered_claim_is_listed_in_the_json_reconciled_lane(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _stub(
        monkeypatch=monkeypatch,
        summary=_summary(reconciled=(_run(),), recovered_claims=(_recovered(),)),
    )

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert [entry["work_item_id"] for entry in payload["reconciled"]] == [
        "bd-ib-orphan",
        "bd-ib-stranded",
    ]
    assert [entry.get("kind") for entry in payload["reconciled"]] == ["run", "claim"]
    recovered = payload["reconciled"][1]
    assert recovered["work_item_id"] == "bd-ib-stranded"
    assert recovered["reason"] == "run-absent"
    assert recovered["route"] == "absent-run-release"
    assert recovered["status"] == "ready"
    assert recovered["effects_written"] == ["journal", "comment", "transition"]


def test_a_claim_only_pass_renders_human_lines_rather_than_reading_as_empty(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The measured defect: a pass that RELEASED a claim printed nothing found.

    No run lane acts here, so the `(no orphaned fabro runs found)`
    fall-through is reachable and would fire on a pass that had just written
    three durable effects.
    """
    _ = _stub(
        monkeypatch=monkeypatch,
        summary=_summary(recovered_claims=(_recovered(),), held_claims=(_held_claim(),)),
    )

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path)])

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "RECLAIM bd-ib-stranded  01GONE  factory=hp reason=run-absent "
        "route=absent-run-release status=ready\n"
        "CLAIM   bd-ib-attribution  01PENDING  factory=hp host=hp-xubuntu "
        "reason=attribution-pending remedy=move it with drive --action\n"
    )


def test_a_hold_the_claim_stamp_could_not_name_renders_each_absent_field(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`claim-unattributable` carries no run, factory or host to print.

    A blank where a value belongs reads as a rendering fault rather than as
    the absence that IS the finding, so every unnamed field says so.
    """
    _ = _stub(monkeypatch=monkeypatch, summary=_summary(held_claims=(_unattributable(),)))

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path)])

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "CLAIM   bd-ib-bare  (none)  factory=(none) host=(none) reason=claim-unattributable\n"
    )


def test_the_pass_record_says_whether_the_claim_lane_did_anything(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A timer tick that released a claim was byte-identical to an idle one."""
    _ = _stub(
        monkeypatch=monkeypatch,
        summary=_summary(recovered_claims=(_recovered(),), held_claims=(_held_claim(),)),
    )
    journal = tmp_path / "journal.jsonl"

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path), "--journal", str(journal)])
    _ = capsys.readouterr()

    records = [
        record
        for record in (
            json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()
        )
        if record.get("stage") == "reconcile-runs-pass"
    ]
    assert exit_code == 0
    assert len(records) == 1
    assert records[0].get("claims_recovered") == 1
    assert records[0].get("claims_held") == 1
    # The claim lane is NOT folded into the orphan census: an orphan is a run
    # the join produced, and counting a claim as one would make a stranded
    # claim read as a factory run this pass failed to terminate.
    assert records[0]["orphans_found"] == 0


def _stub(
    *,
    monkeypatch: pytest.MonkeyPatch,
    summary: ReconcileRunsSummary,
) -> dict[str, object]:
    calls: dict[str, object] = {}

    def _load_items(*, repo: Path) -> list[WorkItem]:
        calls["items_repo"] = repo
        return []

    def _store_config(*, repo: Path) -> Any:
        calls["store_repo"] = repo
        return _StoreConfig()

    def _factories(*, repo: Path, factory: str | None = None) -> tuple[FactoryTarget, ...]:
        calls["factories"] = (repo, factory)
        return (_HP,)

    def _fabro_bin(*, cwd: Path) -> str:
        calls["fabro_bin_cwd"] = cwd
        return "resolved-fabro"

    def _attribution(*, repo: Path) -> RunAttribution:
        calls["attribution_repo"] = repo
        return RunAttribution(metadata_run_ids={})

    def _reconcile(*, inputs: Any, factories: Any, dry_run: bool) -> ReconcileRunsSummary:
        calls["inputs_repo"] = inputs.repo
        calls["factory_targets"] = factories
        calls["dry_run"] = dry_run
        return summary

    monkeypatch.setattr(cli, "load_items", _load_items)
    monkeypatch.setattr(cli, "store_config", _store_config)
    monkeypatch.setattr(cli, "make_beads_client", lambda **_: object())
    monkeypatch.setattr(cli, "reconcile_factory_targets", _factories)
    monkeypatch.setattr(cli, "resolve_fabro_bin", _fabro_bin)
    monkeypatch.setattr(cli, "reconcile_runs", _reconcile)
    monkeypatch.setattr(cli, "repo_run_attribution", _attribution)
    return calls


class _StoreConfig:
    prefix = "bd-ib"


def _summary(
    *,
    reconciled: tuple[ReconciledRun, ...] = (),
    held: tuple[HeldRun, ...] = (),
    recovered_claims: tuple[RecoveredClaim, ...] = (),
    held_claims: tuple[HeldClaim, ...] = (),
) -> ReconcileRunsSummary:
    return ReconcileRunsSummary(
        reconciled=reconciled,
        errors=(),
        dry_run=False,
        held=held,
        recovered_claims=recovered_claims,
        held_claims=held_claims,
    )


def _held_run() -> HeldRun:
    return HeldRun(
        run_id="01YOUNG",
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        status_kind="blocked",
        work_item_id="bd-ib-parked",
        work_item_status="blocked",
        hold_reason="blocked-within-grace",
        parked_seconds=300.0,
        seconds_remaining=1500.0,
        grace_seconds=1800,
    )


def _held_claim() -> HeldClaim:
    return HeldClaim(
        work_item_id="bd-ib-attribution",
        run_id="01PENDING",
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        dispatching_host="hp-xubuntu",
        hold_reason="attribution-pending",
        remedy="move it with drive --action",
    )


def _unattributable() -> HeldClaim:
    return HeldClaim(
        work_item_id="bd-ib-bare",
        run_id=None,
        factory_name=None,
        factory_server_url=None,
        dispatching_host=None,
        hold_reason="claim-unattributable",
        remedy=None,
    )


def _recovered() -> RecoveredClaim:
    return RecoveredClaim(
        work_item_id="bd-ib-stranded",
        run_id="01GONE",
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        reason="run-absent",
        route="absent-run-release",
        status="ready",
        effects_written=("journal", "comment", "transition"),
    )


def _run() -> ReconciledRun:
    return ReconciledRun(
        run_id="01ORPHAN",
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        status_kind="blocked",
        work_item_id="bd-ib-orphan",
        work_item_status="closed",
        orphan_reason="item-not-active",
        termination_route="cancel",
        termination_succeeded=True,
        termination_detail="cancel route returned 200",
        export_comment_id="c-1",
    )
