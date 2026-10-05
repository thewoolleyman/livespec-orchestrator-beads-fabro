"""The host leg's evidence rule: what counts as a host replay, and why not.

The host-captured leg of the post-merge acceptance section of
`SPECIFICATION/contracts.md` (v115) states the whole rule: the pass judges a
`host_captured` assertion passing "only from a `host_verified` record, on the pull
request of the latest merged run for the item, that lists the assertion as
reproduced and names a build identity containing the merged change"; it "MUST verify
that containment itself"; "a record that fails the containment check, sits on an
earlier pull request, or whose replaying identity equals its capturing identity is
not evidence, and the pass MUST report why"; a `host_not_reproduced` record that IS
evidence "is a FAIL for the assertions it names"; and with no host record that is
evidence "the assertion is PENDING ... and no `acceptance_rework_cap` attempt is
consumed".

WHY THE EARLIER-PULL-REQUEST ARM IS NOT A CHECK IN THIS MODULE. The clause names
three ways a record fails to be evidence, and this module implements two of them. The
third — a record on an EARLIER pull request — is discharged by WHERE the records are
read: the caller reads the pull request of the latest merged run and hands only those
records here, so a record on an earlier pull request is absent from the input rather
than rejected within it. That is the stronger construction, because a record this
module never sees cannot be admitted by a later edit to the admission ladder; but it
means the guarantee lives at the READ and a change there is what would break it.

WHY A GRADE IS TRI-STATE. PASS, FAIL and PENDING have three different consequences —
the item closes, returns to `active` with the rework marker, or rests in `acceptance`
— so `passed` is `bool | None` rather than a boolean. Collapsing PENDING into FAIL
would route an item whose replay has simply not happened into rework and spend a
rework attempt the clause forbids spending; collapsing it into PASS would close an
item on a replay nobody performed.

WHY AN UNOBSERVABLE CONTAINMENT CHECK REFUSES. `contains_merge` is `None` when the
comparison could not be read at all, and that is treated exactly as a FAILED
containment rather than as containment the pass may skip. A gauge that passes when
blinded converts the whole containment rule into a formality: blinding the
comparison — an unresolvable tag, an unavailable forge — would become the cheapest
way past it, and the resulting record would read as a clean pass rather than as an
unmade measurement.

WHY THE SELF-REPLAY CHECK IS RE-RUN HERE AT ALL, when the posting primitive already
refuses one. Because the clause says it is not evidence "however it was posted". A
record reaches the pull request by routes the primitive does not own — a
hand-written comment, an older build, a human with `gh` — so the primitive's refusal
is a courtesy to the publisher and THIS is the enforcement.

WHY NEWEST WINS. A record "MUST NOT be edited after posting; a correction is a new
record", so the latest record that yields a decision is the one that stands. Reading
an older one would let a superseded replay hold an assertion passing after a later
replay reported it did not reproduce, which closes an item on retracted proof.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_TITLE,
    VERDICT_HOST_NOT_REPRODUCED,
    VERDICT_HOST_VERIFIED,
    ProofRecord,
)

__all__: list[str] = [
    "NOT_EVIDENCE_CONTAINMENT",
    "NOT_EVIDENCE_NO_BUILD",
    "NOT_EVIDENCE_SELF_REPLAY",
    "NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT",
    "PENDING_HOST_LEG_REASON",
    "REPLAY_VERDICTS",
    "HostAssertionGrade",
    "HostLeg",
    "HostReplay",
    "host_leg",
]

# The standing reason an assertion is pending when NOTHING has been published for it.
# It names what would move the item, which is what the parking record renders.
PENDING_HOST_LEG_REASON = (
    "pending the host leg; passes only from an independent host_verified record"
    " naming a build identity that contains the merge"
)
# The four ways a published replay fails to be evidence. Each is a distinct remedy —
# republish naming the build, replay against the released build, make the comparison
# readable, have a different party replay — so they are distinct strings rather than
# one "not evidence" message an operator would have to diff the record to interpret.
NOT_EVIDENCE_NO_BUILD = "names no build identity"
NOT_EVIDENCE_CONTAINMENT = "names a build that does not contain the merge"
NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT = "names a build whose containment could not be read"
NOT_EVIDENCE_SELF_REPLAY = "was published by the identity that recorded the capture"
# The two verdicts that can DECIDE an assertion. `host_recorded` is deliberately
# absent: a capture is not its own replay, so a `host_recorded` record decides
# nothing even when it claims a reproduction verdict, and even when no recording
# identity is known for the identity check to catch it on.
REPLAY_VERDICTS = (VERDICT_HOST_VERIFIED, VERDICT_HOST_NOT_REPRODUCED)

# The ONLY two (verdict, reproduction-verdict) pairs that decide an assertion, each
# with the disposition and the wording it earns. A TABLE rather than a pair of
# conjunctions because what it leaves out is the interesting part: a `host_verified`
# record listing an assertion as NOT reproduced decides nothing — it is neither
# passing evidence, which the clause admits only from a `host_verified` record that
# "lists the assertion as reproduced", nor a FAIL, which the clause sources only from
# a `host_not_reproduced` record. So does a `host_not_reproduced` record that lists an
# assertion as reproduced. Both fall through to the next replay and then to PENDING,
# and a reader can see that here instead of deriving it from two `and`s.
_DECISIVE: dict[tuple[str, bool | None], tuple[bool, str]] = {
    (VERDICT_HOST_VERIFIED, True): (True, "reproduced"),
    (VERDICT_HOST_NOT_REPRODUCED, False): (False, "not reproduced"),
}


@dataclass(frozen=True, kw_only=True)
class HostReplay:
    """One host record, its parsed build identity, and the containment verdict.

    The three travel together because the evidence question needs all three at once
    and each comes from a different place: the record from the forge, the build from
    parsing its body, the containment from a second forge read aimed at that build.
    """

    record: ProofRecord
    build: BuildIdentity | None
    contains_merge: bool | None

    @property
    def reference(self) -> str:
        """The build ref this replay was checked against, or `""` when it names none.

        A string rather than `str | None` because every consumer is building a
        message: the empty case is "the record named no ref", which each caller
        renders as the absence of a build clause rather than as the word `None`.
        """
        build = self.build
        if build is None or build.containment_ref is None:
            return ""
        return build.containment_ref

    @property
    def refusal(self) -> str | None:
        """Why this replay is not evidence, or `None` when it is.

        A record naming no build and one naming a build with nothing to check
        against are ONE refusal: both leave the containment check with no ref to aim
        at, and the remedy for both is to republish naming the build exercised.

        The identity check is NOT here: it needs the capture's identity, which is a
        property of the pull request rather than of this record, and putting it here
        would mean carrying the same recording identity onto every replay.
        """
        if not self.reference:
            return NOT_EVIDENCE_NO_BUILD
        if self.contains_merge is None:
            return NOT_EVIDENCE_UNOBSERVABLE_CONTAINMENT
        if not self.contains_merge:
            return NOT_EVIDENCE_CONTAINMENT
        return None


@dataclass(frozen=True, kw_only=True)
class HostAssertionGrade:
    """One host-captured assertion's disposition and the reason reported for it."""

    text: str
    passed: bool | None
    reason: str
    record_comment: str | None


