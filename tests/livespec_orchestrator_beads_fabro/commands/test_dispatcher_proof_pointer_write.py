"""Tests for the post-merge pointer write's refusals and its human-record link.

The happy path is bound through a real dispatch in
`tests/integration/test_proof_of_done_acceptance_scenarios132_133.py`. What this
module owns is that NOTHING here raises and every refusal says which fact
stopped it: the pointer is provenance, so an item whose work merged must never be
left undisposed because its description could not be rewritten, and three
different causes must not collapse into one message.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_proof_pointer_write
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
    PROOF_MODE_HUMAN_ATTESTED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
    EffectiveCriteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    ProofLeg,
    proof_leg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer_write import (
    human_attested_record_url,
    write_proof_pointer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import proof_records
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.types import WorkItem

_RUN_ID = "01M3WRITERUN"
_ASSERTION = "The projection carries the parent field."
_HUMAN_ASSERTION = "The production console renders the banner."
_RECORD_URL = "https://example.test/c/1"
_HUMAN_URL = "https://example.test/c/2"
_DESCRIPTION = f"## Definition of Done\n\n- {_ASSERTION}\n\nReferences: ## Something\n"


def _item(*, description: str = _DESCRIPTION) -> WorkItem:
    return WorkItem(
        id="bd-ib-write",
        type="task",
        status="acceptance",
        title="Task",
        description=description,
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria=None,
    )


def _outcome(*, pr_number: int | None = 7) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-write",
        status="green",
        stage="done",
        pr_number=pr_number,
        merge_sha="abc123",
        detail="merged",
        fabro_run_id=_RUN_ID,
    )


def _criteria(*, modes: tuple[str, ...], assertions: tuple[str, ...]) -> EffectiveCriteria:
    return EffectiveCriteria(
        text="\n".join(assertions),
        source=DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
        assertions=assertions,
        proof_modes=modes,
    )


def _verified_leg(*, bodies: tuple[tuple[str, str], ...] = ()) -> ProofLeg:
    comments = [
        {"url": url, "body": body}
        for url, body in (
            (
                _RECORD_URL,
                f"Proof of Done — verified — run {_RUN_ID} — 2026-10-01T09:00:00Z\n\n"
                f"## Assertion 1 — {_ASSERTION}\n\nReproduced: yes.\n",
            ),
            *bodies,
        )
    ]
    return proof_leg(
        criteria=_criteria(modes=(PROOF_MODE_FACTORY_CAPTURED,), assertions=(_ASSERTION,)),
        records=proof_records(comments=comments),
        run_ids=(_RUN_ID,),
        reason="read",
    )


def _records(*, journal: JournalFile) -> list[dict[str, object]]:
    text = journal.path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


@pytest.mark.parametrize(
    ("leg", "pr_number", "description", "reason"),
    [
        (None, 7, _DESCRIPTION, "the effective criteria declare no proof mode"),
        (
            "verified",
            None,
            _DESCRIPTION,
            "the merged dispatch recorded no pull request",
        ),
        (
            "unrecorded",
            7,
            _DESCRIPTION,
            "no verified Proof of Done record for the merging run",
        ),
        (
            "verified",
            7,
            "## Context\n\nNo definition here.\n",
            "the description carries no Definition of Done section to write after",
        ),
    ],
)
def test_each_reason_the_pointer_is_not_written_is_journaled_in_its_own_words(
    leg: str | None,
    pr_number: int | None,
    description: str,
    reason: str,
    tmp_path: Path,
) -> None:
    proof = None
    if leg == "verified":
        proof = _verified_leg()
    elif leg == "unrecorded":
        proof = proof_leg(
            criteria=_criteria(modes=(PROOF_MODE_FACTORY_CAPTURED,), assertions=(_ASSERTION,)),
            records=(),
            run_ids=(_RUN_ID,),
            reason="nothing published",
        )
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    write_proof_pointer(
        repo=tmp_path,
        item=_item(description=description),
        outcome=_outcome(pr_number=pr_number),
        proof=proof,
        journal=journal,
    )

    assert [one["stage"] for one in _records(journal=journal)] == ["proof-pointer-skipped"]
    assert _records(journal=journal)[0]["reason"] == reason


def test_a_failed_ledger_write_is_journaled_rather_than_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The merge is real whatever the ledger says, so the write never crashes it."""

    def _boom(**_: object) -> None:
        raise BeadsCommandError(command="bd update", exit_code=1, stderr="gone")

    monkeypatch.setattr(_dispatcher_proof_pointer_write, "update_work_item_description", _boom)
    monkeypatch.setattr(_dispatcher_proof_pointer_write, "store_config", lambda **_: tmp_path)
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    write_proof_pointer(
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(),
        proof=_verified_leg(),
        journal=journal,
    )

    records = _records(journal=journal)
    assert [one["stage"] for one in records] == ["proof-pointer-error"]
    assert records[0]["reason"] == "BeadsCommandError"


def test_the_human_attested_link_is_resolved_only_for_an_item_that_owes_one() -> None:
    """Three states, and the middle one is why this is not a bare record lookup.

    An item with no human-attested assertion owes no link even when a
    human-attested record happens to exist on the pull request; an item that owes
    one has no link until the record lands; and an item that owes one and has it
    gets the record's own comment link.
    """
    human_comment = (
        _HUMAN_URL,
        "Proof of Done — human_attested — alice — 2026-10-01T10:00:00Z\n\nAttested.\n",
    )
    attested_comment = (
        _HUMAN_URL,
        "Proof of Done — human_attested — run alice — 2026-10-01T10:00:00Z\n\nAttested.\n",
    )
    mixed = _criteria(
        modes=(PROOF_MODE_FACTORY_CAPTURED, PROOF_MODE_HUMAN_ATTESTED),
        assertions=(_ASSERTION, _HUMAN_ASSERTION),
    )

    owes_nothing = _verified_leg(bodies=(attested_comment,))
    owes_and_waiting = proof_leg(
        criteria=mixed,
        records=_verified_leg().records,
        run_ids=(_RUN_ID,),
        reason="read",
    )
    owes_and_has = proof_leg(
        criteria=mixed,
        records=_verified_leg(bodies=(attested_comment,)).records,
        run_ids=(_RUN_ID,),
        reason="read",
    )
    # The malformed header below is NOT a record, so it cannot satisfy the leg.
    owes_and_malformed = proof_leg(
        criteria=mixed,
        records=_verified_leg(bodies=(human_comment,)).records,
        run_ids=(_RUN_ID,),
        reason="read",
    )

    assert human_attested_record_url(proof=owes_nothing) is None
    assert human_attested_record_url(proof=owes_and_waiting) is None
    assert human_attested_record_url(proof=owes_and_has) == _HUMAN_URL
    assert human_attested_record_url(proof=owes_and_malformed) is None
