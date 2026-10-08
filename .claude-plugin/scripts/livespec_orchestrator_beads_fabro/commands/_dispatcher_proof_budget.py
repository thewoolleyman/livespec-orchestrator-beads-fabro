"""The declared size budget every proof record is measured against before posting.

A Proof of Done record is ONE forge comment carrying the complete native output of
every reproduction step. Before this module nothing measured one, and the failure
mode that leaves is the worst available: a record the forge REJECTS is a LOST
proof that reads downstream as an ABSENT one. The acceptance pass finds no record,
`reproduced` answers `None`, and the assertion is reported unevidenced — so the
item parks on a refusal naming the missing record rather than the size that lost
it, and nothing on any surface points at the real cause.

WHY THE CEILING IS A MEASUREMENT, WITH ITS PROVENANCE RECORDED BESIDE IT. The
defect this module closes was raised against a reported "65536-character
publication limit", and that number was an ASSUMPTION — the forge had accepted a
66,680-character record minutes earlier. It is ALSO exactly what the forge's own
422 payload says when it does refuse (`Body is too long (maximum is 65536
characters)`), which is where the assumption came from and why it is so durable:
the wrong number arrives stamped with the forge's authority.

Measured against live GitHub on 2026-10-07, bracketed to a single byte, and
written up with its controls in
`plan/definition-and-proof-of-done/research/005-forge-comment-ceiling-measurement-2026-10-07.md`:
the enforced issue-comment ceiling is **262144 UTF-8 bytes**, four times the
advertised figure. Do not "correct" the constant below back toward 65536 on the
strength of the forge's message or of upstream documentation; re-measure instead,
and if the measurement moves, move the research file with it.

WHY EVERY MEASUREMENT HERE IS IN BYTES AND NEVER IN CHARACTERS. This is the arm
most likely to be simplified away by a later reader, because on ASCII the two are
equal and every test would still pass. The discriminating probe was 131072 em
dashes: 131072 CHARACTERS — half the character ceiling, and only twice the
advertised one — but 393216 BYTES, which the forge refused. So a budget measured
in `len(str)` over-admits by up to 4x, and it does so precisely on the proof most
likely to be multibyte: rendered prose, box-drawing tables, `tree` and `git log
--graph` glyphs, and this repository's own ratified em-dash header separator. The
over-admitting direction is the one that loses proofs.

WHY A BUDGET BELOW THE CEILING, rather than the ceiling itself. The ceiling is one
server-side validation, measured once, on one day, by one instrument. A record
that merely equalled it would begin silently losing proofs the moment upstream
moved the number down by a byte. The budget is the headroom that buys a margin
against that, and against whatever per-publisher overhead the measurement did not
see.

WHY THE INLINE ALLOWANCE IS DECLARED SEPARATELY, AND WHY THE BUDGET IS DERIVED
FROM IT. The allowance exists so a capture agent can plan a bounded proof recipe
BEFORE it runs, rather than discovering at post time that its evidence does not
fit — at which point the steps have already been executed and the only remedy is
to re-run them. Deriving the budget as a whole number of allowances makes the
relationship between the two legible: at `_BUDGETED_ASSERTIONS` assertions each
spending its full inline allowance, the record lands exactly on budget. That is a
realistic high-water mark for assertions per item, and it happens to put the
budget at three quarters of the measured ceiling.

WHY THE REFUSAL HAS TWO ARMS. A record exceeds the budget two ways, and the
operator's remedy differs between them, so one wording cannot serve both. Either
a single assertion's proof is individually enormous — the remedy is to attach it —
or every proof is modest while their SUM is over budget, where the remedy is a
smaller recipe or a split item. A refusal written only for the first arm would, in
the second, name "the overflowing assertion" when none of them overflows: it would
point at the largest innocent proof and read as a defect in the refusal rather
than as a fact about the record. Both arms therefore name an assertion AND say
which situation they are describing.
"""

from __future__ import annotations

from collections.abc import Sequence

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    RecordAssertion,
)

__all__: list[str] = [
    "FORGE_COMMENT_CEILING_BYTES",
    "INLINE_PROOF_ALLOWANCE_BYTES",
    "PROOF_RECORD_BUDGET_BYTES",
    "measured_bytes",
    "proof_overflows_inline_allowance",
    "record_budget_refusal",
]

# The MEASURED, enforced forge issue-comment ceiling, in UTF-8 bytes. See the
# module docstring for the measurement and for why this is not 65536.
FORGE_COMMENT_CEILING_BYTES = 262144

