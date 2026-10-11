"""Protect production publication state from the execution-test boundary."""

from __future__ import annotations

import fcntl
import runpy
import tempfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import cast

import pytest

_EXECUTION_TEST = Path(__file__).with_name("test_scripted_publication_execution.py")
_STATE_PAYLOADS = {
    Path("/tmp/livespec-publish-head"): b"production-head\n",
    Path("/tmp/livespec-pr-refresh-count"): b"2\n",
    Path("/tmp/livespec-pr-refresh-changed"): b"production-changed\n",
}


def _seed_state(*, backup_root: Path, state_payloads: dict[Path, bytes]) -> dict[Path, Path]:
    backups: dict[Path, Path] = {}
    for index, (path, payload) in enumerate(state_payloads.items()):
        if path.exists() or path.is_symlink():
            backup = backup_root / str(index)
            path.replace(backup)
            backups[path] = backup
        path.write_bytes(payload)
    return backups


def _observe_and_restore(
    *, backup_root: Path, backups: dict[Path, Path], state_payloads: dict[Path, bytes]
) -> dict[Path, bytes | None]:
    observed: dict[Path, bytes | None] = {}
    for path in state_payloads:
        observed[path] = path.read_bytes() if path.is_file() else None
        path.unlink(missing_ok=True)
        backup = backups.get(path)
        if backup is not None:
            backup.replace(path)
    backup_root.rmdir()
    return observed


@pytest.mark.parametrize("preexisting", [False, True])
def test_control_harness_restores_its_caller_state(*, tmp_path: Path, preexisting: bool) -> None:
    """The regression control itself preserves both absence and prior bytes."""
    state_path = tmp_path / "state"
    state_payloads = {state_path: b"controlled\n"}
    original = b"original\n"
    if preexisting:
        state_path.write_bytes(original)
    backup_root = tmp_path / "backups"
    backup_root.mkdir()

    backups = _seed_state(
        backup_root=backup_root,
        state_payloads=state_payloads,
    )
    assert state_path.read_bytes() == state_payloads[state_path]
    observed = _observe_and_restore(
        backup_root=backup_root,
        backups=backups,
        state_payloads=state_payloads,
    )

    assert observed == state_payloads
    assert state_path.read_bytes() == original if preexisting else not state_path.exists()


@pytest.mark.parametrize("control_fails", [False, True])
def test_execution_boundary_restores_preexisting_production_state(
    *, monkeypatch: pytest.MonkeyPatch, control_fails: bool
) -> None:
    """Normal and failing controls leave every pre-existing state file intact."""
    namespace = runpy.run_path(str(_EXECUTION_TEST))
    publication_state = cast(
        Callable[[], AbstractContextManager[tuple[Path, ...]]],
        namespace["_publication_state"],
    )
    real_flock = fcntl.flock
    backups: dict[Path, Path] = {}
    observed: dict[Path, bytes | None] = {}
    backup_root = Path(tempfile.mkdtemp(prefix="publication-boundary-control-", dir="/tmp"))

    def controlled_flock(*, file_descriptor: int, operation: int) -> None:
        if operation == fcntl.LOCK_UN:
            observed.update(
                _observe_and_restore(
                    backup_root=backup_root,
                    backups=backups,
                    state_payloads=_STATE_PAYLOADS,
                )
            )
            real_flock(file_descriptor, operation)
            return
        assert operation == fcntl.LOCK_EX
        real_flock(file_descriptor, operation)
        backups.update(
            _seed_state(
                backup_root=backup_root,
                state_payloads=_STATE_PAYLOADS,
            )
        )

    monkeypatch.setattr(
        fcntl,
        "flock",
        lambda file_descriptor, operation: controlled_flock(
            file_descriptor=file_descriptor,
            operation=operation,
        ),
    )
    if control_fails:
        with (
            pytest.raises(RuntimeError, match="controlled failure"),
            publication_state(),
        ):
            raise RuntimeError("controlled failure")
    else:
        with publication_state():
            pass

    assert observed == _STATE_PAYLOADS
