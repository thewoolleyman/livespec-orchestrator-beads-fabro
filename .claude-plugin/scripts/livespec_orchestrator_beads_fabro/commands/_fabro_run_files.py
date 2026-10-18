"""The changed files a factory server still holds for one run.

A run's work tree survives its container: the Petri engine keeps it under the
server's own run directory, and the server serves it over
`GET /api/v1/runs/<id>/files`. That is the ONLY route to the work of a run that
ended on a failed engine checkpoint, because the checkpoint is what would have
committed it and no stage diff artifact carries a failed node's tree.

THE SHAPE THE DEPLOYED SERVER SERVES IS MEASURED, and it is NESTED. Read on hp
:32276 on 2026-10-18 through `FabroHttpPort.run_files` against run
01M57JEFQH7KJG4WVS0BFR82KA (HTTP 200, 601960 bytes, four committed changes):
the response is `data` plus `meta`; each entry carries `change_kind`, a
`new_file` object and an `old_file` object, each of those holding `name` and
`contents`; and an entry has NO top-level `path`, `name` or `content` key at
all. `meta` carries `scope` (`committed`) and `source` (where the server read
from -- `sandbox` on that run, `final_patch` on another), which is why both are
carried out of here and named on the ledger comment: the first real
checkpoint-failed ending is the only thing that can say whether UNCOMMITTED
work is served, and a record that did not name the scope could not be asked.

The reader was written before that measurement and keyed on the top level
alone, so it returned `RunFilesUnreadable` for every real run -- which wrote
the "tree was NOT preserved" comment and published nothing, reporting a parse
failure rather than the shape mismatch behind it.

THE TOLERANT TOP-LEVEL READINGS ARE KEPT BESIDE THE MEASURED ONE, AND THE
MEASURED ONE WINS. The two are disjoint on every shape seen so far, and a
container or an entry neither can read still becomes `RunFilesUnreadable`
naming what it saw. Fail-closed is the right direction here: an unreadable read
writes a ledger comment saying the tree was NOT preserved, while a parse that
silently dropped entries it did not recognize would publish a ref whose tree
disagrees with the run -- a recovery artifact that misreports the work, which
is worse than none.

A REMOVAL IS `content is None`, WHICH IS NOT EMPTY CONTENT. A run that truncated
a file reports zero bytes and a run that deleted it reports no content at all;
the tree entry each produces is different (a blob against a JSON null), so
collapsing the two would publish the deleted file as an empty one.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpPort
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "RunFile",
    "RunFiles",
    "RunFilesUnreadable",
    "read_run_files",
    "run_files_from_payload",
]

# The mode a tree entry takes when the factory reported none. Duplicated from
# no other module: the publication reads it off the `RunFile` it is handed, so
# the default belongs where the reading happens.
_DEFAULT_MODE = "100644"

_CONTAINER_KEYS = ("data", "files")
_PATH_KEYS = ("path", "name")
_CONTENT_KEYS = ("content", "contents", "text")
_REMOVAL_FLAGS = ("deleted", "removed")
_REMOVAL_STATES = ("deleted", "removed")
_STATE_KEYS = ("status", "change", "change_kind")
_BASE64 = "base64"
_MODE_LENGTH = 6

# The measured nesting. `_NEW_FILE` is read for a path BEFORE `_OLD_FILE`, and
# an empty name is passed over rather than taken: an ADDED entry carries
# `old_file.name` as the empty string, which read as a path would publish a
# blob at the repository root.
_NEW_FILE = "new_file"
_OLD_FILE = "old_file"
_NESTED_PATH_KEY = "name"
_NESTED_CONTENT_KEY = "contents"

# The response's own account of what it served. Carried out of here unchanged,
# including a reading that is absent.
_META_KEY = "meta"
_META_SCOPE_KEY = "scope"
_META_SOURCE_KEY = "source"

_READ_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True, kw_only=True)
class RunFile:
    """One file a run changed, as the factory reports it."""

    path: str
    content: bytes | None
    mode: str


@dataclass(frozen=True, kw_only=True)
class RunFiles:
    """Every file the run changed, with the bytes it left in each.

    `scope` and `source` are the server's OWN account of what it served, read
    off the response's `meta` and never derived: the scope says which tree it
    answered from and the source says where it read it. Both are optional
    because a response that carries no readable `meta` has said neither, and
    both are REQUIRED arguments for the reason `_dispatcher_sandbox_image_
    source` gives about its own record -- a default is how one read silently
    reports the no-declaration answer for a read that did declare one.
    """

    files: tuple[RunFile, ...]
    scope: str | None
    source: str | None


@dataclass(frozen=True, kw_only=True)
class RunFilesUnreadable:
    """The read did not happen, or its answer could not be understood."""

    detail: str


def read_run_files(
    *,
    port: FabroHttpPort,
    run_id: str,
    timeout_seconds: float = _READ_TIMEOUT_SECONDS,
) -> RunFiles | RunFilesUnreadable:
    """Ask ONE named factory for the changed files of ONE run.

    The port arrives already built from the dispatch's resolved factory target,
    never constructed here: a reader that built its own would ask whichever
    server a default named, which is the wrong-population trap this fleet's own
    catalogue records against a bare `fabro ps`.
    """
    result = port.run_files(run_id=run_id, timeout_seconds=timeout_seconds)
    if not result.succeeded:
        return RunFilesUnreadable(
            detail=(
                f"the factory's run-files read for {run_id} returned status"
                f" {result.status}: {result.error or result.body.strip() or 'no body'}"
            )
        )
    return run_files_from_payload(payload=result.payload)


def run_files_from_payload(*, payload: object) -> RunFiles | RunFilesUnreadable:
    """What one run-files response says the run changed. PURE."""
    entries = _entries(payload=payload)
    if entries is None:
        return RunFilesUnreadable(
            detail=(
                "the factory's run-files response carried no list of changed files"
                f" under any of {', '.join(_CONTAINER_KEYS)} or at its top level"
            )
        )
    files: list[RunFile] = []
    for entry in entries:
        read = _run_file(entry=entry)
        if isinstance(read, RunFilesUnreadable):
            return read
        files.append(read)
    scope, source = _served(payload=payload)
    return RunFiles(files=tuple(files), scope=scope, source=source)


def _served(*, payload: object) -> tuple[str | None, str | None]:
    """What the response's `meta` says it served, and from where.

    An unreadable or absent `meta` yields two absences rather than a refusal:
    the scope and the source are PROVENANCE the comment reports, not inputs the
    publication needs, so a response that named neither still carries a tree
    worth preserving.
    """
    if not isinstance(payload, dict):
        return (None, None)
    held = cast("dict[object, object]", payload).get(_META_KEY)
    if not isinstance(held, dict):
        return (None, None)
    meta = cast("dict[object, object]", held)
    return (
        _first_string(mapping=meta, keys=(_META_SCOPE_KEY,)),
        _first_string(mapping=meta, keys=(_META_SOURCE_KEY,)),
    )


def _entries(*, payload: object) -> tuple[object, ...] | None:
    """The response's list of changed files, however it chose to carry it."""
    if isinstance(payload, list):
        return tuple(cast("list[object]", payload))
    if not isinstance(payload, dict):
        return None
    mapping = cast("dict[object, object]", payload)
    for key in _CONTAINER_KEYS:
        held = mapping.get(key)
        if isinstance(held, list):
            return tuple(cast("list[object]", held))
    return None