@dataclass(frozen=True, kw_only=True)
class HostLeg:
    """The host leg of one acceptance pass.

    `verified_record` is the record the pointer cites, and it is populated only when
    a `host_verified` record was actually EVIDENCE for something: a pointer naming a
    record the pass refused would advertise proof the verdict never rested on.

    `refused` names every published replay the rule rejected, with its reason. It is
    separate from the grades because a refusal is a fact about the PULL REQUEST, not
    about one assertion — the same bad record refuses for all of them — and an
    operator reading five identical reasons would have no way to tell one bad record
    from five.
    """

    grades: tuple[HostAssertionGrade, ...]
    verified_record: ProofRecord | None
    refused: tuple[str, ...]

    @property
    def pending(self) -> tuple[str, ...]:
        """The assertions still awaiting an independent host replay."""
        return tuple(one.text for one in self.grades if one.passed is None)


def host_leg(
    *,
    assertions: Sequence[str],
    replays: Sequence[HostReplay],
    recording_identity: str | None,
) -> HostLeg:
    """Grade each host-captured assertion against the replays published for the merge.

    `replays` arrives in the forge's own comment order, which is chronological, and
    is walked NEWEST first. `recording_identity` is the identity of the latest
    `host_recorded` record on the same pull request, or `None` when none was
    published — in which case no replay can be a self-replay, because there is no
    capture for it to be a replay OF.
    """
    admissible = tuple(one for one in replays if one.record.verdict in REPLAY_VERDICTS)
    judged = tuple(
        (one, _refusal(replay=one, recording_identity=recording_identity)) for one in admissible
    )
    evidence = tuple(one for one, refusal in judged if refusal is None)
    grades = tuple(_grade(text=text, evidence=evidence, judged=judged) for text in assertions)
    return HostLeg(
        grades=grades,
        verified_record=_cited_record(grades=grades, evidence=evidence),
        refused=tuple(
            _refused_line(replay=one, refusal=refusal)
            for one, refusal in judged
            if refusal is not None
        ),
    )


