"""The instant one ratified spec version was CUT, read off its revision record.

The ledger-intent scan of the `capture-spec-drift` clause of
`SPECIFICATION/contracts.md`
is scoped by a spec-version CUT: without `--since-version` it considers every
live work-item plus every work-item "captured on or after the most-recently-cut
spec version", and with the flag it considers only work-items captured on or
after the cut of the named version. Both readings need one instant per version,
and nothing else in this package resolved one.

WHERE THE INSTANT COMES FROM, and why it is not the directory's mtime. A revise
pass writes `<spec-root>/history/v<NNN>/proposed_changes/<topic>-revision.md`
carrying a `revised_at` front-matter field — the instant the revision was
ratified, recorded by the pass that cut it. A filesystem timestamp is a fact
about THIS CHECKOUT (a fresh clone stamps every file with the clone's own
instant), so it would answer the right question on the dispatching host and a
different one everywhere else, with nothing announcing the divergence.

TWO PROPERTIES AN EDITOR MUST NOT INVERT.

An unresolvable cut answers `None` and NEVER a sentinel instant. Both available
sentinels are wrong in opposite and equally silent directions: the epoch admits
every work-item the tenant holds, so a scan reports a population nobody scoped,
while a far-future instant admits none, so the scan reports the clean empty
answer on exactly the population it exists to cover. The caller refuses instead
and names the version whose cut it could not read.

The newest `revised_at` of the directory wins, rather than the first record
found. A revision that ratified several proposals carries one record per
proposal, so a first-match read answers whichever name sorts first — a value
that is a cut instant of SOMETHING, which is why nothing downstream could
notice it is not the version's own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.spec_reader import current_specification_version

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "CUT_INSTANT_FIELD",
    "SpecVersionCut",
    "latest_spec_version_cut",
    "parse_spec_version",
    "spec_version_cut",
]

CUT_INSTANT_FIELD = "revised_at"

_FRONTMATTER_DELIMITER = "---"


@dataclass(frozen=True, kw_only=True)
class SpecVersionCut:
    """One ratified spec version and the instant it was cut.

    The version rides WITH the instant because every refusal a caller renders
    has to name the version whose cut could not be read, and a bare instant
    would make that refusal say which measurement failed without saying what it
    was a measurement of.
    """

    version: int
    instant: str


def spec_version_cut(*, spec_root: Path, version: int) -> SpecVersionCut | None:
    """The cut of one ratified spec version, or `None` when none is readable."""
    directory = spec_root / "history" / f"v{version:03d}" / "proposed_changes"
    if not directory.is_dir():
        return None
    instants: list[str] = []
    for candidate in sorted(directory.glob("*.md")):
        recorded = _revised_at(text=candidate.read_text(encoding="utf-8"))
        if recorded is not None:
            instants.append(recorded)
    if not instants:
        return None
    return SpecVersionCut(version=version, instant=max(instants))


def latest_spec_version_cut(*, spec_root: Path) -> SpecVersionCut | None:
    """The cut of the most-recently-ratified spec version, or `None`.

    The version is asked of the Spec Reader rather than derived here, so the
    "latest version" this scan scopes itself by and the one every other surface
    reads cannot drift onto two derivations.
    """
    version = current_specification_version(spec_root=spec_root)
    if version <= 0:
        return None
    return spec_version_cut(spec_root=spec_root, version=version)


def parse_spec_version(*, raw: str) -> int | None:
    """One `--since-version` value as a version number, or `None` when unusable.

    Accepts the ratified `v<N>` spelling and a bare `<N>`, which is the same
    pair `detect-impl-gaps` documents for its own `--since-version`: an
    operator who learned one flag types either at the other. Unifying the two
    readers is deliberately NOT done here — that detector's flag means
    something different (it scopes a file diff, not a capture instant), and
    folding them would make one grammar module serve two populations.

    `None` rather than a raised usage error, because the caller is a CLI arm
    that owes the operator a narrated exit 2 naming the value it refused.
    """
    candidate = raw[1:] if raw[:1] in {"v", "V"} else raw
    if not candidate.isdigit():
        return None
    version = int(candidate)
    return version if version > 0 else None


def _revised_at(*, text: str) -> str | None:
    """The `revised_at` value one revision record's front matter carries.

    Front matter only: the scan stops at the closing delimiter rather than
    searching the whole document, because a revision record's prose quotes the
    field routinely — the decision narration of a proposal ABOUT revision
    timestamps would otherwise supply the instant.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIMITER:
        return None
    for line in lines[1:]:
        if line.strip() == _FRONTMATTER_DELIMITER:
            return None
        key, separator, value = line.partition(":")
        if separator != "" and key.strip() == CUT_INSTANT_FIELD and value.strip() != "":
            return value.strip()
    return None
