"""CLI wiring tests for the `reconcile-runs` dispatcher subcommand."""

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
    ReconcileError,
    ReconcileRunsSummary,
)
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.types import WorkItem

_HP = FactoryTarget(name="hp", server="https://hp.example:32276", dev_token=None)
_VPS = FactoryTarget(name="vps", server="https://vps.example:32276", dev_token=None)


def test_reconcile_runs_emits_a_json_projection_and_wires_every_input(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _stub(monkeypatch=monkeypatch, summary=_summary(reconciled=(_run(),)))

    exit_code = main(
        argv=[
            "reconcile-runs",
            "--repo",
            str(tmp_path),
            "--fabro-bin",
            "fabro",
            "--invoker",
            "agent:test",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["dry_run"] is False
    assert payload["reconciled"][0]["run_id"] == "01ORPHAN"
    assert payload["reconciled"][0]["orphan_reason"] == "item-not-active"
    # The NAMES, not only the count: a pass that reached one of two declared
    # factories reports the same three keys as a healthy one without them.
    assert payload["factories_surveyed"] == 2
    assert payload["factory_names"] == ["hp", "vps"]
    assert calls["factories"] == (tmp_path, None)
    inputs = calls["inputs"]
    assert isinstance(inputs, dict)
    assert inputs["fabro_bin"] == "fabro"
    assert inputs["repo"] == tmp_path
    assert inputs["journal_path"] == tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    assert inputs["invoker"] == "agent:test"
    # The ledger stamp leg reaches the reconciler rather than the join falling
    # back to the goal-text regex: the attribution handed in is the one
    # `repo_run_attribution` built for THIS repo.
    assert calls["attribution_repo"] == tmp_path
    assert inputs["metadata_run_ids"] == {"01STAMPED": "bd-ib-stamped"}
    assert inputs["telemetry_spans_path"] == (
        tmp_path / "tmp" / "fabro-dispatch-journal-calibration-spans.jsonl"
    )
    assert inputs["cancelling_actor"] == "agent:test"


def test_the_retired_stale_run_sweep_name_fails_as_an_unknown_subcommand(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The alias is retired: argparse's own refusal, not a custom farewell.

    A custom message would keep the retired name a recognised token, which is
    how a caller keeps invoking it and how the alias grows back.
    """
    _ = _stub(monkeypatch=monkeypatch, summary=_summary())

    with pytest.raises(SystemExit) as refusal:
        _ = main(argv=["stale-run-sweep", "--repo", str(tmp_path), "--factory", "hp"])

    captured = capsys.readouterr()
    assert refusal.value.code == 2
    assert "invalid choice: 'stale-run-sweep'" in captured.err
    assert captured.out == ""


def test_the_factory_flag_reaches_the_factory_resolver(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _stub(monkeypatch=monkeypatch, summary=_summary())

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path), "--factory", "hp"])

    assert exit_code == 0
    assert capsys.readouterr().out == "(no orphaned fabro runs found)\n"
    assert calls["factories"] == (tmp_path, "hp")


def test_every_invocation_leaves_exactly_one_pass_record_carrying_its_invoker(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The timer invokes THIS command, so its ticks are visible only here."""
    _ = _stub(monkeypatch=monkeypatch, summary=_summary(reconciled=(_run(),)))
    journal = tmp_path / "journal.jsonl"

    exit_code = main(
        argv=[
            "reconcile-runs",
            "--repo",
            str(tmp_path),
            "--journal",
            str(journal),
            "--invoker",
            "timer:reconcile-runs",
        ]
    )
    _ = capsys.readouterr()

    records = _pass_records(journal=journal)
    assert exit_code == 0
    assert len(records) == 1
    # The asserted identity, not the `unattributed:<user>@<host>` mark: a timer
    # tick that resolves to the fallback cannot be told from a hand invocation.
    assert records[0]["invoker"] == "timer:reconcile-runs"
    assert records[0]["invoker_source"] == "flag"
    assert _unstamped(record=records[0]) == {
        "stage": "reconcile-runs-pass",
        "dry_run": False,
        "factories_surveyed": 2,
        "factory_names": ["hp", "vps"],
        "orphans_found": 1,
        "orphans_reconciled": 1,
        "errors": 0,
        "failure_detail": None,
    }


def test_a_dry_run_leaves_a_pass_record_too_and_says_it_was_dry(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A dry pass reconciles nothing by design; unflagged it reads as a live one."""
    _ = _stub(monkeypatch=monkeypatch, summary=_summary(dry_run=True), factories=(_HP,))
    journal = tmp_path / "journal.jsonl"

    exit_code = main(
        argv=["reconcile-runs", "--repo", str(tmp_path), "--journal", str(journal), "--dry-run"]
    )
    _ = capsys.readouterr()

    records = _pass_records(journal=journal)
    assert exit_code == 0
    assert len(records) == 1
    assert records[0]["dry_run"] is True
    assert records[0]["factory_names"] == ["hp"]


def test_a_pass_that_surveyed_no_factory_journals_zero_and_refuses_to_read_clean(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Nothing-to-reconcile and nothing-was-looked-at are the same empty output."""
    _ = _stub(monkeypatch=monkeypatch, summary=_summary(), factories=())
    journal = tmp_path / "journal.jsonl"

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path), "--journal", str(journal)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert output == (
        "ERROR   (none)  no-factory-surveyed: this pass surveyed no factory, so it "
        "reconciled nothing and observed nothing\n"
    )
    records = _pass_records(journal=journal)
    assert len(records) == 1
    assert records[0]["factories_surveyed"] == 0
    assert records[0]["factory_names"] == []


def test_a_zero_factory_json_projection_reports_the_empty_survey(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _stub(monkeypatch=monkeypatch, summary=_summary(), factories=())

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["factories_surveyed"] == 0
    assert payload["factory_names"] == []


def test_a_dry_run_reaches_the_reconciler_as_a_dry_run(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _stub(monkeypatch=monkeypatch, summary=_summary(dry_run=True))

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path), "--dry-run", "--json"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert calls["dry_run"] is True
    assert calls["fabro_bin_cwd"] == tmp_path


def test_a_failure_on_either_leg_sets_the_nonzero_exit(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _stub(
        monkeypatch=monkeypatch,
        summary=_summary(
            errors=(
                ReconcileError(
                    factory_name="hp",
                    factory_server_url=None,
                    run_id=None,
                    work_item_id=None,
                    reason="factory-ps-failed",
                    detail="fabro ps exited 7",
                ),
            )
        ),
    )
    errored = main(argv=["reconcile-runs", "--repo", str(tmp_path)])
    error_output = capsys.readouterr().out

    _ = _stub(
        monkeypatch=monkeypatch,
        summary=_summary(reconciled=(_run(termination_succeeded=False),)),
    )
    unterminated = main(argv=["reconcile-runs", "--repo", str(tmp_path)])
    orphan_output = capsys.readouterr().out

    assert errored == 1
    assert error_output == "ERROR   hp  factory-ps-failed: fabro ps exited 7\n"
    assert unterminated == 1
    assert orphan_output == (
        "ORPHAN  bd-ib-orphan  01ORPHAN  factory=hp run=blocked item=closed "
        "reason=item-not-active route=cancel\n"
    )


def test_an_omitted_repo_defaults_to_the_working_directory(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    calls = _stub(monkeypatch=monkeypatch, summary=_summary())

    exit_code = main(argv=["reconcile-runs", "--journal", str(tmp_path / "own.jsonl")])

    assert exit_code == 0
    assert capsys.readouterr().out == "(no orphaned fabro runs found)\n"
    inputs = calls["inputs"]
    assert isinstance(inputs, dict)
    assert inputs["repo"] == tmp_path
    assert inputs["journal_path"] == tmp_path / "own.jsonl"


def test_a_held_parked_run_is_projected_with_the_time_it_has_left(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _stub(monkeypatch=monkeypatch, summary=_summary(held=(_held(),)))

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path), "--dry-run", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["held"][0]["hold_reason"] == "blocked-within-grace"
    assert payload["held"][0]["seconds_remaining"] == 1500.0
    assert payload["held"][0]["grace_seconds"] == 1800


def test_a_held_parked_run_renders_a_human_line_rather_than_reading_as_empty(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = _stub(monkeypatch=monkeypatch, summary=_summary(held=(_held(),)))

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path)])

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "HELD    bd-ib-parked  01YOUNG  factory=hp run=blocked item=blocked "
        "reason=blocked-within-grace remaining=1500.0\n"
    )


def test_the_committed_grace_setting_reaches_the_reconciler(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _stub(monkeypatch=monkeypatch, summary=_summary())
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"dispatcher": {"blocked_run_grace_seconds": 0}}}
        ),
        encoding="utf-8",
    )

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path)])

    inputs = calls["inputs"]
    assert exit_code == 0
    assert capsys.readouterr().out == "(no orphaned fabro runs found)\n"
    assert isinstance(inputs, dict)
    assert inputs["blocked_run_grace_seconds"] == 0


