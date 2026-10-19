"""The run-branch checkpoint declaration of the shipped `implement-work-item` payload.

WHAT THIS BINDS, AND WHY IT IS A TEST RATHER THAN A COMMENT. The engine
checkpoints the run branch between nodes, and `[run.checkpoint]` is where this
repository tells it how. Both keys here were set the other way until 2026-10-12,
with a rationale written in the file itself, and the setting that rationale chose
killed 27 hp runs between 2026-10-09 and 2026-10-12: the checkpoint commit ran
this repository's pre-commit aggregate, and a node that ended with an
unfinished tree -- a coverage gate still red, a Red awaiting its Green -- turned
a REPAIRABLE tree into run death at `workflow_error`. The measurement is
`plan/checkpoint-commit-hook-failures/research/001-measured-checkpoint-failures-2026-10-12.md`;
the ledger item is `bd-ib-jb53pu`.

So the declaration is asserted here, through a real TOML parse, because that is
what the engine reads and because a value reverted by a well-meaning edit would
otherwise announce nothing until runs started dying again.

WHY THE THIRD CASE EXISTS. `commit_timeout` is not a local choice: the Dispatcher
bills it THREE TIMES PER ATTEMPT into the credential-lifetime floor
(`_dispatcher_credential_requirement`, which reads it precisely because a
repository that raised it raises that cost threefold), and the Codex freshness
gate then demands that floor of a ten-day token. The old `"15m"` put the floor at
801525 seconds -- 9.28 days, which is most of a Codex token's whole life. The
case asserts the figure the shipped declaration now resolves AND re-resolves the
same payload at `"15m"` as its control, so the bound is proved to be cleared BY
this checkpoint budget rather than by some unrelated narrowing of the graph.

BOTH FIGURES MOVE WHEN THE GRAPH GAINS A NODE, and that is why they are stated
with the payload they were measured against rather than as constants of the
repository. Scripted publication (work-item `bd-ib-c3txja`) split the single
`pr` stage into `pr_refresh` and `pr`, so the requirement -- which sums the
resolved node timeouts, the visit caps and the retry budgets -- gained one more
attempt's worth of this budget: the 15m control moved from the 796830 seconds
measured against the single-`pr` graph to 801525, and the shipped 5m figure from
519630 to 522525. Neither move is a regression and neither is this case's
subject; re-measure both against the payload in the tree when a node timeout,
visit cap or retry budget changes, and re-check the shipped figure against the
bound while doing it. Raising the `janitor` node timeout from 3600 to 4340
(`bd-ib-qieqc6.2`) moved the 15m control to 808925 and the shipped 5m figure to
529925, which is still under the bound; 4340 was the largest janitor value that
stayed under the bound as it then stood.

The v134 refresh-repair route (`bd-ib-5guqmt`) moved both again, and by more
than any earlier edit: it adds the `refresh_repair` classifier AND widens
`fix.max_visits`, and `fix` is the node three other loops re-enter, so every
node a repair round re-earns gains visits with it. The 15m control moved to
958455 and the shipped 5m figure to 625455, so the bound moved to 650000 to
stay between the two measured figures, which is the relation this case asserts.
The ceiling that matters is unchanged: the shipped figure stays well inside a
ten-day token's life, and only the 15m control does not.

Completing that route for the second refreshing stage (`bd-ib-5oc2d3`) moved
both once more, and the mechanism is worth stating because it adds NO node and
changes NO attribute: `pr_refresh` now routes its failure through the shared
`refresh_repair` classifier, which gives that node a SECOND predecessor, and
the derivation sums a node's visits over its distinct predecessors. So the
classifier and everything the repair round re-earns gain visits from an edge
alone. The 15m control moved to 977235 and the shipped 5m figure to 637035 --
still under the 650000 bound, so the bound is unchanged and the relation this
case asserts still holds, with 12965 seconds of headroom. Two consequences to
carry forward rather than rediscover: the next edit that widens this graph is
likely to need the bound re-chosen between the two figures, and the shipped
figure plus `CODEX_FRESHNESS_MARGIN_SECONDS` now demands 640635 of a token's
remaining life, so a ten-day Codex token has to be under about 2.59 days old
to pass the freshness gate.

Budgeting the two PUBLICATION stages for an hour each (`bd-ib-xi63mq`,
Scenario 177 -- `publish_draft` and `pr_refresh` run this repository's declared
check suite inside a push hook) moves both again. This is a RE-MEASUREMENT
against the payload and the `.livespec.jsonc` in THIS tree, not a figure
carried over from the earlier attempt at this item: that attempt measured
555125 and 834125 against a tree whose `fix.max_visits` and `pr_refresh`
predecessor set predate v134 and v135, so neither of its figures survives
here. Measured now: 665835 seconds shipped and 1006035 at the retired `"15m"`,
so the bound moves to 680000 to stay between the two, with 14165 seconds of
headroom. That also retires the janitor reasoning two paragraphs above -- the
"largest value that stayed under the bound" was derived against the 530000
bound of that day rather than against a property of 4340 -- while the janitor
entry itself is untouched. The derived figure in the paragraph above moves with
it: the shipped figure plus `CODEX_FRESHNESS_MARGIN_SECONDS` now demands 669435
of a token's remaining life, so a ten-day Codex token has to be under about
2.25 days old to pass the freshness gate. The bound moving is not a relaxation
of the enforcement that matters: `credential_deadline_epoch` still caps every
run at the token's OBSERVED expiry minus its margin, and this figure is the
allowance a graph may ASK for, not a lifetime anything grants.

THAT PREDICTED RE-CHOOSING HAPPENED AT v145 (the `pr` to `pr_refresh` route,
work-item bd-ib-3hpdvm), and the mechanism is worth stating because the route's
own four nodes are the SMALL half of the move. The route makes `pr_refresh`
re-enterable, so its `max_visits` had to be sized at the entries the
three-refresh bound actually admits -- three counted refreshes, an uncounted
entry around each, and the entry that refuses, i.e. 8 rather than 4 -- and the
derivation then propagates those visits into every node of the proof loop the
refresh re-earns: `review` and `proof_verify` moved from 18 to 22 visits apiece,
`proof_capture` to 19, `refresh_repair` to 20. The figures below are measured
against a tree carrying BOTH that route AND the hour-each publication budget of
the paragraph above, because the two compound: the hour-each budget raises what
one `pr_refresh` visit costs and this route raises how many of those visits the
bound admits, so neither side's separately-measured figure survives the
integration. Measured against THIS tree: 1168170 at the retired `"15m"` and
768570 shipped, so the bound moves to 800000 to stay between them, with 31430
seconds of headroom. The derivation is an upper bound summed over distinct
predecessors and no run reaches it, which is the correct direction for a
credential floor.

IT HAPPENED AGAIN AT v156 (the per-assertion proof grade, work-item
bd-ib-kcq6pu), and this one is worth stating because both new nodes are CHEAP
and the move is large anyway. `proof_grade` is one `gh pr view` plus a
sub-second parse, and `proof_grade_route` is a `cat` of one counter file; what
makes them expensive is WHERE they sit. The grade is the single edge out of a
`verified` replay, so the derivation bills it at `proof_verify`'s own visit
count, and the route closes a CYCLE back into that replay, so it raises the
replay's count by its own `max_visits` and the replay is the most expensive
node in the graph at two attempts of 1800 s each. Both nodes are therefore
declared DOWNWARD in this repository's `.livespec.jsonc` at 600 s -- still three
times a generous budget for a forge read and a file read -- which is the gate's
own documented remedy ("a shorter configured timeout") applied to work that
genuinely takes seconds, and NOT a visit cap sized below what the graph can
reach. Measured against THIS tree with those declarations in place: 1310580 at
the retired `"15m"` and 842580 shipped, so the bound moves to 880000 to stay
between them, with 37420 seconds of headroom.

WHAT THAT COSTS, STATED RATHER THAN ABSORBED, and it is the tightest this figure
has been: the shipped figure plus `CODEX_FRESHNESS_MARGIN_SECONDS` now demands
846180 of a token's remaining life -- about 9.79 days -- so a ten-day Codex
token has to be under roughly 0.21 days old to pass the freshness gate. The next
widening of this graph will not be absorbable by declaring the new node's own
timeout downward: the remaining headroom is in `implement` (14400) and
`review_fix` (7200), which are measured against real turns, so the honest move
then is a credential-gate change rather than another bound.
This repository routes NO factory node to Codex (`.livespec.jsonc`'s `acp_nodes`
put every node on a Claude adapter), so nothing here is refused by it; a
repository that does route one and raises its node timeouts should expect that
gate to bite, and the remedy is the gate's own -- a shorter configured timeout
or a fresher credential -- not a visit cap sized below what the graph can reach.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement import (
    credential_lifetime_requirement_for,
    resolve_credential_lifetime_requirement,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PAYLOAD = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_SHIPPED_WORKFLOW = _PAYLOAD / "workflow.toml"

# The bound the freshness requirement has to sit under, and the figure the
# RETIRED `"15m"` resolved. The bound is deliberately looser than the measured
# 845475 seconds this budget yields: the requirement also sums the resolved node
# timeouts, so pinning it exactly would make every unrelated timeout edit fail
# this case. The control below pins the 15m figure exactly, because that one is
# the thing being moved away from and a drifting comparand would hide the move.
#
# BOTH FIGURES MOVE WHENEVER THE GRAPH GAINS A TIMED NODE, and that is the cost
# of pinning the control exactly rather than a defect in it. v165 added
# `implement_partial_progress` (work-item bd-ib-ahxcjx), one visit at the
# resolved default timeout, which raised the measured figure from 842580 and the
# 15m control from 1310580. Re-measure both through
# `resolve_credential_lifetime_requirement`; do NOT loosen the control into an
# inequality, which is what would hide the next move of the budget itself.
_FRESHNESS_BOUND_SECONDS = 880_000
_FRESHNESS_AT_THE_RETIRED_FIFTEEN_MINUTES = 1_315_275


def _checkpoint() -> dict[str, Any]:
    """The shipped `[run.checkpoint]` table, parsed as the engine parses it.

    `tomli`, not the stdlib `tomllib`: this suite runs on 3.10, where the stdlib
    module does not exist yet. Parsed rather than grepped because the property
    is the VALUE the engine resolves, and a line-shaped assertion would pass for
    a commented-out declaration.
    """
    import tomli

    document: dict[str, Any] = tomli.loads(_SHIPPED_WORKFLOW.read_text(encoding="utf-8"))
    checkpoint: dict[str, Any] = document["run"]["checkpoint"]
    return checkpoint


def test_the_run_branch_checkpoint_skips_this_repositorys_commit_hooks() -> None:
    """`skip_git_hooks` is true, so a checkpoint commit cannot be refused by a gate.

    The engine passes `--no-verify` to the checkpoint commit ONLY when this key
    is true (`sandbox_git.rs` on the deployed 0.254.0 build), so with it false
    every checkpoint re-runs the repository's pre-commit aggregate. That run is
    the THIRD of the same suite in one node cycle -- the janitor node runs the
    declared check suite after implement, and `publish_draft`'s pre-push runs the
    aggregate again -- and it is the only one of the three whose failure is fatal
    rather than routed into a fix loop.

    `is True` rather than a truthiness test: TOML's `1` and `"true"` are not
    booleans, and the engine's own deserializer would refuse them, so a case that
    accepted them would certify a configuration no run could load.
    """
    assert _checkpoint()["skip_git_hooks"] is True


def test_the_run_branch_checkpoint_budget_is_five_minutes() -> None:
    """`commit_timeout` is `"5m"`, which is a ceiling question, not a local one.

    Floor: the engine's stock thirty seconds destroyed completed work when a
    hook-free `git add` or `git commit` crossed it (ledger bd-ib-6ka), so the
    budget has to be generously above it. Ceiling: the Dispatcher bills this
    value THREE TIMES PER ATTEMPT into the credential-lifetime floor, and the
    case below is what holds that end.

    Five minutes is ten times the stock budget and ample for a hook-free stage
    and commit in a contended sandbox -- the hooks are what took minutes, and
    `skip_git_hooks` above has now removed them.
    """
    assert _checkpoint()["commit_timeout"] == "5m"


def test_the_checkpoint_budget_holds_the_credential_freshness_floor_under_the_bound(
    tmp_path: Path,
) -> None:
    """The shipped declaration resolves a freshness requirement under the bound.

    WHY THE CONTROL IS THE LOAD-BEARING HALF. The requirement sums the resolved
    node timeouts, the visit caps and the retry budgets as well as this
    checkpoint value, so a bare inequality would also be satisfied by a graph
    that happened to shrink -- a pass earned by something this item never
    touched. The control re-resolves the SAME payload with only the checkpoint
    budget restored to the retired `"15m"` and requires it to land ABOVE the
    bound at exactly the measured figure named above, which is what makes the
    first assertion evidence about this declaration rather than about the graph.

    The replacement is asserted to match exactly once before it is applied: a
    `str.replace` that matched nothing would leave the control resolving the
    shipped value and reporting agreement with itself.
    """
    resolved = resolve_credential_lifetime_requirement(repo=_REPO_ROOT)
    assert hasattr(resolved, "required_seconds"), resolved
    assert resolved.required_seconds < _FRESHNESS_BOUND_SECONDS

    copied = tmp_path / _PAYLOAD.name
    _ = shutil.copytree(_PAYLOAD, copied)
    committed = copied / _SHIPPED_WORKFLOW.name
    shipped_text = committed.read_text(encoding="utf-8")
    assert shipped_text.count('commit_timeout = "5m"') == 1, "the budget is not declared once"
    _ = committed.write_text(
        shipped_text.replace('commit_timeout = "5m"', 'commit_timeout = "15m"'), encoding="utf-8"
    )

    retired = credential_lifetime_requirement_for(
        committed=committed, block=dispatcher_block(cwd=_REPO_ROOT)
    )
    assert hasattr(retired, "required_seconds"), retired
    assert retired.required_seconds == _FRESHNESS_AT_THE_RETIRED_FIFTEEN_MINUTES
    assert retired.required_seconds > _FRESHNESS_BOUND_SECONDS
