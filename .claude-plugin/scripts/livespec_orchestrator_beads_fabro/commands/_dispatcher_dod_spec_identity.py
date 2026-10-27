"""The stable specification identity of one Definition-of-Done judgement.

A Definition-of-Done subject must move when the clauses the host selected as
governing move, but not when an unrelated ratified clause changes.  The
governing-heading verdict is the selection authority; this module only resolves
that recorded selection into bytes and hashes an unambiguous framing of it.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    judgement_subject_digest,
    spec_tree_identity,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "ClauseProvenance",
    "SpecIdentity",
    "clause_spec_identity",
    "spec_identity_for_governing",
    "subject_digest_for_governing",
]

_SPECIFICATION_DIRECTORY = "SPECIFICATION"
_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


class _Digest(Protocol):
    """The one hashing operation this module needs."""

    def update(self, data: bytes, /) -> object:
        """Consume one byte sequence."""


@dataclass(frozen=True, kw_only=True)
class ClauseProvenance:
    """The bytes and stable address of one clause a verdict selected."""

    path: str
    heading: str
    body: bytes


@dataclass(frozen=True, kw_only=True)
class SpecIdentity:
    """The labelled identity supplied to a host taking and its record."""

    form: str
    value: str
    provenance: tuple[ClauseProvenance, ...] = ()


def spec_identity_for_governing(
    *, item: WorkItem, cwd: Path, governing: GoverningHeadingVerdict | None
) -> SpecIdentity:
    """Resolve a recorded verdict to clauses, falling back to the whole tree.

    A partial, absent, duplicate, or unreadable selection cannot prove that
    every assertion has clause provenance, so it deliberately receives the
    whole-tree identity.  This function never takes a governing-heading
    judgement; callers use the recorded verdict they already have.
    """
    if governing is None or not governing.stated_by:
        return _tree_identity(cwd=cwd)
    clauses = _selected_clauses(cwd=cwd, headings=governing.stated_by)
    if clauses is None:
        return _tree_identity(cwd=cwd)
    assertions = tuple(
        assertion.text for assertion in definition_of_done(description=item.description).assertions
    )
    if not assertions:
        return _tree_identity(cwd=cwd)
    return SpecIdentity(
        form="clauses",
        value=clause_spec_identity(assertions=assertions, clauses=clauses).value,
        provenance=clauses,
    )


def clause_spec_identity(
    *, assertions: tuple[str, ...], clauses: tuple[ClauseProvenance, ...]
) -> SpecIdentity:
    """Hash framed assertion text and clause provenance without ambiguity."""
    digest = hashlib.sha256()
    _update_many(digest=digest, label=b"assertion", values=assertions)
    _update_many(
        digest=digest, label=b"clause", values=tuple(_clause_bytes(clause=one) for one in clauses)
    )
    return SpecIdentity(form="clauses", value="clauses:" + digest.hexdigest(), provenance=clauses)


def subject_digest_for_governing(
    *,
    item: WorkItem,
    cwd: Path,
    comments: Sequence[str],
    governing: GoverningHeadingVerdict | None,
) -> str:
    """Build the one judgement digest from an already-recorded heading verdict."""
    return judgement_subject_digest(
        item=item,
        cwd=cwd,
        comments=comments,
        spec_identity=spec_identity_for_governing(item=item, cwd=cwd, governing=governing).value,
    )


def _tree_identity(*, cwd: Path) -> SpecIdentity:
    """The labelled whole-tree fallback, including its unreadable sentinel."""
    return SpecIdentity(form="tree", value="tree:" + spec_tree_identity(cwd=cwd))


def _selected_clauses(
    *, cwd: Path, headings: tuple[str, ...]
) -> tuple[ClauseProvenance, ...] | None:
    """Resolve every named heading once, or return no clause identity."""
    requested = tuple(_title(heading=heading) for heading in headings)
    if len(set(requested)) != len(requested):
        return None
    found = _clauses_in(cwd=cwd)
    if found is None:
        return None
    by_heading = {clause.heading: clause for clause in found}
    selected = tuple(by_heading.get(heading) for heading in requested)
    if any(clause is None for clause in selected):
        return None
    return tuple(clause for clause in selected if clause is not None)


def _clauses_in(*, cwd: Path) -> tuple[ClauseProvenance, ...] | None:
    """Read each H2 clause in the governed specification tree."""
    root = cwd / _SPECIFICATION_DIRECTORY
    if not root.is_dir():
        return None
    clauses: list[ClauseProvenance] = []
    for path in sorted(root.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        matches = tuple(_HEADING.finditer(text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            clauses.append(
                ClauseProvenance(
                    path=path.name,
                    heading=match.group(1),
                    body=text[match.start() : end].encode("utf-8"),
                )
            )
    return tuple(clauses)


def _update_many(*, digest: _Digest, label: bytes, values: tuple[object, ...]) -> None:
    """Feed length-delimited values into the sha256 object."""
    for value in values:
        encoded = value if isinstance(value, bytes) else str(value).encode("utf-8")
        _ = digest.update(
            label + b"\x00" + str(len(encoded)).encode("ascii") + b"\x00" + encoded + b"\x00"
        )


def _clause_bytes(*, clause: ClauseProvenance) -> bytes:
    """The provenance fields that identify one selected clause."""
    return b"\x00".join((clause.path.encode("utf-8"), clause.heading.encode("utf-8"), clause.body))


def _title(*, heading: str) -> str:
    """Normalise the optional H2 marker used by governing verdicts."""
    return heading.removeprefix("## ").strip()
