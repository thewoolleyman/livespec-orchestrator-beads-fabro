"""This repository's own declared venue for its post-merge janitor check suite.

WHAT THIS BINDS, AND WHY IT IS A TEST RATHER THAN A COMMENT. The venue is read
from the governed repository's committed `.livespec.jsonc` at post-merge time,
so the declaration IS the behaviour: the module that acts on it is exercised
against fixture configs, and nothing else observes what THIS repository actually
says. The declaration is `cluster_job`, and it is written out rather than left to
silence so that an edit flipping it is a diff a reviewer can see; an absent key
is indistinguishable from a repository that never considered the question.

WHY THE CLUSTER, WHEN THIS FILE PREVIOUSLY PINNED `host_local`. The shared gate
Job's pod command used to be fixed in the dev-tooling package as four `just`
invocations ending in `just warm-typecheck` and `just hook_gate=1 check` --
neither of which exists here, so declaring the cluster then would have aborted
the pod on a GREEN TREE and reported red for every merge, after the work had
already landed. That was a property of the shared pod command rather than of
this repository, and it is gone: the pinned package resolves the pod's suite
through `gate_remote_delegate.declared_gate_check_suite`, which reads a
`gate_check_suite` declaration out of the consuming repository's own
`[tool.livespec_dev_tooling]` block and otherwise falls through to
`GATE_CHECK_SUITE_FALL_THROUGH` -- `install-worktree-pack`,
`install-commit-refuse-hooks`, `check-pre-push`. Measured against this tree,
`just --summary` lists all three of those recipes and this repository declares no
`gate_check_suite`, so it takes that fall-through. Scope searched: this
repository's full `just --summary` and its `pyproject.toml`.

THE POSITIVE CONTROL IS A REAL JOB, not that measurement. Gate Job
`gate-livespec-orchestrator-beads-fabro-1c5e8de33c1f` in namespace `gates` ran
this repository's own declared suite against tree
`1c5e8de33c1f5c1376e7027e89a6d7d55de03fa1` (master `655306cb`, `ci-green`
success) under livespec-dev-tooling v1.112.5 and reported PASSED, 92 targets and
0 failed, with livespec core resolved at v0.42.1.

WHAT IS STILL A HOST PREMISE, AND WHICH WAY IT FAILS. The cluster venue reaches
the gate from the DISPATCHING host, so it needs that host's gates kubeconfig and
a `render-gate-job.sh` -- the in-repo copy or the converged
`/usr/local/lib/ci-runner-k3s/gates/render-gate-job.sh`. Neither is observable
from a test, and `resolve_renderer` deliberately returns the converged path
unchecked so an absent one fails AT THE SEAM: the run reports `NO_VERDICT`, and
`cluster_janitor_red` turns that into a RED post-merge outcome naming the missing
cluster verdict. So a host that cannot reach the gate makes merges loud rather
than falsely green, which is the only direction in which this declaration's
remaining premise can be wrong cheaply.

THE TWO CONTROLS BELOW ARE WHY THIS FILE IS NOT MERELY AN INVERTED ASSERTION. A
reader hardwired to answer "cluster" would satisfy the first case while making
the venue key decorative, and would strand the opt-out the brief requires for
repositories that keep the host-local path. So silence and the explicit
host-local word are both resolved through the SAME reader and asserted to select
the host: the venue this repository does not choose is proved to still be
choosable by one that does.
"""

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_check_venue import (
    JANITOR_VENUE_HOST_LOCAL,
    cluster_venue_declared,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_this_repository_declares_the_cluster_venue_for_its_janitor_check_suite() -> None:
    assert cluster_venue_declared(block=dispatcher_block(cwd=_REPO_ROOT)) is True


def test_a_block_declaring_no_venue_keeps_the_host_local_check_suite() -> None:
    """The control: silence is not the cluster, so the key above is what answers."""
    assert cluster_venue_declared(block={"wip_cap": 10}) is False


def test_a_block_declaring_the_host_local_word_keeps_the_host_local_check_suite() -> None:
    """The opt-out stays expressible, so a repository can say no in its own diff."""
    declared = {"janitor": {"venue": JANITOR_VENUE_HOST_LOCAL}}
    assert cluster_venue_declared(block=declared) is False
