"""Bounded credential re-probe for the Dispatcher's `loop` path.

Implements the v103 provider-spend-containment clause in
`SPECIFICATION/contracts.md`: a `loop` invocation refused by the
admission-time credential-usability probe MUST NOT exit on that refusal while
its `--budget` is unspent. It holds the pass open, re-runs the SAME probe on a
bounded cadence, and returns as soon as the probe reports usable, so normal
admission resumes on the PROBE'S OWN next result rather than on a clock. The
incident this retires: a drain was refused by a transient rate limit, exited,
and the factory then sat idle behind three hand-written resumers that slept
until a provider-stated reset instant the credential had in fact recovered
long before.

Three boundaries are load-bearing, and each is here rather than at the call
site because each is what a reader would otherwise mis-read about the wait:

- ONLY a provider-limit / rate-limit refusal is held for. Every other refusal
  condition — absent, revoked, permission-denied, unavailable — returns
  immediately, because re-probing cannot change any of them; the per-dispatch
  refusal that already surfaces them is left untouched.
- The wait writes ONE journal record per refused probe and consults no
  exhaustion record. It creates NO new retirement route: a live credential
  probe is a host-side availability signal, and host and sandbox credential
  state diverge by construction, so a usable probe here retires nothing. The
  three ratified routes — bounded expiry, dispatch-outcome falsification, and
  operator clearance — stand unchanged, and where an unexpired record also
  governs the provider, admission stays refused by that record.
- The cadence is COMMITTED-ONLY. It is read from `.livespec.jsonc`
  `dispatcher.credential_reprobe_interval_seconds` and is deliberately absent
  from the declared-API-configurable key manifest in `_drive_config_schema`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    ClaudeCredentialStatus,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    credential_status,
)

__all__: list[str] = [
    "CREDENTIAL_REPROBE_REFUSED_STAGE",
    "DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS",
    "await_usable_credential",
    "credential_reprobe_interval_seconds",
    "sleep_for_reprobe_cadence",
]

DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS = 300
CREDENTIAL_REPROBE_REFUSED_STAGE = "credential-reprobe-refused"

_INTERVAL_KEY = "credential_reprobe_interval_seconds"
# The ONE probe condition this wait is for. `classify_claude_probe` folds HTTP
# 402 and 429 and the `billing_error` / `rate_limit_error` types onto it, which
# is exactly the "provider-limit or rate-limit condition" the clause names.
# Keying on the classified condition rather than on a status code is what keeps
# this in step with the classifier instead of duplicating its table.
_PROVIDER_LIMIT_CONDITION = "exhausted"


class _Journal(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


class _Sleeper(Protocol):
    def __call__(self, *, seconds: float) -> None:
        """Block for the bounded re-probe cadence."""
        ...


def credential_reprobe_interval_seconds(*, cwd: Path) -> int:
    """The committed re-probe cadence in seconds, defaulting to 300.

    A key that is absent, non-integer, boolean, or not positive answers the
    default rather than refusing: the cadence bounds a WAIT, so a malformed
    value must not be able to turn the wait into an exit, which is the very
    behavior this module exists to retire. `True` is excluded explicitly
    because `bool` is an `int` subclass and would otherwise resolve to a
    one-second spin.
    """
    raw = dispatcher_block(cwd=cwd).get(_INTERVAL_KEY)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        return DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS
    return raw


def await_usable_credential(
    *,
    repo: Path,
    journal: _Journal,
    budget: int,
    probe: Callable[..., ClaudeCredentialStatus] | None = None,
    sleeper: _Sleeper | None = None,
) -> ClaudeCredentialStatus | None:
    """Hold this pass open across a provider-limit credential refusal.

    Returns the status the pass resumes on — usable, or a refusal condition
    re-probing cannot change — or None when there was no budget to keep alive
    and therefore nothing to wait for. The caller does NOT branch on the
    result: admission proceeds either way, and a non-provider-limit refusal
    stays the per-dispatch refusal's business.
    """
    if budget <= 0:
        return None
    wait = sleeper if sleeper is not None else sleep_for_reprobe_cadence
    interval = credential_reprobe_interval_seconds(cwd=repo)
    refused = 0
    while True:
        status = credential_status(repo=repo, probe=probe)
        if status.condition != _PROVIDER_LIMIT_CONDITION:
            return status
        refused += 1
        journal.append(
            record={
                "stage": CREDENTIAL_REPROBE_REFUSED_STAGE,
                "condition": status.condition,
                "http_status": status.http_status,
                "error_type": status.error_type,
                "refused_probes": refused,
                "reprobe_interval_seconds": interval,
                "budget": budget,
            }
        )
        wait(seconds=interval)


def sleep_for_reprobe_cadence(*, seconds: float) -> None:
    """The production wait between two probes.

    PUBLIC, and named, so a caller exercising the loop end to end can replace
    THIS seam rather than the shared `time.sleep`. Replacing the shared one
    captures every unrelated sleep the same pass performs — a retry backoff, a
    poll — so an assertion about the re-probe cadence would be reading someone
    else's waits alongside its own.
    """
    time.sleep(seconds)
