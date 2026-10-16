"""This repository's own declared venue for its post-merge janitor check suite.

WHAT THIS BINDS, AND WHY IT IS A TEST RATHER THAN A COMMENT. The venue is read
from the governed repository's committed `.livespec.jsonc` at post-merge time,
so the declaration IS the behaviour: the module that acts on it is exercised
against fixture configs, and nothing else observes what THIS repository actually
says. `bd-ib-26deyw` requires this repository's janitor to run its fresh-checkout
check suite as a Job on the maintainer-owned k3s cluster rather than on the
dispatching host, and an edit that dropped the key would silently return every
later post-merge gate to the host with nothing announcing it -- the key's absence
is exactly what a repository that never opted in looks like.

THE CONTROL IS THE SECOND CASE, and it is what makes the first one mean anything.
A reader that answered "on the cluster" for every repository would satisfy the
first case while making the declaration decorative; the control re-resolves a
block carrying NO venue key through the same reader and asserts the host-local
answer, so the first case is proved to turn on what this file says.
"""

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_check_venue import (
    cluster_venue_declared,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_this_repository_declares_the_cluster_venue_for_its_janitor_check_suite() -> None:
    assert cluster_venue_declared(block=dispatcher_block(cwd=_REPO_ROOT)) is True


def test_a_block_declaring_no_venue_keeps_the_host_local_check_suite() -> None:
    """The control: silence is not the cluster, so the first case turns on the key."""
    assert cluster_venue_declared(block={"wip_cap": 10}) is False
