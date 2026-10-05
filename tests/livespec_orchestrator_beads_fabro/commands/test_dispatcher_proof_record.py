"""Tests for the Proof of Done record reader.

The header shape, the verdict enumeration and the per-assertion `Reproduced:`
line are what `SPECIFICATION/contracts.md` and the `proof_verify` prompt between
them fix, so each refusal below is a case the
reader has to tell apart from a real record rather than a defensive branch: a
pull request carries ordinary discussion alongside its records, and reading a
comment that merely MENTIONS the title as proof would let any reviewer's remark
evidence an assertion.

The tri-state `reproduced` answer is asserted in all three directions, because
`None` is the one the evidence rule depends on and it is the one a reader
collapsing it into `False` would still pass two assertions out of three on.

THE FENCED CASES AT THE END ARE WHERE REAL RECORDS LIVE. Every body above is
hand-written prose, and a hand-written body carries no proof; a real record's
sections are mostly fenced code whose lines begin with a hash, so the bodies below
are shaped like the records the factory actually publishes. They are asserted in
both directions deliberately: a fence-aware splitter that merely stopped splitting
would be fail-OPEN, letting an assertion with no `Reproduced:` line of its own
report whatever a LATER assertion said. The measured half of all of this, over two
real payloads, is
`tests/integration/test_proof_record_fenced_section_segmentation.py`.
"""

from __future__ import annotations

import textwrap

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_VERDICTS,
    VERDICT_HUMAN_ATTESTED,
    VERDICT_VERIFIED,
    ProofRecord,
    latest_proof_record,
    proof_records,
)

_RUN_ID = "01M3RECORDRUN"
# Spelled as a literal rather than imported, for the reason the case below
# records: a top-level import of a name the module does not carry yet turns a
# Red into a collection error.
_NOT_CAPTURED = "not_captured"


def _record(*, body: str, url: str = "https://example.test/c/1") -> dict[str, object]:
    return {"url": url, "body": body}


def _verified_body(*, assertion: str, reproduced: str, run_id: str = _RUN_ID) -> str:
    return textwrap.dedent(f"""\
        Proof of Done — verified — run {run_id} — 2026-10-01T09:00:00Z

        ## Assertion 1 — {assertion}

        Proof mode: `factory_captured`

        Reproduced: {reproduced}
        """)


def test_a_record_header_is_parsed_into_verdict_run_and_timestamp() -> None:
    records = proof_records(
        comments=[_record(body=_verified_body(assertion="It works.", reproduced="yes."))]
    )

    assert [one.verdict for one in records] == [VERDICT_VERIFIED]
    assert [one.run_id for one in records] == [_RUN_ID]
    assert [one.timestamp for one in records] == ["2026-10-01T09:00:00Z"]
    assert [one.url for one in records] == ["https://example.test/c/1"]


def test_a_header_with_no_timestamp_field_still_parses_with_an_empty_timestamp() -> None:
    """Three fields is the MINIMUM: the timestamp is read when present."""
    records = proof_records(
        comments=[_record(body="Proof of Done — human_attested — run alice\n\nAttested.\n")]
    )

    assert [(one.verdict, one.run_id, one.timestamp) for one in records] == [
        (VERDICT_HUMAN_ATTESTED, "alice", "")
    ]


def test_each_identity_introducer_the_header_grammar_admits_is_parsed() -> None:
    """`run`, `session` and `human`, each stripped to the bare identity.

    The v115 host-leg records are published by an agent SESSION on an operator
    host, so the third field carries `session <identity>` and no Fabro run exists
    for them. A reader admitting only `run ` drops the whole host leg — and drops
    it SILENTLY, because a comment it refuses to parse is simply not a record, so
    the valve that reads for a `host_verified` record finds none and reports the
    replay as unpublished when it is sitting on the pull request.

    The CONTROL is the case below, which still refuses a third field carrying no
    introducer at all: widening the grammar must not reduce to accepting anything.
    """
    bodies = (
        f"Proof of Done — verified — run {_RUN_ID} — t\n",
        "Proof of Done — host_verified — session replaying-session — t\n",
        "Proof of Done — human_attested — human cwoolley — t\n",
    )

    records = proof_records(comments=[_record(body=body) for body in bodies])

    assert [(one.verdict, one.run_id) for one in records] == [
        (VERDICT_VERIFIED, _RUN_ID),
        ("host_verified", "replaying-session"),
        (VERDICT_HUMAN_ATTESTED, "cwoolley"),
    ]


