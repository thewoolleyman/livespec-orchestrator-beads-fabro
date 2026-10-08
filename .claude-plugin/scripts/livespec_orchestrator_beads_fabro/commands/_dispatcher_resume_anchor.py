"""The anchor a resume reads off a terminated run's pull request.

A run that terminates AFTER publishing leaves everything a resume needs on the
pull request: the branch, the head it ran on, and the records that say how far it
got. `SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" makes those three one answer — the *earlier run* is the
dispatch whose identifier the LATEST proof record carries, the *published head* is
the full commit sha that record names, and the *resumed-at stage* is the node the
earlier run was executing when it terminated, or the stage that record's verdict
implies when the factory no longer holds the run. This module reads that answer;
the refusals that guard it and the dispatch that acts on it are separate concerns
in separate modules.

WHY THE SOURCE IS PART OF THE ANSWER. The clause requires the `resume` record to
name "the source that decided it", and the two sources differ in the direction
that matters: the factory's own run record knows the node the run died INSIDE,
while the verdict fallback can only know the last node that PUBLISHED. An
operator reading a resume record has to be able to tell a precise entry from an
inferred one, because the inferred one may re-run a node the factory record would
have skipped.

WHY A RECORD NAMING NO HEAD ANCHORS NOTHING. The clause says outright that "a
record published before this clause was ratified names no head and cannot anchor
a resume", and the head is what the head-moved refusal compares the pull
request's current head against. An anchor carrying an empty head would send that
refusal after an unknown and resume on a tree no record describes.

WHY TWO DIFFERENT HEADS IN ONE BODY ALSO ANCHOR NOTHING. The clause requires the
head be named "once". A body naming two is a record whose own account of which
tree it ran on is contradictory, and choosing either is choosing at random, so
the reader fails closed — the same direction `_dispatcher_proof_attachment`'s
partial read takes, for the same reason: a half-read anchor sends the comparison
after a sha nobody published.

WHY THE SCAN IS FENCE-AWARE. A record's proof is fenced, and a replay proof
routinely PRINTS the head line it is checking — a `git rev-parse HEAD`, a `cat` of
the record it replays. A line-oriented scan would read that output as the record's
own declaration, so a `verified` record replaying a capture would be attributed
the capture's head rather than its own. `_dispatcher_proof_record` records the
identical trap on the `Reproduced:` line, and the fence reader is shared with it
rather than re-derived.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_NOT_CAPTURED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_VERIFIED,
    ProofRecord,
)

__all__: list[str] = [
    "FACTORY_RECORD_VERDICTS",
    "PUBLISH_HEAD_LABEL",
    "RESUMED_AT_FIX",
    "RESUMED_AT_PR",
    "RESUMED_AT_PROOF_CAPTURE",
    "RESUMED_AT_REVIEW",
    "SOURCE_FACTORY_RUN",
    "SOURCE_LATEST_RECORD",
    "ResumeAnchor",
    "published_head",
    "resume_anchor",
    "resumed_at_for_verdict",
]

# The label a factory record declares its publish-branch head under. Spelled once
# here and rendered by the two capture prompts from this same wording, so the
# reader and the writer cannot drift into naming different lines.
PUBLISH_HEAD_LABEL = "Publish-branch head"

RESUMED_AT_PR = "pr"
RESUMED_AT_REVIEW = "review"
RESUMED_AT_FIX = "fix"
RESUMED_AT_PROOF_CAPTURE = "proof_capture"

# Which party decided the resumed-at stage. Each value NAMES the measurement
# rather than ranking it, per the repository rule that an option set is never
# labelled as numbered tiers.
SOURCE_FACTORY_RUN = "factory-run-record"
SOURCE_LATEST_RECORD = "pull-request-latest-record"

# The four verdicts a FACTORY stage publishes. A host-leg or human-attested
# record is not an anchor: it carries a session identity or a forge login rather
# than a run the journal can attribute, and it names no publish-branch head
# because no factory stage ran to have one.
FACTORY_RECORD_VERDICTS = (
    VERDICT_CAPTURED,
    VERDICT_NOT_CAPTURED,
    VERDICT_VERIFIED,
    VERDICT_NOT_REPRODUCED,
)

# The stage each factory verdict implies, for the fallback the clause spells out.
# `not_captured` and `not_reproduced` share `fix` because both are findings a code
# change has to answer, which is the node that owns one.
_RESUMED_AT_BY_VERDICT = {
    VERDICT_VERIFIED: RESUMED_AT_PR,
    VERDICT_CAPTURED: RESUMED_AT_REVIEW,
    VERDICT_NOT_CAPTURED: RESUMED_AT_FIX,
    VERDICT_NOT_REPRODUCED: RESUMED_AT_FIX,
}

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True, kw_only=True)
class ResumeAnchor:
    """What one pull request says about the run a resume would finish.

    `record` is the anchoring record itself rather than its id alone, because
    every consumer needs something different off it — the refusals need its head,
    the journal record needs its run id, and the pointer needs its url — and a
    second read of the pull request to recover a field this one already held
    could answer differently.
    """

    record: ProofRecord
    head: str
    resumed_at: str
    source: str


def published_head(*, body: str) -> str | None:
    """The full commit sha one record's PROSE declares, or `None` when it declares none.

    `None` covers three cases on purpose, because all three mean the same thing to
    a resume — there is no head this record can be held to: a record that names
    none, a record naming something that is not a full sha, and a record naming
    two different ones. The caller refuses in each, rather than resuming on a tree
    no record describes.
    """
    found: set[str] = set()
    fence: str | None = None
    for line in body.splitlines():
        delimiter = _FENCE.match(line)
        if delimiter is not None:
            fence = _fence_after(fence=fence, delimiter=delimiter.group(1))
            continue
        if fence is not None:
            continue
        sha = _declared_sha(line=line)
        if sha is not None:
            found.add(sha)
    return found.pop() if len(found) == 1 else None


def resumed_at_for_verdict(*, verdict: str) -> str:
    """The stage one factory verdict implies, for the factory-lost-the-run fallback.

    An unrecognised verdict answers `proof_capture`, which is the clause's
    "no such record" value: the run published nothing a later stage could build
    on, so capture is the first stage with work left to do.
    """
    return _RESUMED_AT_BY_VERDICT.get(verdict, RESUMED_AT_PROOF_CAPTURE)


def resume_anchor(
    *, records: Sequence[ProofRecord], executing_node: str | None
) -> ResumeAnchor | None:
    """The anchor the LATEST factory record on a pull request provides, or `None`.

    LATEST rather than "the newest one that happens to carry a head": the clause
    names the latest record as the anchor, so a headless newest record is the
    whole answer and an older headed one must not stand in for it. Resuming from
    the older record's head would enter a stage whose own evidence was published
    on a tree the run has since moved past.

    `executing_node` is the factory's answer and outranks the verdict fallback
    whenever the factory still holds the run, because it names the node the run
    died inside rather than the last one that published.
    """
    factory = [one for one in records if one.verdict in FACTORY_RECORD_VERDICTS]
    if not factory:
        return None
    latest = factory[-1]
    head = published_head(body=latest.body)
    if head is None:
        return None
    if executing_node is not None:
        return ResumeAnchor(
            record=latest, head=head, resumed_at=executing_node, source=SOURCE_FACTORY_RUN
        )
    return ResumeAnchor(
        record=latest,
        head=head,
        resumed_at=resumed_at_for_verdict(verdict=latest.verdict),
        source=SOURCE_LATEST_RECORD,
    )


def _declared_sha(*, line: str) -> str | None:
    """The sha one labelled prose line declares, or `None` for any other line."""
    stripped = line.strip()
    prefix = f"{PUBLISH_HEAD_LABEL}:"
    if not stripped.casefold().startswith(prefix.casefold()):
        return None
    value = stripped[len(prefix) :].strip().strip("`").casefold()
    return value if _FULL_SHA.match(value) is not None else None


def _fence_after(*, fence: str | None, delimiter: str) -> str | None:
    """The open fence after one delimiter line, or `None` outside a fence.

    The OPEN delimiter is carried rather than a boolean for the reason
    `_dispatcher_proof_record` records: CommonMark closes a fence only on its own
    character with at least as long a run, and a record legitimately nests one
    fence inside another, so a boolean inverts on that line and stays inverted —
    after which every remaining line reads as fenced and a genuine head
    declaration below the proof is never seen.
    """
    if fence is None:
        return delimiter
    if delimiter[0] == fence[0] and len(delimiter) >= len(fence):
        return None
    return fence
