"""Tests for the ONE primitive that renders a proof record, so no session formats one.

The host-leg clause of `SPECIFICATION/contracts.md` (v115) requires that "the
implementation MUST provide one posting primitive that renders these records, so
that no session hand-formats one", and the plan-record clause requires the same of
plan records. This module is the renderer both reach for, which is why the title
is a parameter: the two differ in their first-line prefix and in where they are
posted, never in the body structure.

EVERY CASE ROUND-TRIPS THROUGH THE READER, not through a string comparison on the
rendered bytes. `_dispatcher_proof_record` is what the acceptance pass reads a
published record with, and the only property that matters is that what this
renderer writes is what that reader recovers. A test asserting rendered text would
pass against a renderer whose output the reader cannot parse — which is precisely
the failure the two-module split can produce.

THE `Reproduced:` LINE'S POSITION IS LOAD-BEARING AND IS BOUND HERE DIRECTLY. The
reader splits a body into per-assertion sections at its PROSE headings, so a
`Reproduced:` line written after the assertion's own `### Reproduction steps`
sub-heading lands in a DIFFERENT section from the assertion text and the reader
answers `None` — the unevidenced answer, which parks a verified item on
NEEDS_ATTENTION. The round trip through `ProofRecord.reproduced` is the only check
that can see that; a renderer test asserting the line is present would pass.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
    build_identity_in,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    GOVERNING_SCENARIO_LABEL,
    NO_GOVERNING_SCENARIO,
    PROOF_HEADING,
    REPRODUCED_LABEL,
    REPRODUCTION_STEPS_HEADING,
    RecordAssertion,
    render_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_TITLE,
    VERDICT_HOST_RECORDED,
    VERDICT_HOST_VERIFIED,
    proof_records,
)

_PLAN_RECORD_TITLE = "Plan Proof of Done"
_IDENTITY = "session 01M44SESSION"
_TIMESTAMP = "2026-10-04T22:30:00Z"
_RELEASE_TAG = "v0.166.0"
_FIRST = "The released build resolves the host mode on an operator host."
_SECOND = "The accept valve refuses while the host leg is pending."
_SCENARIO = (
    "## Scenario 136 — A host-captured assertion holds the item in acceptance"
    " (Posting the independent replay re-runs the pass and closes the item)"
)
_BUILD = BuildIdentity(
    release_tag=_RELEASE_TAG, installed_build="orchestrator 0.166.0", commit=None
)


def _assertion(
    *,
    text: str,
    reproduced: bool | None = True,
    proof: str = "$ drive --action accept:x\nrefused\n",
) -> RecordAssertion:
    return RecordAssertion(
        text=text,
        proof_mode=PROOF_MODE_HOST_CAPTURED,
        governing_scenario=_SCENARIO,
        steps=("Install the released build through its normal path.", "Drive the valve."),
        proof=proof,
        reproduced=reproduced,
    )


def _one_record(*, body: str) -> object:
    records = proof_records(comments=[{"body": body, "url": "https://example.test/c/1"}])
    assert len(records) == 1
    return records[0]


def test_a_rendered_record_is_read_back_as_a_record_listing_its_assertion_reproduced() -> None:
    """The whole point: what the renderer writes, the acceptance pass's reader recovers.

    The header's three fields and the per-assertion reproduction verdict are
    asserted together because they are the fields the pass actually consumes — the
    verdict selects the record, the identity decides independence, and the
    reproduction verdict decides the assertion.
    """
    body = render_proof_record(
        title=PROOF_RECORD_TITLE,
        verdict=VERDICT_HOST_VERIFIED,
        identity=_IDENTITY,
        timestamp=_TIMESTAMP,
        build=_BUILD,
        assertions=(_assertion(text=_FIRST),),
    )
    record = _one_record(body=body)
    assert record.verdict == VERDICT_HOST_VERIFIED
    assert record.run_id == "01M44SESSION"
    assert record.timestamp == _TIMESTAMP
    assert record.reproduced(assertion=_FIRST) is True
    assert build_identity_in(body=body) == _BUILD
    assert REPRODUCTION_STEPS_HEADING in body
    assert PROOF_HEADING in body


def test_each_assertions_verdict_is_read_from_its_own_section() -> None:
    """Two assertions, opposite verdicts, and neither section absorbs the other's.

    The failure this forbids is the fail-OPEN one: a body whose sections merge
    reports the first assertion's verdict for the second, so a replay that
    reproduced one of two assertions would pass both.
    """
    body = render_proof_record(
        title=PROOF_RECORD_TITLE,
        verdict=VERDICT_HOST_VERIFIED,
        identity=_IDENTITY,
        timestamp=_TIMESTAMP,
        build=_BUILD,
        assertions=(
            _assertion(text=_FIRST, reproduced=True),
            _assertion(text=_SECOND, reproduced=False),
        ),
    )
    record = _one_record(body=body)
    assert record.reproduced(assertion=_FIRST) is True
    assert record.reproduced(assertion=_SECOND) is False


def test_a_proof_carrying_its_own_fence_does_not_break_the_readers_fence_tracking() -> None:
    """A proof that prints a fenced block is wrapped in a LONGER fence.

    A capture routinely prints part of a Markdown file, and that output carries
    its own triple-backtick fences. Wrapping it in a three-backtick fence closes
    the record's fence early, after which the reader treats the rest of the proof
    as prose — its `#` lines open new sections and the assertion's verdict is read
    from the wrong one.
    """
    proof = "```gherkin\nScenario: a nested fence\n```\n# not a heading\n"
    body = render_proof_record(
        title=PROOF_RECORD_TITLE,
        verdict=VERDICT_HOST_VERIFIED,
        identity=_IDENTITY,
        timestamp=_TIMESTAMP,
        build=_BUILD,
        assertions=(_assertion(text=_FIRST, proof=proof), _assertion(text=_SECOND)),
    )
    record = _one_record(body=body)
    assert record.reproduced(assertion=_FIRST) is True
    assert record.reproduced(assertion=_SECOND) is True


def test_an_assertion_claiming_no_reproduction_verdict_carries_no_reproduced_line() -> None:
    """A capture asserts what it exercised, never that it reproduced itself.

    `host_recorded` is the FIRST leg: there is nothing yet to have reproduced, so
    the record must not claim a verdict. The reader's `None` is the honest answer,
    and it is what keeps the assertion pending until an independent replay posts
    one.
    """
    body = render_proof_record(
        title=PROOF_RECORD_TITLE,
        verdict=VERDICT_HOST_RECORDED,
        identity=_IDENTITY,
        timestamp=_TIMESTAMP,
        build=_BUILD,
        assertions=(_assertion(text=_FIRST, reproduced=None),),
    )
    record = _one_record(body=body)
    assert record.verdict == VERDICT_HOST_RECORDED
    assert record.reproduced(assertion=_FIRST) is None


def test_the_statement_that_no_scenario_governs_an_assertion_is_rendered_verbatim() -> None:
    """The clause's either/or: the scenario, or the statement that none governs it."""
    body = render_proof_record(
        title=PROOF_RECORD_TITLE,
        verdict=VERDICT_HOST_VERIFIED,
        identity=_IDENTITY,
        timestamp=_TIMESTAMP,
        build=_BUILD,
        assertions=(
            RecordAssertion(
                text=_FIRST,
                proof_mode=PROOF_MODE_HOST_CAPTURED,
                governing_scenario=NO_GOVERNING_SCENARIO,
                steps=("Drive it.",),
                proof="output\n",
                reproduced=True,
            ),
        ),
    )
    assert NO_GOVERNING_SCENARIO in body
    assert _one_record(body=body).reproduced(assertion=_FIRST) is True