def test_an_absent_url_reads_as_an_empty_string_rather_than_refusing_the_record() -> None:
    records = proof_records(comments=[{"body": _verified_body(assertion="X.", reproduced="yes.")}])

    assert [one.url for one in records] == [""]


def test_comments_that_are_not_records_are_dropped() -> None:
    """Each refusal arm, over one comment list, so none can hide behind another."""
    comments: list[dict[str, object]] = [
        # No body at all, and a body that is not a string.
        {"url": "u"},
        _record(body=0),  # pyright: ignore[reportArgumentType]
        # Empty body: there is no first line to read a header off.
        _record(body=""),
        # Too few em-dash-separated fields.
        _record(body="Proof of Done — verified\n"),
        # The right shape, the wrong title.
        _record(body="Proof of Doing — verified — run r — t\n"),
        # The right title, a verdict outside the closed enumeration.
        _record(body="Proof of Done — maybe — run r — t\n"),
        # The right title and verdict, no `run ` introducer.
        _record(body="Proof of Done — verified — 01M3 — t\n"),
    ]

    assert proof_records(comments=comments) == ()


def test_an_assertion_listed_as_reproduced_is_true() -> None:
    record = proof_records(
        comments=[_record(body=_verified_body(assertion="It works.", reproduced="yes."))]
    )[0]

    assert record.reproduced(assertion="It works.") is True


def test_an_assertion_listed_as_not_reproduced_is_false() -> None:
    record = proof_records(
        comments=[
            _record(body=_verified_body(assertion="It works.", reproduced="NO. Step 1 failed."))
        ]
    )[0]

    assert record.reproduced(assertion="It works.") is False


def test_an_assertion_the_record_never_mentions_is_unevidenced() -> None:
    record = proof_records(
        comments=[_record(body=_verified_body(assertion="It works.", reproduced="yes."))]
    )[0]

    assert record.reproduced(assertion="Something else entirely.") is None


def test_an_empty_assertion_is_unevidenced_rather_than_matching_every_section() -> None:
    """A blank needle is a substring of everything, so it is refused outright."""
    record = proof_records(
        comments=[_record(body=_verified_body(assertion="It works.", reproduced="yes."))]
    )[0]

    assert record.reproduced(assertion="   ") is None


def test_a_section_with_no_readable_reproduced_line_is_unevidenced() -> None:
    """Both arms: no `Reproduced:` line at all, and one whose value says neither."""
    silent = ProofRecord(
        verdict=VERDICT_VERIFIED,
        run_id=_RUN_ID,
        timestamp="t",
        url="u",
        body="Proof of Done — verified — run r — t\n\n## Assertion 1 — It works.\n\nProof: none.\n",
    )
    unreadable = ProofRecord(
        verdict=VERDICT_VERIFIED,
        run_id=_RUN_ID,
        timestamp="t",
        url="u",
        body=(
            "Proof of Done — verified — run r — t\n\n"
            "## Assertion 1 — It works.\n\nReproduced: partially, in a sense.\n"
        ),
    )

    assert silent.reproduced(assertion="It works.") is None
    assert unreadable.reproduced(assertion="It works.") is None


def test_an_assertion_hard_wrapped_across_lines_is_still_matched() -> None:
    """Section-scoped, whitespace-normalized matching: a wrap is not a mismatch."""
    record = ProofRecord(
        verdict=VERDICT_VERIFIED,
        run_id=_RUN_ID,
        timestamp="t",
        url="u",
        body=(
            "Proof of Done — verified — run r — t\n\n"
            "## Assertion 1 — The projection carries the\n"
            "  parent field on every record.\n\n"
            "Reproduced: yes.\n"
        ),
    )

    assert record.reproduced(assertion="The projection carries the parent field on every record.")


def test_a_later_section_does_not_absorb_an_earlier_assertions_verdict() -> None:
    """Two assertions, opposite verdicts, read off their own sections."""
    record = ProofRecord(
        verdict=VERDICT_VERIFIED,
        run_id=_RUN_ID,
        timestamp="t",
        url="u",
        body=(
            "Proof of Done — verified — run r — t\n\n"
            "## Assertion 1 — First one.\n\nReproduced: yes.\n\n"
            "## Assertion 2 — Second one.\n\nReproduced: NO.\n"
        ),
    )

    assert record.reproduced(assertion="First one.") is True
    assert record.reproduced(assertion="Second one.") is False


