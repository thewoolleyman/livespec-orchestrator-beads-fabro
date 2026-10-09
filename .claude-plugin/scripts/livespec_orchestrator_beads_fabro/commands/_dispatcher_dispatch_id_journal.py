"""Dispatch-id journal record emission.

THE RECORD CARRIES THE RESOLVED INTEGRATION CONTRACT. The
resolve-once-project-everywhere clause requires the frozen contract to be
journaled WITH the dispatch record, and this is that record: it is the one
artifact written before the run starts, so it is the only place a reader can
later establish what the orchestrator believed about the governed repository at
the moment it dispatched. Without it, a post-hoc question -- which check-suite
was this repository declaring, was its core pin declared or defective, which
merge strategy armed -- can only be answered by re-reading a `.livespec.jsonc`
that may have changed since, which answers a different question.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_binary_record import (
    EngineBinary,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_contract import (
    ResolvedIntegrationContract,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    integration_contract_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

__all__: list[str] = [
    "DispatchJournalIdentity",
    "append_dispatch_id_record",
]


@dataclass(frozen=True, kw_only=True)
class DispatchJournalIdentity:
    dispatch_id: str
    dispatch_factory: str | None


def append_dispatch_id_record(  # noqa: PLR0913 — kw-only record writer; each argument is one INDEPENDENT field of the dispatch record, and folding any pair into a carrier would invent a grouping the record does not have.
    *,
    journal: JournalFile,
    work_item_id: str,
    identity: DispatchJournalIdentity,
    engine: EngineBinary,
    started_at_epoch: float,
    workflow_toml: Path,
    workflow_name: str,
    integration: ResolvedIntegrationContract,
    merge_hold: bool,
) -> None:
    # `workflow_name` rides BESIDE `workflow_toml` rather than replacing it:
    # the path says which file won the target-local-then-bundle resolution,
    # the name says which registered variant the operator (or the item's own
    # pin) selected, and neither is recoverable from the other once a target
    # registers more than one directory.
    #
    # `merge_hold` is the item's effective per-item merge hold, recorded as the
    # value the run was RENDERED with rather than re-read from the ledger later.
    # The label can be set or released at any moment, so a reader asking "did
    # this dispatch arm auto-merge" cannot answer it from today's labels; the
    # record and the run agree only because both project the one value the plan
    # resolved.
    #
    # `fabro_bin` and `fabro_version` name the ENGINE CLIENT this dispatch
    # drove, measured rather than re-derived. Both are unconditional: a
    # per-factory `bin` means two dispatches minutes apart can run different
    # engines, and a record that omitted the fields when they matched the
    # global would make "which engine was this?" answerable only for the
    # dispatches that already looked unusual.
    record: dict[str, object] = {
        "stage": "dispatch-id",
        "work_item_id": work_item_id,
        "dispatch_id": identity.dispatch_id,
        "started_at_epoch": started_at_epoch,
        "workflow_toml": str(workflow_toml),
        "workflow_name": workflow_name,
        "merge_hold": merge_hold,
        "fabro_bin": engine.path,
        "fabro_version": engine.version,
        **integration_contract_journal_record(resolved=integration),
    }
    if identity.dispatch_factory is not None:
        record["dispatch_factory"] = identity.dispatch_factory
    journal.append(record=record)
