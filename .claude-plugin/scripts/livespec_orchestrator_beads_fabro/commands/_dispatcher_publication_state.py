"""Where a run's publication stages keep the facts they hand each other.

WHAT THE STATE IS. `SPECIFICATION/contracts.md` section
"Definition-of-Done and Proof-of-Done stages" -> "Scripted publication and
proof-head integrity" requires `pr_refresh` to establish "the run's previously
published head from its recorded publication or validated resume provenance,
never from a stale local tracking ref", to bound repeated refreshes "to three
refreshes per run", and to route a CHANGED head back through capture. Those are
three facts no single command stage can hold, because each is written by one
stage and read by a later one:

- the PUBLISHED HEAD, written by `publish_draft` and rewritten by every
  successful refresh, read by `pr_refresh` as the lease target and by `pr` as
  what this run put on the branch;
- the REFRESH COUNT, read and written by `pr_refresh` alone, which is what
  makes the three-refresh bound a measured fact rather than a hope;
- the CHANGED MARKER, written by `pr_refresh` and read by `pr_refresh_head`,
  which is how a two-outcome command node expresses a three-way decision.

WHY IT LIVES IN THE RUN'S OWN GIT DIRECTORY, which is the whole design decision
here and the one a reader is most likely to mistake for an arbitrary choice.

`publish_draft` already keeps its needs-human reason file at
`git rev-parse --git-path livespec-needs-human-reason`, so the pattern is the
established one in this very graph: a path inside `$GIT_DIR` belongs to ONE
clone, survives a rebase and every stage boundary, and is not a predictable
name in a directory anything else writes.

The alternative — a fixed path under the system temp directory — fails on a
property specific to THIS stage. `pr_refresh` runs the repository-declared
`sandbox_check_suite` as its post-rebase gate, IN THE SAME SANDBOX, and this
repository's check suite executes the rendered publication scripts against real
Git as part of its own integration tier. At a fixed shared path that nested
execution reads, writes and deletes the live state of the very stage running it
— erasing the refresh counter mid-gate, which lets the next refresh restart at
one and evade the three-refresh bound the clause imposes. Anchoring the state to
`$GIT_DIR` makes that impossible by CONSTRUCTION rather than by careful
bookkeeping: a nested execution runs in its own throwaway repository, so it
resolves its own directory and cannot name the enclosing run's.

The state is therefore per CLONE, which is per sandbox, which is per run — and
that is why "the three-refresh bound starts at zero for each resumed run" is a
property of the container rather than a rule anything has to remember.
"""

from __future__ import annotations

__all__: list[str] = [
    "PUBLICATION_STATE_GIT_PATH",
    "PUBLISH_HEAD_STATE_FILENAME",
    "REFRESH_CHANGED_STATE_FILENAME",
    "REFRESH_COUNT_STATE_FILENAME",
    "REFRESH_REPAIR_BRIEF_STATE_FILENAME",
    "REFRESH_REPAIR_COUNT_STATE_FILENAME",
    "publication_state_filenames",
    "publication_state_root_command",
]

# The directory's name RELATIVE TO `$GIT_DIR`. Resolved by git rather than
# joined onto a path this module guesses: `$GIT_DIR` is `.git` in an ordinary
# clone and a file-pointer indirection in a worktree, and `--git-path` is the
# one answer that is correct in both.
PUBLICATION_STATE_GIT_PATH = "livespec-publication"

PUBLISH_HEAD_STATE_FILENAME = "livespec-publish-head"
REFRESH_COUNT_STATE_FILENAME = "livespec-pr-refresh-count"
REFRESH_CHANGED_STATE_FILENAME = "livespec-pr-refresh-changed"

# The two REFRESH-REPAIR facts (v134 "Refresh repair" and "Refresh-repair
# accounting"), which are the same kind of hand-off as the three above: each is
# written by one stage and read by another.
#
# The BRIEF is written by whichever refreshing stage restored its pre-refresh
# head, and read by the `refresh_repair` classifier that routes on its presence
# and by the `fix` turn that works from its contents. Its PRESENCE is the signal
# and not merely its contents, which is why the writing stages delete it on
# entry: a brief left behind by an earlier round would route a later
# unrepairable failure — an authentication refusal, an unreachable origin — into
# the fix loop instead of to the human it belongs to.
#
# The COUNT is read and written by both refreshing stages, which is what makes
# the two-round budget a measured fact rather than a hope. It is deliberately
# SEPARATE from `REFRESH_COUNT_STATE_FILENAME`: that one bounds `pr_refresh`'s
# non-convergence at three refreshes of its own, while this one bounds repair
# rounds across BOTH stages at two, and the accounting paragraph moves them
# independently.
REFRESH_REPAIR_BRIEF_STATE_FILENAME = "livespec-refresh-repair-brief"
REFRESH_REPAIR_COUNT_STATE_FILENAME = "livespec-refresh-repair-count"


def publication_state_root_command() -> str:
    """The command every publication stage resolves the state directory through.

    Spelled here rather than at each of the four call sites, because a stage
    resolving a different directory than its predecessor would read an absent
    file and report it as absent provenance — a fail-closed refusal whose stated
    cause would be wrong.
    """
    return f"git rev-parse --git-path {PUBLICATION_STATE_GIT_PATH}"


def publication_state_filenames() -> tuple[str, ...]:
    """Every state filename, in the order the stages first write them.

    A tuple rather than three separate reads because the one caller that needs
    all three — a control asserting an execution boundary left the enclosing
    run's state intact — needs the COMPLETE set: a filename missing from that
    list is a file the control does not cover, and nothing about the resulting
    read would say so.
    """
    return (
        PUBLISH_HEAD_STATE_FILENAME,
        REFRESH_COUNT_STATE_FILENAME,
        REFRESH_CHANGED_STATE_FILENAME,
        REFRESH_REPAIR_BRIEF_STATE_FILENAME,
        REFRESH_REPAIR_COUNT_STATE_FILENAME,
    )
