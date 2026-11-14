"""Mirror test module for already-satisfied lifecycle handling."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_already_satisfied_rest import (
    rest_already_satisfied,
)


def test_already_satisfied_rest_is_importable() -> None:
    """The dedicated lifecycle disposition is available to the loop selector."""
    assert callable(rest_already_satisfied)
