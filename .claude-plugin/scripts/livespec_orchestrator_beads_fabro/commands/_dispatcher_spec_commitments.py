"""Spec-commitment obligation walker for the Dispatcher's spec-check surface.

Port of the retired livespec doctor helper
`_unresolved_spec_commitment_helpers.py` (retired by livespec PR #396
when v103 made work-items orchestrator-private; source recoverable at
livespec commit 682bf9cc under
`.claude-plugin/scripts/livespec/doctor/static/`), adapted to the
beads orchestrator. The front-matter parser and history walker keep
the retired semantics; work-item hint matching now reads the Ledger's
`WorkItem.spec_commitment_hint` field in the sibling
`_dispatcher_spec_checks.py` module.

Walks `<spec-root>/history/vNNN/proposed_changes/` and collects, for
every propose-change whose paired `<stem>-revision.md` carries
`decision: accept` or `decision: modify`, the declared
`spec_commitments.impl_followups[]` id_hints plus the union of every
`spec_commitments.supersedes[]` entry (membership in that set exempts
the listed id_hint from the coverage check). Pruned version
directories (carrying `PRUNED_HISTORY.json`) are skipped, mirroring
the retired walker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = [
    "Obligation",
    "collect_obligations_and_supersedes",
]

_HISTORY_SUBDIR = "history"
_PROPOSED_CHANGES_DIR = "proposed_changes"
_REVISION_SUFFIX = "-revision.md"
_PRUNED_MARKER = "PRUNED_HISTORY.json"
_VERSION_RE = re.compile(r"^v(\d+)$")


@dataclass(frozen=True, kw_only=True, slots=True)
class Obligation:
    """One declared impl_followups id_hint plus the PC that introduced it."""

    id_hint: str
    version_label: str
    pc_stem: str


@dataclass(frozen=True, kw_only=True, slots=True)
class _ParsedCommitments:
    """The id_hints + supersedes slugs parsed from one PC's front-matter."""

    impl_followups_id_hints: tuple[str, ...]
    supersedes: tuple[str, ...]


def collect_obligations_and_supersedes(
    *,
    spec_root: Path,
) -> tuple[list[Obligation], set[str]]:
    """Walk history/vNNN/ and collect declared obligations + the supersedes set.

    Returns `(obligations, superseded_set)`. ALL accepted-or-modified
    obligations are collected, including ones later superseded —
    supersession is applied as a second pass by the caller.
    """
    obligations: list[Obligation] = []
    superseded_set: set[str] = set()
    for version_dir in _version_dirs(history_path=spec_root / _HISTORY_SUBDIR):
        for pc_stem in _pc_stems(version_dir=version_dir):
            commitments = _accepted_commitments(version_dir=version_dir, pc_stem=pc_stem)
            if commitments is None:
                continue
            obligations.extend(
                Obligation(id_hint=hint, version_label=version_dir.name, pc_stem=pc_stem)
                for hint in commitments.impl_followups_id_hints
            )
            superseded_set.update(commitments.supersedes)
    return obligations, superseded_set


def _accepted_commitments(*, version_dir: Path, pc_stem: str) -> _ParsedCommitments | None:
    """Return the PC's commitments iff its revision decision is accept/modify."""
    pc_path = version_dir / _PROPOSED_CHANGES_DIR / f"{pc_stem}.md"
    revision_path = version_dir / _PROPOSED_CHANGES_DIR / f"{pc_stem}{_REVISION_SUFFIX}"
    if not revision_path.is_file():
        return None
    if _revision_decision(revision_path=revision_path) not in ("accept", "modify"):
        return None
    return _pc_file_commitments(pc_path=pc_path)


def _version_dirs(*, history_path: Path) -> list[Path]:
    """Return vNNN dirs under history/ in version order, skipping pruned markers."""
    if not history_path.is_dir():
        return []
    pairs: list[tuple[int, Path]] = []
    for child in sorted(history_path.iterdir()):
        if not child.is_dir():
            continue
        match = _VERSION_RE.match(child.name)
        if match is None:
            continue
        if (child / _PRUNED_MARKER).is_file():
            continue
        pairs.append((int(match.group(1)), child))
    pairs.sort(key=lambda pair: pair[0])
    return [version_dir for _, version_dir in pairs]


