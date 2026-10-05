"""Plan Proof of Done records read off an epic's timeline, with their positions.

Covers `_plan_proof_record`: the title and verdict set that separate a plan
record from an item record, the append-position pairing the archive proof leg
orders by, and the latest-by-position accessor.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_TITLE,
    VERDICT_CAPTURED,
    VERDICT_HOST_VERIFIED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
    PLAN_REPLAY_VERDICTS,
    latest_plan_proof_entry,
    plan_proof_entries,
)

_ASSERTION = "The released build runs in a real session."


def _record(*, verdict: str, identity: str, title: str = PLAN_PROOF_RECORD_TITLE) -> str:
    return (
        f"{title} — {verdict} — session {identity} — 2026-10-05T00:00:00Z\n"
        "\n"
        "## Build identity\n"
        "\n"
        "- Release tag: v0.167.0\n"
        "\n"
        f"## Assertion 1 — {_ASSERTION}\n"
        "\n"
        "Reproduced: yes.\n"
    )


def test_a_plan_record_is_paired_with_its_own_comment_index() -> None:
    comments: list[dict[str, object]] = [
        {"text": "plan-handoff-entry\nauthor: console\ntimestamp: x\n\nWrapping up."},
        {"text": _record(verdict=VERDICT_CAPTURED, identity="capturing")},
        {"text": "plan-scope-event\nauthor: console\ntimestamp: x\n\nRuling."},
        {"text": _record(verdict=VERDICT_VERIFIED, identity="replaying")},
    ]

    entries = plan_proof_entries(comments=comments)

    # The position is the comment's own index in the timeline, NOT its index
    # among the records: the proof leg compares record positions against the
    # carrier-map event's position, and a records-only index would compare two
    # different coordinate systems while both looked like small integers.
    assert [(one.record.verdict, one.position) for one in entries] == [
        (VERDICT_CAPTURED, 1),
        (VERDICT_VERIFIED, 3),
    ]
    assert entries[1].record.run_id == "replaying"
    assert entries[1].record.reproduced(assertion=_ASSERTION) is True


def test_an_item_record_and_a_host_verdict_are_not_plan_records() -> None:
    comments: list[dict[str, object]] = [
        # The ITEM title, which the plan reader must not accept: the two record
        # kinds grade different Definition of Done sections, so reading one as
        # the other would prove a plan from an item's own evidence.
        {"text": _record(verdict=VERDICT_VERIFIED, identity="x", title=PROOF_RECORD_TITLE)},
        # The plan title carrying a HOST-leg verdict, which the clause reserves
        # for item records. A plan has one leg and reuses the factory words.
        {"text": _record(verdict=VERDICT_HOST_VERIFIED, identity="x")},
        # Not a record at all, and the shape the ledger is mostly made of.
        {"text": "plan-handoff-entry\nauthor: console\ntimestamp: x\n\nNo record here."},
        # A non-string body, which `omitempty` sparseness can produce.
        {"created_at": "2026-10-05T00:00:00Z"},
    ]

    assert plan_proof_entries(comments=comments) == ()


def test_latest_is_by_position_even_when_the_entries_were_filtered() -> None:
    comments: list[dict[str, object]] = [
        {"text": _record(verdict=VERDICT_VERIFIED, identity="first")},
        {"text": _record(verdict=VERDICT_CAPTURED, identity="capturing")},
        {"text": _record(verdict=VERDICT_VERIFIED, identity="second")},
    ]
    entries = plan_proof_entries(comments=comments)
    # Deliberately reversed, so a reader that took the last LIST element rather
    # than the highest position would answer `first`.
    reversed_entries = tuple(reversed(entries))

    latest = latest_plan_proof_entry(entries=reversed_entries, verdicts=PLAN_REPLAY_VERDICTS)

    assert latest is not None
    assert (latest.record.run_id, latest.position) == ("second", 2)
    assert latest_plan_proof_entry(entries=(), verdicts=PLAN_REPLAY_VERDICTS) is None