def test_an_unconfigured_grace_reaches_the_reconciler_as_the_documented_default(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _stub(monkeypatch=monkeypatch, summary=_summary())

    exit_code = main(argv=["reconcile-runs", "--repo", str(tmp_path)])

    inputs = calls["inputs"]
    assert exit_code == 0
    assert capsys.readouterr().out == "(no orphaned fabro runs found)\n"
    assert isinstance(inputs, dict)
    assert inputs["blocked_run_grace_seconds"] == 1800


def _stub(
    *,
    monkeypatch: pytest.MonkeyPatch,
    summary: ReconcileRunsSummary,
    factories: tuple[FactoryTarget, ...] = (_HP, _VPS),
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
        return factories

    def _fabro_bin(*, cwd: Path) -> str:
        calls["fabro_bin_cwd"] = cwd
        return "resolved-fabro"

    def _attribution(*, repo: Path) -> RunAttribution:
        calls["attribution_repo"] = repo
        return RunAttribution(metadata_run_ids={"01STAMPED": "bd-ib-stamped"})

    def _reconcile(*, inputs: Any, factories: Any, dry_run: bool) -> ReconcileRunsSummary:
        calls["inputs"] = {
            "repo": inputs.repo,
            "fabro_bin": inputs.fabro_bin,
            "id_prefix": inputs.id_prefix,
            "journal_path": inputs.journal.path,
            "invoker": inputs.journal.identity.invoker,
            "metadata_run_ids": dict(inputs.attribution.metadata_run_ids),
            "blocked_run_grace_seconds": inputs.blocked_run_grace_seconds,
            "telemetry_spans_path": inputs.telemetry_spans_path,
            "cancelling_actor": inputs.cancelling_actor,
        }
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


def _held() -> HeldRun:
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


def _pass_records(*, journal: Path) -> list[dict[str, Any]]:
    lines = journal.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    return [record for record in records if record.get("stage") == "reconcile-runs-pass"]


def _unstamped(*, record: dict[str, Any]) -> dict[str, Any]:
    stamped = {"at", "invoker", "invoker_source"}
    return {key: value for key, value in record.items() if key not in stamped}


def _summary(
    *,
    reconciled: tuple[ReconciledRun, ...] = (),
    errors: tuple[ReconcileError, ...] = (),
    dry_run: bool = False,
    held: tuple[HeldRun, ...] = (),
) -> ReconcileRunsSummary:
    return ReconcileRunsSummary(reconciled=reconciled, errors=errors, dry_run=dry_run, held=held)


def _run(*, termination_succeeded: bool = True) -> ReconciledRun:
    return ReconciledRun(
        run_id="01ORPHAN",
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        status_kind="blocked",
        work_item_id="bd-ib-orphan",
        work_item_status="closed",
        orphan_reason="item-not-active",
        termination_route="cancel",
        termination_succeeded=termination_succeeded,
        termination_detail="cancel route returned 200",
        export_comment_id="c-1",
    )
