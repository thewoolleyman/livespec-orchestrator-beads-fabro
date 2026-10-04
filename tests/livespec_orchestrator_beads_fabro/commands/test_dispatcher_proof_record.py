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
"""

from __future__ import annotations

import textwrap

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HUMAN_ATTESTED,
    VERDICT_VERIFIED,
    ProofRecord,
    latest_proof_record,
    proof_records,
)

_RUN_ID = "01M3RECORDRUN"


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


def test_no_record_of_the_asked_verdict_is_none() -> None:
    records = proof_records(
        comments=[_record(body=_verified_body(assertion="X.", reproduced="yes."))]
    )

    assert latest_proof_record(records=records, verdict=VERDICT_HUMAN_ATTESTED) is None
