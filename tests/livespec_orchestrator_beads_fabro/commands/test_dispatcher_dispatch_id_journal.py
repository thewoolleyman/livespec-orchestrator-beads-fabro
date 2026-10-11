"""The dispatch-id record's own snapshot of the resolved factory declaration.

`_dispatcher_dispatch_id_journal`'s whole argument is that the record is the
one artifact written before the run starts, so it is where a later reader
establishes what the orchestrator believed at dispatch time. The post-dispatch
`run_turn` guard is one such reader: it asks whether THIS dispatch's factory
exports `run_turn` telemetry, and a re-read of `.livespec.jsonc` would answer
what that file says now. These cases pin the declaration onto the record and
pin it to the factory NAME it describes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
    append_dispatch_id_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_binary_record import (
    EngineBinary,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_contract import (
    resolve_integration_contract,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

_TELEMETRY_KEY = "dispatch_factory_exports_run_turn_telemetry"


def _record(*, tmp_path: Path, identity: DispatchJournalIdentity) -> dict[str, object]:
    journal_path = tmp_path / "journal.jsonl"
    append_dispatch_id_record(
        journal=JournalFile(path=journal_path),
        work_item_id="bd-ib-demo",
        identity=identity,
        engine=EngineBinary(path="/global/fabro", version="fabro 0.254.0"),
        started_at_epoch=1.0,
        workflow_toml=tmp_path / "wf.toml",
        workflow_name="implement-work-item",
        integration=resolve_integration_contract(declaration={}),
        merge_hold=False,
    )
    parsed = json.loads(journal_path.read_text(encoding="utf-8").strip())
    assert isinstance(parsed, dict)
    return parsed


@pytest.mark.parametrize("exports", [True, False])
def test_the_dispatch_record_journals_the_factory_run_turn_declaration(
    *, tmp_path: Path, exports: bool
) -> None:
    """Both arms are recorded, so the guard never has to infer one from silence."""
    record = _record(
        tmp_path=tmp_path,
        identity=DispatchJournalIdentity(
            dispatch_id="d-1",
            dispatch_factory="hp-candidate",
            exports_run_turn_telemetry=exports,
        ),
    )
    assert record["dispatch_factory"] == "hp-candidate"
    assert record[_TELEMETRY_KEY] is exports


def test_an_unnamed_factory_journals_no_run_turn_declaration(tmp_path: Path) -> None:
    """The declaration describes a NAMED factory, so it never stands alone.

    A flag written without the name would say nothing a reader could attribute
    to anything, and the guard's own default already answers the unresolved
    single-factory target.
    """
    record = _record(
        tmp_path=tmp_path,
        identity=DispatchJournalIdentity(dispatch_id="d-1", dispatch_factory=None),
    )
    assert "dispatch_factory" not in record
    assert _TELEMETRY_KEY not in record
