"""Tests for the host leg's evidence RULE — what counts as a host replay, and why not.

The gathering half — which records are replays, and whether the build each names
carries the merge — lives in `_dispatcher_host_containment` and is tested beside it.

The host-captured leg of the post-merge acceptance section of
`SPECIFICATION/contracts.md` (v115) states the rule this module implements: the pass
judges a `host_captured` assertion passing "only from a `host_verified` record, on
the pull request of the latest merged run for the item, that lists the assertion as
reproduced and names a build identity containing the merged change"; it "MUST verify
that containment itself"; "a record that fails the containment check, sits on an
earlier pull request, or whose replaying identity equals its capturing identity is
not evidence, and the pass MUST report why"; a `host_not_reproduced` record that IS
evidence "is a FAIL for the assertions it names"; and with no host record that is
evidence "the assertion is PENDING".

THE THREE OUTCOMES ARE TRI-STATE AND MUST STAY SO. PASS, FAIL and PENDING are three
different dispositions with three different consequences — close, rework, rest — so
a grade carries `passed: bool | None` rather than a boolean. Collapsing PENDING into
FAIL would route an item with no replay yet into rework and spend an
`acceptance_rework_cap` attempt the clause forbids spending; collapsing it into PASS
would close an item on a replay nobody performed.

EVERY REFUSAL IS ASSERTED BY ITS REPORTED TEXT, not merely by the pending verdict.
The clause requires the pass to "report why", and a refusal reported as a bare
"pending" is indistinguishable from the ordinary case of a replay that has simply not
happened yet — which is the one state an operator must NOT confuse it with, because
one needs a replay and the other needs the published record fixed.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import (
    NOT_EVIDENCE_CONTAINMENT,
    NOT_EVIDENCE_NO_BUILD,
    NOT_EVIDENCE_SELF_REPLAY,
    NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT,
    PENDING_HOST_LEG_REASON,
    HostReplay,
    host_leg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    RecordAssertion,
    render_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_TITLE,
    VERDICT_HOST_NOT_REPRODUCED,
    VERDICT_HOST_RECORDED,
    VERDICT_HOST_VERIFIED,
    ProofRecord,
    proof_records,
)

_RELEASE_TAG = "v0.166.0"
_CAPTURING = "01M44CAPTURINGSESSION"
_REPLAYING = "01M44REPLAYINGSESSION"
_ASSERTION = "The released build resolves the host mode on an operator host."
_OTHER = "The accept valve refuses while the host leg is pending."
_BUILD = BuildIdentity(
    release_tag=_RELEASE_TAG, installed_build="orchestrator 0.166.0", commit=None
)
_URL = "https://example.test/owner/repo/pull/36#issuecomment-900"


def _record(
    *,
    verdict: str,
    identity: str,
    reproduced: bool | None,
    assertions: tuple[str, ...] = (_ASSERTION,),
    url: str = _URL,
) -> ProofRecord:
    """One record built by RENDERING it, so the fixtures cannot drift from production.

    A hand-written body would let these tests agree with a reader the posting
    primitive's own output disagrees with — the exact failure the renderer's tests
    exist to prevent, re-introduced one layer up.
    """
    body = render_proof_record(
        title=PROOF_RECORD_TITLE,
        verdict=verdict,
        identity=f"session {identity}",
        timestamp="2026-10-04T22:30:00Z",
        build=_BUILD,
        assertions=tuple(
            RecordAssertion(
                text=text,
                proof_mode="host_captured",
                governing_scenario=None,
                steps=("Install the released build.",),
                proof="output\n",
                reproduced=reproduced,
            )
            for text in assertions
        ),
    )
    records = proof_records(comments=[{"body": body, "url": url}])
    assert len(records) == 1
    return records[0]


def _replay(*, record: ProofRecord, contains_merge: bool | None = True) -> HostReplay:
    return HostReplay(record=record, build=_BUILD, contains_merge=contains_merge)


def test_an_independent_verified_replay_against_a_containing_build_passes_the_assertion() -> None:
    """The one path to PASS: independent identity, containment held, listed reproduced."""
    leg = host_leg(
        assertions=(_ASSERTION,),
        replays=(
            _replay(
                record=_record(verdict=VERDICT_HOST_VERIFIED, identity=_REPLAYING, reproduced=True)
            ),
        ),
        recording_identity=_CAPTURING,
    )
    assert [one.passed for one in leg.grades] == [True]
    assert leg.pending == ()
    assert leg.verified_record is not None
    assert leg.verified_record.url == _URL
    assert _REPLAYING in leg.grades[0].reason


def test_a_replay_published_by_the_recording_identity_is_not_evidence() -> None:
    """A self-replay leaves the assertion pending and the refusal names the reason.

    The clause makes this true "however it was posted", so the pass re-checks it
    rather than trusting that the posting primitive refused: a record posted by any
    other route — a hand-written comment, an older build of the primitive — reaches
    the same pull request and must be rejected here too.
    """
    leg = host_leg(
        assertions=(_ASSERTION,),
        replays=(
            _replay(
                record=_record(verdict=VERDICT_HOST_VERIFIED, identity=_CAPTURING, reproduced=True)
            ),
        ),
        recording_identity=_CAPTURING,
    )
    assert [one.passed for one in leg.grades] == [None]
    assert leg.pending == (_ASSERTION,)
    assert leg.verified_record is None
    assert any(NOT_EVIDENCE_SELF_REPLAY in one for one in leg.refused)
    assert NOT_EVIDENCE_SELF_REPLAY in leg.grades[0].reason


def test_a_replay_naming_a_build_that_does_not_contain_the_merge_is_not_evidence() -> None:
    """A failed containment check is reported, and the assertion stays pending."""
    leg = host_leg(
        assertions=(_ASSERTION,),
        replays=(
            _replay(
                record=_record(verdict=VERDICT_HOST_VERIFIED, identity=_REPLAYING, reproduced=True),
                contains_merge=False,
            ),
        ),
        recording_identity=_CAPTURING,
    )
    assert [one.passed for one in leg.grades] == [None]
    assert any(NOT_EVIDENCE_CONTAINMENT in one for one in leg.refused)
    assert _RELEASE_TAG in leg.grades[0].reason


def test_an_unobservable_containment_check_is_not_evidence_either() -> None:
    """An unreadable comparison refuses rather than passing, which is fail-closed.

    A gauge that passed when it could not observe its input would turn the whole
    containment rule into a formality: blinding the comparison — an unresolvable
    tag, an unavailable forge — would be the cheapest way past it.
    """
    leg = host_leg(
        assertions=(_ASSERTION,),
        replays=(
            _replay(
                record=_record(verdict=VERDICT_HOST_VERIFIED, identity=_REPLAYING, reproduced=True),
                contains_merge=None,
            ),
        ),
        recording_identity=_CAPTURING,
    )
    assert [one.passed for one in leg.grades] == [None]
    assert any(NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT in one for one in leg.refused)


def test_a_replay_naming_no_build_identity_is_not_evidence() -> None:
    """The clause requires the record to name the build; one that does not is refused."""
    leg = host_leg(
        assertions=(_ASSERTION,),
        replays=(
            HostReplay(
                record=_record(verdict=VERDICT_HOST_VERIFIED, identity=_REPLAYING, reproduced=True),
                build=None,
                contains_merge=None,
            ),
        ),
        recording_identity=_CAPTURING,
    )
    assert [one.passed for one in leg.grades] == [None]
    assert any(NOT_EVIDENCE_NO_BUILD in one for one in leg.refused)


def test_an_independent_not_reproduced_replay_fails_the_assertions_it_names() -> None:
    """A `host_not_reproduced` record that IS evidence is a FAIL, which is rework input."""
    leg = host_leg(
        assertions=(_ASSERTION,),
        replays=(
            _replay(
                record=_record(
                    verdict=VERDICT_HOST_NOT_REPRODUCED, identity=_REPLAYING, reproduced=False
                )
            ),
        ),
        recording_identity=_CAPTURING,
    )
    assert [one.passed for one in leg.grades] == [False]
    assert leg.pending == ()
    assert leg.verified_record is None


def test_with_no_host_record_at_all_the_assertion_is_pending_with_the_standing_reason() -> None:
    """The ordinary case: nothing published yet, so nothing to report but the wait."""
    leg = host_leg(assertions=(_ASSERTION,), replays=(), recording_identity=None)
    assert [one.passed for one in leg.grades] == [None]
    assert leg.grades[0].reason == PENDING_HOST_LEG_REASON
    assert leg.refused == ()


def test_a_record_that_says_nothing_about_one_assertion_leaves_only_that_one_pending() -> None:
    """Per-assertion grading: a replay covering one of two decides only that one.

    The fail-OPEN failure this forbids is a leg that passed every assertion because
    the record it found was evidence for one of them.
    """
    leg = host_leg(
        assertions=(_ASSERTION, _OTHER),
        replays=(
            _replay(
                record=_record(verdict=VERDICT_HOST_VERIFIED, identity=_REPLAYING, reproduced=True)
            ),
        ),
        recording_identity=_CAPTURING,
    )
    assert [one.passed for one in leg.grades] == [True, None]
    assert leg.pending == (_OTHER,)


def test_the_newest_evidence_record_decides_and_an_older_one_does_not_override_it() -> None:
    """A correction is a new record, so the later one wins.

    Both records here are evidence, and they disagree. Reading the OLDER one would
    let a superseded replay hold an assertion passing after a later replay reported
    it did not reproduce — which is the direction that closes an item on retracted
    proof.
    """
    leg = host_leg(
        assertions=(_ASSERTION,),
        replays=(
            _replay(
                record=_record(verdict=VERDICT_HOST_VERIFIED, identity=_REPLAYING, reproduced=True)
            ),
            _replay(
                record=_record(
                    verdict=VERDICT_HOST_NOT_REPRODUCED, identity=_REPLAYING, reproduced=False
                )
            ),
        ),
        recording_identity=_CAPTURING,
    )
    assert [one.passed for one in leg.grades] == [False]


def test_a_host_recorded_record_never_decides_an_assertion() -> None:
    """The capture is not its own replay, whatever it claims about reproduction.

    A `host_recorded` record normally claims no reproduction verdict, but nothing
    stops one being published that does. It must still not pass the assertion — the
    clause admits only a `host_verified` record as passing evidence — and the
    identity check alone would not catch it, because a capture's identity is of
    course the recording identity and this leg must stay correct for a record whose
    recording identity is unknown.
    """
    leg = host_leg(
        assertions=(_ASSERTION,),
        replays=(
            _replay(
                record=_record(verdict=VERDICT_HOST_RECORDED, identity=_CAPTURING, reproduced=True)
            ),
        ),
        recording_identity=None,
    )
    assert [one.passed for one in leg.grades] == [None]
    assert leg.refused == ()
