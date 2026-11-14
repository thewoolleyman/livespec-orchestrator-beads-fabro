"""Mirror test module for post-run loop selection."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    post_run_dispositions,
)


def test_post_run_dispositions_is_importable() -> None:
    """Already-satisfied disposition coverage exercises the public seam."""
    assert callable(post_run_dispositions)
