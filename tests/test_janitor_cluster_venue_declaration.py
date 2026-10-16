"""This repository's own declared venue for its post-merge janitor check suite.

WHAT THIS BINDS, AND WHY IT IS A TEST RATHER THAN A COMMENT. The venue is read
from the governed repository's committed `.livespec.jsonc` at post-merge time,
so the declaration IS the behaviour: the module that acts on it is exercised
against fixture configs, and nothing else observes what THIS repository actually
says. The declaration is `host_local`, and it is written out rather than left to
silence so that an edit flipping it is a diff a reviewer can see; an absent key
is indistinguishable from a repository that never considered the question.

WHY HOST-LOCAL, WHEN `bd-ib-26deyw` BUILT THE CLUSTER VENUE. The gate Job's pod
command is fixed in the shared dev-tooling package's
`ci-runner/k3s/phase2/gates/gate-job-template.yaml` as four `just` invocations
under `set -euo pipefail`: `just install-worktree-pack`,
`just install-commit-refuse-hooks`, `just warm-typecheck`, and
`just hook_gate=1 check`. THE LAST TWO DO NOT EXIST HERE. Measured against this
tree, `just --summary` lists `check`, `install-commit-refuse-hooks` and
`install-worktree-pack` and carries no `warm-typecheck` recipe, and this
repository's justfile declares no `hook_gate` variable, so
`just hook_gate=1 check` exits 1 with "error: Variable hook_gate overridden on
the command line but not present in justfile". Scope searched: this repository's
full `just --summary`, its `justfile` and its `dev-tooling/*.just`.

Declaring the cluster here would therefore abort the pod on a GREEN TREE, the
gate would return FAILED, and the janitor would report red for every merge --
after the work had already landed, which is the one moment nothing can re-run.
So the declaration waits on that template's pod command becoming repo-agnostic,
which is that package's change to make. The `.livespec.jsonc` comment beside the
key carries the same measurement and names what has to change to flip it.

THE THIRD CASE IS WHY THIS FILE IS NOT MERELY AN INVERTED ASSERTION. A reader
hardwired to answer "host" would satisfy the first two cases while making the
venue key decorative and silently stranding the mechanism this item built. So the
cluster word is resolved through the SAME reader and asserted to select the
cluster: the venue this repository does not currently choose is proved to still
be choosable, which is what makes flipping the key above a one-line change rather
than a re-implementation.
"""

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_check_venue import (
    JANITOR_VENUE_CLUSTER_JOB,
    cluster_venue_declared,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_this_repository_declares_the_host_local_venue_for_its_janitor_check_suite() -> None:
    assert cluster_venue_declared(block=dispatcher_block(cwd=_REPO_ROOT)) is False


def test_a_block_declaring_no_venue_keeps_the_host_local_check_suite() -> None:
    """The control: silence is not the cluster, so the key above is what answers."""
    assert cluster_venue_declared(block={"wip_cap": 10}) is False


def test_a_block_declaring_the_cluster_word_still_selects_the_cluster_venue() -> None:
    """The cluster venue stays selectable, so this repository's declaration is what waits."""
    declared = {"janitor": {"venue": JANITOR_VENUE_CLUSTER_JOB}}
    assert cluster_venue_declared(block=declared) is True