def test_the_latest_record_of_a_verdict_wins_and_the_run_filter_binds() -> None:
    records = proof_records(
        comments=[
            _record(body=_verified_body(assertion="X.", reproduced="yes."), url="first"),
            _record(
                body=_verified_body(assertion="X.", reproduced="yes.", run_id="other"),
                url="other-run",
            ),
            _record(body=_verified_body(assertion="X.", reproduced="NO."), url="second"),
        ]
    )

    unfiltered = latest_proof_record(records=records, verdict=VERDICT_VERIFIED)
    attributed = latest_proof_record(records=records, verdict=VERDICT_VERIFIED, run_ids=(_RUN_ID,))
    other = latest_proof_record(records=records, verdict=VERDICT_VERIFIED, run_ids=("other",))
    # A set carrying BOTH identifiers of one dispatch takes the newest record of
    # either, which is the widening the acceptance pass depends on.
    either = latest_proof_record(
        records=records, verdict=VERDICT_VERIFIED, run_ids=(_RUN_ID, "other")
    )
    # And an EMPTY set is not the unfiltered set: an unidentifiable dispatch
    # matches nothing rather than inheriting the newest record.
    unidentifiable = latest_proof_record(records=records, verdict=VERDICT_VERIFIED, run_ids=())

    assert unfiltered is not None
    assert unfiltered.url == "second"
    assert attributed is not None
    assert attributed.url == "second"
    assert other is not None
    assert other.url == "other-run"
    assert either is not None
    assert either.url == "second"
    assert unidentifiable is None


def _not_captured_body(*, run_id: str = _RUN_ID) -> str:
    return textwrap.dedent(f"""\
        Proof of Done — not_captured — run {run_id} — 2026-10-04T09:00:00Z

        ## Assertion 1 — The command refuses an unsorted id list.

        Proof mode: `factory_captured`

        Could not capture: step 2 accepted the unsorted list `[z, a]`.
        """)


def test_a_capture_finding_record_parses_under_the_not_captured_verdict() -> None:
    """`not_captured` is inside the closed enumeration, so its record is readable.

    A `proof_capture` visit that ends with `preferred_label=fix` publishes its
    finding as a record carrying this verdict, and the `fix` stage it routes to
    reads the latest record on the pull request when its own preamble carries no
    finding. A verdict OUTSIDE the enumeration is not a record at all — the
    reader drops the whole comment, silently — so the finding would be
    unreachable by exactly the stage that has to act on it, and the drop would
    look identical to a stage that never published anything.

    THE CONSTANT IS DELIBERATELY NOT IMPORTED AT MODULE TOP. A top-level import
    of a name the module does not carry yet makes the Red a COLLECTION error,
    which proves only unimportability and never that the verdict is unadmitted.
    The literal plus the membership assertion fail as genuine assertions
    instead, and `PROOF_RECORD_VERDICTS` is the surface every reader consults.

    The near-miss verdict is the control. Without it, the first assertion is
    equally consistent with a reader that stopped grading the field at all,
    which would admit any comment opening with the title as proof.
    """
    records = proof_records(comments=[_record(body=_not_captured_body())])

    assert [one.verdict for one in records] == [_NOT_CAPTURED]
    assert _NOT_CAPTURED in PROOF_RECORD_VERDICTS
    assert latest_proof_record(records=records, verdict=_NOT_CAPTURED) is records[0]
    assert proof_records(comments=[_record(body="Proof of Done — not_capture — run r — t\n")]) == ()


def test_no_record_of_the_asked_verdict_is_none() -> None:
    records = proof_records(
        comments=[_record(body=_verified_body(assertion="X.", reproduced="yes."))]
    )

    assert latest_proof_record(records=records, verdict=VERDICT_HUMAN_ATTESTED) is None


def _fenced_record(*, body: str) -> ProofRecord:
    return ProofRecord(
        verdict=VERDICT_VERIFIED,
        run_id=_RUN_ID,
        timestamp="t",
        url="u",
        body=f"Proof of Done — verified — run {_RUN_ID} — t\n\n{textwrap.dedent(body)}",
    )


