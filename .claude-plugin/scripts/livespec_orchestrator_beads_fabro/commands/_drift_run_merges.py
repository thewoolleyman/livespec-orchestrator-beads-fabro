"""The default-branch merges after one frontier, and each merge as git records it.

The ONE account of two things the drift run and the drift-staleness fact both
depend on: WHICH ref the default branch is, and WHICH range "after the
frontier" names. Both were private to `_needs_attention_detection_staleness`
until the drift run needed them too, and a second copy is the shape that
matters here — the detection coverage-record contract requires the fact to name
"the merges after the frontier" and the run to enumerate "every default-branch
merge after the recorded frontier", so the two naming different populations
would make the fact report a number the run never acted on, with nothing
announcing the divergence.

The two READINGS of that one range stay separate and bounded: the fact asks git
for a COUNT and the run asks for the LIST. Neither is derivable from the other
more cheaply than asking, and a list read on the fact's path would put an
unbounded listing inside an interactive inbox render for a figure it renders as
one integer.

MERGE COUNTING EXCLUDES NOTHING SILENTLY — the contract's own words, and the
reason `merges_after` passes no `--merges`, no `--first-parent` and no path
filter. Under this repository's rebase-merge discipline a landed pull request
appears on the default branch as its REBASED SERIES rather than as one merge
commit, so a filter on merge commits would enumerate almost nothing while
reporting a clean empty answer, and the run would advance its frontier over
merges it never judged.

EVERY ARM FAILS SOFT ONTO `None`, and `None` is never an empty answer. A clone
whose `refs/remotes/origin/HEAD` is unset, or a `git` invocation that does not
answer, has not told us there are no merges — it has told us nothing. An empty
TUPLE is the real answer for a frontier that is already the branch head, and
the drift run owes those two opposite treatments: nothing to judge is a
complete pass, while a reading that could not be taken must leave the previous
frontier standing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._drift_run_findings import MergeUnderJudgement

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "GIT_TIMEOUT_SECONDS",
    "default_branch_ref",
    "merge_range",
    "merge_under_judgement",
    "merges_after",
]

GIT_TIMEOUT_SECONDS = 30.0


def default_branch_ref(*, project_root: Path, runner: CommandRunner) -> str | None:
    """The local `origin/<default>` ref, resolved WITHOUT touching the forge.

    Deliberately not `resolve_default_branch`, whose second route shells out to
    `gh repo view`. That route is right for a dispatch preflight, which is
    already talking to the forge and can afford a network round trip; it is
    wrong for both callers here. One runs inside every `needs-attention`
    composition — an interactive operator surface — so a forge call would put
    an unbounded network wait in front of an inbox render on behalf of one
    fact; the other runs on the root reconcile timer every ten minutes. A clone
    whose `refs/remotes/origin/HEAD` is unset simply yields nothing.
    """
    result = runner.run(
        argv=["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        cwd=project_root,
        timeout_seconds=GIT_TIMEOUT_SECONDS,
    )
    resolved = result.stdout.strip()
    if result.exit_code != 0 or resolved == "":
        return None
    return resolved


def merge_range(*, since: str | None, ref: str) -> str:
    """The revision range "after the frontier", or the whole branch with none.

    An absent frontier is the state of a repository on which no drift pass has
    ever completed, and there every merge is unaccounted for — so the range is
    the ref itself rather than an empty one.
    """
    return f"{since}..{ref}" if since else ref


def merges_after(
    *, project_root: Path, runner: CommandRunner, since: str | None
) -> tuple[str, ...] | None:
    """Every default-branch commit after `since`, OLDEST FIRST, or None unread.

    Oldest first is the contract's "in merge order", and it is what makes the
    frontier contiguous: a pass that judged newest-first would file the newest
    merge's proposal while an earlier merge still blocked the frontier, so the
    run would spend a model call and a proposal on work the coverage point
    cannot yet account for.
    """
    ref = default_branch_ref(project_root=project_root, runner=runner)
    if ref is None:
        return None
    result = runner.run(
        argv=["git", "rev-list", "--reverse", merge_range(since=since, ref=ref)],
        cwd=project_root,
        timeout_seconds=GIT_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return None
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def merge_under_judgement(
    *, project_root: Path, runner: CommandRunner, sha: str
) -> MergeUnderJudgement | None:
    """One merge's subject and diff, read in a single `git show`, or None unread.

    ONE read rather than two, because a subject and a diff taken by separate
    invocations can describe different commits if the ref moved between them —
    and the statement the judgement is asked about would then pair one merge's
    words with another's change.
    """
    result = runner.run(
        argv=["git", "show", "--no-color", "--no-ext-diff", "--format=%s", sha],
        cwd=project_root,
        timeout_seconds=GIT_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return None
    subject, _, diff = result.stdout.partition("\n")
    return MergeUnderJudgement(sha=sha, subject=subject.strip(), diff=diff)
