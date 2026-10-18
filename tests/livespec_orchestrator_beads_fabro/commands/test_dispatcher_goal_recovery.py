"""What a seeded dispatch's goal brief tells its agent about the tree it starts on.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work": "The new sandbox MUST check out
the recorded SHA, and the goal brief MUST name that commit as an interrupted prior
attempt whose current state the agent inspects before continuing."

WHY THE BRIEF IS LOAD-BEARING AND NOT A COURTESY. A seeded sandbox is placed on a
commit the agent never made, carrying work nobody reviewed and nobody graded —
and the placement is SILENT. Measured 2026-10-16 on this repository's own
`bd-ib-26deyw`, a plain re-dispatch after a provider-limit ending started from
master and discarded about eighty minutes of implement work, which is the loss
the seed exists to prevent; an agent handed that tree with no account of it is
one commit away from the mirror failure, trusting a half-finished tree as a
reviewed baseline or starting over on top of it. The prepare step puts the tree
there and this section says what it is, so the two belong together.

WHY A RESUME IS THE CONTROL RATHER THAN A SECOND POSITIVE. A `resume` route
carries `resume_head` and NO `resume_fetch_ref`: its tree is the published head of
its own pull request, entered at the node it stopped at, and it is that dispatch's
own continuation rather than somebody else's interrupted attempt. Only the SEEDED
route carries both attributes, and the clause attaches this requirement to the
seed. So the presence of BOTH is the discriminator, and a build keyed on the head
alone would narrate every resume as an interrupted attempt to be inspected —
telling a run finishing its own publication to go and audit it first.

WHAT THE WIRING CASE DOES AND DOES NOT ESTABLISH. The brief's assembly is
exercised directly; the final case reads the ONE call site that renders a
dispatch's brief and asserts, structurally, that it passes this section through.
That binds the two ends together — a section nothing passed is a section no
dispatch ever sees, and an absent attribute resolves silently to a plain brief
with nothing in the output saying so. It is NOT a measurement of a live dispatch,
which belongs to the integration tier.
"""

from __future__ import annotations

import argparse
import ast
import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _dispatcher_goal as goal
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_goal_recovery"
_COMMANDS = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_MODULE_PATH = _COMMANDS / "_dispatcher_goal_recovery.py"
_LOOP_PATH = _COMMANDS / "_dispatcher_loop.py"

_ITEM_ID = "bd-ib-kn7ktk"
_BRANCH = f"feat/{_ITEM_ID}"
_REPO = Path("/data/projects/livespec-orchestrator-beads-fabro")

# The seeded placement: the commit the dead run preserved, and the ref it lives
# on. They are the two attributes `_dispatcher_recovery_launch` sets for a
# `seeded` route and the two `resume_checkout_prepare_steps_block` renders the
# sandbox's own fetch-and-checkout from.
_PRESERVED_COMMIT = "216c811200000000000000000000000000000002"
_PRESERVATION_REF = "refs/heads/needs-human/01M52R2WND7Y0000000000000Z"

# What a resume carries instead: the published head of its own pull request, and
# the node it re-enters at. No fetch ref, because that head is on the publish
# branch by construction.
_PUBLISHED_HEAD = "db9feb3900000000000000000000000000000001"
_ENTRY_NODE = "proof_capture"


def _recovery_module() -> Any:
    """The module under test, reached only after its path is established.

    The import is inside the body and the path assertion precedes it, which is
    what makes this module's Red a genuine assertion about an absent file rather
    than a collection error that proves only unimportability.
    """
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        # NEITHER field may carry the word this module's negative case searches
        # for: a fixture that spelled it would satisfy that case from the item's
        # own prose and so could never fail, which is exactly the instrument that
        # cannot return a hit.
        title="A seeded re-dispatch onto preserved work",
        description="Continue from the preserved tree.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _brief(*, args: argparse.Namespace | None) -> str:
    """One item's rendered brief, with or without a recovery placement."""
    module = _recovery_module()
    attempt = None if args is None else module.interrupted_attempt_for(args=args)
    return goal.render_goal(item=_work_item(), repo=_REPO, branch=_BRANCH, interrupted=attempt)