def test_a_fenced_proof_whose_lines_begin_with_a_hash_does_not_end_the_section() -> None:
    """The shape of every real record: hash lines inside the proof, verdict after it.

    A proof prints things, and the things it prints begin with a hash — shell
    comments, Python comments, the headings of a Markdown file it `cat`s. The
    `Reproduced:` line follows the fenced block, so a splitter treating those lines
    as headings ends the section before reaching it and reports an assertion the
    record states was reproduced as unobserved.
    """
    record = _fenced_record(
        body="""\
        ## Assertion 1 — The checker refuses an unsorted list.

        Proof mode: `factory_captured`

        Proof 01:

        ```text
        $ ./check.sh
        # the guard's own comment, printed by `cat check.sh`
        ### 1. the committed enumeration
        #!/usr/bin/env bash
        refused: [z, a] is not sorted
        ```

        Reproduced: yes. Proof 01 matches the captured record byte-for-byte.
        """
    )

    assert record.reproduced(assertion="The checker refuses an unsorted list.") is True


def test_an_assertion_with_no_reproduced_line_cannot_borrow_a_later_ones() -> None:
    """The fail-OPEN direction, through the fence shape that reaches it.

    A proof that prints part of a Markdown file prints that file's OWN fences, so a
    record legitimately carries a shorter fence nested inside a longer one — and an
    EXCERPT can carry one half of a pair. A splitter that flips a boolean on every
    delimiter reads that inner line as closing the outer block and the outer closer
    as opening a new one, so from there on it believes it is inside a fence forever:
    the NEXT assertion's heading stops being a boundary, the two sections merge, and
    the first assertion — which published no verdict of its own — reports the second
    one's `yes`. That is evidence nobody wrote, which is strictly worse than the
    unevidenced answer it replaces.

    The second assertion is the control. Without it the expectation is equally
    consistent with a reader that had stopped reading the `Reproduced:` line
    altogether, which would answer `None` here for the right reason and `None`
    everywhere else for the wrong one.
    """
    record = _fenced_record(
        body="""\
        ## Assertion 1 — Alpha is published without a verdict.

        Proof 01:

        ````text
        $ sed -n '1,3p' prompts/fix.md
        # a heading inside the file the proof printed
        ```
        ````

        ## Assertion 2 — Beta carries the only verdict in the body.

        Reproduced: yes.
        """
    )

    assert record.reproduced(assertion="Alpha is published without a verdict.") is None
    assert record.reproduced(assertion="Beta carries the only verdict in the body.") is True


def test_a_reproduced_no_survives_a_fenced_proof_that_prints_headings() -> None:
    """The `no` direction, in the same shape: a refusal is still a refusal.

    `False` and `None` route the item differently — one is failing evidence and the
    other is no evidence — so a fence-aware splitter that recovered the `yes` arm
    while losing this one would trade a park for a wrong pass.
    """
    record = _fenced_record(
        body="""\
        ## Assertion 1 — The banner renders on the runs page.

        Proof 01:

        ```text
        $ curl -s localhost:8099/runs | head -3
        # no capacity banner in the rendered page
        ```

        Reproduced: NO. Step 2 renders the runs page with no capacity banner.
        """
    )

    assert record.reproduced(assertion="The banner renders on the runs page.") is False


def test_fenced_proof_output_under_a_nested_heading_keeps_every_assertion_boundary() -> None:
    """The real record shape: a nested `### Replay proof` holding the fenced proof.

    This is the body the normal record format produces once a verifier gives each
    assertion a replay subsection — the `## Assertion N` heading states the
    assertion, a nested heading introduces the replay, the fenced proof prints
    whatever it printed, and the `Reproduced:` line closes the subtree. The nested
    heading is PROSE, so the fence arm cannot reach it; a splitter that opens a new
    section at it detaches the verdict from the assertion that earned it and the
    reader answers `None` for an assertion the record states was reproduced.

    All three arms ride in one body because the recovery has to be paid for. An
    assertion whose nested subsection publishes no verdict must stay unevidenced
    rather than borrow the next one's, and an assertion publishing a refusal must
    still report `False` — the fenced heading-like output is present in each
    subsection, so the fence-aware behaviour is exercised in the arms that must NOT
    widen as well as in the one that must.
    """
    record = _fenced_record(
        body="""\
        ## Assertion 1 — The reader grades a verdict beneath a nested heading.

        Proof mode: `factory_captured`

        ### Replay proof

        ```text
        $ ./dev-tooling/just-check.sh
        # the runner's own comment, printed by `cat`
        ### 3. the executed target list
        ## Assertion 2 — printed from the captured record
        ```

        Reproduced: yes. The replay matches the capture byte-for-byte.

        ## Assertion 2 — The boundary survives the printed heading.

        ### Replay proof

        ```text
        $ ./check.sh
        # this subsection publishes no verdict of its own
        ```

        ## Assertion 3 — The last assertion publishes its own refusal.

        ### Replay proof

        ```text
        $ ./check.sh
        # no capacity banner in the rendered page
        ```

        Reproduced: NO. Step 2 printed nothing.
        """
    )

    assert record.reproduced(assertion="The reader grades a verdict beneath a nested heading.")
    assert record.reproduced(assertion="The boundary survives the printed heading.") is None
    assert record.reproduced(assertion="The last assertion publishes its own refusal.") is False


