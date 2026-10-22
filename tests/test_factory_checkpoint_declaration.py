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

v165 ADDED ONE MORE NODE AND THE SENTENCE ABOVE PROVED TOO PESSIMISTIC, which is
worth recording rather than quietly editing: the implement stage's completion
gate (Scenario 204, work-item bd-ib-ahxcjx) is one file read declared DOWNWARD
at 600 s, and it sits on `implement`'s single fallthrough rather than on any
cycle, so the derivation bills it at that turn's two attempts and no other
node's count moves. Measured against THIS tree: 1314075 at the retired `"15m"`
and 844275 shipped, so the BOUND DOES NOT MOVE and the headroom narrows from
37420 to 35725 seconds. The warning stands for the node after this one — a new
node on a cycle, or one whose work is a turn rather than a read, has nowhere
left to be absorbed.

v175's RECAPTURE ROUTE WAS THAT NODE, IT CROSSED A CEILING NO CASE HERE HELD,
AND THAT IS WHY A THIRD FIGURE IS PINNED BELOW (work-item bd-ib-qnokup, which
re-lands the prompt-only half of the reverted change). The route added
`review -> recapture_route -> proof_capture -> review`, a third cycle through
the proof loop, and the derivation billed `proof_capture`, `review`,
`proof_verify` and `proof_grade` one more visit each per lap it admitted:
906555 seconds shipped. Every case in this module still passed, because the one
inequality they assert is against a BOUND this repository chooses, and the
remedy for crossing a bound is to move it -- which is what that change did,
to 940000. What it actually crossed is a ceiling this repository does NOT
choose: 864000 seconds, the lifetime of a FRESH Codex credential, so under
that graph the freshness gate could refuse a dispatch holding a
just-renewed token and no raised bound could ever buy it back. The change was
reverted in full (PR 3416, released v0.229.3) and the bound is back at 880000.

v177 RETIRED THE WHOLE RACE, AND EVERY FIGURE HERE CHANGED MEANING WITH IT
(work-item bd-ib-2oxr6v). The worker's maximum run budget is now the SMALLER of
the execution allowance this module measures and the bounded credential-use
window -- `dispatcher.credential_queue_allowance_seconds` plus the resolved
whole-run wall budget, 86400 + 21600 = 108000 seconds for this repository -- so
the freshness gate demands 111600 seconds whatever the graph costs. A ratified
graph change can no longer price a fresh credential out of a dispatch, which is
the defect v175 hit and the reason the route was reverted.

WHAT THAT DOES TO THE THREE CASES BELOW IS NOT UNIFORM, and reading it as "the
ceiling no longer binds" would quietly retire the only guard that ever caught
the real defect. Two separate relations are now asserted, against two different
figures:

* The CHECKPOINT BUDGET moves the EXECUTION ALLOWANCE and nothing else. So the
  bound and its retired-`"15m"` control are measured against
  `execution_allowance_seconds`, not against the required lifetime -- which,
  being window-governed, is 111600 at `"5m"` AND at `"15m"` and therefore
  discriminates nothing. Re-measured against this tree, which carries the
  RE-LANDED recapture route: 902955 shipped and 1415955 at the retired `"15m"`,
  so the bound moves to 1000000 between them, with 97045 seconds of headroom.
  Both figures are now the allowance itself rather than the allowance plus the
  margin, which is why they do not match the pre-v177 readings by 3600.
* The CREDENTIAL CEILING is graded against the REQUIRED LIFETIME, which is what
  the gate demands of a token, and it stays exactly as it was: a shipped payload
  asking more than a freshly renewed credential carries is refusable on a token
  minted moments earlier.

AND THE ROUTE v175 ADDED IS BACK IN THIS TREE, which is what the smaller-of-two
rule was ratified for. `review -> recapture_route -> proof_capture -> review` is
a third cycle through the proof loop, so the derivation bills `proof_capture`,
`review`, `proof_verify` and `proof_grade` one more visit each per lap it
admits, and the allowance is 902955 seconds -- the figure whose 906555-second
requirement priced a freshly renewed credential out of every Codex dispatch
before v177. Under the bounded window that same graph requires 111600 seconds,
which a fresh credential clears with 752400 to spare. The route's own node is
declared DOWNWARD at 600 s in `.livespec.jsonc` like the two route nodes before
it, and its `max_visits` is the EXACT bound the contract admits -- three
verdicts, not the grade route's bound-plus-one -- because a fourth admitted
visit here would buy a fourth visit of each of those four nodes.

