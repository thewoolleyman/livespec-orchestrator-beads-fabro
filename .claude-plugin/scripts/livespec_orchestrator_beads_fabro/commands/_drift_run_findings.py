"""What ONE default-branch merge states, as the drift run puts it to the judgement.

PURE, and the leaf of the drift-run family: `_drift_run_merges` reads a merge
out of git into the `MergeUnderJudgement` value declared here, and
`behaviour_statement` is what the shared spec-stated judgement is then asked
about. The whole of the drift run's reading of a merge lives in these two
names, so a change to what "the behaviour a merge adds" means is one edit
rather than one per consumer.

ONE STATEMENT PER MERGE, and that is a decision rather than a simplification.
`livespec_runtime.spec_stated.judge` judges ONE behaviour statement and returns
ONE verdict; the detection coverage-record contract asks for the drift pass to
be run "over each merge's diff" and for a proposal per `partial` or `unstated`
behaviour the merge adds. A pass that first asked a model to ENUMERATE the
behaviours in a diff and then judged each one would double the model calls on a
primitive the root reconcile timer fires every ten minutes, and it would need a
second prompt the shared judgement does not define — so the two would drift
apart, each returning plausible verdicts about different behaviours. The merge
is therefore put as it records itself: its subject, its identity and its own
diff, which is exactly what Scenario 207's first case describes ("one later
default-branch merge whose diff adds a behaviour the spec-stated judgement
reports unstated").

THE DIFF EXCERPT IS BOUNDED, and the bound is not a precaution against large
merges but against a prompt no model would read whole. The judge prompt already
carries the entire ratified tree — 1.36 MB in this repository, measured
2026-10-22 — so a merge diff appended to it unbounded buys context nobody
reads while pushing the judgement's own subject past whatever the model
truncates at, silently. A truncated excerpt SAYS SO in the statement, because
an excerpt that ended mid-hunk with no marker reads to the judge as a diff that
genuinely stops there, and a verdict about half a change is a verdict about a
behaviour the merge does not add.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_runtime.spec_stated import SpecStatedVerdict

__all__: list[str] = [
    "DIFF_EXCERPT_CHARACTERS",
    "FINDING_IDENTITY_PREFIX",
    "FINDING_KINDS",
    "DriftFinding",
    "MergeUnderJudgement",
    "behaviour_statement",
    "finding_identity",
    "findings_from_verdict",
]

# Generous enough to carry an ordinary slice whole, small enough that the
# statement stays a minority of a prompt whose spec tree is already enormous.
DIFF_EXCERPT_CHARACTERS = 20_000

# The two verdict kinds that ARE findings. `stated` is not one: the ratified
# text already states the behaviour, so a proposal for it would propose a
# change nobody needs — and filing on every verdict is the failure mode that
# looks most like a thoroughly working pass.
FINDING_KINDS = ("partial", "unstated")

# Domain separation on the digest, and a prefix a reader of a proposal's front
# matter can recognise the KIND of identity by without consulting anything.
FINDING_IDENTITY_PREFIX = "drift"

_TRUNCATION_MARKER = "\n[diff excerpt truncated at {limit} characters]\n"
_IDENTITY_HEX = 16
_IDENTITY_DOMAIN = b"livespec-drift-finding-v1\x00"


@dataclass(frozen=True, kw_only=True)
class MergeUnderJudgement:
    """One default-branch merge, as the drift run reads it out of git.

    `subject` is the merge's own one-line subject and `diff` is its patch with
    that subject line removed, so the two can be rendered separately without
    either being re-derived from the other.
    """

    sha: str
    subject: str
    diff: str


def behaviour_statement(*, merge: MergeUnderJudgement) -> str:
    """The behaviour statement the spec-stated judgement is asked about.

    Carries the merge's identity as well as its content, because the finding
    identity is derived from this statement and from the merge: two merges
    whose diffs happened to be identical must not share one identity, or the
    second would read as a duplicate of the first and file nothing.
    """
    truncated = len(merge.diff) > DIFF_EXCERPT_CHARACTERS
    marker = _TRUNCATION_MARKER.format(limit=DIFF_EXCERPT_CHARACTERS) if truncated else ""
    return (
        f"The behaviour that default-branch merge {merge.sha} adds, whose subject "
        f"reads {merge.subject!r}, as its own diff records it:\n\n"
        f"{merge.diff[:DIFF_EXCERPT_CHARACTERS]}{marker}"
    )


@dataclass(frozen=True, kw_only=True)
class DriftFinding:
    """One `partial` or `unstated` behaviour a merge adds.

    `identity` is the STABLE finding identity the contract asks for, derived
    from the merge and the behaviour so that a retried pass recognises its own
    earlier filing rather than filing a second proposal under a second name.

    `generalization_target` is the one existing heading whose generalization
    would state the behaviour, or None when the judgement found none — which is
    a real answer and not a missing one, so the finding is still filed and the
    proposal says outright that no existing heading generalizes to it.
    """

    merge: str
    kind: str
    generalization_target: str | None
    statement: str
    rationale: str
    identity: str


def finding_identity(*, merge: str, behaviour: str) -> str:
    """The stable identity of ONE finding, derived from the merge and behaviour.

    BOTH inputs, which is what the contract asks for and what keeps two merges
    apart: a digest over the behaviour alone would collapse two merges whose
    diffs happen to be identical onto one identity, and the second merge's
    behaviour would then read as a duplicate and never be proposed. A digest
    over the merge alone would do the mirror damage, folding every behaviour one
    merge adds into one finding.
    """
    digest = hashlib.sha256(
        _IDENTITY_DOMAIN + merge.encode("utf-8") + b"\x00" + behaviour.encode("utf-8")
    )
    return f"{FINDING_IDENTITY_PREFIX}-{digest.hexdigest()[:_IDENTITY_HEX]}"


def findings_from_verdict(
    *, merge: str, statement: str, verdict: SpecStatedVerdict
) -> tuple[DriftFinding, ...]:
    """The findings one judged merge carries: one per non-`stated` verdict, else none."""
    if verdict.kind not in FINDING_KINDS:
        return ()
    return (
        DriftFinding(
            merge=merge,
            kind=verdict.kind,
            generalization_target=verdict.generalization_target,
            statement=statement,
            rationale=verdict.rationale,
            identity=finding_identity(merge=merge, behaviour=statement),
        ),
    )
