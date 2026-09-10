"""Tests for the reconciliation pass the dispatch path runs automatically."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_records import (
    ReconciledRun,
    ReconcileError,
    ReconcileRunsSummary,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_spans import (
    emit_reconcile_pass_span,
)
from livespec_orchestrator_beads_fabro.errors import LivespecConfigUnreadableError

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_reconcile_runs_pass.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_pass"

_HP = FactoryTarget(name="hp", server="https://hp.example:32276", dev_token=None)
_VPS = FactoryTarget(name="vps", server="https://vps.example:32276", dev_token=None)


def test_an_unwritable_telemetry_path_never_breaks_reconciliation(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("occupied", encoding="utf-8")

    emit_reconcile_pass_span(
        summary=importlib.import_module(_MODULE_NAME).ReconcilePassSummary(
            factories_surveyed=0,
            factory_names=(),
            dry_run=False,
            orphans_found=0,
            orphans_reconciled=0,
            errors=0,
            failure_detail=None,
        ),
        tenant="bd-ib",
        cancelling_actor="timer:reconcile-runs",
        spans_path=blocker / "spans.jsonl",
        now_ns=1,
    )

    assert blocker.read_text(encoding="utf-8") == "occupied"


def test_a_pass_surveys_every_factory_and_journals_its_own_summary(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    captured = _stub(
        module=module,
        monkeypatch=monkeypatch,
        factories=(_HP, _VPS),
        summary=ReconcileRunsSummary(
            reconciled=(_reconciled(run_id="01A"), _reconciled(run_id="01B", succeeded=False)),
            errors=(),
            dry_run=False,
        ),
    )

    summary = module.reconcile_runs_pass(args=_args(tmp_path=tmp_path), repo=tmp_path)

    assert (summary.factories_surveyed, summary.orphans_found) == (2, 2)
    assert (summary.orphans_reconciled, summary.errors) == (1, 0)
    assert summary.failure_detail is None
    # The pass is NOT a dry run: this is the wiring that actually disposes of
    # an orphan, so a `dry_run=True` here would report reconciliations that
    # never happened.
    assert captured["dry_run"] is False
    assert captured["attribution_repo"] == tmp_path
    assert summary.factory_names == ("hp", "vps")
    spans = _spans(path=tmp_path / "journal-calibration-spans.jsonl")
    assert [span["name"] for span in spans] == ["dispatcher.reconcile-runs-pass"]
    assert _span_attrs(span=spans[0]) == {
        "livespec.tenant": "bd-ib",
        "reconcile.factories_surveyed": 2,
        "reconcile.orphans_found": 2,
        "reconcile.orphans_reconciled": 1,
        "reconcile.dry_run": False,
        "reconcile.errors": 0,
        "reconcile.cancelling_actor": "agent:test",
    }
    assert _pass_records(tmp_path=tmp_path) == [
        {
            "stage": "reconcile-runs-pass",
            "dry_run": False,
            "factories_surveyed": 2,
            "factory_names": ["hp", "vps"],
            "orphans_found": 2,
            "orphans_reconciled": 1,
            "errors": 0,
            "failure_detail": None,
        }
    ]


def test_a_pass_that_found_nothing_still_leaves_a_record(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A silent pass and an empty pass are otherwise the same absence."""
    module = importlib.import_module(_MODULE_NAME)
    _ = _stub(
        module=module,
        monkeypatch=monkeypatch,
        factories=(_HP,),
        summary=ReconcileRunsSummary(reconciled=(), errors=(), dry_run=False),
    )

    summary = module.reconcile_runs_pass(args=_args(tmp_path=tmp_path), repo=tmp_path)

    assert (summary.orphans_found, summary.errors) == (0, 0)
    assert [record["factories_surveyed"] for record in _pass_records(tmp_path=tmp_path)] == [1]