def _run_file(*, entry: object) -> RunFile | RunFilesUnreadable:
    """One entry read as a changed file, or the reason it could not be."""
    if not isinstance(entry, dict):
        return RunFilesUnreadable(
            detail=f"a run-files entry was {type(entry).__name__} rather than an object"
        )
    mapping = cast("dict[object, object]", entry)
    path = _path(mapping=mapping)
    if path is None:
        return RunFilesUnreadable(
            detail=(
                "a run-files entry named no path under"
                f" {_NEW_FILE}.{_NESTED_PATH_KEY}, {_OLD_FILE}.{_NESTED_PATH_KEY}"
                f" or any of {', '.join(_PATH_KEYS)}"
            )
        )
    mode = _mode(mapping=mapping)
    if _removed(mapping=mapping):
        return RunFile(path=path, content=None, mode=mode)
    return _with_content(mapping=mapping, path=path, mode=mode)


def _path(*, mapping: dict[object, object]) -> str | None:
    """The path one entry names, in the MEASURED nesting first.

    `_OLD_FILE` is the fallback rather than an equal, because for every entry
    that has both they agree, and where they differ -- a removal, or a rename --
    the new name is the one the published tree must carry.
    """
    for key in (_NEW_FILE, _OLD_FILE):
        nested = _nested_string(mapping=mapping, key=key, field=_NESTED_PATH_KEY)
        if nested:
            return nested
    return _first_string(mapping=mapping, keys=_PATH_KEYS)