AND THE CEILING CASE IS HONEST ABOUT ITS OWN REACH, which is the half worth
stating rather than leaving a reader to infer. With the window at 108000 no
graph change can carry the required lifetime past 864000 -- so that case can no
longer fail from a widened graph, and claiming it still guards one would be an
instrument reported as pointed where it is not. What CAN still fail it is a
raised window: `dispatcher.credential_queue_allowance_seconds` plus the wall
budget above 860400 seconds puts the requirement past a fresh credential again,
and that is a committed-configuration edit this repository can make. The case
therefore guards the configuration rather than the graph, and the EXACT pin on
the allowance is what keeps a graph widening from passing unremarked: it fails
and forces a re-measurement, which is the step that was skipped in v175.

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

# The bound the EXECUTION ALLOWANCE has to sit under, and the allowance the
# RETIRED `"15m"` resolved. Measured against the ALLOWANCE rather than the
# required lifetime since v177: the checkpoint budget moves the allowance and
# the required lifetime is window-governed, so a required-lifetime comparison
# reads 111600 at both budgets and discriminates nothing. The bound is
# deliberately looser than the measured 840675 this budget yields, because the
# allowance also sums the resolved node timeouts and pinning it here as well
# would make every unrelated timeout edit fail this case; the control pins the
# 15m figure exactly, because that one is the thing being moved away from and a
# drifting comparand would hide the move.
_ALLOWANCE_BOUND_SECONDS = 1_000_000
_ALLOWANCE_AT_THE_RETIRED_FIFTEEN_MINUTES = 1_415_955

# The execution ALLOWANCE the shipped payload resolves, the lifetime the
# freshness gate actually demands of a credential, and the lifetime of a FRESH
# Codex credential. Unlike the bound above, none of these is this repository's to
# choose freely: the first is what the graph in this tree costs, the second is
# what the smaller-of-two rule derives from it and the committed window, and the
# third is what the host mints at renewal -- so their relation is a fact about
# whether a dispatch can run at all rather than a threshold anyone may move. The
# allowance is pinned EXACTLY for the reason the docstring gives: a loose
# comparand is what let v175's widened graph cross the credential ceiling while
# every case here still passed, and an exact pin forces the re-measurement that
# was skipped.
_SHIPPED_EXECUTION_ALLOWANCE_SECONDS = 902_955
_SHIPPED_FRESHNESS_REQUIREMENT_SECONDS = 111_600
_FRESH_CODEX_CREDENTIAL_LIFETIME_SECONDS = 864_000


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


def test_the_checkpoint_budget_holds_the_execution_allowance_under_the_bound(
    tmp_path: Path,
) -> None:
    """The shipped declaration resolves an execution allowance under the bound.

    THE ALLOWANCE IS THE SUBJECT AND NOT THE REQUIRED LIFETIME, since v177. The
    checkpoint budget enters the allowance three times per attempt and moves
    nothing else; the required lifetime is the smaller of that allowance and the
    bounded credential-use window, and the window governs for this repository --
    so a required-lifetime comparison reads 111600 at `"5m"` and 111600 at
    `"15m"` and could not fail however large the budget grew. Grading the
    allowance keeps this case about the declaration it was written for.

    WHY THE CONTROL IS THE LOAD-BEARING HALF. The allowance also sums the
    resolved node timeouts, the visit caps and the retry budgets, so a bare
    inequality would be satisfied by a graph that happened to shrink -- a pass
    earned by something this item never touched. The control re-resolves the SAME
    payload with only the checkpoint budget restored to the retired `"15m"` and
    requires it to land ABOVE the bound at exactly the measured figure named
    above, which is what makes the first assertion evidence about this
    declaration rather than about the graph.

    The replacement is asserted to match exactly once before it is applied: a
    `str.replace` that matched nothing would leave the control resolving the
    shipped value and reporting agreement with itself.
    """
    resolved = resolve_credential_lifetime_requirement(repo=_REPO_ROOT)
    assert hasattr(resolved, "execution_allowance_seconds"), resolved
    assert resolved.execution_allowance_seconds < _ALLOWANCE_BOUND_SECONDS

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
    assert hasattr(retired, "execution_allowance_seconds"), retired
    assert retired.execution_allowance_seconds == _ALLOWANCE_AT_THE_RETIRED_FIFTEEN_MINUTES
    assert retired.execution_allowance_seconds > _ALLOWANCE_BOUND_SECONDS


