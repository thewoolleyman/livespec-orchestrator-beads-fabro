"""What a FAILED post-merge janitor command leaves behind for diagnosis.

A post-merge janitor's journal row carries a BOUNDED EXCERPT of the one stream
its exit code selected, which is enough to see that the janitor was red and not
enough to see WHY. The failing target of an aggregate check suite is named once,
often on whichever stream the excerpt did not keep, and the disposable checkout
the janitor ran in is the only other place that diagnosis ever lived. Measured
on the reconcile-merged gate of 2026-10-07: the retained journal carried no
failing-check traceback at all, so the cause of a red post-merge janitor on an
already-merged item could not be established from the record.

So a non-zero janitor command retains EVERYTHING the runner captured, as a
private artifact beside the dispatch journal, and the row names that artifact's
path and the sha256 of its bytes. The row keeps its excerpt exactly as it was:
the artifact is what survives the checkout's removal, not a second copy of the
excerpt, and no journal row grows a stream it did not already carry.

The retention-clause of `SPECIFICATION/contracts.md` governs, and Scenario 145
exercises it. The runner's `CommandResult` carries no signal or timeout field of
its own -- a timeout arrives as a non-zero exit code carrying its own stderr --
so that clause's conditional `signal` / `timed_out` keys have nothing here to
report and are absent rather than invented.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

__all__: list[str] = [
    "JanitorRetention",
    "janitor_retention",
    "retained_output_record",
]

# The one directory every retained artifact lives in, created under the
# directory that already holds the dispatch journal. Deliberately NOT inside
# the janitor checkout: that checkout is disposable, and the whole point of the
# artifact is to outlive it.
_ARTIFACT_DIRECTORY_NAME = "janitor-failed-output"

# Owner-only, so the artifact is private to the invocation that wrote it. Set
# through `fchmod` on the open descriptor rather than by moving the process
# umask, which is process-global state every later child would inherit. An
# observation that changed its subject would not be an observation.
_ARTIFACT_MODE = 0o600


@dataclass(frozen=True, kw_only=True)
class JanitorRetention:
    """WHERE a failed janitor command's complete output is retained, and under which key.

    `directory` is the directory that holds the dispatch journal, so the
    artifact lands beside the record that names it and lives as long as that
    record does. `invocation` is the dispatch id on the dispatch path and the
    `reconcile-merged` invocation's own journaled identifier under that valve --
    an identity, never a work-item id, because two dispatches of one item must
    not retain into one another's evidence.
    """

    directory: Path
    invocation: str


def janitor_retention(*, directory: Path, invocation: str | None) -> JanitorRetention | None:
    """The retention venue for an invocation, or None when it has no identity.

    An invocation that minted no identity resolves NO venue rather than a venue
    keyed on something else: a fallback key -- the work-item id, a timestamp --
    would make two invocations' artifacts indistinguishable, which is the exact
    confusion the unique path exists to prevent. Its janitor rows then carry
    their bounded excerpt alone, which is what they carried before this clause.
    """
    if invocation is None:
        return None
    return JanitorRetention(directory=directory, invocation=invocation)


def retained_output_record(
    *, retention: JanitorRetention, stage: str, result: CommandResult
) -> dict[str, object]:
    """The journal-row fields naming what this stage's failure retained."""
    payload = _artifact_payload(result=result)
    written = _write_artifact(retention=retention, stage=stage, payload=payload)
    return {
        "retained_output_path": str(written),
        "retained_output_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _artifact_payload(*, result: CommandResult) -> bytes:
    """The artifact's exact bytes, which are also what the row's digest covers.

    Built once and both written and hashed, so the digest a reader checks the
    file against cannot be computed over a different serialization than the one
    that reached the disk.
    """
    document = {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    return (json.dumps(document, sort_keys=True) + "\n").encode()


def _write_artifact(*, retention: JanitorRetention, stage: str, payload: bytes) -> Path:
    """The path the artifact was written to.

    The name carries the invocation, the stage and a PER-RETENTION token, in
    that order, so an operator reading a journal row can find the file by the
    two identities the row already gave them while a second retention of the
    same stage still gets its own path. A stage-keyed name would make the
    second failure of a retried janitor replace the first failure's evidence,
    which is the one occasion where both copies matter. `O_EXCL` is the belt on
    that: a name that somehow already exists is a failure to write, never a
    silent replacement.
    """
    name = f"{retention.invocation}-{stage}-{uuid.uuid4().hex}.json"
    path = retention.directory / _ARTIFACT_DIRECTORY_NAME / name
    _create_artifact(path=path, payload=payload)
    return path


def _create_artifact(*, path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, _ARTIFACT_MODE)
    with os.fdopen(descriptor, "wb") as handle:
        os.fchmod(handle.fileno(), _ARTIFACT_MODE)
        _ = handle.write(payload)
