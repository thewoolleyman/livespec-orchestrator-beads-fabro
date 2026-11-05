"""Read and authenticate a blob-addressed stage diff from a Fabro run."""

from __future__ import annotations

import hashlib

from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = ["read_run_blob"]

_READ_FAILED = "the run-scoped blob could not be read"
_SHA256_MISMATCH = "the run-scoped blob does not match its sha256 address"


def read_run_blob(
    *, run_id: str, blob_sha256: str, port: FabroPort, timeout_seconds: float
) -> bytes:
    """Fetch a run-scoped blob and reject bytes unlike their sha256 address."""
    blob = port.server_api().run_blob(
        run_id=run_id,
        blob_sha256=blob_sha256,
        timeout_seconds=timeout_seconds,
    )
    if not blob.succeeded:
        raise OSError(_READ_FAILED)
    payload = blob.raw_body if blob.raw_body is not None else blob.body.encode("utf-8")
    if hashlib.sha256(payload).hexdigest() != blob_sha256:
        raise OSError(_SHA256_MISMATCH)
    return payload
