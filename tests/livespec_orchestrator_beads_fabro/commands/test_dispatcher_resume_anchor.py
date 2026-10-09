"""The anchor a resume reads off a terminated run's pull request.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" says the *earlier run* is the dispatch whose identifier the
LATEST proof record on the item's open pull request carries, the *published head*
is the full commit sha that record names, and the *resumed-at stage* is the node
the earlier run was executing when it terminated — or, when the factory no longer
holds the run, the stage the latest record's VERDICT implies: `verified` -> `pr`,
`captured` -> `review`, `not_captured` or `not_reproduced` -> `fix`, no such
record -> `proof_capture`. Scenario 142 exercises all four.

WHY THE SOURCE IS PART OF THE ANSWER AND NOT A LOG LINE. The clause requires the
resume record to name "the source that decided it", and the two sources disagree
in the one direction that matters: the factory's own record knows the node the run
died INSIDE, while the verdict fallback can only know the last node that
PUBLISHED. A resume whose record did not say which one decided would leave an
operator unable to tell a precise entry from an inferred one, and the inferred one
can re-run a node the factory record would have skipped.

WHY A RECORD NAMING NO HEAD ANCHORS NOTHING. The clause says outright that "a
record published before this clause was ratified names no head and cannot anchor a
resume", and the head is what the head-moved refusal compares against. Answering
with an anchor carrying an empty head would make that refusal compare one unknown
against the pull request's real head and resume on a tree no record describes.

WHY TWO DIFFERENT HEADS IN ONE BODY ALSO ANCHOR NOTHING. The clause requires a
factory record to name the head "once". A body naming two is a record whose own
account of which tree it ran on is contradictory, and picking either one is
picking at random — so the reader fails closed, which is the same direction
`_dispatcher_proof_attachment`'s partial read takes and for the same reason: a
half-read anchor sends the head comparison after a sha nobody published.

WHY THE SCAN IS FENCE-AWARE. A record's proof is fenced, and a replay proof
routinely PRINTS the head line it is checking — a `git rev-parse HEAD`, a `cat` of
an earlier record. A line-oriented scan would read that printed output as the
record's own declaration, so a verify record replaying a capture would be
attributed the capture's head rather than its own. `_dispatcher_proof_record`
records the same trap on the `Reproduced:` line.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_HUMAN_ATTESTED,
    VERDICT_NOT_CAPTURED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_VERIFIED,
    ProofRecord,
)

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_resume_anchor.py"
)

_HEAD = "a" * 40
_OTHER_HEAD = "b" * 40


def _anchor_module() -> Any:
    """Import the resume-anchor reader, proving the file exists first."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _record(*, verdict: str, body: str, run_id: str = "run-1") -> ProofRecord:
    return ProofRecord(
        verdict=verdict,
        run_id=run_id,
        timestamp="2026-10-08T00:00:00Z",
        url="https://example.invalid/c/1",
        body=body,
    )


def _body(*, verdict: str, head: str | None) -> str:
    module = _anchor_module()
    label = "" if head is None else f"\n{module.PUBLISH_HEAD_LABEL}: {head}\n"
    return f"Proof of Done — {verdict} — run run-1 — 2026-10-08T00:00:00Z\n{label}"


def test_published_head_reads_the_labelled_sha() -> None:
    """A factory record's own head declaration is the published head."""
    module = _anchor_module()
    assert module.published_head(body=_body(verdict=VERDICT_VERIFIED, head=_HEAD)) == _HEAD


def test_published_head_is_none_when_the_record_names_none() -> None:
    """A pre-ratification record names no head and so anchors no resume."""
    module = _anchor_module()
    assert module.published_head(body=_body(verdict=VERDICT_VERIFIED, head=None)) is None


def test_published_head_is_none_when_two_different_heads_are_named() -> None:
    """A contradictory body fails closed rather than resolving at random."""
    module = _anchor_module()
    body = (
        f"{_body(verdict=VERDICT_VERIFIED, head=_HEAD)}\n"
        f"{module.PUBLISH_HEAD_LABEL}: {_OTHER_HEAD}\n"
    )
    assert module.published_head(body=body) is None


