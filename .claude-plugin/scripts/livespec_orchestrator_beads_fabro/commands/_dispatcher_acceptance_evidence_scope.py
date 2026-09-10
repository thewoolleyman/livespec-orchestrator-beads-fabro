"""Which of a merged diff's text is admissible evidence for one criterion.

The acceptance judge grades a criterion by looking for its own vocabulary in
the merged diff. Read over the WHOLE diff, that rule grades a DECLARATION of a
change as the change itself: `.livespec-workflow-edit-exemption` carries prose
DESCRIBING the `.github/workflows/` edit it authorizes, so a criterion demanding
that edit finds every one of its own terms in the declaration. Measured
2026-09-10 on bd-ib-6t4, whose merge (PR 2446, 47edb04a) touched exactly that
declaration and one test file: four criteria naming the CI workflow file were
graded met, the item was accepted and CLOSED, and `.github/` was never touched.

Two mechanical rules close it, and neither reads semantics. A declaration file
does not CARRY a change, so its text leaves the searchable body entirely. And a
criterion whose subject is a named PATH CLASS — today the CI workflow file — is
searched only within changes to a path of that class, so vocabulary found
anywhere else cannot satisfy it.

Both rules can only REMOVE text from a criterion's search body, never add any,
so neither can turn an unmet criterion into a met one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__: list[str] = [
    "DiffEvidence",
    "EvidenceScope",
    "diff_evidence",
    "scope_for",
]

# Files that DECLARE a change rather than carrying it. Their prose necessarily
# restates the change's own vocabulary — that is what a declaration is for — so
# they are the one file class guaranteed to read as evidence for work nobody did.
_DECLARATION_PATHS = frozenset({".livespec-workflow-edit-exemption"})
_CI_WORKFLOW_PATH_PREFIX = ".github/workflows/"
# A criterion NAMES the CI workflow file only when it says so unambiguously: the
# path class written out, or the phrase `CI workflow`. Deliberately narrow — a
# bare `workflow file` also names this repo's `.fabro/workflows/.../workflow.fabro`
# graph, and reading that as a `.github/workflows/` demand would fail landed work.
# Under-firing leaves the status quo; over-firing invents rework.
_CI_WORKFLOW_SUBJECT = re.compile(r"\.github/workflows|\bci[\s\-]+workflows?\b")
_DIFF_HEADER = re.compile(r"^diff --git a/(?P<before>.*) b/(?P<after>.*)$")
_ADMISSIBLE_ABSENT_REASON = "no merged diff or telemetry evidence"
_CI_WORKFLOW_ABSENT_REASON = "no merged diff change under .github/workflows/"


@dataclass(frozen=True, kw_only=True)
class EvidenceScope:
    """The merged-diff text one criterion may be evidenced against.

    `absent_reason` travels with the text because a criterion that finds nothing
    needs to be told WHICH body was empty: "no merged diff or telemetry
    evidence" and "the named path class was never touched" are different
    findings, and only the second tells an operator what to change.
    """

    text: str
    absent_reason: str


@dataclass(frozen=True, kw_only=True)
class DiffEvidence:
    """A merged diff split into the bodies a criterion may be graded against."""

    admissible: str
    ci_workflow: str


def diff_evidence(*, merged_diff: str | None) -> DiffEvidence:
    """Split a merged diff into its admissible bodies, dropping declarations."""
    if merged_diff is None:
        return DiffEvidence(admissible="", ci_workflow="")
    admissible: list[str] = []
    ci_workflow: list[str] = []
    for section in _sections(diff=merged_diff):
        if _is_declaration(paths=section.paths):
            continue
        admissible.append(section.text)
        if _is_ci_workflow(paths=section.paths):
            ci_workflow.append(section.text)
    return DiffEvidence(
        admissible="\n".join(admissible).lower(),
        ci_workflow="\n".join(ci_workflow).lower(),
    )


def scope_for(*, evidence: DiffEvidence, criterion: str) -> EvidenceScope:
    """Resolve the body one criterion is searched within."""
    if _CI_WORKFLOW_SUBJECT.search(criterion.lower()) is not None:
        return EvidenceScope(text=evidence.ci_workflow, absent_reason=_CI_WORKFLOW_ABSENT_REASON)
    return EvidenceScope(text=evidence.admissible, absent_reason=_ADMISSIBLE_ABSENT_REASON)


@dataclass(frozen=True, kw_only=True)
class _Section:
    """One `diff --git` run of a unified diff, with the paths it changes."""

    paths: tuple[str, ...]
    text: str


def _sections(*, diff: str) -> tuple[_Section, ...]:
    """Split a unified diff into one section per changed file.

    Text before the first header is its own PATH-LESS section. It belongs to no
    file, so no path rule can classify it, and it stays in the admissible body
    rather than silently leaving the text every other criterion is graded
    against — narrowing evidence is this module's job only where a path says so.
    """
    sections: list[_Section] = []
    paths: tuple[str, ...] = ()
    current: list[str] = []
    for line in diff.splitlines():
        header = _DIFF_HEADER.match(line)
        if header is not None:
            _flush(sections=sections, paths=paths, current=current)
            paths = (header.group("before"), header.group("after"))
        current.append(line)
    _flush(sections=sections, paths=paths, current=current)
    return tuple(sections)


def _flush(*, sections: list[_Section], paths: tuple[str, ...], current: list[str]) -> None:
    if not current:
        return
    sections.append(_Section(paths=paths, text="\n".join(current)))
    current.clear()


def _is_declaration(*, paths: tuple[str, ...]) -> bool:
    """Report whether every path a section changes is a declaration file.

    EVERY path, not any: a rename that moves a declaration into a real source
    path carries that source path's change, and dropping it would hide it.
    """
    return bool(paths) and all(path in _DECLARATION_PATHS for path in paths)


def _is_ci_workflow(*, paths: tuple[str, ...]) -> bool:
    return any(path.startswith(_CI_WORKFLOW_PATH_PREFIX) for path in paths)
