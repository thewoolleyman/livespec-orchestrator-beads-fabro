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

from dataclasses import dataclass

__all__: list[str] = [
    "DIFF_EXCERPT_CHARACTERS",
    "MergeUnderJudgement",
    "behaviour_statement",
]

# Generous enough to carry an ordinary slice whole, small enough that the
# statement stays a minority of a prompt whose spec tree is already enormous.
DIFF_EXCERPT_CHARACTERS = 20_000

_TRUNCATION_MARKER = "\n[diff excerpt truncated at {limit} characters]\n"


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
