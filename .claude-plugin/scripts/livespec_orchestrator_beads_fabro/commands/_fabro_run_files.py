"""The changed files a factory server still holds for one run.

A run's work tree survives its container: the Petri engine keeps it under the
server's own run directory, and the server serves it over
`GET /api/v1/runs/<id>/files`. That is the ONLY route to the work of a run that
ended on a failed engine checkpoint, because the checkpoint is what would have
committed it and no stage diff artifact carries a failed node's tree.

THE PARSE IS TOLERANT ON PURPOSE, AND SAYS SO RATHER THAN GUESSING. The exact
response shape is a HOST-CAPTURED assertion of `bd-ib-na2xvm` and was NOT
measured when this was written: fabro-currency measured the endpoint returning
48 changed files with full contents on a live hp-candidate run, and the
production engine answered 401 rather than 404, so the route exists on both --
but the key names were read from neither. Every reading this accepts is
therefore a shape the endpoint PLAUSIBLY uses, and a container or an entry it
cannot read becomes `RunFilesUnreadable` naming what it saw. Fail-closed is the
right direction here: an unreadable read writes a ledger comment saying the
tree was NOT preserved, while a parse that silently dropped entries it did not
recognize would publish a ref whose tree disagrees with the run -- a recovery
artifact that misreports the work, which is worse than none.

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
_STATE_KEYS = ("status", "change")
_BASE64 = "base64"
_MODE_LENGTH = 6

_READ_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True, kw_only=True)
class RunFile:
    """One file a run changed, as the factory reports it."""

    path: str
    content: bytes | None
    mode: str


@dataclass(frozen=True, kw_only=True)
class RunFiles:
    """Every file the run changed, with the bytes it left in each."""

    files: tuple[RunFile, ...]


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
    return RunFiles(files=tuple(files))


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
    path = _first_string(mapping=mapping, keys=_PATH_KEYS)
    if path is None:
        return RunFilesUnreadable(
            detail=f"a run-files entry named no path under any of {', '.join(_PATH_KEYS)}"
        )
    mode = _mode(mapping=mapping)
    if _removed(mapping=mapping):
        return RunFile(path=path, content=None, mode=mode)
    return _with_content(mapping=mapping, path=path, mode=mode)


def _with_content(
    *, mapping: dict[object, object], path: str, mode: str
) -> RunFile | RunFilesUnreadable:
    """Decode the bytes one entry reports for `path`."""
    held = _first_string(mapping=mapping, keys=_CONTENT_KEYS)
    if held is None:
        return RunFilesUnreadable(
            detail=(
                f"the run-files entry for {path} is neither a removal nor carries content"
                f" under any of {', '.join(_CONTENT_KEYS)}"
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


def _removed(*, mapping: dict[object, object]) -> bool:
    """Whether the entry says the run DELETED the path.

    Both spellings are read -- a boolean flag and a state word -- because the
    response shape is unmeasured and a removal misread as content is the one
    error that publishes a deleted file back into the tree.
    """
    if any(mapping.get(flag) is True for flag in _REMOVAL_FLAGS):
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