def _refusal(*, replay: HostReplay, recording_identity: str | None) -> str | None:
    if recording_identity is not None and replay.record.run_id == recording_identity:
        return NOT_EVIDENCE_SELF_REPLAY
    return replay.refusal


def _refused_line(*, replay: HostReplay, refusal: str) -> str:
    """One refused replay, naming the record, the build it claimed, and the reason.

    The build is named because two of the four refusals are ABOUT it and the remedy
    differs by which build was claimed: an operator told only that containment failed
    has to open the comment to find out whether the record named last week's release
    or this one.
    """
    build = f" (build {replay.reference})" if replay.reference else ""
    return (
        f"{PROOF_RECORD_TITLE} {replay.record.verdict} record {replay.record.url}{build}"
        f" is not evidence: it {refusal}"
    )


def _grade(
    *,
    text: str,
    evidence: Sequence[HostReplay],
    judged: Sequence[tuple[HostReplay, str | None]],
) -> HostAssertionGrade:
    """This assertion's disposition from the newest evidence replay that decides it."""
    for replay in reversed(evidence):
        decision = _DECISIVE.get((replay.record.verdict, replay.record.reproduced(assertion=text)))
        if decision is None:
            continue
        passed, listing = decision
        return _decided(text=text, replay=replay, passed=passed, listing=listing)
    return HostAssertionGrade(
        text=text,
        passed=None,
        reason=_pending_reason(judged=judged),
        record_comment=None,
    )


def _decided(*, text: str, replay: HostReplay, passed: bool, listing: str) -> HostAssertionGrade:
    """The reason a decided assertion carries: which record, which party, which build.

    All three are named because all three are what the clause makes the decision turn
    on, and because this reason is what the journal and the parking record render. A
    reason naming only the record leaves a reader unable to check the independence or
    the containment that admitted it without re-reading the comment.
    """
    return HostAssertionGrade(
        text=text,
        passed=passed,
        reason=(
            f"{PROOF_RECORD_TITLE} {replay.record.verdict} record {replay.record.url}"
            f" published by {replay.record.run_id} against {replay.reference}"
            f" lists the assertion as {listing}"
        ),
        record_comment=replay.record.url,
    )


def _pending_reason(*, judged: Sequence[tuple[HostReplay, str | None]]) -> str:
    """The standing reason, extended with every refusal when there were any.

    An operator reading a pending assertion needs to know whether nothing has been
    published or whether something was published and rejected: the first needs a
    replay, the second needs the published record fixed, and the two are otherwise
    the same observation.
    """
    refusals = tuple(
        _refused_line(replay=one, refusal=refusal) for one, refusal in judged if refusal is not None
    )
    if not refusals:
        return PENDING_HOST_LEG_REASON
    return f"{PENDING_HOST_LEG_REASON}; {'; '.join(refusals)}"


def _cited_record(
    *, grades: Sequence[HostAssertionGrade], evidence: Sequence[HostReplay]
) -> ProofRecord | None:
    """The `host_verified` record the pointer cites, when the pass rested on one.

    Keyed on a grade this record actually PASSED rather than on such a record merely
    existing, so a pointer never names a record the pass refused — and never names a
    `host_verified` record that a later `host_not_reproduced` replay superseded, which
    is the case that would advertise retracted proof on a failing item.
    """
    cited = {one.record_comment for one in grades if one.passed}
    for replay in reversed(evidence):
        if replay.record.verdict == VERDICT_HOST_VERIFIED and replay.record.url in cited:
            return replay.record
    return None
