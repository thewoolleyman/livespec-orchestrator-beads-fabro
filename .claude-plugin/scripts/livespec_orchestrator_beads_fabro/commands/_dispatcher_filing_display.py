"""The filing-time Definition-of-Done display, assembled ONCE for every front-end.

The Definition-of-Done-and-Proof-of-Done clause of `SPECIFICATION/contracts.md`
(v115) gives `capture-work-item`, `capture-impl-gaps`, `groom` and the `plan`
front-end the same duty: display, before the filing is confirmed, "the
effective-criteria parse, each assertion with its proof mode, the sandbox
capabilities it resolved ... and every Definition-of-Done finding the host-side
wall can detect", and display `definition-of-done: missing` when the filer
declines the section.

WHY THIS IS ONE PRIMITIVE RATHER THAN FOUR PASSAGES OF PROSE. Four front-ends
owe the identical display, and prose is the one place a requirement cannot be
kept in lockstep: a rule added to the clause would land in whichever file the
next author happened to open, and the three that missed it would still read as
complete. A filer who sees a different display at capture than at groom cannot
tell which surface is behind.

WHY IT RETURNS TEXT AND NEVER WRITES OR REFUSES. "Filing stays consent-gated and
a front-end MUST NOT refuse on a finding." So every arm here renders a LINE,
including the two that are configuration faults rather than item faults: a
malformed `dispatcher.sandbox_capabilities` mirror and an unreadable
`.livespec.jsonc` both produce a capability line saying so. Raising there would
turn an advisory surface into a refusal on an environment fault — and the filer
whose filing was refused is not the person who can fix the config.

WHY THE TWO KINDS OF FINDING ARE LABELLED RATHER THAN MERGED. The consequence
differs: a mechanical finding withholds `ready` at intake and an advisory one is
forbidden to. A display that merged them would leave the filer unable to tell
which of the two is holding the item out of the queue, which is the only question
the display exists to answer about findings.

WHY A LEGACY SOURCE RENDERS `undeclared` RATHER THAN THE DEFAULT MODE. An item
resolved from the criteria field or an "Exit criteria" section declared no mode
at all, and `EffectiveCriteria` keeps that distinguishable from declaring every
assertion `factory_captured` on purpose. Rendering the default would tell a filer
their assertion already carries a mode, which is exactly the reading that stops
them authoring the section the marker on the same line is asking for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_advisories import (
    advisory_definition_of_done_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_findings import (
    definition_of_done_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    EffectiveCriteria,
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_capabilities import (
    UNPUBLISHED_REPORT,
    mirrored_sandbox_capabilities,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import LivespecConfigUnreadableError

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "ADVISORY_FINDING_PREFIX",
    "CAPABILITIES_PREFIX",
    "FINDINGS_NONE_REPORT",
    "MECHANICAL_FINDING_PREFIX",
    "NO_ASSERTIONS_REPORT",
    "UNDECLARED_PROOF_MODE_REPORT",
    "filing_display",
]

# The capability line's leader. It matches the prefix of `UNPUBLISHED_REPORT`,
# which the clause spells out, so every arm of the capability answer renders on
# one greppable line shape rather than three unrelated sentences.
CAPABILITIES_PREFIX = "sandbox-capabilities:"
# What a present-but-unusable mirror and an unreadable configuration file render.
# Both are CONFIGURATION faults rather than item faults, and both are shown
# instead of raised.
_CAPABILITIES_UNUSABLE = "declared but unusable"
_CAPABILITIES_UNREADABLE = "unreadable"
# The two finding leaders, which carry the KIND because the consequence differs.
MECHANICAL_FINDING_PREFIX = "definition-of-done finding (mechanical):"
ADVISORY_FINDING_PREFIX = "definition-of-done finding (advisory):"
# What a clean item renders. An absent line would be indistinguishable from a
# display that simply never looked.
FINDINGS_NONE_REPORT = "definition-of-done findings: none"
# What an item with no gradeable assertion renders, for the same reason.
NO_ASSERTIONS_REPORT = "assertions: none"
# The mode an assertion from a LEGACY source carries, which is none.
UNDECLARED_PROOF_MODE_REPORT = "undeclared"


def filing_display(*, item: WorkItem, cwd: Path) -> str:
    """The whole pre-confirmation display for one item, as lines of text.

    The parse line is FIRST and unconditional, because it is the line that says
    whether the Definition of Done section was read at all — and it carries the
    `definition-of-done: missing` marker for an item that declined it.
    """
    resolved = effective_criteria(item=item)
    lines = [resolved.parse_display()]
    lines.extend(_assertion_lines(criteria=resolved))
    lines.append(_capability_line(cwd=cwd))
    lines.extend(_finding_lines(item=item, cwd=cwd))
    return "\n".join(lines)


def _assertion_lines(*, criteria: EffectiveCriteria) -> list[str]:
    """One line per assertion, numbered from one, each naming its declared mode."""
    if not criteria.assertions:
        return [NO_ASSERTIONS_REPORT]
    return [
        _assertion_line(criteria=criteria, index=index) for index in range(len(criteria.assertions))
    ]


def _assertion_line(*, criteria: EffectiveCriteria, index: int) -> str:
    """One assertion's display line, numbered from one and naming its mode."""
    mode = _mode(criteria=criteria, index=index)
    text = _one_line(text=criteria.assertions[index])
    return f"assertion {index + 1} (proof mode: {mode}): {text}"


def _mode(*, criteria: EffectiveCriteria, index: int) -> str:
    """The mode the assertion at one position declared, or the undeclared report.

    `proof_modes` is EITHER empty or parallel to `assertions`, so a bounds test is
    the whole of the legacy case and no second flag is needed to detect it.
    """
    if index >= len(criteria.proof_modes):
        return UNDECLARED_PROOF_MODE_REPORT
    return criteria.proof_modes[index]


def _one_line(*, text: str) -> str:
    """One assertion collapsed onto a single display line.

    A wrapped bullet reaches here with its newlines intact, and a multi-line
    entry would break the per-line pairing of assertion to mode that is the
    display's whole contribution.
    """
    return " ".join(text.split())


def _capability_line(*, cwd: Path) -> str:
    """The resolved capability mirror, or the ratified report for each other arm."""
    read = attempt(
        action=lambda: dispatcher_block(cwd=cwd), exceptions=(LivespecConfigUnreadableError,)
    )
    if isinstance(read, AttemptFailure):
        return f"{CAPABILITIES_PREFIX} {_CAPABILITIES_UNREADABLE} — {read.error}"
    resolved = mirrored_sandbox_capabilities(block=read)
    if isinstance(resolved, str):
        return f"{CAPABILITIES_PREFIX} {_CAPABILITIES_UNUSABLE} — {resolved}"
    if not resolved:
        return UNPUBLISHED_REPORT
    return f"{CAPABILITIES_PREFIX} {', '.join(resolved)}"


def _finding_lines(*, item: WorkItem, cwd: Path) -> list[str]:
    """Every finding the host-side wall can detect, labelled by kind.

    The mechanical ones lead, because they are the ones that withhold `ready`: a
    filer reading top to bottom meets the blocking repair before the advisory one.
    """
    lines = [
        f"{MECHANICAL_FINDING_PREFIX} {finding}"
        for finding in definition_of_done_findings(item=item, cwd=cwd)
    ]
    lines.extend(
        f"{ADVISORY_FINDING_PREFIX} {finding}"
        for finding in advisory_definition_of_done_findings(item=item, cwd=cwd)
    )
    if not lines:
        return [FINDINGS_NONE_REPORT]
    return lines