def test_a_run_scoped_error_counts_as_an_orphan_a_factory_error_does_not(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    _ = _stub(
        module=module,
        monkeypatch=monkeypatch,
        factories=(_HP, _VPS),
        summary=ReconcileRunsSummary(
            reconciled=(),
            errors=(
                _error(run_id="01UNTERMINATED", reason="export-not-verified"),
                _error(run_id=None, reason="factory-ps-failed"),
            ),
            dry_run=False,
        ),
    )

    summary = module.reconcile_runs_pass(args=_args(tmp_path=tmp_path), repo=tmp_path)

    assert summary.orphans_found == 1
    assert summary.errors == 2


def test_a_repo_declaring_no_factory_never_reaches_the_ledger(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Nothing to survey means the tenant round-trip below would be pure cost."""
    module = importlib.import_module(_MODULE_NAME)

    def _none(*, repo: Path, factory: str | None = None) -> tuple[FactoryTarget, ...]:
        _ = (repo, factory)
        return ()

    reads: list[str] = []
    monkeypatch.setattr(module, "reconcile_factory_targets", _none)
    monkeypatch.setattr(module, "store_config", lambda **_: reads.append("store_config"))
    monkeypatch.setattr(module, "load_items", lambda **_: reads.append("load_items"))

    summary = module.reconcile_runs_pass(args=_args(tmp_path=tmp_path), repo=tmp_path)

    # Recorded rather than raised: a stub that raises would be an uncovered
    # line, and the absence of a read is exactly what is being asserted.
    assert reads == []
    assert (summary.factories_surveyed, summary.errors) == (0, 0)
    assert summary.factory_names == ()
    assert summary.failure_detail is None
    assert [record["factories_surveyed"] for record in _pass_records(tmp_path=tmp_path)] == [0]


def test_an_unreadable_config_is_journaled_and_never_raised(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reconciliation is not a dispatch precondition, so it cannot refuse one."""
    module = importlib.import_module(_MODULE_NAME)

    def _explode(*, repo: Path, factory: str | None = None) -> tuple[FactoryTarget, ...]:
        _ = (repo, factory)
        raise LivespecConfigUnreadableError(detail="stray comma")

    monkeypatch.setattr(module, "reconcile_factory_targets", _explode)

    summary = module.reconcile_runs_pass(args=_args(tmp_path=tmp_path), repo=tmp_path)

    assert summary.factories_surveyed == 0
    assert summary.factory_names == ()
    assert summary.errors == 1
    assert summary.failure_detail is not None
    assert "LivespecConfigUnreadableError" in summary.failure_detail
    assert "stray comma" in summary.failure_detail
    records = _pass_records(tmp_path=tmp_path)
    assert len(records) == 1
    detail = records[0]["failure_detail"]
    assert isinstance(detail, str)
    assert "stray comma" in detail


def _stub(
    *,
    module: Any,
    monkeypatch: pytest.MonkeyPatch,
    factories: tuple[FactoryTarget, ...],
    summary: ReconcileRunsSummary,
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def _factories(*, repo: Path, factory: str | None = None) -> tuple[FactoryTarget, ...]:
        _ = (repo, factory)
        return factories

    def _attribution(*, repo: Path) -> object:
        captured["attribution_repo"] = repo
        return object()

    def _reconcile(*, inputs: Any, factories: Any, dry_run: bool) -> ReconcileRunsSummary:
        captured["dry_run"] = dry_run
        captured["factory_targets"] = tuple(factories)
        captured["fabro_bin"] = inputs.fabro_bin
        captured["id_prefix"] = inputs.id_prefix
        return summary

    monkeypatch.setattr(module, "reconcile_factory_targets", _factories)
    monkeypatch.setattr(module, "store_config", lambda **_: _StoreConfig())
    monkeypatch.setattr(module, "load_items", lambda **_: [])
    monkeypatch.setattr(module, "make_beads_client", lambda **_: object())
    monkeypatch.setattr(module, "repo_run_attribution", _attribution)
    monkeypatch.setattr(module, "reconcile_runs", _reconcile)
    return captured


class _StoreConfig:
    prefix = "bd-ib"


def _args(*, tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        journal=str(tmp_path / "journal.jsonl"),
        fabro_bin="fabro",
        invoker="agent:test",
    )


def _pass_records(*, tmp_path: Path) -> list[dict[str, object]]:
    lines = (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    stamped = {"at", "invoker", "invoker_source"}
    records = [json.loads(line) for line in lines]
    return [
        {key: value for key, value in record.items() if key not in stamped}
        for record in records
        if record.get("stage") == "reconcile-runs-pass"
    ]


def _spans(*, path: Path) -> list[dict[str, Any]]:
    request = json.loads(path.read_text(encoding="utf-8"))
    return request["resourceSpans"][0]["scopeSpans"][0]["spans"]


def _span_attrs(*, span: dict[str, Any]) -> dict[str, object]:
    attrs: dict[str, object] = {}
    for attribute in span["attributes"]:
        encoded = attribute["value"]
        value = next(iter(encoded.values()))
        if "intValue" in encoded:
            value = int(value)
        attrs[attribute["key"]] = value
    return attrs


def _reconciled(*, run_id: str, succeeded: bool = True) -> ReconciledRun:
    return ReconciledRun(
        run_id=run_id,
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        status_kind="blocked",
        work_item_id="bd-ib-orphan",
        work_item_status="closed",
        orphan_reason="item-not-active",
        termination_route="cancel",
        termination_succeeded=succeeded,
        termination_detail="cancel route returned 200",
        export_comment_id="c-1",
    )


def _error(*, run_id: str | None, reason: str) -> ReconcileError:
    return ReconcileError(
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        run_id=run_id,
        work_item_id="bd-ib-orphan" if run_id is not None else None,
        reason=reason,
        detail=reason,
    )
