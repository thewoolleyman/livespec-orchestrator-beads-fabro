"""The committed-only `dispatcher.overflow_factories` array, read and graded.

The factory-overflow-selection clause of `SPECIFICATION/contracts.md` gives this
key THREE outcomes, and keeping them three is the whole job of this module — the
same answer-or-finding-or-absent shape `_dispatcher_idle_slot_config` uses, for
the same reason. An ABSENT or EMPTY array means overflow selection is not
configured, which is an answer rather than a fault: selection is then exactly
the registry section's order and nothing in the overflow section applies. A
VIOLATING entry is a refusal that must land before any item is claimed. A
well-formed array is the candidate list.

So the return type is `tuple[str, ...] | str | None`: the declared entries, a
finding string, or `None` for absent. There is deliberately no
partially-parsed variant — `overflow_candidates` yields `()` for a refused
array rather than the prefix that happened to parse, because selection is the
one act the refusal exists to precede and a list built from the surviving
entries would read exactly like a healthy one.

WHY THE KEY IS COMMITTED-ONLY. The clause says so in as many words, and the
reason is the same one `dispatcher.factories` has: which machine a dispatch
lands on is a recorded argument, not something an ad-hoc API call moves
underneath a wave that has already measured capacity. Nothing here reads the
environment, and the key is absent from `_drive_config_schema.CONFIG_KEYS`.

WHY EVERY REFUSAL NAMES THE POSITION AS WELL AS THE VALUE. Three of the four
faults are about ONE entry of an array an operator may have written several
entries into, and two of them — a repeat, and a name equal to the default — are
violations only in RELATION to something else in the same file. A message
naming neither leaves the operator to re-derive which relation broke. The
repeat names the SECOND occurrence, because the first is not the offence and a
message pointing at it would send an operator to delete the entry they meant to
keep.

WHY THE DEFAULT COMES FROM `_factory_default` AND NOT FROM
`resolve_fabro_factory`. The obvious reader is the wrong one: it consults
`LIVESPEC_FABRO_FACTORY` before any configuration, and the key being graded is
committed-only. An operator who exported the overflow factory's own name would
then see the array that names the committed default ADMITTED — the one shape the
clause forbids — and would see the candidate list open with the overflow factory,
which is where a utilization tie makes it win. `configured_factory_name` answers
the same question from the block alone, and it is the same answer
`resolve_fabro_factory` reaches once its own two layers decline, so there is one
authority rather than two.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
    has_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._factory_default import (
    configured_factory_name,
)

__all__: list[str] = [
    "OVERFLOW_FACTORIES_KEY",
    "overflow_candidates",
    "overflow_factories_refusal",
    "resolve_overflow_factories",
]

OVERFLOW_FACTORIES_KEY = "overflow_factories"
_CONFIG_PREFIX = f"dispatcher.{OVERFLOW_FACTORIES_KEY}"
_DEFAULT_FACTORY_KEY = "dispatcher.default_factory"


def resolve_overflow_factories(*, cwd: Path) -> tuple[str, ...] | str | None:
    """Read the committed array: the entries, a finding, or `None` when absent.

    An EMPTY array answers `None` beside an absent key, because the clause names
    the two together and they configure the same thing — nothing. An
    implementation testing only for the key's presence would read `[]` as a
    configured overflow with no entries, which is a one-candidate list and a
    capacity read nobody asked for.
    """
    block = dispatcher_block(cwd=cwd)
    raw = block.get(OVERFLOW_FACTORIES_KEY)
    if raw is None:
        return None
    if not isinstance(raw, list):
        return _finding(key=_CONFIG_PREFIX, detail=f"is not an array: {raw!r}")
    entries = cast("list[object]", raw)
    if not entries:
        return None
    return _graded_entries(cwd=cwd, entries=entries)


def overflow_factories_refusal(*, repo: Path) -> str | None:
    """The pre-claim refusal a violating array earns, or `None` to proceed.

    Shaped as the dispatch preamble's other configuration refusals are — a
    message to report and short-circuit on, or `None` — so the array is graded
    in the same pass that grades the capability mirror and the resolved
    factory's own declarations, and by the same convention.
    """
    resolved = resolve_overflow_factories(cwd=repo)
    if not isinstance(resolved, str):
        return None
    return (
        f"ERROR: {resolved}. Overflow selection reads each candidate's own Fabro"
        " server, so an entry that names no declared factory, repeats, or names"
        " the default factory has no candidate to read; this dispatch is refused"
        " before any item is claimed rather than selecting from a list it cannot"
        " act on\n"
    )


def overflow_candidates(*, cwd: Path) -> tuple[str, ...]:
    """The candidates overflow selection considers, in the clause's own order.

    `dispatcher.default_factory` first, then each declared entry. `()` means
    overflow selection does not apply — the key is absent, empty, or refused —
    and every caller reads that as "resolve the factory exactly as before".
    """
    resolved = resolve_overflow_factories(cwd=cwd)
    if not isinstance(resolved, tuple):
        return ()
    return (_default_factory(cwd=cwd), *resolved)


def _graded_entries(*, cwd: Path, entries: list[object]) -> tuple[str, ...] | str:
    """Every entry graded in declaration order; the first fault wins."""
    default = _default_factory(cwd=cwd)
    seen: list[str] = []
    for position, entry in enumerate(entries):
        finding = _entry_finding(
            cwd=cwd, entry=entry, position=position, default=default, seen=seen
        )
        if finding is not None:
            return finding
        seen.append(cast("str", entry))
    return tuple(seen)


def _entry_finding(
    *,
    cwd: Path,
    entry: object,
    position: int,
    default: str,
    seen: list[str],
) -> str | None:
    """Why one entry violates the clause, or `None` when it conforms."""
    key = f"{_CONFIG_PREFIX}[{position}]"
    if not isinstance(entry, str) or entry == "":
        return _finding(key=key, detail=f"is not a non-empty string: {entry!r}")
    if entry == default:
        return _finding(key=key, detail=f"names {_DEFAULT_FACTORY_KEY}: {entry!r}")
    if entry in seen:
        return _finding(key=key, detail=f"repeats an earlier entry: {entry!r}")
    if not has_fabro_factory(cwd=cwd, factory=entry):
        return _finding(key=key, detail=f"names no dispatcher.factories entry: {entry!r}")
    return None


def _default_factory(*, cwd: Path) -> str:
    """The configured default factory's name, with the environment excluded.

    Through `configured_factory_name` and never `resolve_fabro_factory`, which
    reads `LIVESPEC_FABRO_FACTORY` first — see the module docstring for what
    that would get wrong in both directions.
    """
    return configured_factory_name(block=dispatcher_block(cwd=cwd))


def _finding(*, key: str, detail: str) -> str:
    return f"configuration finding: {key} {detail}"