def test_an_assertion_with_no_governing_scenario_field_renders_no_such_line() -> None:
    """`None` omits the line, which is the PLAN record's shape.

    The plan-record clause lists the assertion text, its proof mode, the steps, the
    proof and the build identity — and NO governing scenario. The item-side caller
    owns the either/or above and passes the statement explicitly; a plan-side
    caller passes `None` and gets a body carrying no claim about scenarios at all.

    This case asserts the rendered body rather than round-tripping it, and the
    reason is a finding worth stating: `_dispatcher_proof_record` is scoped to the
    ITEM record's title, so it reads a `Plan Proof of Done` first line as prose and
    returns no record at all. That is the correct answer for the item reader — a
    plan record on an item's pull request is not that item's evidence — and it means
    the plan slice owes a reader of its own rather than inheriting this one.
    """
    body = render_proof_record(
        title=_PLAN_RECORD_TITLE,
        verdict=VERDICT_HOST_VERIFIED,
        identity=_IDENTITY,
        timestamp=_TIMESTAMP,
        build=_BUILD,
        assertions=(
            RecordAssertion(
                text=_FIRST,
                proof_mode=PROOF_MODE_HOST_CAPTURED,
                governing_scenario=None,
                steps=("Drive it.",),
                proof="output\n",
                reproduced=True,
            ),
        ),
    )
    assert NO_GOVERNING_SCENARIO not in body
    assert GOVERNING_SCENARIO_LABEL not in body
    assert body.splitlines()[0].startswith(_PLAN_RECORD_TITLE)
    assert f"{REPRODUCED_LABEL}: yes." in body
    assert proof_records(comments=[{"body": body}]) == ()


def test_the_steps_are_numbered_in_the_order_they_were_given() -> None:
    """The clause asks for NUMBERED reproduction steps, so the replay is unambiguous."""
    body = render_proof_record(
        title=PROOF_RECORD_TITLE,
        verdict=VERDICT_HOST_RECORDED,
        identity=_IDENTITY,
        timestamp=_TIMESTAMP,
        build=_BUILD,
        assertions=(_assertion(text=_FIRST, reproduced=None),),
    )
    assert "1. Install the released build through its normal path." in body
    assert "2. Drive the valve." in body