# What ONE assertion's proof may spend inline before it travels as an attachment.
# 32 KiB is roughly five hundred lines of terminal output, which is a generous
# text capture rather than a tight one.
INLINE_PROOF_ALLOWANCE_BYTES = 32768

# How many full inline allowances the budget is sized to hold. The budget is
# derived from the allowance rather than declared independently so the two cannot
# drift into a pair where no record can satisfy both.
_BUDGETED_ASSERTIONS = 6

# The declared budget: strictly below the ceiling, leaving 64 KiB of headroom
# against a future downward move in the measurement and against per-publisher
# overhead this measurement did not see.
PROOF_RECORD_BUDGET_BYTES = INLINE_PROOF_ALLOWANCE_BYTES * _BUDGETED_ASSERTIONS

_REFUSAL = (
    "ERROR: {surface} refused: the rendered record measures {measured} bytes"
    " against a declared budget of {budget} bytes (the measured forge comment"
    " ceiling is {ceiling} bytes of UTF-8). Posting it would risk a rejected"
    " comment, and a rejected record is a LOST proof that reads downstream as an"
    " absent one.\n{culprits}Nothing was published.\n"
)
_OVER_ALLOWANCE = (
    "These assertions carry a proof over the per-assertion inline allowance of"
    " {allowance} bytes, and belong in an attached asset rather than inline:\n"
    "{listing}\n"
)
_AGGREGATE = (
    "No single proof exceeds the per-assertion inline allowance of {allowance}"
    " bytes, so the record is over budget in AGGREGATE across its {count}"
    " assertions; the largest is {text} ({size} bytes). The remedy is a smaller"
    " proof recipe or a smaller item, not an attachment.\n"
)
_NO_ASSERTIONS = (
    "The record carries no assertions at all, so its size is in the header or"
    " build identity rather than in any proof.\n"
)


def measured_bytes(*, text: str) -> int:
    """How large `text` is on the wire, in the UTF-8 bytes the forge counts.

    The one place the denomination is decided. Every size in this module and every
    size a refusal reports comes through here, so there is no second place for a
    character count to creep back in.
    """
    return len(text.encode("utf-8"))


def proof_overflows_inline_allowance(*, proof: str) -> bool:
    """Whether one assertion's proof is too large to publish inline.

    The boundary is inclusive on the admitted side: a proof measuring EXACTLY the
    allowance still publishes inline, so the allowance reads as "this much is
    allowed" rather than as "one less than this".
    """
    return measured_bytes(text=proof) > INLINE_PROOF_ALLOWANCE_BYTES


def record_budget_refusal(
    *, body: str, surface: str, assertions: Sequence[RecordAssertion]
) -> str | None:
    """The refusal an over-budget record earns, or `None` when it is within budget.

    `body` is the FULLY RENDERED record — the exact bytes that would be posted —
    rather than anything reconstructed from the assertions. Measuring a
    reconstruction would measure a different artifact than the one at risk, and the
    header, the build identity and the per-assertion scaffolding are all real bytes
    the forge counts.

    `assertions` is used ONLY to name a culprit in the refusal, never to decide
    whether to refuse: the decision is the body's measured size against the budget,
    full stop. That is why an empty sequence still refuses rather than raising —
    a publisher handed a crash instead of a refusal has lost the proof twice.
    """
    measured = measured_bytes(text=body)
    if measured <= PROOF_RECORD_BUDGET_BYTES:
        return None
    return _REFUSAL.format(
        surface=surface,
        measured=measured,
        budget=PROOF_RECORD_BUDGET_BYTES,
        ceiling=FORGE_COMMENT_CEILING_BYTES,
        culprits=_culprits(assertions=assertions),
    )


def _culprits(*, assertions: Sequence[RecordAssertion]) -> str:
    """The refusal's middle paragraph: which assertion, and which of the two arms.

    The sort is by SIZE alone and Python's sort is stable, so assertions of equal
    proof size stay in Definition of Done order — the order every other record
    surface presents them in, and the order a publisher is reading its own payload
    in while it acts on this refusal.
    """
    sized = sorted(
        ((measured_bytes(text=one.proof), one.text) for one in assertions),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not sized:
        return _NO_ASSERTIONS
    over = [pair for pair in sized if pair[0] > INLINE_PROOF_ALLOWANCE_BYTES]
    if over:
        return _OVER_ALLOWANCE.format(
            allowance=INLINE_PROOF_ALLOWANCE_BYTES,
            listing="\n".join(f"  - {text} ({size} bytes)" for size, text in over),
        )
    size, text = sized[0]
    return _AGGREGATE.format(
        allowance=INLINE_PROOF_ALLOWANCE_BYTES, count=len(sized), text=text, size=size
    )
