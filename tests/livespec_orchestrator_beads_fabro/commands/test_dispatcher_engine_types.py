"""Mirror test module for dispatcher outcome types."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import DispatchOutcome


def test_dispatch_outcome_exposes_the_already_satisfied_base() -> None:
    """The no-op outcome carries the proved dispatch base."""
    assert "already_satisfied_base" in DispatchOutcome.__dataclass_fields__
