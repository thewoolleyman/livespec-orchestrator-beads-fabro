"""The `generator` key of a committed `dispatcher.record_files` entry, as graded.

The declared-record-file clause of `SPECIFICATION/contracts.md` says that "Any
entry MAY also name `generator`, a non-empty argv array run from the repository
root that rewrites the file at `path` from the repository's tree", and that "A
file whose entry names a generator is a GENERATED record file. Its correct
content is its generator's output over the tree it sits in, so a conflict in it
is never resolved by merging its text, on any route." This module is the
configuration surface that admits such a declaration: until it existed, nothing
read the key, so no repository could declare a generated record file at all.

THREE OUTCOMES, AND KEEPING THEM THREE IS THE JOB — the same
answer-or-finding-or-absent shape `_dispatcher_overflow_factories` uses, for the
same reason. An ABSENT or EMPTY array declares no record files, which the clause
states outright and which is an answer rather than a fault. A malformed
`generator` is a refusal that must land before any refresh could run it. A
well-formed array is the declaration. So the return type is
`tuple[tuple[str, ...] | None, ...] | str | None`.

WHY THE RESOLUTION IS POSITIONAL, AND SAYS NOTHING ABOUT `path` OR `format`. The
same ratified paragraph governs the entry-wise merge of Scenario 200, whose
`path` / `format` / `key` parse is a separate TODO owned by work-item
bd-ib-davaxq and is not implemented anywhere. A reader that graded those keys
here would become a second authority on the entry grammar, and the two would
drift in the direction nothing announces: both would keep producing a
well-formed entry list. So each slot carries ONE entry's generator argv, or
`None` where that entry declares none, and a consumer joins those positions with
the full entry parse that item adds.

WHY AN ENTRY THAT NAMES NO GENERATOR IS ACCEPTED RATHER THAN DEFAULTED. The
clause makes the key optional — a record file that no generator rewrites is the
ordinary case, and is exactly what the entry-wise merge applies to — so an entry
declaring none is an answer. `None` in a slot and a refusal are therefore
different outcomes, and collapsing them would refuse every repository that
declares a record file at all.

WHY THERE IS NO PARTIALLY-PARSED VARIANT. A refused declaration yields the
finding and nothing else, never the slots that happened to parse. The refusal
exists to precede a refresh that would otherwise RUN one of these commands, and a
list assembled from the survivors would read exactly like a healthy one.

WHY EVERY REFUSAL NAMES THE POSITION AS WELL AS THE KEY. `record_files` is an
array an operator may have written several entries into, and only one of them is
the offence. A message naming `dispatcher.record_files.generator` would leave the
operator to read the whole array back and guess which entry it meant.

WHAT IS DELIBERATELY NOT GRADED, so a later reader does not mistake it for an
oversight. The clause calls the value "a non-empty argv array run from the
repository root", and an argv whose program name is the empty string cannot be
run, so an empty token is refused here as conformance to that wording. Whether
the first token RESOLVES to an executable is not graded: the argv runs in the
sandbox clone against that tree, and a host-side resolution would be a reading
taken on the wrong machine.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block

__all__: list[str] = [
    "GENERATOR_KEY",
    "RECORD_FILES_KEY",
    "record_file_generators_refusal",
    "resolve_record_file_generators",
]

RECORD_FILES_KEY = "record_files"
GENERATOR_KEY = "generator"
_CONFIG_PREFIX = f"dispatcher.{RECORD_FILES_KEY}"


def resolve_record_file_generators(*, cwd: Path) -> tuple[tuple[str, ...] | None, ...] | str | None:
    """One slot per declared entry, a finding, or `None` when none are declared.

    An EMPTY array answers `None` beside an absent key, because the clause names
    the absent case as declaring no record files and an empty one declares the
    same nothing. A reader testing only for the key's presence would report a
    declaration of zero entries, which is the same answer reached a way that
    cannot be told apart from a parse that silently dropped the content.
    """
    block = dispatcher_block(cwd=cwd)
    raw = block.get(RECORD_FILES_KEY)
    if raw is None:
        return None
    if not isinstance(raw, list):
        return _finding(key=_CONFIG_PREFIX, detail=f"is not an array: {raw!r}")
    entries = cast("list[object]", raw)
    if not entries:
        return None
    return _graded_entries(entries=entries)


def record_file_generators_refusal(*, repo: Path) -> str | None:
    """The pre-dispatch refusal a malformed declaration earns, or `None`.

    Shaped as the dispatch preamble's other configuration refusals are — a
    message to report and short-circuit on, or `None` — so the key is graded in
    the same pass that grades the overflow array and the resolved factory's own
    declarations, and by the same convention.
    """
    resolved = resolve_record_file_generators(cwd=repo)
    if not isinstance(resolved, str):
        return None
    return (
        f"ERROR: {resolved}. A declared record file's generator is the argv a"
        " refresh runs from the repository root to rewrite that file, so a"
        " declaration naming anything other than a non-empty argv array has no"
        " command to run; this dispatch is refused before any item is claimed"
        " rather than reaching a refresh that would resolve a conflict in that"
        " file by merging its text\n"
    )


def _graded_entries(*, entries: list[object]) -> tuple[tuple[str, ...] | None, ...] | str:
    """Every entry graded in declaration order; the first fault wins."""
    graded: list[tuple[str, ...] | None] = []
    for position, entry in enumerate(entries):
        finding = _entry_finding(entry=entry, position=position)
        if finding is not None:
            return finding
        graded.append(_entry_generator(entry=cast("dict[str, object]", entry)))
    return tuple(graded)


def _entry_finding(*, entry: object, position: int) -> str | None:
    """Why one entry's `generator` violates the clause, or `None` when it does not.

    An entry that is not an object has no `generator` key to read, so it is
    reported at the ENTRY's own position rather than at a key it does not carry —
    naming a `generator` on a value that cannot hold one would send an operator
    looking for a key that is not there.
    """
    key = f"{_CONFIG_PREFIX}[{position}]"
    if not isinstance(entry, dict):
        return _finding(key=key, detail=f"is not an object: {entry!r}")
    raw = cast("dict[str, object]", entry).get(GENERATOR_KEY)
    if raw is None:
        return None
    if _is_argv(raw=raw):
        return None
    return _finding(
        key=f"{key}.{GENERATOR_KEY}",
        detail=f"is not a non-empty array of non-empty strings: {raw!r}",
    )


def _entry_generator(*, entry: dict[str, object]) -> tuple[str, ...] | None:
    """One already-graded entry's generator argv, or `None` when it declares none."""
    raw = entry.get(GENERATOR_KEY)
    if raw is None:
        return None
    return tuple(cast("list[str]", raw))


def _is_argv(*, raw: object) -> bool:
    """Whether one value is the non-empty argv array of strings the clause admits."""
    if not isinstance(raw, list) or not raw:
        return False
    return all(isinstance(token, str) and token != "" for token in cast("list[object]", raw))


def _finding(*, key: str, detail: str) -> str:
    return f"configuration finding: {key} {detail}"
