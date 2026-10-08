"""Tests for the declared proof-record budget and the refusal it earns.

`bd-ib-555xcd`: a Proof of Done record is ONE forge comment carrying complete
native outputs, and before this module nothing measured one before posting it. A
record the forge rejects is a LOST proof that reads as an ABSENT one — the
acceptance pass sees no record, reports the assertion unevidenced, and the item
parks on a refusal whose real cause was a size nobody looked at.

WHY THE CEILING IS A MEASUREMENT AND NOT A CONSTANT SOMEONE REMEMBERED. The item
was raised against a reported "65536-character publication limit", and that figure
was an ASSUMPTION — the forge accepted a 66,680-character record. It is also what
the forge's own 422 message says when it refuses, which is where the assumption
came from and why it is so durable. Measured against live GitHub on 2026-10-07
(`plan/definition-and-proof-of-done/research/005-forge-comment-ceiling-measurement-2026-10-07.md`):
the enforced issue-comment ceiling is **262144 UTF-8 bytes**, four times the
advertised figure, and it is denominated in BYTES rather than characters.

THE BYTES-VERSUS-CHARACTERS ARM IS LOAD-BEARING, not pedantry, and it has its own
test below. The discriminating probe was 131072 em dashes: 131072 CHARACTERS —
half the character ceiling, and only twice the forge's advertised one — but 393216
BYTES, and the forge refused it. A budget measured in `len(str)` therefore
over-admits by up to 4x on exactly the proof most likely to carry multibyte text:
rendered prose, box-drawing tables, `git log --graph` glyphs, and this
repository's own ratified em-dash header separator.

WHY THE REFUSAL HAS TWO ARMS. A record can exceed the budget two ways, and an
operator's remedy differs between them. One assertion's proof may be individually
enormous — the remedy is to attach it. Or every proof may be modest while their
SUM is over budget — the remedy is a smaller proof recipe or a split item, and a
refusal that pointed at "the overflowing assertion" would be pointing at nothing,
because none of them individually overflows. Both arms name an assertion and a
byte count, so neither reads as a bug in the refusal.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    NO_GOVERNING_SCENARIO,
    RecordAssertion,
)

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_budget"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_proof_budget.py"
)

# The measured, enforced issue-comment ceiling, in UTF-8 bytes. Spelled here as a
# literal rather than imported, so this test asserts the module carries the
# MEASURED number rather than agreeing with itself about whatever it carries.
_MEASURED_CEILING_BYTES = 262144

_SURFACE = "post-host-record"


def _module() -> object:
    """The budget module, imported inside the test body.

    Imported here rather than at module top so a Red commit fails on the
    `is_file()` assertion below — a genuine assertion about the deliverable —
    instead of dying at collection with `ModuleNotFoundError`, which would prove
    only unimportability and not that the behaviour is unimplemented.
    """
    return importlib.import_module(_MODULE)


def _assertion(*, text: str, proof: str) -> RecordAssertion:
    """One record assertion carrying a given proof, with the rest held constant."""
    return RecordAssertion(
        text=text,
        proof_mode="factory_captured",
        governing_scenario=NO_GOVERNING_SCENARIO,
        steps=("Run the command the assertion names.",),
        proof=proof,
        reproduced=True,
    )


def test_module_declares_the_measured_ceiling_budget_and_inline_allowance() -> None:
    """The three declared numbers exist, and the ceiling is the MEASURED one."""
    assert _MODULE_PATH.is_file()
    budget = _module()
    assert budget.FORGE_COMMENT_CEILING_BYTES == _MEASURED_CEILING_BYTES  # pyright: ignore[reportAttributeAccessIssue]
    assert isinstance(budget.PROOF_RECORD_BUDGET_BYTES, int)  # pyright: ignore[reportAttributeAccessIssue]
    assert isinstance(budget.INLINE_PROOF_ALLOWANCE_BYTES, int)  # pyright: ignore[reportAttributeAccessIssue]


def test_budget_sits_strictly_below_the_measured_ceiling() -> None:
    """A budget AT the ceiling is not a budget: it leaves no headroom at all.

    The ceiling is one server-side validation measured on one day, so a record
    that merely equalled it would start being refused the moment upstream moved
    the number down by a byte — and the proof would be lost for a reason no
    publisher could see.
    """
    budget = _module()
    assert 0 < budget.PROOF_RECORD_BUDGET_BYTES < budget.FORGE_COMMENT_CEILING_BYTES  # pyright: ignore[reportAttributeAccessIssue]
    assert 0 < budget.INLINE_PROOF_ALLOWANCE_BYTES < budget.PROOF_RECORD_BUDGET_BYTES  # pyright: ignore[reportAttributeAccessIssue]


def test_measured_bytes_counts_utf8_bytes_not_characters() -> None:
    """The discriminating probe from the measurement, as a test.

    131072 em dashes is 131072 characters and 393216 bytes. A measurement in
    characters reports a number the forge would accept for a body it in fact
    refuses, which is the over-admitting direction — a lost proof.
    """
    budget = _module()
    multibyte = "—" * 131072
    assert len(multibyte) == 131072
    assert budget.measured_bytes(text=multibyte) == 393216  # pyright: ignore[reportAttributeAccessIssue]
    assert budget.measured_bytes(text=multibyte) > budget.FORGE_COMMENT_CEILING_BYTES  # pyright: ignore[reportAttributeAccessIssue]


def test_proof_overflows_inline_allowance_is_measured_in_bytes_too() -> None:
    """The per-assertion predicate shares the byte denomination, not just the budget."""
    budget = _module()
    allowance = budget.INLINE_PROOF_ALLOWANCE_BYTES  # pyright: ignore[reportAttributeAccessIssue]
    assert not budget.proof_overflows_inline_allowance(proof="a" * allowance)  # pyright: ignore[reportAttributeAccessIssue]
    assert budget.proof_overflows_inline_allowance(proof="a" * (allowance + 1))  # pyright: ignore[reportAttributeAccessIssue]
    # Exactly at the allowance in CHARACTERS, but three times it in bytes.
    assert budget.proof_overflows_inline_allowance(proof="—" * allowance)  # pyright: ignore[reportAttributeAccessIssue]


def test_under_budget_record_earns_no_refusal() -> None:
    """The ordinary record is unaffected: no refusal, nothing to act on."""
    budget = _module()
    body = "Proof of Done — captured — run 01M4 — 2026-10-07T00:00:00Z\n"
    refusal = budget.record_budget_refusal(  # pyright: ignore[reportAttributeAccessIssue]
        body=body,
        surface=_SURFACE,
        assertions=(_assertion(text="The command reports the version.", proof="0.173.7\n"),),
    )
    assert refusal is None


def test_refusal_names_measured_size_budget_and_the_overflowing_assertion() -> None:
    """The single-enormous-proof arm names the assertion whose proof overflowed."""
    budget = _module()
    allowance = budget.INLINE_PROOF_ALLOWANCE_BYTES  # pyright: ignore[reportAttributeAccessIssue]
    overflowing = "The listing projects every record's parent field."
    modest = "The command reports the version."
    assertions = (
        _assertion(text=modest, proof="0.173.7\n"),
        _assertion(text=overflowing, proof="z" * (allowance + 1)),
    )
    body = "x" * (budget.PROOF_RECORD_BUDGET_BYTES + 1)  # pyright: ignore[reportAttributeAccessIssue]
    refusal = budget.record_budget_refusal(  # pyright: ignore[reportAttributeAccessIssue]
        body=body, surface=_SURFACE, assertions=assertions
    )
    assert refusal is not None
    assert _SURFACE in refusal
    # The measured size, the budget, and the assertion whose proof overflowed.
    assert str(budget.PROOF_RECORD_BUDGET_BYTES + 1) in refusal  # pyright: ignore[reportAttributeAccessIssue]
    assert str(budget.PROOF_RECORD_BUDGET_BYTES) in refusal  # pyright: ignore[reportAttributeAccessIssue]
    assert str(allowance) in refusal
    assert overflowing in refusal
    assert str(allowance + 1) in refusal
    # Nothing was published is the operative fact for a publisher reading this.
    assert "Nothing was published" in refusal


def test_refusal_names_the_largest_proof_when_no_single_proof_overflows() -> None:
    """The aggregate arm: every proof is modest and their SUM is over budget.

    This arm is why the refusal cannot simply name "the overflowing assertion":
    here NONE of them overflows the per-assertion allowance, so a refusal written
    only for the other arm would name nothing and read as a defect in itself.
    """
    budget = _module()
    allowance = budget.INLINE_PROOF_ALLOWANCE_BYTES  # pyright: ignore[reportAttributeAccessIssue]
    largest = "The largest of the modest proofs."
    assertions = (
        *(
            _assertion(text=f"Assertion number {index}.", proof="m" * (allowance // 2))
            for index in range(8)
        ),
        _assertion(text=largest, proof="L" * (allowance - 1)),
    )
    body = "x" * (budget.PROOF_RECORD_BUDGET_BYTES + 4096)  # pyright: ignore[reportAttributeAccessIssue]
    refusal = budget.record_budget_refusal(  # pyright: ignore[reportAttributeAccessIssue]
        body=body, surface=_SURFACE, assertions=assertions
    )
    assert refusal is not None
    assert largest in refusal
    assert str(allowance - 1) in refusal
    # It must SAY that no single proof overflowed, or the named assertion reads as
    # the culprit when the real remedy is a smaller recipe or a split item.
    assert "No single proof" in refusal


def test_refusal_with_no_assertions_still_names_the_size_and_budget() -> None:
    """A body over budget carrying no assertions at all is still refused.

    Degenerate, and deliberately covered: the refusal's two arms both reach for an
    assertion, so an empty sequence is the one input that could raise instead of
    refusing — and raising here would crash a publisher rather than refuse it.
    """
    budget = _module()
    over = budget.PROOF_RECORD_BUDGET_BYTES + 1  # pyright: ignore[reportAttributeAccessIssue]
    refusal = budget.record_budget_refusal(  # pyright: ignore[reportAttributeAccessIssue]
        body="x" * over, surface=_SURFACE, assertions=()
    )
    assert refusal is not None
    assert str(over) in refusal


@given(text=st.text(max_size=400))
def test_measured_bytes_is_the_utf8_length_for_any_text(*, text: str) -> None:
    """The measurement is exactly UTF-8 length, for every input rather than one."""
    budget = _module()
    assert budget.measured_bytes(text=text) == len(text.encode("utf-8"))  # pyright: ignore[reportAttributeAccessIssue]


@given(size=st.integers(min_value=0, max_value=400))
def test_refusal_fires_exactly_when_the_body_exceeds_the_budget(*, size: int) -> None:
    """Refused iff over budget — the boundary is inclusive on the admitted side.

    Driven around the boundary by offsetting from the budget itself rather than by
    generating whole bodies, so the property is about the COMPARISON rather than
    about Hypothesis's ability to build a 192 KiB string.
    """
    budget = _module()
    at = budget.PROOF_RECORD_BUDGET_BYTES  # pyright: ignore[reportAttributeAccessIssue]
    under = budget.record_budget_refusal(  # pyright: ignore[reportAttributeAccessIssue]
        body="x" * max(0, at - size), surface=_SURFACE, assertions=()
    )
    over = budget.record_budget_refusal(  # pyright: ignore[reportAttributeAccessIssue]
        body="x" * (at + size + 1), surface=_SURFACE, assertions=()
    )
    assert under is None
    assert over is not None