def _pc_stems(*, version_dir: Path) -> list[str]:
    """Return sorted PC filename stems (no `-revision.md`) in version_dir."""
    proposed_changes = version_dir / _PROPOSED_CHANGES_DIR
    if not proposed_changes.is_dir():
        return []
    stems: list[str] = []
    for entry in sorted(proposed_changes.iterdir()):
        if not entry.is_file():
            continue
        if entry.name.endswith(_REVISION_SUFFIX) or not entry.name.endswith(".md"):
            continue
        stems.append(entry.name[: -len(".md")])
    return stems


def _revision_decision(*, revision_path: Path) -> str | None:
    """Return the top-level `decision:` value from a revision's front-matter."""
    body_lines = _front_matter_body(text=revision_path.read_text(encoding="utf-8"))
    if body_lines is None:
        return None
    for line in body_lines:
        if line.startswith("decision:"):
            return line[len("decision:") :].strip()
    return None


def _pc_file_commitments(*, pc_path: Path) -> _ParsedCommitments | None:
    """Read a PC file and extract its `spec_commitments` block, if declared."""
    body_lines = _front_matter_body(text=pc_path.read_text(encoding="utf-8"))
    if body_lines is None:
        return None
    block_start = next(
        (index for index, line in enumerate(body_lines) if line.rstrip() == "spec_commitments:"),
        None,
    )
    if block_start is None:
        return None
    block_lines = _indented_block(lines=body_lines, start_index=block_start)
    return _ParsedCommitments(
        impl_followups_id_hints=_id_hints(block_lines=block_lines),
        supersedes=_supersedes_slugs(block_lines=block_lines),
    )


def _front_matter_body(*, text: str) -> list[str] | None:
    """Return the lines between the leading and closing `---` fences, or None."""
    if not text.startswith("---\n"):
        return None
    lines = text.split("\n")
    for index in range(1, len(lines)):
        if lines[index] == "---":
            return lines[1:index]
    return None


def _indented_block(*, lines: list[str], start_index: int) -> list[str]:
    """Return the lines indented strictly deeper than the line at start_index."""
    start_indent = _leading_spaces(line=lines[start_index])
    collected: list[str] = []
    for index in range(start_index + 1, len(lines)):
        candidate = lines[index]
        if candidate.strip() == "":
            collected.append(candidate)
            continue
        if _leading_spaces(line=candidate) <= start_indent:
            break
        collected.append(candidate)
    return collected


def _subheader_block(*, block_lines: list[str], header_name: str) -> list[str]:
    """Return the indented lines under `<header_name>:` inside block_lines."""
    start_index = next(
        (index for index, line in enumerate(block_lines) if line.strip() == f"{header_name}:"),
        None,
    )
    if start_index is None:
        return []
    return _indented_block(lines=block_lines, start_index=start_index)


def _id_hints(*, block_lines: list[str]) -> tuple[str, ...]:
    """Extract non-empty `- id_hint:` values from the impl_followups entries."""
    hints: list[str] = []
    for line in _subheader_block(block_lines=block_lines, header_name="impl_followups"):
        stripped = line.strip()
        if not stripped.startswith("- id_hint:"):
            continue
        value = stripped[len("- id_hint:") :].strip()
        if value:
            hints.append(value)
    return tuple(hints)


def _supersedes_slugs(*, block_lines: list[str]) -> tuple[str, ...]:
    """Extract bare-slug list items from the `supersedes:` sub-section."""
    return tuple(
        line.strip()[2:].strip()
        for line in _subheader_block(block_lines=block_lines, header_name="supersedes")
        if line.strip().startswith("- ")
    )


def _leading_spaces(*, line: str) -> int:
    """Return the count of leading space characters in `line`."""
    return len(line) - len(line.lstrip(" "))
