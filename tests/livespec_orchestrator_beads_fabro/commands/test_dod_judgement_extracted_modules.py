"""The governing receipt renders as its own module.

It was split out of the record, which sits at the file size ceiling, and keeps the
behaviour it had there: a receipt renders the lines the reuse rule scans for.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_record import (
    GoverningHeadingReceipt,
    governing_record_lines,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)


def test_governing_record_lines_name_kind_digest_provenance_and_headings() -> None:
    receipt = GoverningHeadingReceipt(
        verdict=GoverningHeadingVerdict(
            kind="partial",
            stated_by=("## A",),
            generalization_target="## B",
            provenance_complete=False,
        ),
        subject_digest="sha256:abc",
    )

    assert governing_record_lines(governing=receipt) == [
        "governing-heading-kind: partial",
        "governing-heading-subject-digest: sha256:abc",
        "governing-heading-provenance: incomplete",
        "governing-heading: ## A",
        "governing-heading-generalization-target: ## B",
    ]