def test_an_assertion_section_at_any_supported_heading_level_keeps_its_own_verdict() -> None:
    """The hierarchy is resolved GENERICALLY, not against one hard-coded depth.

    Nothing fixes the depth a record states its assertions at. A verifier writing
    `### Assertion N` under a record-wide `##` heading, or `# Assertion N` with a
    `##` replay subsection, is publishing the same structure one level up or down,
    and a reader that recognised only one depth would answer the nested arm
    correctly while merging the other arm's siblings into one section.

    Each arm therefore carries a sibling with the OPPOSITE verdict, which is what
    makes a merge visible: a splitter that stopped treating this arm's assertion
    headings as boundaries would report the first sibling's `yes` for the second,
    and a splitter that treated this arm's replay headings as boundaries would
    report `None` for both.
    """
    deeper = _fenced_record(
        body="""\
        ### Assertion 1 — The deeper section carries its own verdict.

        #### Replay proof

        Reproduced: yes.

        ### Assertion 2 — The deeper sibling keeps its own refusal.

        #### Replay proof

        Reproduced: NO.
        """
    )
    shallower = _fenced_record(
        body="""\
        # Assertion 1 — The top-level section carries its own verdict.

        ## Replay proof

        Reproduced: yes.

        # Assertion 2 — The top-level sibling keeps its own refusal.

        ## Replay proof

        Reproduced: NO.
        """
    )

    assert deeper.reproduced(assertion="The deeper section carries its own verdict.") is True
    assert deeper.reproduced(assertion="The deeper sibling keeps its own refusal.") is False
    assert shallower.reproduced(assertion="The top-level section carries its own verdict.") is True
    assert shallower.reproduced(assertion="The top-level sibling keeps its own refusal.") is False


def test_an_unverdicted_assertion_borrows_from_neither_a_sibling_nor_a_summary() -> None:
    """The fail-OPEN direction of nesting, which is what the recovery has to not buy.

    Reading a nested heading as prose inside the current section is correct going
    DOWN and catastrophic going UP: a record wrapped in one `#` heading has every
    `##` assertion nested below it, so a rule that merely carried the current depth
    forward would collapse the whole body into one section. The first assertion
    then reports whatever the first `Reproduced:` line in the body says, which on a
    record whose assertions disagree is evidence nobody published for the assertion
    it is attached to — strictly worse than the unevidenced answer it replaces.

    The sibling summary is the second way in, and it is the one a record format
    invites: a trailing `## Summary` that states the run reproduced everything is
    not a per-assertion verdict, and the clause on unevidenceable assertions makes
    an assertion with no verdict of its own unevidenced rather than passed.

    Both arms carry a control, because a reader that had stopped reading the
    `Reproduced:` line at all would answer `None` here for the wrong reason: the
    sibling that DOES publish a verdict must still read `True` off its own section.
    """
    wrapped = _fenced_record(
        body="""\
        # Proof of Done record

        ## Assertion 1 — The wrapped assertion publishes no verdict of its own.

        ### Replay proof

        ```text
        $ ./check.sh
        # this subsection publishes nothing
        ```

        ## Assertion 2 — The wrapped sibling carries the only assertion verdict.

        ### Replay proof

        Reproduced: yes.

        ## Summary

        Reproduced: yes. Every assertion replayed.
        """
    )
    summarized = _fenced_record(
        body="""\
        ## Assertion 1 — The flat assertion publishes no verdict of its own.

        ### Replay proof

        ```text
        $ ./check.sh
        # this subsection publishes nothing
        ```

        ## Summary

        Reproduced: yes. Every assertion replayed.
        """
    )

    assert (
        wrapped.reproduced(assertion="The wrapped assertion publishes no verdict of its own.")
        is None
    )
    assert wrapped.reproduced(assertion="The wrapped sibling carries the only assertion verdict.")
    assert (
        summarized.reproduced(assertion="The flat assertion publishes no verdict of its own.")
        is None
    )
