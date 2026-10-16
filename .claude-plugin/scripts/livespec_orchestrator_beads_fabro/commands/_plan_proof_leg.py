"""The archive gate's proof leg: which plan assertions a timeline actually proves.

The archive-on-completion clause of `SPECIFICATION/contracts.md` (v115) states
the whole rule: "the plan epic MUST carry a Definition of Done section; the
latest plan Proof of Done record on the epic whose verdict is `verified` or
`not_reproduced` MUST be `verified`, MUST cover every plan assertion that is not
`human_attested`, and MUST postdate both the latest `captured` record and the
last carrier-map event; and, independently, each `human_attested` plan assertion
MUST be covered by a `human_attested` record that postdates the last carrier-map
event. A later `human_attested` record does not unseat an earlier `verified`
one, and a ruling or deferral that is not a carrier-map event does not void
either."

This module is that decision, and it is PURE: a function of the parsed
assertions, the timeline's records with their positions, where the last
carrier-map event sits, and one reader that answers, per record, which release
repository it is judged against and what the forge said of that repository. The
IO it needs lives in its own modules (`_plan_proof_record`, and the
`_plan_release_repository` / `_plan_release_forge` / `_plan_release_reader`
trio) for the usual reason — a decision that reached for a subprocess could not
be exercised across the states the clause distinguishes.

WHY THE RELEASE INPUT IS A READER AND NO LONGER A TAG SET. The plan-record clause
(v148) judges the release rule "against the RELEASE REPOSITORY of each record",
and a record names its own through its first installed build identifier — so one
timeline can carry records judged against different repositories, and a single
tag set cannot express that. The leg therefore asks PER RECORD, through a seam
whose whole surface is one record body in and one reading out; it never learns
that a repository name is parsed out of a build identity, or that a forge was
asked.

WHY AN UNPROVED ASSERTION IS THE ANSWER AND A BOOLEAN IS NOT. The refusal must
name EACH unproved plan assertion, so the leg returns the assertions rather than
whether it is met. A boolean would send its reader back to count bullets in the
epic description to learn which assertion went unproved — the same reason the
carrier map's own refusal names assertions by ordinal AND by text.

WHY REJECTED RECORDS TRAVEL BESIDE THE UNPROVED ASSERTIONS. "Nothing was
published" and "something was published and the gate rejected it" are the same
observation from the assertion's side and need opposite remedies: the first needs
a replay, the second needs the published record republished against the released
build. So a rejection is a fact about the TIMELINE, carried separately, exactly
as the host leg carries its refusals separately from its grades.

WHY A LATER CAPTURE VOIDS AN EARLIER VERIFIED RECORD. The clause requires the
verified record to postdate the latest `captured` record, and that ordering is
load-bearing rather than tidy: a capture published after a replay describes steps
the replay never ran, so the replay is evidence about a superseded capture. A
capture the release rule REJECTED still counts for this ordering — it is the
newest statement of what the plan's own proof steps are, and treating it as
absent would let a stale replay keep an assertion proved. That is the fail-closed
direction, and the remedy is the ordinary one: replay the new capture.

WHY A SELF-VERIFIED RECORD IS REJECTED HERE AND NOT ONLY AT THE POST. The clause
says such a record "is not evidence, however it was posted", and a record reaches
an epic by routes the posting primitive does not own — `bd comment` by hand, an
older build, a human at a terminal. The primitive's refusal is a courtesy to the
publisher; THIS is the enforcement.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HUMAN_ATTESTED,
    DefinitionOfDoneAssertion,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    build_identity_in,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_HUMAN_ATTESTED,
    VERDICT_VERIFIED,
    ProofRecord,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
    PLAN_REPLAY_VERDICTS,
    PlanProofEntry,
    latest_plan_proof_entry,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_repository import (
    ReleaseReader,
    UnreadableRelease,
)

__all__: list[str] = [
    "NOT_EVIDENCE_NO_RELEASE",
    "NOT_EVIDENCE_SELF_VERIFIED",
    "NOT_EVIDENCE_UNKNOWN_RELEASE",
    "NOT_EVIDENCE_UNREADABLE_RELEASE",
    "PlanProofLeg",
    "plan_proof_leg",
]

# The four ways a published plan record fails to be evidence. Each is a distinct
# remedy — rerun the steps against the released artifact, name a tag the release
# repository carries, give the gate a forge it can read, have a different party
# replay — so they are distinct strings rather than one "not evidence" message
# whose reader would have to open the record to work out which.
#
# EACH RELEASE REJECTION NAMES THE RELEASE REPOSITORY IT JUDGED, composed onto the
# constant at the point of refusal. The clause requires it, and without it the two
# tag rejections are unactionable once a record may be judged against a sibling: an
# operator told only that "a release applies" cannot tell whether the gate asked
# about the repository they released from.
NOT_EVIDENCE_NO_RELEASE = "states release none, and a release applies to its release repository"
NOT_EVIDENCE_UNKNOWN_RELEASE = "names a release tag its release repository does not carry"
NOT_EVIDENCE_UNREADABLE_RELEASE = (
    "names a release repository whose release tags the gate could not read"
)
NOT_EVIDENCE_SELF_VERIFIED = "was published by the identity that captured the steps it replays"


@dataclass(frozen=True, kw_only=True)
class PlanProofLeg:
    """One epic's proof leg: what is unproved, what was rejected, what stands.

    `verified_record` is populated only when a `verified` record was actually
    EVIDENCE for something, so an archive record never cites proof the gate
    refused.
    """

    unproved: tuple[str, ...]
    rejected: tuple[str, ...]
    verified_record: ProofRecord | None

    @property
    def met(self) -> bool:
        """Whether every plan assertion is covered by evidence the gate admits."""
        return not self.unproved


def plan_proof_leg(
    *,
    assertions: Sequence[DefinitionOfDoneAssertion],
    entries: Sequence[PlanProofEntry],
    carrier_map_position: int | None,
    release_reader: ReleaseReader,
) -> PlanProofLeg:
    """Grade every plan assertion against the records on its epic's timeline.

    `carrier_map_position` is the index of the LAST carrier-map event, or `None`
    when the epic carries none. `None` imposes no recency floor rather than
    rejecting everything: a plan whose map has never been restated has nothing
    for a record to postdate, and refusing on that would make the first archive
    of every pre-clause plan unreachable.
    """
    judged = tuple(
        (one, _rejection(entry=one, entries=entries, reader=release_reader)) for one in entries
    )
    evidence = tuple(one for one, rejection in judged if rejection is None)
    fresh = tuple(
        one
        for one in evidence
        if carrier_map_position is None or one.position > carrier_map_position
    )
    replay = _standing_replay(fresh=fresh, entries=entries)
    attested = tuple(one for one in fresh if one.record.verdict == VERDICT_HUMAN_ATTESTED)
    unproved = tuple(
        one.text
        for one in assertions
        if not _covered(assertion=one, replay=replay, attested=attested)
    )
    return PlanProofLeg(
        unproved=unproved,
        rejected=tuple(
            _rejected_line(entry=one, rejection=rejection)
            for one, rejection in judged
            if rejection is not None
        ),
        verified_record=None if replay is None or unproved else replay.record,
    )


def _standing_replay(
    *, fresh: Sequence[PlanProofEntry], entries: Sequence[PlanProofEntry]
) -> PlanProofEntry | None:
    """The replay that decides the non-attested assertions, or `None` for none.

    Three conditions, all from the clause and all fail-closed: the LATEST replay
    is the one that stands, it must be `verified` rather than `not_reproduced`,
    and it must postdate the latest `captured` record. A `not_reproduced` latest
    replay therefore proves nothing at all — it does not fall through to an
    earlier `verified` one, because that would let a superseded replay hold an
    assertion proved after a later party reported it did not reproduce.
    """
    replay = latest_plan_proof_entry(entries=fresh, verdicts=PLAN_REPLAY_VERDICTS)
    if replay is None or replay.record.verdict != VERDICT_VERIFIED:
        return None
    capture = latest_plan_proof_entry(entries=entries, verdicts=(VERDICT_CAPTURED,))
    if capture is not None and replay.position < capture.position:
        return None
    return replay


def _covered(
    *,
    assertion: DefinitionOfDoneAssertion,
    replay: PlanProofEntry | None,
    attested: Sequence[PlanProofEntry],
) -> bool:
    """Whether one assertion's own leg reports it reproduced.

    The two legs are independent by ratification: a `human_attested` assertion is
    covered by a `human_attested` record and never by the verified replay, and
    every other assertion is covered by the replay and never by an attestation.
    Letting either substitute for the other is how a plan would close its host
    leg by attestation, or its human leg by a machine replay.
    """
    if assertion.proof_mode == PROOF_MODE_HUMAN_ATTESTED:
        return any(one.record.reproduced(assertion=assertion.text) is True for one in attested)
    return replay is not None and replay.record.reproduced(assertion=assertion.text) is True


def _rejection(
    *, entry: PlanProofEntry, entries: Sequence[PlanProofEntry], reader: ReleaseReader
) -> str | None:
    """Why this record is not evidence, or `None` when the gate admits it.

    The self-verified test runs FIRST, and that ordering is worth keeping: it is
    pure, so a record refused on independence costs no forge round trip at all.
    """
    self_verified = _self_verified(entry=entry, entries=entries)
    if self_verified is not None:
        return self_verified
    return _release_rejection(record=entry.record, reader=reader)


def _self_verified(*, entry: PlanProofEntry, entries: Sequence[PlanProofEntry]) -> str | None:
    """Whether a replay was published by the identity that captured its steps.

    The capture a replay replays is the latest one PRECEDING it, which is the same
    record the recency rule measures the replay against. An attestation is not a
    replay of anything, so it is exempt: a human attesting an assertion is the
    independent leg rather than a second party to a capture.
    """
    if entry.record.verdict not in PLAN_REPLAY_VERDICTS:
        return None
    preceding = tuple(one for one in entries if one.position < entry.position)
    capture = latest_plan_proof_entry(entries=preceding, verdicts=(VERDICT_CAPTURED,))
    if capture is None or capture.record.run_id != entry.record.run_id:
        return None
    return NOT_EVIDENCE_SELF_VERIFIED


def _release_rejection(*, record: ProofRecord, reader: ReleaseReader) -> str | None:
    """Whether this record satisfies the release rule of its OWN release repository.

    Three arms, in the clause's own order of precedence.

    An UNREADABLE release repository rejects, and that is the reversal v148
    landed: the retired reading returned an empty tag set for a failed read, and an
    empty set MEANS "no release applies", so an unreachable forge or a rejected
    credential made every record evidence. The refusal carries the reading's own
    failure line, which already names the repository the gate tried to read.

    An empty tag set from a SUCCESSFUL read means no release applies, so the rule
    does not fire — and a record that names a tag anyway is left alone rather than
    rejected for naming one the repository does not carry, because the condition
    the clause attaches the whole rule to was not met.

    Otherwise the record's FIRST release tag must be one the release repository
    carries. The gate "MUST NOT accept a tag merely because some repository carries
    it", which holds structurally here: the only tag set in scope is the one the
    reading brought back for this record's own repository.
    """
    reading = reader.reading(body=record.body)
    if isinstance(reading, UnreadableRelease):
        return f"{NOT_EVIDENCE_UNREADABLE_RELEASE}: {reading.failure}"
    if not reading.tags:
        return None
    build = build_identity_in(body=record.body)
    named = None if build is None else build.release_tag
    if named is None:
        return f"{NOT_EVIDENCE_NO_RELEASE} {reading.repository}"
    if named not in reading.tags:
        return f"{NOT_EVIDENCE_UNKNOWN_RELEASE}: {reading.repository} does not carry {named}"
    return None


def _rejected_line(*, entry: PlanProofEntry, rejection: str) -> str:
    """One rejected record, naming the verdict, the publisher and the reason.

    The publishing identity is named because one of the three rejections is ABOUT
    it, and because a line naming only the verdict cannot distinguish two records
    of the same verdict on one timeline.
    """
    return (
        f"{PLAN_PROOF_RECORD_TITLE} {entry.record.verdict} record published by"
        f" {entry.record.run_id} is not evidence: it {rejection}"
    )
