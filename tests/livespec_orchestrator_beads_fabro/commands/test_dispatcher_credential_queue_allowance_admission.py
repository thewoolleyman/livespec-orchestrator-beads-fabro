"""The credential queue allowance's pre-dispatch admission.

The worker-credential-projection clause of `SPECIFICATION/contracts.md` makes
`dispatcher.credential_queue_allowance_seconds` a committed-only positive
integer of seconds whose non-positive or non-integer value "MUST be rejected
before any run exists, naming the key", with its resolution and journaling
following the whole-run wall budget key.

SO THE REFUSAL IS GRADED WHERE THAT BUDGET'S IS, in the payload preparation,
and for the same reason: the two figures are SUMMED into one bound, so a
dispatch that resolved them from two reads of the same configuration could
launch against a window neither key's refusal would describe. Grading them side
by side is also what makes "before any run exists" structural rather than
careful — nothing downstream of this function has a run to refuse.

WHY THE ADMITTED CASE IS HERE AND NOT ONLY THE REFUSALS. Four refusals are
equally consistent with a gate that refuses every value, and that gate would
pass every refusal case while admitting no dispatch at all. The admitted case
also reads the JOURNAL, because the clause requires the allowance to be
journaled as the wall budget is and a resolution nothing records is one no
operator can see — a refusal naming a key says what was wrong, and only the row
says what a healthy dispatch resolved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_queue_allowance import (
    CREDENTIAL_QUEUE_ALLOWANCE_KEY,
    DEFAULT_CREDENTIAL_QUEUE_ALLOWANCE_SECONDS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    prepare_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    REPOSITORY_LAYER,
    WORKFLOW_DEFAULT_LAYER,
)

_COMMITTED_WORKFLOW_TOML = '_version = 1\n\n[workflow]\ngraph = "workflow.fabro"\n'
_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    '        prompt="@prompts/implement.md"\n'
    "    ]\n"
    "}\n"
)
_QUEUE_ALLOWANCE_RECORD_KEY = "credential_queue_allowance"


class _RecordingJournal:
    """Minimal JournalWriter seam that keeps every appended record."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _prepared(
    *, tmp_path: Path, dispatcher: dict[str, object]
) -> tuple[WorkflowPayload | str, _RecordingJournal]:
    workflow_dir = tmp_path / "workflow"
    prompts = workflow_dir / "prompts"
    prompts.mkdir(parents=True)
    _ = (prompts / "implement.md").write_text("implement prompt\n", encoding="utf-8")
    _ = (workflow_dir / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    committed = workflow_dir / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )
    journal = _RecordingJournal()
    prepared = prepare_workflow_payload(
        repo=tmp_path,
        committed=committed,
        payload_dir=tmp_path / "payload",
        journal=cast("Any", journal),
        work_item_id="bd-ib-2oxr6v",
        adapters={},
    )
    return prepared, journal


@pytest.mark.parametrize(
    "value",
    [0, -1, 1.5, "bad"],
    ids=["zero", "negative", "fractional", "string"],
)
def test_an_invalid_queue_allowance_is_rejected_before_any_run_exists(
    tmp_path: Path, value: object
) -> None:
    """The four values Scenario 228 enumerates, each refused naming the key.

    "Before any run exists" is read off the fact that NO PAYLOAD was
    materialized and NO record was journaled, not off the refusal's own text: a
    refusal that had already rendered a run config would still return a string,
    and the payload directory is the one thing a later launch would be pointed
    at.
    """
    prepared, journal = _prepared(
        tmp_path=tmp_path, dispatcher={"credential_queue_allowance_seconds": value}
    )

    assert isinstance(prepared, str), prepared
    assert CREDENTIAL_QUEUE_ALLOWANCE_KEY in prepared
    assert repr(value) in prepared
    assert journal.records == []
    assert not (tmp_path / "payload").exists()


def test_a_declared_queue_allowance_is_journaled_with_its_layer(tmp_path: Path) -> None:
    """The admitted control, which is what keeps the four refusals meaningful."""
    prepared, journal = _prepared(
        tmp_path=tmp_path, dispatcher={"credential_queue_allowance_seconds": 3_600}
    )

    assert not isinstance(prepared, str), prepared
    assert len(journal.records) == 1
    assert journal.records[0][_QUEUE_ALLOWANCE_RECORD_KEY] == {
        "seconds": 3_600,
        "layer": REPOSITORY_LAYER,
    }


def test_a_target_declaring_nothing_journals_the_documented_default(tmp_path: Path) -> None:
    """A repository declaring nothing still RECORDS what its dispatch resolved.

    Journaled rather than omitted, for the reason the wall budget's layer rides
    its own row: 86400 seconds is the fleet default on one target and a
    deliberate repository decision on another, and only the layer says whether
    raising the key would have admitted a refused dispatch.
    """
    _, journal = _prepared(tmp_path=tmp_path, dispatcher={})

    assert journal.records[0][_QUEUE_ALLOWANCE_RECORD_KEY] == {
        "seconds": DEFAULT_CREDENTIAL_QUEUE_ALLOWANCE_SECONDS,
        "layer": WORKFLOW_DEFAULT_LAYER,
    }
