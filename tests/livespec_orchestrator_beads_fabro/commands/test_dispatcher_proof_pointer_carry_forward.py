"""The pointer names the `carried_forward` record that reached the merged head.

The pointer clause of `SPECIFICATION/contracts.md` (v138) adds one field to the
closed set the `## Proof of Done` section may contain: "— when the merged head
was reached through a carry-forward — the comment link of the `carried_forward`
record naming that head". It is the one pointer field whose SUBJECT is not the
record the acceptance pass rested on: the pass still grades the
factory-captured assertions from the `verified` record, and the carry-forward
record is what says that verification reached the tree that merged.

WHY THE CITATION IS A QUESTION ABOUT THE NEWEST ANCHOR. "Reached through a
carry-forward" is not "a carry-forward record exists": a run can carry its proof
forward, be sent back round capture and replay by a later refresh, and merge on a
freshly VERIFIED head. Citing the carry-forward there would advertise, in the
item's own description, a decision a later verification superseded. So the field
is populated only when the newest of the two anchor verdicts is the
carry-forward -- the same reading `_dispatcher_publication_head` takes when it
decides which head `pr` may ready, and for the same reason.

WHY THE FIELD IS SPELLED AS A LITERAL BELOW AND BOUND BY ONE CASE. A Red's test
bytes are fixed across its Red-to-Green pair, so a top-level import of a name
this change INTRODUCES would make the Red a collection error -- which proves the
name is absent and nothing about the behaviour.
"""

from __future__ import annotations

import dataclasses

from livespec_orchestrator_beads_fabro.commands import _dispatcher_proof_pointer_write
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import (
    ProofPointer,
    description_with_pointer,
    pointer_in,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CARRIED_FORWARD,
    VERDICT_VERIFIED,
    proof_records,
)

_FIELD = "carried_forward_url"
_LABEL = "Carried-forward record"
_VERIFIED_URL = "https://forge.invalid/pull/7#issuecomment-1"
_CARRIED_URL = "https://forge.invalid/pull/7#issuecomment-2"
_LATER_VERIFIED_URL = "https://forge.invalid/pull/7#issuecomment-3"
_DEFINITION_OF_DONE = "## Definition of Done\n\n- The thing holds.\n"


def _pointer(**overrides: object) -> ProofPointer:
    """One pointer, built through the field names the dataclass declares."""
    fields: dict[str, object] = {
        "pull_request": 7,
        "record_url": _VERIFIED_URL,
        "run_id": "run-1",
        "timestamp": "2026-10-15T00:00:00Z",
        "verdict": VERDICT_VERIFIED,
    }
    fields.update(overrides)
    return ProofPointer(**fields)  # pyright: ignore[reportArgumentType]


def _record(*, verdict: str, url: str) -> dict[str, str]:
    return {
        "body": f"Proof of Done — {verdict} — run run-1 — 2026-10-15T00:00:00Z\n",
        "url": url,
    }


class _Leg:
    """The one attribute `carried_forward_record_url` reads off the proof leg."""

    def __init__(self, *, comments: list[dict[str, str]]) -> None:
        self.records = proof_records(comments=tuple(comments))


def _cited(*, leg: object) -> str | None:
    """The resolver's answer, reached through the module so the Red is an assertion.

    `getattr` rather than a top-level import for the reason the module docstring
    gives: importing a name this change introduces would make the Red a
    collection error, which proves the name is absent and nothing about which
    record the pointer cites.
    """
    resolver = getattr(_dispatcher_proof_pointer_write, "carried_forward_record_url", None)
    assert callable(resolver), (
        "the pointer writer exposes no carried_forward_record_url, so nothing decides "
        "whether the merged head was reached through a carry-forward"
    )
    answer = resolver(proof=leg)
    assert answer is None or isinstance(answer, str)
    return answer


def test_the_pointer_declares_a_carried_forward_field() -> None:
    """The literal above is the dataclass's own, so the cases below bind the product."""
    assert _FIELD in {one.name for one in dataclasses.fields(ProofPointer)}


def test_the_rendered_pointer_names_the_carried_forward_record() -> None:
    """The link is a BULLET in the section, which is what a reader of the clause reads."""
    rendered = _pointer(**{_FIELD: _CARRIED_URL}).render()

    assert f"- {_LABEL}: {_CARRIED_URL}" in rendered
    assert f"- Verified record: {_VERIFIED_URL}" in rendered


def test_an_ordinary_pointer_renders_no_carried_forward_bullet() -> None:
    """The clause says the section contains ONLY the fields it names.

    A bullet for a carry-forward that never happened would be content the clause
    does not admit, and a reader would take the empty value for a decision that
    had been posted.
    """
    rendered = _pointer().render()

    assert _LABEL not in rendered


def test_the_written_pointer_reads_back_with_its_carried_forward_link() -> None:
    """The staleness fact re-reads this section, so the write and the read must agree."""
    description = description_with_pointer(
        description=_DEFINITION_OF_DONE, pointer=_pointer(**{_FIELD: _CARRIED_URL})
    )

    assert description is not None
    assert description.startswith(_DEFINITION_OF_DONE)
    assert getattr(pointer_in(description=description), _FIELD) == _CARRIED_URL


def test_the_newest_anchor_being_a_carry_forward_is_what_cites_it() -> None:
    """A carry-forward that reached the merged head is cited; nothing else is."""
    leg = _Leg(
        comments=[
            _record(verdict=VERDICT_VERIFIED, url=_VERIFIED_URL),
            _record(verdict=VERDICT_CARRIED_FORWARD, url=_CARRIED_URL),
        ]
    )

    assert _cited(leg=leg) == _CARRIED_URL


def test_a_later_verification_supersedes_the_carry_forward_and_is_not_cited() -> None:
    """The case the "a carry-forward record exists" reading gets wrong.

    A run may carry its proof forward, be sent back round capture and replay by a
    later refresh, and merge on a freshly verified head. The carry-forward is
    then a superseded decision, and citing it would advertise proof of a tree
    that is not the one that merged.
    """
    leg = _Leg(
        comments=[
            _record(verdict=VERDICT_VERIFIED, url=_VERIFIED_URL),
            _record(verdict=VERDICT_CARRIED_FORWARD, url=_CARRIED_URL),
            _record(verdict=VERDICT_VERIFIED, url=_LATER_VERIFIED_URL),
        ]
    )

    assert _cited(leg=leg) is None


def test_a_pull_request_with_no_carry_forward_cites_none() -> None:
    """The ordinary run, which is the control for every case above."""
    leg = _Leg(comments=[_record(verdict=VERDICT_VERIFIED, url=_VERIFIED_URL)])

    assert _cited(leg=leg) is None