def _nested_string(*, mapping: dict[object, object], key: str, field: str) -> str | None:
    """One string `field` of the object `mapping` nests under `key`."""
    held = mapping.get(key)
    if not isinstance(held, dict):
        return None
    return _first_string(mapping=cast("dict[object, object]", held), keys=(field,))


def _with_content(
    *, mapping: dict[object, object], path: str, mode: str
) -> RunFile | RunFilesUnreadable:
    """Decode the bytes one entry reports for `path`."""
    held = _content_text(mapping=mapping)
    if held is None:
        return RunFilesUnreadable(
            detail=(
                f"the run-files entry for {path} is neither a removal nor carries content"
                f" under {_NEW_FILE}.{_NESTED_CONTENT_KEY}"
                f" or any of {', '.join(_CONTENT_KEYS)}"
            )
        )
    if mapping.get("encoding") != _BASE64:
        return RunFile(path=path, content=held.encode("utf-8"), mode=mode)
    decoded = attempt(
        action=lambda: base64.b64decode(held, validate=True),
        exceptions=(binascii.Error, ValueError),
    )
    if isinstance(decoded, AttemptFailure):
        return RunFilesUnreadable(
            detail=f"the run-files entry for {path} declared base64 content that does not decode"
        )
    return RunFile(path=path, content=decoded, mode=mode)


def _content_text(*, mapping: dict[object, object]) -> str | None:
    """The bytes one entry reports, in the MEASURED nesting first."""
    nested = _nested_string(mapping=mapping, key=_NEW_FILE, field=_NESTED_CONTENT_KEY)
    if nested is not None:
        return nested
    return _first_string(mapping=mapping, keys=_CONTENT_KEYS)


def _removed(*, mapping: dict[object, object]) -> bool:
    """Whether the entry says the run DELETED the path.

    THIS ARM IS THE ONE PART OF THE MEASURED SHAPE THAT IS STILL UNMEASURED.
    The 2026-10-18 control read carried `change_kind` values `modified` and
    `added` and no removal at all, so neither the word the server spells a
    deletion with nor what it puts in `new_file` for one was observed. Both
    plausible spellings are therefore read: a `change_kind` (or either older
    state key) naming a deletion, and a `new_file` of JSON null.

    EVERY SPELLING IS READ RATHER THAN ONE BEING CHOSEN, because a removal
    misread as content publishes the deleted file back into the preservation
    tree and a file being PRESENT looks like the normal case -- while the
    mirror error drops a file from the tree, which shows up the first time
    anyone opens it.
    """
    if any(mapping.get(flag) is True for flag in _REMOVAL_FLAGS):
        return True
    if _NEW_FILE in mapping and mapping[_NEW_FILE] is None:
        return True
    for key in _STATE_KEYS:
        state = mapping.get(key)
        if isinstance(state, str) and state.lower() in _REMOVAL_STATES:
            return True
    return False


def _mode(*, mapping: dict[object, object]) -> str:
    """The entry's own file mode when it reads as one, else the regular-file mode."""
    declared = mapping.get("mode")
    if isinstance(declared, str) and len(declared) == _MODE_LENGTH and declared.isdigit():
        return declared
    return _DEFAULT_MODE


def _first_string(*, mapping: dict[object, object], keys: tuple[str, ...]) -> str | None:
    """The first of `keys` the entry carries as a string."""
    for key in keys:
        held = mapping.get(key)
        if isinstance(held, str):
            return held
    return None
