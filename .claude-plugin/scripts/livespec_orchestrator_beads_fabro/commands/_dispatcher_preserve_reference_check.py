"""Re-read a preserved pointer and check whether it still resolves.

A preserve-by-reference pointer is a PROMISE that a failed or blocked
run's work is still retrievable from the factory. Nothing re-read one: a
search for the pointer marker across the production tree returned only
the module that WROTE it. So a pointer could go dangling — the run
pruned, the factory replaced — and sit on the ledger reading exactly like
a live one, because a pointer's text is identical either way.

This module is the missing reader. It parses a body written by
`_dispatcher_preserve_reference_body` and re-runs the export the pointer
itself prints, reporting one of three states:

- `intact` — the export resolves and every recorded digest still matches
  the bytes it returns.
- `dangling` — the export no longer resolves, or it does and a recorded
  artifact is absent or its bytes no longer match the recorded digest.
- `unverifiable` — the export resolves but the pointer carries no digest
  to check it against.

`unverifiable` is deliberately a THIRD state rather than a charitable
`intact`. A pointer written after a failed export has no digest by
construction, so folding that case into `intact` would report the
weakest pointers in the store as the strongest — the precise silence
this module exists to end.
"""

from __future__ import annotations

import hashlib
import string
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_body import (
    DIGEST_UNAVAILABLE_PREFIX,
    PRESERVE_POINTER_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "POINTER_DANGLING",
    "POINTER_INTACT",
    "POINTER_UNVERIFIABLE",
    "PointerCheck",
    "PreservedPointer",
    "PreservedPointerArtifact",
    "check_preserved_pointer",
    "parse_preserved_pointer",
]

POINTER_INTACT = "intact"
POINTER_DANGLING = "dangling"
POINTER_UNVERIFIABLE = "unverifiable"

_DUMP_TIMEOUT_SECONDS = 300.0
_RUN_ID_PREFIX = "run id: "
_SERVER_URL_PREFIX = "factory server url: "
_ARTIFACT_PATH_PREFIX = "stage artifact path: "
_DIGEST_PREFIX = "sha256: "
_SHA256_LENGTH = 64
_HEX_CHARS = frozenset(string.hexdigits)


@dataclass(frozen=True, kw_only=True)
class PreservedPointerArtifact:
    """One export-relative artifact path and the sha256 recorded for it."""

    path: str
    digest: str


@dataclass(frozen=True, kw_only=True)
class PreservedPointer:
    """The machine-readable content of a pointer body.

    `artifacts` holds only entries carrying a REAL digest, so a caller
    cannot accidentally verify against a placeholder;
    `digest_unavailable_reason` carries the writer's explanation when
    there is none.
    """

    run_id: str
    server_url: str
    artifacts: tuple[PreservedPointerArtifact, ...]
    digest_unavailable_reason: str | None


@dataclass(frozen=True, kw_only=True)
class PointerCheck:
    """The verdict on one pointer: `state` plus why it was reached."""

    state: str
    detail: str


def parse_preserved_pointer(*, body: str) -> PreservedPointer | None:
    """Parse a pointer body; None when the text is not a pointer.

    None means "this comment is not a preserve-by-reference pointer" — a
    ledger carries many other comments — and is never a verdict about the
    referenced work.
    """
    lines = [line.strip() for line in body.splitlines()]
    if not lines or lines[0] != PRESERVE_POINTER_MARKER:
        return None
    run_id = _first_value(lines=lines, prefix=_RUN_ID_PREFIX)
    server_url = _first_value(lines=lines, prefix=_SERVER_URL_PREFIX)
    if run_id is None or server_url is None:
        return None
    paths = _all_values(lines=lines, prefix=_ARTIFACT_PATH_PREFIX)
    digests = _all_values(lines=lines, prefix=_DIGEST_PREFIX)
    return PreservedPointer(
        run_id=run_id,
        server_url=server_url,
        artifacts=tuple(
            PreservedPointerArtifact(path=path, digest=digest)
            # `strict=False` on purpose: the writer always emits a digest line
            # per path, but this reads text off a LEDGER COMMENT, which a human
            # can truncate or hand-edit. Pairing what is there beats raising on
            # a pointer that is merely damaged.
            for path, digest in zip(paths, digests, strict=False)
            if _is_sha256(value=digest)
        ),
        digest_unavailable_reason=_first_value(lines=lines, prefix=DIGEST_UNAVAILABLE_PREFIX),
    )


def check_preserved_pointer(
    *,
    pointer: PreservedPointer,
    repo: Path,
    fabro_bin: str,
    runner: CommandRunner,
) -> PointerCheck:
    """Re-export the pointer's run and report whether it still resolves.

    The re-export goes through a `FabroPort` built from the pointer's OWN
    recorded server url, which is what makes this a check of the promise the
    pointer made rather than of whatever factory happens to be configured now.
    """
    port = FabroPort(
        fabro_bin=fabro_bin,
        target=FabroTarget(server_url=pointer.server_url),
        runner=runner,
        cwd=repo,
    )
    with tempfile.TemporaryDirectory(prefix=f"fabro-pointer-check-{pointer.run_id}-") as raw_dir:
        export_dir = Path(raw_dir)
        dumped = port.dump(
            run_id=pointer.run_id,
            output_dir=export_dir,
            timeout_seconds=_DUMP_TIMEOUT_SECONDS,
        ).command
        if dumped.exit_code != 0:
            return PointerCheck(
                state=POINTER_DANGLING,
                detail=(
                    f"run {pointer.run_id} no longer exports from {pointer.server_url} "
                    f"(fabro dump exit {dumped.exit_code})"
                ),
            )
        if not pointer.artifacts:
            return PointerCheck(
                state=POINTER_UNVERIFIABLE,
                detail=(
                    f"run {pointer.run_id} still exports, but the pointer recorded no "
                    f"digest to verify it against: "
                    f"{pointer.digest_unavailable_reason or 'no reason recorded'}"
                ),
            )
        return _verify_recorded_digests(pointer=pointer, export_dir=export_dir)


def _verify_recorded_digests(*, pointer: PreservedPointer, export_dir: Path) -> PointerCheck:
    for artifact in pointer.artifacts:
        path = export_dir / artifact.path
        if not path.is_file():
            return PointerCheck(
                state=POINTER_DANGLING,
                detail=f"run {pointer.run_id} exports, but no longer contains {artifact.path}",
            )
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.digest:
            return PointerCheck(
                state=POINTER_DANGLING,
                detail=(
                    f"{artifact.path} re-exported with bytes that do not match the "
                    f"recorded sha256 {artifact.digest}"
                ),
            )
    return PointerCheck(
        state=POINTER_INTACT,
        detail=(
            f"run {pointer.run_id} re-exported {len(pointer.artifacts)} recorded "
            f"artifact(s), every sha256 matching"
        ),
    )


def _first_value(*, lines: list[str], prefix: str) -> str | None:
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None


def _all_values(*, lines: list[str], prefix: str) -> list[str]:
    return [line[len(prefix) :] for line in lines if line.startswith(prefix)]


def _is_sha256(*, value: str) -> bool:
    return len(value) == _SHA256_LENGTH and set(value) <= _HEX_CHARS