def _seeded_args() -> argparse.Namespace:
    return argparse.Namespace(resume_head=_PRESERVED_COMMIT, resume_fetch_ref=_PRESERVATION_REF)


def _render_goal_keywords() -> tuple[str, ...]:
    """The keyword names the dispatch path's one `render_goal` call passes.

    Read from the parsed source rather than matched as text, so the answer cannot
    be a pattern that happened not to fit the formatting the call is written in —
    the "instrument that cannot return a hit" failure this repository's own
    AGENTS.md catalogues.
    """
    tree = ast.parse(_LOOP_PATH.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "render_goal"
    ]
    assert len(calls) == 1
    return tuple(keyword.arg for keyword in calls[0].keywords if keyword.arg is not None)


def test_a_seeded_placement_is_named_in_the_brief_as_an_interrupted_prior_attempt() -> None:
    """The commit, the ref it was fetched from, what it is, and what to do with it.

    Four separate claims, because a brief that named the commit without saying
    whose work it is reads as a baseline, and one that said "interrupted" without
    directing the agent to inspect it leaves the clause's own instruction
    unstated.
    """
    brief = _brief(args=_seeded_args())

    assert _PRESERVED_COMMIT in brief
    assert _PRESERVATION_REF in brief
    assert "interrupted prior attempt" in brief.lower()
    assert "inspect its current state before continuing" in brief.lower()
    # The item's own brief is still whole: the section is an addition, not a
    # replacement for the fields every dispatch is briefed with.
    assert f"Work-item: {_ITEM_ID}" in brief
    assert f"Publish branch (push HEAD to this exact ref at the PR stage): {_BRANCH}" in brief


def test_a_resume_placement_leaves_the_brief_byte_identical_to_a_plain_dispatch() -> None:
    """A resume is finishing its OWN publication, so it has no attempt to audit.

    This is the discriminating case: a build keyed on `resume_head` alone passes
    the case above and then narrates every resumed run's own branch as an
    interrupted attempt whose state must be inspected first — which is both
    false and expensive, since the resumed run enters at the node it stopped at
    precisely because the nodes before it are already done.
    """
    resumed = argparse.Namespace(resume_head=_PUBLISHED_HEAD, resume_entry_node=_ENTRY_NODE)

    assert _brief(args=resumed) == _brief(args=None)


def test_an_ordinary_dispatch_carries_no_recovery_section_at_all() -> None:
    """No heading, no placeholder bleed-through, nothing a plain brief did not have.

    The positive control for the two cases above: a section that rendered
    unconditionally would satisfy the first and could not be told apart from a
    correct build by the second, because a resume's brief would then match a
    plain one's only by both being wrong.
    """
    module = _recovery_module()

    assert module.interrupted_attempt_for(args=argparse.Namespace()) is None
    assert module.interrupted_attempt_section(attempt=None) == ""
    assert "interrupted" not in _brief(args=None).lower()


def test_a_placement_whose_commit_or_ref_is_empty_narrates_nothing() -> None:
    """Both attributes must be present AND non-empty, or there is nothing to name.

    An empty head reaches `git checkout --detach ''`, which fails the run in
    preparation; a brief that had already told the agent to inspect commit `''`
    would be describing a placement that never happened.
    """
    module = _recovery_module()

    assert (
        module.interrupted_attempt_for(
            args=argparse.Namespace(resume_head="", resume_fetch_ref=_PRESERVATION_REF)
        )
        is None
    )
    assert (
        module.interrupted_attempt_for(
            args=argparse.Namespace(resume_head=_PRESERVED_COMMIT, resume_fetch_ref="")
        )
        is None
    )


def test_the_dispatch_paths_one_goal_render_passes_the_recovery_section() -> None:
    """The wiring, read off the parsed call rather than hoped for.

    A section no dispatch passes is a section no agent reads, and the failure is
    silent: `render_goal`'s parameter defaults to absent, so the brief renders
    exactly as it did before and nothing in the output says the placement went
    unnarrated. See this module's docstring for what this case does not claim.
    """
    assert "interrupted" in _render_goal_keywords()
