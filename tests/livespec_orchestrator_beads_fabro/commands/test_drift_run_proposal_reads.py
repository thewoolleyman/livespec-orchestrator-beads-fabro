"""The proposal store's reads, and the documents they must not be fooled by.

Every case here is a document the open queue or the archive legitimately holds
and that a looser reading would classify wrongly — and each wrong
classification has a cost the pass cannot recover from on its own.

The FRONT MATTER is read only in the LEADING fenced block, because this
proposal format is itself a thing proposals get written about: a document whose
PROSE quotes `drift_origin:` would otherwise count against
`dispatcher.drift_proposal_queue_cap` and could hold the queue closed with no
machine-filed proposal open at all.

An UNREADABLE document answers nothing rather than raising, because the whole
pass runs behind it; the consequence is bounded (one finding filed twice, which
`revise` can see and dispose of) while raising would stop every merge of the
scope over one file somebody left in a bad state.

And a finding whose judgement named NO generalization target still files,
naming no target file: where a new heading belongs is a human's call, so the
proposal says it has none rather than guessing a file into the record a human
adjudicates.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._drift_run_findings import DriftFinding
from livespec_orchestrator_beads_fabro.commands._drift_run_proposals import (
    drift_proposal_document,
    file_drift_proposal,
    filed_finding_identities,
    open_drift_origin_proposals,
    target_spec_files,
)

_TARGET = "## A governing heading"


def _finding(*, identity: str = "drift-abc", target: str | None = _TARGET) -> DriftFinding:
    return DriftFinding(
        merge="aaaaaaa1",
        kind="unstated",
        generalization_target=target,
        statement="a behaviour",
        rationale="because",
        identity=identity,
    )


def _spec_root(*, root: Path) -> Path:
    spec_root = root / "SPECIFICATION"
    (spec_root / "proposed_changes").mkdir(parents=True)
    (spec_root / "history" / "v001" / "proposed_changes").mkdir(parents=True)
    return spec_root


def _write(*, path: Path, body: str) -> None:
    _ = path.write_text(body, encoding="utf-8")


def test_a_finding_with_no_target_names_no_target_file(tmp_path: Path) -> None:
    spec_root = _spec_root(root=tmp_path)
    finding = _finding(target=None)

    targets = target_spec_files(spec_tree={"contracts.md": _TARGET}, finding=finding)
    document = drift_proposal_document(
        finding=finding, author="a", now="2026-10-22T00:00:00Z", targets=targets
    )
    path = file_drift_proposal(spec_root=spec_root, finding=finding, document=document)

    assert targets == ()
    assert "no existing heading would state this behaviour" in path.read_text(encoding="utf-8")


def test_a_target_is_resolved_to_every_spec_file_carrying_it() -> None:
    tree = {"contracts.md": f"{_TARGET}\n", "constraints.md": "## Another\n"}

    assert target_spec_files(spec_tree=tree, finding=_finding()) == ("contracts.md",)


def test_an_archived_proposals_identity_counts_as_filed(tmp_path: Path) -> None:
    spec_root = _spec_root(root=tmp_path)
    _write(
        path=spec_root / "history" / "v001" / "proposed_changes" / "drift-old.md",
        body="---\ntopic: drift-old\nfinding_identity: drift-old\n---\n\nbody\n",
    )

    assert filed_finding_identities(spec_root=spec_root) == frozenset({"drift-old"})


def test_an_archived_proposal_is_not_an_open_one(tmp_path: Path) -> None:
    spec_root = _spec_root(root=tmp_path)
    _write(
        path=spec_root / "history" / "v001" / "proposed_changes" / "drift-old.md",
        body="---\ndrift_origin: dispatcher-drift-run\n---\n\nbody\n",
    )

    # The cap bounds the OPEN queue. A ratified proposal that still counted
    # would close the queue permanently, one disposal at a time.
    assert open_drift_origin_proposals(spec_root=spec_root) == ()


@pytest.mark.parametrize(
    ("case", "body"),
    [
        ("no front matter at all", "## Proposal: something\n\ndrift_origin: quoted\n"),
        (
            "the field only in the prose",
            "---\ntopic: t\n---\n\nThe front matter carries drift_origin: x\n",
        ),
        ("front matter with no such field", "---\ntopic: t\nauthor: a\n---\n\nbody\n"),
        ("front matter that is never closed", "---\ntopic: t\nauthor: a\n"),
        ("an empty field value", "---\ndrift_origin:\n---\n\nbody\n"),
    ],
)
def test_a_document_that_is_not_machine_filed_is_not_in_the_open_queue(
    tmp_path: Path, case: str, body: str
) -> None:
    spec_root = _spec_root(root=tmp_path)
    _write(path=spec_root / "proposed_changes" / "something.md", body=body)

    assert open_drift_origin_proposals(spec_root=spec_root) == (), case


def test_an_unreadable_document_answers_nothing_rather_than_raising(tmp_path: Path) -> None:
    spec_root = _spec_root(root=tmp_path)
    # A directory where a document belongs: `read_text` raises `IsADirectoryError`,
    # which is an `OSError`, and does so for root as well as for anybody else —
    # a mode bit would not, because this suite runs as root in the sandbox.
    (spec_root / "proposed_changes" / "not-a-file.md").mkdir()

    assert open_drift_origin_proposals(spec_root=spec_root) == ()
    assert filed_finding_identities(spec_root=spec_root) == frozenset()
