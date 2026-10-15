"""The anchor a resume reads off a terminated run's pull request.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" says the *earlier run* is the dispatch whose identifier the
LATEST proof record on the item's open pull request carries, the *published head*
is the full commit sha that record names, and the *resumed-at stage* is the node
the earlier run was executing when it terminated — or, when the factory no longer
holds the run, the stage the latest record's VERDICT implies: `verified` ->
`pr_refresh`, `captured` -> `review`, `not_captured` or `not_reproduced` ->
`fix`, no such record -> `proof_capture`. Scenario 142 exercises all four.

WHY A `pr` ENTRY NORMALIZES TO `pr_refresh`, AND WHY BOTH SOURCES OWE IT. The
scripted publication of v121 put `pr_refresh` in front of `pr`, and the clause
says in as many words that "an earlier `pr` entry MUST normalize to
`pr_refresh`". Both sources can name `pr`: a run terminated under an EARLIER
build reports `pr` as the node it died inside, and the verdict fallback used to
answer `pr` for `verified`. Entering `pr` directly would publish without
refreshing the publish branch onto the authoritative default and without
re-establishing the refresh provenance `pr` then reads — so the stage would
refuse for absent provenance, or, worse, ready a pull request whose base nothing
had rebased. Normalizing in the READER is what makes that true of both sources at
once; normalizing at one call site would leave the other entering the retired
node.

THE NORMALIZED NAME IS CHECKED AGAINST THE COMMITTED GRAPH rather than against
this module's own constant. A constant compared with itself passes for any
spelling, including one no node in the workflow carries — and the one thing that
makes this value correct is that the engine can enter it.

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

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
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

# The node name the clause spells, written here as a LITERAL rather than read
# off the module under test, so the assertions below cannot be satisfied by a
# constant compared with itself. `test_the_normalized_entry_node_is_a_node_the_
# committed_graph_declares` is what ties this literal to the shipped workflow.
_PR_REFRESH = "pr_refresh"

_IMPLEMENT_GRAPH = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")


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
        VERDICT_VERIFIED: _PR_REFRESH,
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


def test_a_legacy_pr_executing_node_normalizes_to_pr_refresh() -> None:
    """A factory naming the retired `pr` entry resumes at `pr_refresh` instead.

    The factory source is the one that can still name `pr` after v121 — a run
    terminated under an earlier build reports the node it died inside — so the
    normalization is asserted on that source rather than only on the fallback.
    The SOURCE is asserted unchanged beside it: normalizing is a correction of
    the stage, not a demotion to the inferred reading, and reporting
    `pull-request-latest-record` here would tell an operator the factory had
    lost a run it still holds.
    """
    module = _anchor_module()
    anchor = module.resume_anchor(
        records=[
            _record(verdict=VERDICT_VERIFIED, body=_body(verdict=VERDICT_VERIFIED, head=_HEAD))
        ],
        executing_node=module.RESUMED_AT_PR,
    )
    assert anchor is not None
    assert anchor.resumed_at == _PR_REFRESH
    assert anchor.source == module.SOURCE_FACTORY_RUN
    assert anchor.head == _HEAD


def test_the_normalized_entry_node_is_a_node_the_committed_graph_declares() -> None:
    """`pr_refresh` is a real entry point, and the retired `pr` is still one too.

    Both halves are asserted because either alone leaves the normalization
    unproven: a graph declaring no `pr_refresh` would make every normalized
    resume enter a node the engine cannot find, and a graph that had DROPPED
    `pr` would mean the input this reader normalizes can no longer arrive, so
    the normalization would be dead code rather than a live correction.
    """
    module = _anchor_module()
    graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    assert _PR_REFRESH in graph.nodes
    assert module.RESUMED_AT_PR in graph.nodes


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
    assert anchor.run_id == "run-new"
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
