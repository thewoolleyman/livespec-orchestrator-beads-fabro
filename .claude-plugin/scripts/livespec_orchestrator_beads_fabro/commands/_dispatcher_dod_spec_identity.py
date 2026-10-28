"""The SPEC IDENTITY of one Definition-of-Done judgement subject.

`contracts.md` section "One rubric, one subject" makes the SPEC IDENTITY the
CLAUSE PROVENANCE of the governing-heading verdicts a taking uses, so that a
ratified revision which leaves every clause a verdict was judged against and
names unchanged leaves the subject digest unchanged. This module owns the
identity and its two forms; the verdict is the selection authority and this
module only turns what the verdict recorded into labelled bytes.

THE TWO FORMS. `clauses:` plus the clause-provenance digest when the verdict
carries complete provenance, and `tree:` plus the whole-tree digest otherwise.
The fallback is the conservative direction, because a verdict that did not run
or that cannot say which clauses it saw cannot show that a revision left them
alone, and reusing a record across a change nobody could see is the failure the
whole-tree digest was introduced to prevent.

THE PATH IS PART OF EACH CLAUSE. A clause moved between two spec files is a
different clause for provenance purposes, and `CondensedClause.path` carries the
spec-relative file for exactly that reason; omitting it would leave the identity
unchanged by a move the clause requires it to notice.

THE VERDICT IS ONE STATEMENT ABOUT THE WHOLE DEFINITION OF DONE, so every
assertion contributes the same selected and named lists. They are still framed
per assertion, which is what the clause states and what keeps the digest
correct the day the judgement is taken per assertion.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    spec_tree_identity,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
        GoverningHeadingVerdict,
    )
    from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
        CondensedClause,
    )
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "FORM_CLAUSES",
    "FORM_TREE",
    "SPEC_IDENTITY_BLOCK_HEADING",
    "SPEC_IDENTITY_JOURNAL_STAGE",
    "SpecIdentity",
    "clause_provenance_digest",
    "spec_identity_block",
    "spec_identity_for_governing",
    "spec_identity_journal_record",
    "whole_tree_identity",
]


class _Digest(Protocol):
    """The one hashing operation the framing needs."""

    def update(self, data: bytes, /) -> object:
        """Consume one byte sequence."""


FORM_CLAUSES = "clauses"
FORM_TREE = "tree"
SPEC_IDENTITY_JOURNAL_STAGE = "dod-judgement-spec-identity"
# The goal block that supplies the run the identity the pre-dispatch taking used.
SPEC_IDENTITY_BLOCK_HEADING = (
    "## Definition-of-Done spec identity (supplied by the pre-dispatch taking)"
)


@dataclass(frozen=True, kw_only=True)
class SpecIdentity:
    """The labelled identity a host taking used, with the clauses behind it.

    `value` is the exact string the subject digest folds in. `selected` and
    `named` are empty for the `tree` form and for an identity read back from a
    record, which carries the labelled value and its form but not the clauses.
    """

    form: str
    value: str
    selected: tuple[CondensedClause, ...] = ()
    named: tuple[CondensedClause, ...] = ()


def whole_tree_identity(*, cwd: Path) -> SpecIdentity:
    """The `tree:` identity, including its unreadable sentinel."""
    return SpecIdentity(form=FORM_TREE, value=f"{FORM_TREE}:{spec_tree_identity(cwd=cwd)}")


def spec_identity_for_governing(
    *, item: WorkItem, cwd: Path, governing: GoverningHeadingVerdict | None
) -> SpecIdentity:
    """Resolve one governing-heading verdict to its identity, never taking one.

    Falls back to the whole tree when there is no verdict, when its provenance is
    incomplete or selected nothing, and when the item states no assertion — each
    is a case where no clause provenance exists to key on.
    """
    assertions = tuple(
        assertion.text for assertion in definition_of_done(description=item.description).assertions
    )
    if (
        governing is None
        or not governing.provenance_complete
        or not governing.selected_clauses
        or not assertions
    ):
        return whole_tree_identity(cwd=cwd)
    digest = clause_provenance_digest(
        assertions=assertions, selected=governing.selected_clauses, named=governing.named_clauses
    )
    return SpecIdentity(
        form=FORM_CLAUSES,
        value=f"{FORM_CLAUSES}:{digest}",
        selected=governing.selected_clauses,
        named=governing.named_clauses,
    )


def clause_provenance_digest(
    *,
    assertions: tuple[str, ...],
    selected: tuple[CondensedClause, ...],
    named: tuple[CondensedClause, ...],
) -> str:
    """A SHA-256 over each assertion, its selected clauses and its named clauses.

    Every value is length-prefixed in ASCII decimal and each list carries its own
    count, so two lists cannot trade a clause across the boundary between them and
    two assertions cannot trade text. Each list is sorted by spec file path and
    then heading line, so the digest does not move when the selection merely
    reorders.
    """
    digest = hashlib.sha256()
    for assertion in assertions:
        _frame(digest=digest, value=assertion.encode("utf-8"))
        for clauses in (selected, named):
            ordered = sorted(clauses, key=lambda one: (one.path, one.heading, one.body))
            _ = digest.update(str(len(ordered)).encode("ascii") + b"\n")
            for clause in ordered:
                _frame(digest=digest, value=_clause_bytes(clause=clause))
    return digest.hexdigest()


def spec_identity_journal_record(
    *, work_item_id: str, stage: str, identity: SpecIdentity
) -> dict[str, object]:
    """The dispatch-journal row recording the identity a taking used.

    The clauses are recorded by address and by the digest of their body, which is
    what a reader comparing two takings needs; the bodies themselves are the spec
    tree's to keep.
    """
    return {
        "stage": SPEC_IDENTITY_JOURNAL_STAGE,
        "work_item_id": work_item_id,
        "judgement_stage": stage,
        "spec_identity_form": identity.form,
        "spec_identity": identity.value,
        "clause_provenance": [
            {
                "list": label,
                "path": clause.path,
                "heading": clause.heading,
                "body_sha256": hashlib.sha256(clause.body.encode("utf-8")).hexdigest(),
            }
            for label, clauses in (("selected", identity.selected), ("named", identity.named))
            for clause in clauses
        ],
    }


def spec_identity_block(*, identity: SpecIdentity) -> str:
    """The goal block supplying a run the identity its host taking used."""
    return "\n".join(
        (
            SPEC_IDENTITY_BLOCK_HEADING,
            f"form: {identity.form}",
            f"identity: {identity.value}",
        )
    )


def _frame(*, digest: _Digest, value: bytes) -> None:
    """Feed one length-prefixed value into the digest."""
    _ = digest.update(str(len(value)).encode("ascii") + b"\n" + value)


def _clause_bytes(*, clause: CondensedClause) -> bytes:
    """One clause as path, heading line and body, NUL-separated, body length first."""
    body = clause.body.encode("utf-8")
    return b"\x00".join(
        (
            clause.path.encode("utf-8"),
            clause.heading.encode("utf-8"),
            str(len(body)).encode("ascii"),
            body,
        )
    )