def test_published_head_ignores_a_head_line_a_proof_printed() -> None:
    """A fenced head line is proof output, never the record's own declaration."""
    module = _anchor_module()
    body = (
        f"{_body(verdict=VERDICT_VERIFIED, head=_HEAD)}\n"
        "```\n"
        f"{module.PUBLISH_HEAD_LABEL}: {_OTHER_HEAD}\n"
        "```\n"
    )
    assert module.published_head(body=body) == _HEAD


def test_the_factory_record_decides_the_stage_when_the_factory_lost_the_run() -> None:
    """Each factory verdict implies the stage the clause names for it."""
    module = _anchor_module()
    expected = {
        VERDICT_VERIFIED: module.RESUMED_AT_PR,
        VERDICT_CAPTURED: module.RESUMED_AT_REVIEW,
        VERDICT_NOT_CAPTURED: module.RESUMED_AT_FIX,
        VERDICT_NOT_REPRODUCED: module.RESUMED_AT_FIX,
    }
    for verdict, stage in expected.items():
        anchor = module.resume_anchor(
            records=[_record(verdict=verdict, body=_body(verdict=verdict, head=_HEAD))],
            executing_node=None,
        )
        assert anchor is not None
        assert anchor.resumed_at == stage
        assert anchor.source == module.SOURCE_LATEST_RECORD
        assert anchor.head == _HEAD


def test_the_executing_node_outranks_the_verdict_fallback() -> None:
    """A factory that still holds the run names the node it died inside."""
    module = _anchor_module()
    anchor = module.resume_anchor(
        records=[
            _record(verdict=VERDICT_VERIFIED, body=_body(verdict=VERDICT_VERIFIED, head=_HEAD))
        ],
        executing_node="review_fix",
    )
    assert anchor is not None
    assert anchor.resumed_at == "review_fix"
    assert anchor.source == module.SOURCE_FACTORY_RUN


def test_a_non_factory_record_is_not_an_anchor() -> None:
    """A human-attested record carries no run and no head, so it anchors nothing."""
    module = _anchor_module()
    assert (
        module.resume_anchor(
            records=[
                _record(
                    verdict=VERDICT_HUMAN_ATTESTED,
                    body=_body(verdict=VERDICT_HUMAN_ATTESTED, head=_HEAD),
                )
            ],
            executing_node=None,
        )
        is None
    )


def test_the_latest_factory_record_anchors_and_earlier_ones_do_not() -> None:
    """Latest wins, and the anchor carries that record's own run and head."""
    module = _anchor_module()
    anchor = module.resume_anchor(
        records=[
            _record(
                verdict=VERDICT_CAPTURED,
                body=_body(verdict=VERDICT_CAPTURED, head=_OTHER_HEAD),
                run_id="run-old",
            ),
            _record(
                verdict=VERDICT_VERIFIED,
                body=_body(verdict=VERDICT_VERIFIED, head=_HEAD),
                run_id="run-new",
            ),
        ],
        executing_node=None,
    )
    assert anchor is not None
    assert anchor.record.run_id == "run-new"
    assert anchor.head == _HEAD


def test_a_headless_latest_record_anchors_nothing_even_with_an_older_head() -> None:
    """The LATEST record is the anchor, so its missing head is the whole answer."""
    module = _anchor_module()
    assert (
        module.resume_anchor(
            records=[
                _record(
                    verdict=VERDICT_CAPTURED,
                    body=_body(verdict=VERDICT_CAPTURED, head=_HEAD),
                    run_id="run-old",
                ),
                _record(
                    verdict=VERDICT_VERIFIED,
                    body=_body(verdict=VERDICT_VERIFIED, head=None),
                    run_id="run-new",
                ),
            ],
            executing_node=None,
        )
        is None
    )


def test_no_records_at_all_anchor_nothing() -> None:
    """An empty record set is the nothing-to-resume-from answer."""
    module = _anchor_module()
    assert module.resume_anchor(records=[], executing_node=None) is None
