"""The durable terminal record for a credential-use deadline ending."""

from __future__ import annotations

import importlib
from pathlib import Path

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline_record"


def test_credential_deadline_record_carries_the_complete_terminal_account() -> None:
    """A queue-exceeded refusal is recoverable rather than a plain failure."""
    assert (_COMMANDS / "_dispatcher_credential_deadline_record.py").is_file()
    records = importlib.import_module(_MODULE)

    record = records.credential_deadline_record(
        work_item_id="bd-ib-6skm77",
        dispatch_id="dispatch-1",
        run_id="run-1",
        factory="petri",
        executing_stage="implement",
        projection_epoch=1_000,
        deadline_epoch=109_000,
        observed_epoch=91_000,
        governing_figure="bounded credential-use window",
        preserved_pointer="preserve:42",
        cause=records.QUEUE_EXCEEDED_CAUSE,
        published_head="a" * 40,
    )

    assert record == {
        "stage": "credential-use-deadline-reached",
        "work_item_id": "bd-ib-6skm77",
        "dispatch_id": "dispatch-1",
        "run_id": "run-1",
        "factory": "petri",
        "executing_stage": "implement",
        "projection_epoch": 1_000,
        "credential_use_deadline_epoch": 109_000,
        "queue_time_consumed_seconds": 90_000,
        "governing_figure": "bounded credential-use window",
        "preserved_pointer": "preserve:42",
        "cause": "queue-exceeded",
        "published_head": "a" * 40,
    }
