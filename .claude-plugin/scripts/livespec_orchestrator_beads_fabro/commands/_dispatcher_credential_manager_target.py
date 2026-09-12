"""The consumer-owned isolated target one dispatch offers the llm-provider-manager.

livespec-overseer `SPECIFICATION/contracts.md` registers a built-in `isolated-run`
provisioning adapter whose input interface is a file under the MANAGER's state directory
that THIS consumer writes: "Which consumer-host component creates that input, how it is
invoked and how it withholds write authority from its agent belong to that consumer's own
contract." This module is that component.

THE DESTINATION IS OURS AND THE REFERENCE IS THEIRS, WHICH IS WHY BOTH HALVES EXIST. The
consumer declares WHERE a credential may land (a per-run directory it created); the
manager issues an opaque `target_ref` bound immutably to one run and resolves it from its
own issuance record rather than from anything we send later. So a dispatch cannot point a
second run at the first run's destination, and cannot rename a destination after issuance.

THE MODE BITS ARE A PRECONDITION, NOT A COURTESY. The adapter refuses issuance unless
every directory from `isolated_root` through the target's parent is a non-symlink
directory owned by the effective user with mode no broader than 0700 — and it explicitly
will NOT create or chmod one of them. The system temporary directory is world-writable,
so a target placed directly in it is refused; `prepare_isolated_target` therefore creates
its own 0700 directory beneath it and hands the manager a path inside that.

HOME COMES FROM THE ACCOUNT DATABASE, NOT FROM `HOME`. The manager resolves its state
directory from the effective user's operating-system account entry independently of the
environment, so that every manager process for that user shares one namespace. A consumer
that resolved `HOME` instead would write its registration into a directory no manager ever
reads, and the failure would present as an unexplained `invalid-request` at issuance.

TEARDOWN IS UNCONDITIONAL AND BEST-EFFORT. Once the value has been copied into the
mode-600 run overlay, the target file is a second copy of a live credential on disk with
no further purpose. `discard_isolated_target` removes it and its directory on every path,
including refusal paths, and never raises: a cleanup failure must not convert a usable
dispatch into a refused one, nor mask the refusal that preceded it.
"""

from __future__ import annotations

import hashlib
import os
import pwd
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final

__all__: list[str] = [
    "MANAGER_STATE_REL",
    "REGISTRATION_TTL_SECONDS",
    "IsolatedTarget",
    "credential_target_root",
    "discard_isolated_target",
    "manager_state_dir",
    "prepare_isolated_target",
    "read_provisioned_value",
    "registration_window",
    "rfc3339_second",
    "run_registration_path",
]

# Byte-identical to the manager's own resolution (contracts.md: `<home>/.local/state/
# livespec-overseer/llm-provider-manager/`), so writer and reader cannot drift.
MANAGER_STATE_REL: Final = Path(".local/state/livespec-overseer/llm-provider-manager")
_REGISTRATIONS_DIR: Final = "run-registrations"

# The registration's own lifetime. The contract caps it at 24 hours after `created_at`;
# a dispatch consumes its registration within seconds, so a short window is both
# sufficient and self-cleaning if a dispatch dies before the manager reads it.
REGISTRATION_TTL_SECONDS: Final = 3600

_TARGET_DIR_MODE: Final = 0o700
_TARGET_FILE_NAME: Final = "credential"


@dataclass(frozen=True, kw_only=True)
class IsolatedTarget:
    """One run's isolated destination: the 0700 root and the file inside it."""

    isolated_root: Path
    target_path: Path


def rfc3339_second(*, epoch: float) -> str:
    """One UTC RFC 3339 second-precision timestamp, the only form the manager accepts."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def manager_state_dir() -> Path:
    """The manager's state directory, resolved exactly as the manager resolves it."""
    return Path(pwd.getpwuid(os.geteuid()).pw_dir) / MANAGER_STATE_REL


def run_registration_path(*, state_dir: Path, consumer_run_id: str) -> Path:
    """The registration file for one run, keyed by the digest the adapter expects."""
    digest = hashlib.sha256(consumer_run_id.encode("utf-8")).hexdigest()
    return state_dir / _REGISTRATIONS_DIR / f"{digest}.json"


def credential_target_root(*, temp_dir: Path, consumer_run_id: str) -> Path:
    """The per-run 0700 directory a provisioned credential may land in."""
    return temp_dir / f"fabro-run-credential-{consumer_run_id}"


def prepare_isolated_target(*, temp_dir: Path, consumer_run_id: str) -> IsolatedTarget | str:
    """Create this run's 0700 target directory; an error string on failure.

    Any pre-existing directory is removed first: a leftover from a previous dispatch of
    the same run id could carry another run's bytes or a mode the adapter refuses, and
    reusing it would make an issuance depend on state nobody audited.
    """
    root = credential_target_root(temp_dir=temp_dir, consumer_run_id=consumer_run_id)
    try:
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(mode=_TARGET_DIR_MODE, parents=True)
        root.chmod(_TARGET_DIR_MODE)
    except OSError as error:
        return (
            f"C-mode dispatch refused: the per-run credential directory {root} could not "
            f"be created ({type(error).__name__}: {error}). The llm-provider-manager "
            "isolated-run adapter refuses to create or chmod it itself."
        )
    return IsolatedTarget(isolated_root=root, target_path=root / _TARGET_FILE_NAME)


def read_provisioned_value(*, target: IsolatedTarget) -> str | None:
    """The credential the manager wrote, or None when the target holds nothing usable.

    A manager that answered `ok` and left the destination empty has broken its own
    atomic-write guarantee; the caller turns that None into a typed refusal rather than
    projecting an empty credential into a sandbox that would then fail to authenticate.
    """
    try:
        value = target.target_path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    return value.strip() or None


def discard_isolated_target(*, target: IsolatedTarget) -> None:
    """Remove the run's credential copy and its directory, tolerating every failure."""
    shutil.rmtree(target.isolated_root, ignore_errors=True)


def registration_window(*, now_epoch: float) -> tuple[str, str]:
    """The registration's `created_at` and `expires_at` pair."""
    created = datetime.fromtimestamp(now_epoch, tz=timezone.utc)
    expires = created + timedelta(seconds=REGISTRATION_TTL_SECONDS)
    return (
        created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
