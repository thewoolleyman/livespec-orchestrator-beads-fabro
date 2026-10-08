"""Fetching an attached proof and deciding whether it IS the evidence it claims.

`bd-ib-555xcd`. Once a bulky proof travels as an asset, the record no longer
CONTAINS its evidence — it contains a POINTER to it. A grading surface that read
only the record would therefore accept the assertion on the publisher's say-so,
which is precisely the property the two-leg proof chain exists to remove. So the
acceptance pass and the replay stage fetch the asset and check its digest.

WHAT CAN GO WRONG AFTER A RECORD IS WRITTEN, which is why this is not paranoia
about the publisher. The asset store is a mutable release: a later fix round
re-enters the capture stage and re-uploads the same name with `--clobber`, an
upload can truncate, a release can be pruned, and an operator can delete an asset
by hand. Every one of those leaves the RECORD perfectly intact and perfectly
readable, stating a size and a digest for bytes that are no longer there or are no
longer those bytes. The digest is the only thing that distinguishes "these are the
bytes the capture measured" from "something is at that name".

WHY THE DECISION IS PURE AND THE FETCH IS A SEAM. The same split every sibling
here uses: `attachment_is_evidence` is a comparison that can be exercised without
a forge, and `attachment_digest_reader` is the one place a `gh release download`
happens. A decision that reached for the network itself could not be tested
without one, and the acceptance pass's own tests would then need a release.

WHY THE DEFAULT READER ANSWERS `None` FOR EVERY ASSET. `unverified_attachment` is
what a caller that supplies no reader gets, and it is fail-CLOSED on purpose: it
reports every asset unfetchable, so an attachment-bearing assertion PARKS rather
than closing on a digest nobody compared. The alternative default — treat an
unread asset as fine — would make forgetting to wire the reader indistinguishable
from verifying successfully, on the one path whose whole job is to refuse that.

WHY `None` RATHER THAN AN EMPTY DIGEST FOR AN UNFETCHABLE ASSET. An empty string
would compare unequal to any real digest and so happen to reach the right verdict
today, but it asserts something false — that the asset WAS read and found
different. Those are different facts with different remedies (re-upload the asset
versus investigate a corrupted one), and the journal records whichever one this
returns.

WHY THE DIGEST IS TAKEN OVER THE DOWNLOADED FILE AND NOTHING ELSE. The one way to
make this check vacuous is to hash something derived from the record — its stated
digest, or the proof text it no longer carries — which would compare a value with
itself and pass every asset. The reader therefore hashes the bytes on disk after
the download, exactly as `sha256sum` on that file would, which is also what the
replay stage's prompt tells a human-driven agent to run.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attachment import (
    DIGEST_ALGORITHM,
    ProofAttachment,
)

__all__: list[str] = [
    "AttachmentDigestReader",
    "attachment_digest_reader",
    "attachment_is_evidence",
    "unverified_attachment",
]

# One asset name in, its fetched digest or `None` out. A callable rather than a
# Protocol because it has exactly one operation and the pure decision beside it
# needs nothing else from a store.
AttachmentDigestReader = Callable[..., "str | None"]

_DOWNLOAD_TIMEOUT_SECONDS = 120.0
_SCRATCH = "tmp"
_FETCHED = "proof-assets-fetched"


def unverified_attachment(*, name: str) -> str | None:
    """The fail-closed default: no asset is fetchable, so none is evidence.

    Named for what it MEANS rather than for what it does ("no reader supplied"),
    because the verdict a caller gets from it is that the attachment is unverified —
    and that is the answer the journal should carry when nobody wired a reader.
    """
    del name
    return None


def attachment_is_evidence(*, attachment: ProofAttachment, fetched: str | None) -> bool:
    """Whether the fetched bytes ARE the bytes the record states.

    Exact equality, and deliberately nothing looser. A prefix or case-insensitive
    comparison would admit a truncated or re-cased digest, and the whole value of
    the check is that it cannot be satisfied by anything but the right bytes.

    `None` — an asset that could not be fetched — is not evidence. It is also not a
    REFUTATION; the caller reports it as absent evidence, never as a failure.
    """
    return fetched is not None and fetched == attachment.digest


def attachment_digest_reader(
    *, repo: Path, release_tag: str, runner: CommandRunner
) -> AttachmentDigestReader:
    """A reader that downloads one named asset from the store and digests it.

    Bound to one repository and one release tag, so the caller cannot accidentally
    ask a different store than the one the record's assets were published to — which
    would answer `None` for a perfectly healthy asset and park a sound item.

    `--clobber` because the same name may already be in the scratch directory from
    an earlier assertion in the same pass, and a download that refused on that would
    report an unfetchable asset for a reason that has nothing to do with the store.
    """

    def _read(*, name: str) -> str | None:
        destination = repo / _SCRATCH / _FETCHED
        destination.mkdir(parents=True, exist_ok=True)
        result = runner.run(
            argv=[
                "gh",
                "release",
                "download",
                release_tag,
                "--pattern",
                name,
                "--dir",
                str(destination),
                "--clobber",
            ],
            cwd=repo,
            timeout_seconds=_DOWNLOAD_TIMEOUT_SECONDS,
        )
        if result.exit_code != 0:
            return None
        return _digest_of(path=destination / name)

    return _read


def _digest_of(*, path: Path) -> str | None:
    """The algorithm-qualified digest of the bytes on disk, or `None` if unreadable.

    Read as BYTES, never as decoded text: the asset is bytes, and a decode step
    would both risk failing on a proof that is not valid UTF-8 and compute the
    digest over something other than what was stored.
    """
    try:
        payload = path.read_bytes()
    except OSError:
        return None
    return f"{DIGEST_ALGORITHM}:{hashlib.sha256(payload).hexdigest()}"
