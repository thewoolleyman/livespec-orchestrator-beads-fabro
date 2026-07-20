"""The reclaim mutex's own I/O MUST ride the Result track.

Every other filesystem access in `_dispatcher_janitor_lock` routes through
`attempt(...)`; the reclaim mutex's `open` and `flock` did not. Because the
mutex is opened BEFORE the lock is read, an expected environment failure there
escaped as a raised exception on EVERY contention path -- crashing the
dispatcher's janitor instead of returning the clean `janitor-checkout-locked`
contention outcome.

Both failures below are provoked in a PRIVILEGE-INDEPENDENT way, deliberately.
The obvious reproduction -- a non-writable (0o555) parent directory -- is
masked for root, which bypasses the permission check and opens the mutex
happily; a test built on it would pass vacuously in CI's root container and
discriminate only off-root. That is the same masking that let the janitor gate
sit red for every non-root runner. Making the mutex path a DIRECTORY provokes
the identical failure track for root and non-root alike:

    uid 1000: 0o555 parent dir -> PermissionError    uid 0: OPEN SUCCEEDS (masked)
    uid 1000: dir-as-mutex     -> IsADirectoryError  uid 0: IsADirectoryError

In both tests the stale lock MUST survive: a claimant that cannot take the
reclaim mutex has not established exclusion, so it must report contention
rather than reclaim.
"""

import json
import os
from pathlib import Path

import livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_lock as janitor_lock
import pytest

_STALE_PAYLOAD = {"pid": 999_999_999, "started_at_epoch": 1.0, "work_item_id": "bd-stale"}


def _write_stale_lock(*, path: Path) -> bytes:
    path.write_text(json.dumps(_STALE_PAYLOAD, sort_keys=True) + "\n", encoding="utf-8")
    return path.read_bytes()


def test_unopenable_reclaim_mutex_reports_contention_instead_of_raising(
    tmp_path: Path,
) -> None:
    """An un-openable reclaim mutex MUST fail closed onto the contention path.

    The mutex path is a directory, so `open("a+b")` raises `IsADirectoryError`
    for any uid. Unwrapped, that propagates out of `claim_janitor_lock` and
    crashes the caller; wrapped, it reads as "not reclaimed" and the caller
    gets the ordinary contention detail.
    """
    path = tmp_path / "janitor.lock"
    before = _write_stale_lock(path=path)
    (tmp_path / "janitor.lock.reclaim").mkdir()

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-claimant")

    assert detail is not None
    assert "work-item bd-stale" in detail
    assert path.read_bytes() == before


def test_unlockable_reclaim_mutex_reports_contention_instead_of_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing `flock` MUST fail closed onto the contention path too.

    `flock` can fail for reasons the caller cannot prevent (ENOLCK on a
    filesystem without lock support, EINTR). It sits one line below the open
    and carried the same unguarded exposure.
    """
    path = tmp_path / "janitor.lock"
    before = _write_stale_lock(path=path)

    def refuse_flock(fd: int, operation: int) -> None:
        _ = (fd, operation)
        raise OSError(os.strerror(37), "no locks available")

    monkeypatch.setattr(janitor_lock.fcntl, "flock", refuse_flock)

    detail = janitor_lock.claim_janitor_lock(path=path, owner="bd-claimant")

    assert detail is not None
    assert "work-item bd-stale" in detail
    assert path.read_bytes() == before
