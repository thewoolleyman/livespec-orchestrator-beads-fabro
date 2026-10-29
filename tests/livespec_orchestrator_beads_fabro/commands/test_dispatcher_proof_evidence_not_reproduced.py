"""A newer `not_reproduced` record grades a factory assertion exactly as a `verified` one does.

The proof-evidence-leg clause judges each assertion on its own section of the newest
applicable counted `proof_verify` record, whatever that record's record-wide verdict,
and does not fall back to an older record. A leg that read only `verified` records
reported the assertion unevidenced (NEEDS_ATTENTION) when the newest record was a
`not_reproduced` one carrying `Reproduced: no`, and fell back to an older record.
"""

from __future__ import annotations

import textwrap

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
    EffectiveCriteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import proof_leg
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    ProofRecord,
    proof_records,
)

_RUN_ID = "01M3NOTREPRODUCED"
_ASSERTION = "The projection carries the parent field."


def _criteria() -> EffectiveCriteria:
    return EffectiveCriteria(
        text=_ASSERTION,
        source=DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
        assertions=(_ASSERTION,),
        proof_modes=(PROOF_MODE_FACTORY_CAPTURED,),
    )


def _comment(*, verdict: str, number: int, reproduced: str | None) -> dict[str, object]:
    section = "" if reproduced is None else f"\nReproduced: {reproduced}.\n"
    body = (
        textwrap.dedent(f"""\
        Proof of Done — {verdict} — run {_RUN_ID} — 2026-10-01T09:0{number}:00Z

        ## Assertion 1 — {_ASSERTION}
        """)
        + section
    )
    return {"url": f"https://example.test/c/{number}", "body": body}


def _records(*comments: dict[str, object]) -> tuple[ProofRecord, ...]:
    return proof_records(comments=comments)


def test_a_newer_not_reproduced_record_fails_the_assertion_instead_of_leaving_it_unobserved() -> (
    None
):
    records = _records(
        _comment(verdict="captured", number=1, reproduced=None),
        _comment(verdict="not_reproduced", number=2, reproduced="no"),
    )

    leg = proof_leg(criteria=_criteria(), records=records, run_ids=(_RUN_ID,), reason="read")

    assert leg.unevidenced == ()
    assert [(one.text, one.passed) for one in leg.checks] == [(_ASSERTION, False)]
    assert [one.record_comment for one in leg.assertions] == ["https://example.test/c/2"]
    assert leg.record is not None
    assert leg.record.verdict == "not_reproduced"


def test_a_not_reproduced_record_newer_than_a_verified_one_is_the_one_graded() -> None:
    records = _records(
        _comment(verdict="verified", number=1, reproduced="yes"),
        _comment(verdict="not_reproduced", number=2, reproduced="no"),
    )

    leg = proof_leg(criteria=_criteria(), records=records, run_ids=(_RUN_ID,), reason="read")

    assert [(one.text, one.passed) for one in leg.checks] == [(_ASSERTION, False)]
    assert [one.record_comment for one in leg.assertions] == ["https://example.test/c/2"]


def test_a_verified_record_newer_than_a_not_reproduced_one_is_the_one_graded() -> None:
    records = _records(
        _comment(verdict="not_reproduced", number=1, reproduced="no"),
        _comment(verdict="verified", number=2, reproduced="yes"),
    )

    leg = proof_leg(criteria=_criteria(), records=records, run_ids=(_RUN_ID,), reason="read")

    assert [(one.text, one.passed) for one in leg.checks] == [(_ASSERTION, True)]
    assert [one.record_comment for one in leg.assertions] == ["https://example.test/c/2"]