def test_the_shipped_freshness_requirement_fits_a_fresh_codex_credential() -> None:
    """The gate asks 111600 seconds of a credential; a fresh one carries 864000.

    This is the case the module was missing when v175 widened the graph. Every
    other case here compares against `_ALLOWANCE_BOUND_SECONDS`, a threshold
    this repository chooses -- so a graph costing more than a credential can ever
    hold passes them all, and the honest-looking remedy is to raise the bound,
    which is exactly what the reverted change did on its way past 864000.

    So the comparand here is the CREDENTIAL, not a bound. A fresh Codex access
    token is minted with a ten-day life and the freshness gate demands the
    resolved requirement of a token's REMAINING life, so a dispatch asking more
    than 864000 seconds is refusable on a token minted moments earlier and no
    bound in this repository can admit it.

    WHAT THIS CASE CAN AND CANNOT FAIL ON, stated rather than implied, because
    an instrument reported as pointed where it is not is worse than none. Since
    v177 the required lifetime is the smaller of the execution allowance and the
    bounded credential-use window, and the window governs here -- so a widened
    GRAPH can no longer carry this figure past the ceiling, and this case would
    not catch one. What still fails it is a raised WINDOW: the committed
    `dispatcher.credential_queue_allowance_seconds` plus the resolved whole-run
    wall budget above 860400 seconds puts the requirement past a fresh
    credential again. The graph is guarded instead by the exact allowance pin
    below, which fails on any derivation move and forces the re-measurement v175
    skipped.

    Three figures are asserted, and each closes a lane the others leave open.
    The exact REQUIRED lifetime pins what the gate demands; the exact
    ALLOWANCE pins what the graph costs, so a widening cannot pass unremarked
    behind a window that absorbs it; and the inequality states the relation the
    demanded figure has to keep. An inequality alone would pass for any
    configuration under the ceiling, including one that had silently consumed
    the whole margin.
    """
    resolved = resolve_credential_lifetime_requirement(repo=_REPO_ROOT)

    assert hasattr(resolved, "required_seconds"), resolved
    assert resolved.required_seconds == _SHIPPED_FRESHNESS_REQUIREMENT_SECONDS, (
        f"the shipped payload resolves {resolved.required_seconds} seconds, not the pinned "
        f"{_SHIPPED_FRESHNESS_REQUIREMENT_SECONDS}: re-measure the derivation against this "
        f"tree, record the move in this module's docstring, and check the new figure against "
        f"the {_FRESH_CODEX_CREDENTIAL_LIFETIME_SECONDS}-second fresh-credential lifetime "
        f"before choosing any bound"
    )
    assert resolved.execution_allowance_seconds == _SHIPPED_EXECUTION_ALLOWANCE_SECONDS, (
        f"the shipped graph costs {resolved.execution_allowance_seconds} seconds, not the "
        f"pinned {_SHIPPED_EXECUTION_ALLOWANCE_SECONDS}: re-measure it, record the move in "
        f"this module's docstring, and check it against the "
        f"{_FRESH_CODEX_CREDENTIAL_LIFETIME_SECONDS}-second fresh-credential lifetime so a "
        f"widening cannot pass behind a credential-use window that happens to absorb it"
    )
    assert resolved.required_seconds <= _FRESH_CODEX_CREDENTIAL_LIFETIME_SECONDS, (
        f"this dispatch asks {resolved.required_seconds} seconds of usable credential "
        f"lifetime, more than the {_FRESH_CODEX_CREDENTIAL_LIFETIME_SECONDS} a freshly minted "
        f"Codex credential carries, so the freshness gate can refuse a dispatch holding a "
        f"just-renewed token and no bound in this repository can admit it"
    )
