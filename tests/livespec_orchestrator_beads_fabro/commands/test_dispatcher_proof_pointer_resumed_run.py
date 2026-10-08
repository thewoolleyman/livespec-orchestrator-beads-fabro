"""The pointer of a RESUMED item names both the record's run and the resumed run.

The pointer clause of `SPECIFICATION/contracts.md` says the section contains
"the pull request number, the comment link of the latest `verified` record, its
run id and timestamp, its verdict, — when the item was resumed … — the resumed
run's identifier", and the resume clause says the same thing from the other side:
"The Proof of Done pointer written for a resumed item MUST name the resumed run's
identifier BESIDE the record's own run id."

WHY BOTH, AND WHY NEITHER REPLACES THE OTHER. The two identifiers answer two
different questions and a resumed item is the one case where they differ. The
record's run id says which run EXECUTED the proof; the resumed run's identifier
says which dispatch MERGED it. Writing only the first leaves an operator unable
to tell that the merging dispatch did not produce the proof it is credited with;
writing only the second attributes the proof to a run that never captured it, and
makes the pointer disagree with the record it links to — which the staleness
hygiene fact then surfaces, every pass, for a pointer that is correct.

WHY AN UNRESUMED ITEM RENDERS NO SUCH BULLET. The clause admits the field "when
the item was resumed" and says the section contains "only" the fields it names.
An ordinary item's pointer must therefore render byte-for-byte as it did before
this field existed — otherwise every pointer in the ledger acquires a bullet whose
value is the same run id the line above it already carries, and a reader has no
way to tell a genuine resume from the rendering of one.

WHY THE READ-BACK MATTERS AS MUCH AS THE WRITE. A pointer is READ to decide
staleness and to resolve the pull request the `accept` valve acts on. A field that
rendered but did not parse would survive one write and vanish on the next rewrite,
so the resumed attribution would silently decay to the pre-resume shape.
"""

from __future__ import annotations

import dataclasses

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import (
    ProofPointer,
    description_with_pointer,
    pointer_in,
)

_RESUMED_RUN = "01M4RESUMEDRUN00000000000"
_RECORD_RUN = "01M4EARLIERRUN0000000000"

_DESCRIPTION = "## Definition of Done\n\n- The valve holds when blinded.\n"


def _pointer(*, resumed_run_id: str | None) -> ProofPointer:
    return ProofPointer(
        pull_request=2639,
        record_url="https://example.invalid/c/1",
        run_id=_RECORD_RUN,
        timestamp="2026-10-08T00:00:00Z",
        verdict="verified",
        resumed_run_id=resumed_run_id,
    )


def test_the_pointer_carries_a_resumed_run_field() -> None:
    """The field exists at all — the genuine assertion the Red half rests on."""
    names = {field.name for field in dataclasses.fields(ProofPointer)}
    assert "resumed_run_id" in names


def test_a_resumed_pointer_renders_both_identifiers() -> None:
    """The record's own run id and the resumed run's identifier, beside each other."""
    rendered = _pointer(resumed_run_id=_RESUMED_RUN).render()
    assert f"- Run: {_RECORD_RUN}" in rendered
    assert f"- Resumed run: {_RESUMED_RUN}" in rendered


def test_an_unresumed_pointer_renders_no_resumed_run_bullet() -> None:
    """The section contains ONLY the fields the clause names for that item."""
    rendered = _pointer(resumed_run_id=None).render()
    assert "Resumed run" not in rendered


def test_the_resumed_run_survives_a_read_back() -> None:
    """A field that rendered but did not parse would decay on the next rewrite."""
    description = description_with_pointer(
        description=_DESCRIPTION, pointer=_pointer(resumed_run_id=_RESUMED_RUN)
    )
    assert description is not None
    read = pointer_in(description=description)
    assert read is not None
    assert read.resumed_run_id == _RESUMED_RUN
    assert read.run_id == _RECORD_RUN


def test_an_unresumed_pointer_reads_back_as_unresumed() -> None:
    """Absence read back as absence, not as an empty-string identifier."""
    description = description_with_pointer(
        description=_DESCRIPTION, pointer=_pointer(resumed_run_id=None)
    )
    assert description is not None
    read = pointer_in(description=description)
    assert read is not None
    assert read.resumed_run_id is None


def test_the_journal_projection_carries_the_resumed_run() -> None:
    """The journal row says which dispatch merged, not only which run proved."""
    record = _pointer(resumed_run_id=_RESUMED_RUN).as_record()
    assert record["resumed_run_id"] == _RESUMED_RUN
