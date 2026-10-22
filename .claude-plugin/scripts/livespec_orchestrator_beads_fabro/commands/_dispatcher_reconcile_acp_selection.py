"""Replay Dispatcher ACP selections against outcomes on their resolved factory.

The Dispatcher, rather than the engine, owns the fallback observation: one
selection record says which candidate it rendered and one stamped run says
which factory executed it.  Reconciliation joins those immutable records,
reads the run through that factory's port, and appends the existing warning
ledger records idempotently.  A missing outcome map is unavailable evidence;
it is recorded and retried on a later reconciliation without retiring a live
warning.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_ledger import (
    ingest_model_fallback_warning,
    primary_replacement_records,
    read_model_fallback_warnings,
    selection_warning_records,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    resolve_acp_primary_generations,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_node_outcomes,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
)

__all__: list[str] = ["reconcile_selection_warnings"]

_INSPECT_TIMEOUT_SECONDS = 30.0
_UNAVAILABLE_STAGE = "acp-selection-outcomes-unavailable"


@dataclass(frozen=True, kw_only=True)
class _SelectionRun:
    run_id: str
    work_item_id: str


def reconcile_selection_warnings(
    *, inputs: ReconcileInputs, factory: FactoryTarget, port: FabroPort
) -> None:
    """Replay every selection stamped to this factory, preserving unavailable evidence.

    The journal source carried by the reconciliation input is the same snapshot
    that attributed the factory pass.  A pathless in-memory input has no durable
    selection history to join, so it deliberately does nothing rather than
    guessing from an item or from journal order.
    """
    records = read_journal_records(journal_path=inputs.journaled.source_path)
    if not records:
        return
    for target in _selection_runs(records=records, factory=factory, inputs=inputs):
        outcomes = _outcomes(port=port, run_id=target.run_id)
        if outcomes is None:
            inputs.journal.append(
                record={
                    "stage": _UNAVAILABLE_STAGE,
                    "work_item_id": target.work_item_id,
                    "run_id": target.run_id,
                    "factory_name": factory.name,
                    "factory_server_url": factory.server,
                }
            )
            continue
        warnings = selection_warning_records(
            records=records,
            work_item_id=target.work_item_id,
            run_id=target.run_id,
            outcomes=outcomes,
        )
        if warnings is None:
            continue
        ledger = read_model_fallback_warnings(journal_path=inputs.journaled.source_path)
        for warning in warnings:
            _ = ingest_model_fallback_warning(record=warning, ledger=ledger, journal=inputs.journal)
        ledger = read_model_fallback_warnings(journal_path=inputs.journaled.source_path)
    ledger = read_model_fallback_warnings(journal_path=inputs.journaled.source_path)
    for replacement in primary_replacement_records(
        ledger=ledger, primary_generations=resolve_acp_primary_generations(repo=inputs.repo)
    ):
        inputs.journal.append(record=replacement)


def _selection_runs(
    *, records: tuple[Mapping[str, object], ...], factory: FactoryTarget, inputs: ReconcileInputs
) -> tuple[_SelectionRun, ...]:
    """The newest readable run stamps joined to the factory now being surveyed."""
    found: dict[str, _SelectionRun] = {}
    for record in records:
        if record.get("stage") != "dispatch-run-stamp":
            continue
        if record.get("dispatch_factory") != factory.name:
            continue
        if record.get("dispatch_factory_server") != factory.server:
            continue
        run_id = _text(value=record.get("run_id"))
        work_item_id = _text(value=record.get("work_item_id"))
        dispatch_id = _text(value=record.get("dispatch_id"))
        if run_id is None or work_item_id is None or dispatch_id is None:
            continue
        if inputs.only_work_item_id is not None and work_item_id != inputs.only_work_item_id:
            continue
        found[run_id] = _SelectionRun(run_id=run_id, work_item_id=work_item_id)
    return tuple(found.values())


def _outcomes(*, port: FabroPort, run_id: str) -> Mapping[str, Mapping[str, object]] | None:
    """One run's readable node outcomes, or ``None`` when the evidence is unavailable."""
    inspect = port.inspect(run_id=run_id, timeout_seconds=_INSPECT_TIMEOUT_SECONDS)
    if inspect.command.exit_code != 0:
        return None
    record = fabro_inspect_record(payload=inspect.payload)
    if record is None:
        return None
    checkpoints = fabro_inspect_checkpoints(record=record)
    checkpoint = checkpoints[-1] if checkpoints else {}
    outcomes = fabro_node_outcomes(record=record, checkpoint=checkpoint)
    return outcomes or None


def _text(*, value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
