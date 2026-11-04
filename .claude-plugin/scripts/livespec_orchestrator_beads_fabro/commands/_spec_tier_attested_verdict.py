"""The governing-heading verdict a standing attestation supplies.

A human's attestation is "a human override of the governing-heading verdict for
the item's asked-for behaviour, not a cached model verdict", and the clause
requires that "every taking, the pre-dispatch wall and the `dod_gate` node
included, MUST use the attested `stated` verdict without requiring model
agreement, and its clause provenance is the cited clause, as both the selected
and the named clause of each attested assertion". This module turns a standing
attestation into that verdict, so the Definition-of-Done judgement and the goal
block the `dod_gate` node reads both consult one reading.

THE LEDGER IS CHECKED BEFORE THE DISK. Almost no item carries an attestation, and
this runs on every taking and every goal render, so an item whose comments hold
none returns without touching the specification tree.

AN UNREADABLE TREE SUPPLIES NO VERDICT rather than a stale one: the attestation
is voided by a change to the cited clause, and a tree nobody could read cannot
show that the clause is unchanged. The taking then falls back on the model as it
would for an item nobody attested.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import SPEC_DIRNAME
from livespec_orchestrator_beads_fabro.commands._spec_tier_attestation import (
    recorded_attestation,
    standing_attestation,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["attested_governing_heading"]


def attested_governing_heading(
    *, item: WorkItem, repo: Path, comments: Sequence[str]
) -> GoverningHeadingVerdict | None:
    """The `stated` verdict a standing attestation supplies, or `None` for none."""
    if recorded_attestation(comments=comments) is None:
        return None
    read = attempt(
        action=lambda: read_current_specification(spec_root=repo / SPEC_DIRNAME).files,
        exceptions=(OSError, UnicodeDecodeError),
    )
    if isinstance(read, AttemptFailure):
        return None
    cited = standing_attestation(item=item, comments=comments, spec_tree=read)
    if cited is None:
        return None
    return GoverningHeadingVerdict(
        kind="stated",
        stated_by=(cited.heading.rstrip(),),
        generalization_target=None,
        selected_clauses=(cited,),
        named_clauses=(cited,),
        provenance_complete=True,
    )
