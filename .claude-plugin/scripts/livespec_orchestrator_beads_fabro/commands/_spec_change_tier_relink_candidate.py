"""The ratified topic a held item's generalization-target heading was amended under.

The autonomy-tier bullet of `SPECIFICATION/contracts.md` asks that, when an item is
held because its linked topic has no revision record with decision `accept` or
`modify`, and such a revision "cut after the specification version of the item's
newest spec-change tier record amended the body of that record's
generalization-target heading under a different topic", the refusal and
`needs-attention` NAME that revision's topic and specification version as a relink
candidate. A seat whose filing-time stem went stale otherwise has nothing that
tells it so, and the hold only ever clears on the EXACT linked topic.

PURE OVER THE SPEC HISTORY, and it needs no model: the hold it decorates is a read
of the same files. NAMING A CANDIDATE RELEASES NOTHING, relinks nothing and writes
nothing — the clause says so in as many words, because releasing on any ratified
edit to a busy heading would free items whose own behaviour is still unratified,
and only the re-run judgement decides `stated`.

AN AMENDMENT IS A CHANGE BETWEEN CONSECUTIVE SNAPSHOTS, not a difference from the
record's own version. Comparing every later snapshot to the record's would name
every ratification cut after the first amendment, because each later snapshot
still carries that amendment's text — a revision that never touched the heading
would then read as the one that amended it. Each version is therefore compared to
the one immediately before it, and a version that ratifies a topic and left the
heading's body alone names nothing.

EVERY ARM THAT CANNOT MEASURE NAMES NOTHING. A record naming no target, a version
that does not parse, a baseline snapshot that is gone, a snapshot that cannot be
read and a heading absent from either side of a comparison are each "no
candidate": a hint pointing an operator at a relink is the more expensive wrong
answer than saying nothing, and the hold itself is unchanged either way.

`reject` IS NEVER NAMED. It is excluded by the same ratification read the hold
uses, which admits only `accept` and `modify`, so a rejected topic cannot appear
here by a path that bypasses that rule — and the relink valve refuses a rejected
topic in any case.

WHEN MORE THAN ONE REVISION QUALIFIES the most recently cut one is named, and
within a single snapshot that ratified several topics the last in sorted order,
which is deterministic and nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_commitments import (
    history_versions,
    ratified_topics_of_version,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_commitments import (
        HistoryVersion,
    )
    from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
        RecordedSpecChangeTier,
    )

__all__: list[str] = [
    "RelinkCandidate",
    "relink_candidate",
]

_H2_PREFIX = "## "
_FENCE = "```"


@dataclass(frozen=True, kw_only=True, slots=True)
class RelinkCandidate:
    """One ratified topic that amended a held item's generalization-target heading.

    `spec_version` is the history directory's own name (`v320`), which is what an
    operator searches the spec tree for.
    """

    topic: str
    spec_version: str


def relink_candidate(
    *, spec_root: Path, recorded: RecordedSpecChangeTier
) -> RelinkCandidate | None:
    """The most recently cut ratified amendment of the record's target, or `None`."""
    title = _title(target=recorded.generalization_target)
    baseline = _record_version(spec_root=spec_root, spec_version=recorded.spec_version)
    if title is None or baseline is None:
        return None
    found: RelinkCandidate | None = None
    previous = _bodies(version=baseline, title=title)
    for version in history_versions(spec_root=spec_root):
        if version.number <= baseline.number:
            continue
        current = _bodies(version=version, title=title)
        topics = tuple(
            topic
            for topic in ratified_topics_of_version(version=version)
            if topic != recorded.linked_proposal_topic
        )
        if topics and _amended(previous=previous, current=current):
            found = RelinkCandidate(topic=topics[-1], spec_version=version.path.name)
        previous = current
    return found


def _title(*, target: str | None) -> str | None:
    """The heading text of a generalization target, with or without its `##` marker."""
    if target is None:
        return None
    return target.lstrip("#").strip()


def _record_version(*, spec_root: Path, spec_version: str) -> HistoryVersion | None:
    """The snapshot the record was taken against, or `None` when it cannot be found."""
    if not spec_version.isdigit():
        return None
    number = int(spec_version)
    return next(
        (version for version in history_versions(spec_root=spec_root) if version.number == number),
        None,
    )


def _amended(*, previous: tuple[str, ...] | None, current: tuple[str, ...] | None) -> bool:
    """Whether the heading's body changed between two snapshots that both carry it."""
    return bool(previous) and bool(current) and previous != current


def _bodies(*, version: HistoryVersion, title: str) -> tuple[str, ...] | None:
    """Every body the heading carries in one snapshot, or `None` if it cannot be read."""
    bodies: list[str] = []
    for path in sorted(version.path.glob("*.md")):
        text = attempt(
            action=lambda path=path: path.read_text(encoding="utf-8"),
            exceptions=(OSError, UnicodeDecodeError),
        )
        if isinstance(text, AttemptFailure):
            return None
        bodies.extend(_section_bodies(text=text, title=title))
    return tuple(bodies)


def _section_bodies(*, text: str, title: str) -> list[str]:
    """The body under each H2 heading titled `title`, ending at the next H2 heading."""
    bodies: list[list[str]] = []
    capturing = False
    in_fence = False
    for line in text.splitlines():
        if line.startswith(_FENCE):
            in_fence = not in_fence
        if not in_fence and line.startswith(_H2_PREFIX):
            capturing = line[len(_H2_PREFIX) :].strip() == title
            if capturing:
                bodies.append([])
            continue
        if capturing:
            bodies[-1].append(line)
    return ["\n".join(body) for body in bodies]
