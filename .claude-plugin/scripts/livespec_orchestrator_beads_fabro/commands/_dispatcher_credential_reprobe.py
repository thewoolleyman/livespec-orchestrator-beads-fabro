"""The loop's bounded credential re-probe: a rate limit waits, it does not exit.

The ratified clause is the admission-time credential-probe refusal that
re-probes rather than exiting, among the provider spend-containment rules in
`SPECIFICATION/contracts.md`, exercised by `SPECIFICATION/scenarios.md`
Scenario 121. A `loop`
invocation whose admission-time credential-usability probe returns a
provider-limit or rate-limit condition MUST NOT exit on that refusal while its
`--budget` is unspent: it re-runs the probe on a bounded cadence and resumes
normal admission on the first usable result, journaling each refused probe.

Four properties are load-bearing rather than incidental.

EVERY ROUND RE-RESOLVES THE CREDENTIAL, rather than re-probing the value the
wrapper injected when the loop was launched. Re-probing a launch-time snapshot
is not a re-probe of the credential at all: it asks the same question of the
same bytes and can only ever get the same answer, so a rotation can never
reach a parked loop. Measured 2026-10-08 on this host, four loops parked from
08:54Z and 11:42Z were still journaling `exhausted` at 23:10Z after the
credential was rotated at roughly 23:00Z, and had to be stopped and
re-dispatched by hand. `_dispatcher_credential_rotation` owns the re-read and
the non-secret identity each refused row records.

THE WAIT IS RETIRED BY THE PROBE'S OWN NEXT RESULT, NEVER BY A CLOCK. Nothing
here reads, parses or honours a provider-stated reset instant, and the cadence
is this repository's own committed dial rather than anything a provider said.
That is the whole point of the clause: the incident it was written from
(plan `idle-factory-visibility`) lost two hours of factory time to resumers that
slept until a 429 body's reset time, while the credential had in fact recovered.

THE WAIT ENGAGES ON EXACTLY ONE CONDITION. A provider-limit refusal is the
`exhausted` condition `classify_claude_probe` assigns to HTTP 402/429 and to the
`billing_error` / `rate_limit_error` types. Every other refusal — an absent
credential, a revoked one, a denied one, one that could not be assessed — is a
fault waiting cannot fix, so this gate returns and leaves the dispatch path's own
refusal to report it exactly as it did before. A gate that waited on all of them
would convert a misconfigured wrapper into a hang.

IT RETIRES NO EXHAUSTION RECORD. The clause is explicit that it creates NO new
retirement route: a usable probe result is a host-side availability signal, and
host and sandbox credential state diverge by construction. So this module writes
only its own refusal records and never a `provider-exhaustion-cleared` line —
where an unexpired record ALSO governs the provider, admission stays refused by
that record until it retires by bounded expiry, a dispatch outcome, or an
operator clearance.

IT IS A WAIT, NOT A REFUSAL. `await_usable_credential` returns nothing and
cannot refuse: returning is "admission may proceed under every OTHER
admission-valve condition". The one bound on the wait is the invocation's own
budget — an invocation with no dispatch slots to spend has nothing to wait for,
so it never enters the loop at all.

IT DOES NOT GOVERN A CHAIN THAT STILL HAS A CANDIDATE. `SPECIFICATION/
contracts.md` section "Factory-configurable ACP fallback priority": "The
re-probe wait applies to a legacy single candidate and a genuinely exhausted
fallback chain, never a primary-only probe refusal with a viable fallback."
A legacy single candidate is exactly what a repository with no fallback
configuration has, so the pre-existing behaviour is the unchanged default; the
new case is a fallback-enabled repository whose success-critical chains still
hold a candidate, where waiting would idle a factory that can run the work on
the next candidate in configured order.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    credential_reprobe_wait_applies,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    ClaudeCredentialStatus,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_env import (
    assess_credential_status,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_rotation import (
    CredentialReading,
    resolve_credential_reading,
    selected_credential_env_name,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS,
    resolve_credential_reprobe_interval_seconds,
)

__all__: list[str] = [
    "CREDENTIAL_REPROBE_STAGE",
    "PROVIDER_LIMIT_CONDITION",
    "await_usable_credential",
]

# The journal stage every refused probe is appended under. One record per
# refused probe, so the re-probe wait is legible in the audit journal rather
# than being a silent gap between a loop's start and its first dispatch.
CREDENTIAL_REPROBE_STAGE = "credential-reprobe-refused"

# The ONE `ClaudeCredentialStatus.condition` this wait engages on — the
# provider-limit / rate-limit refusal named by the clause.
PROVIDER_LIMIT_CONDITION = "exhausted"


def await_usable_credential(
    *,
    repo: Path,
    journal: JournalFile,
    budget: int,
    probe: Callable[..., ClaudeCredentialStatus] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    preflight: AcpPreflightVerdict | None = None,
) -> None:
    """Hold the loop's admission while the projected credential is provider-limited.

    Returns as soon as the probe reports a condition this wait does not govern
    — a usable credential, or a refusal no amount of waiting repairs — leaving
    every other admission-valve condition to decide what happens next.

    The cadence is read ONCE, before the first probe: re-reading it per round
    would let a mid-wait config edit change the interval the operator was told
    about in the record they are reading, and the wait would then be
    unreproducible from its own journal.

    `preflight` is the pass's ACP candidate-chain verdict. The loop wave — the
    one caller that can hold a loop — resolves it and supplies it on every
    invocation, which is what makes the gate below reachable in production
    rather than only from a test that hands one in. An ABSENT verdict leaves
    the legacy behaviour exactly as it was: this gate can only ever SUPPRESS a
    wait, never start one.
    """
    if preflight is not None and not credential_reprobe_wait_applies(verdict=preflight):
        return
    interval = unsafe_perform_io(
        resolve_credential_reprobe_interval_seconds(cwd=repo).value_or(
            DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS
        )
    )
    # The credential's env-var NAME is resolved once, for the same reason the
    # cadence is: a per-round re-selection would re-emit the pool-slot
    # selector's loud fallback line once a cadence, and the rotation this wait
    # must notice is a change of VALUE under the name a dispatch would project.
    env_name = selected_credential_env_name()
    while budget > 0:
        reading = resolve_credential_reading(repo=repo, env_name=env_name, environ=os.environ)
        status = assess_credential_status(repo=repo, probe=probe, token=reading.token)
        if status.condition != PROVIDER_LIMIT_CONDITION:
            return
        journal.append(
            record=_refused_probe_record(status=status, interval=interval, reading=reading)
        )
        sleep(interval)


def _refused_probe_record(
    *,
    status: ClaudeCredentialStatus,
    interval: int,
    reading: CredentialReading,
) -> dict[str, object]:
    """One refused probe, as the non-secret facts that explain the wait.

    The credential value and the probe's response body never reach here —
    `ClaudeCredentialStatus` carries only the classification and the two
    non-secret transport facts, and `CredentialReading` contributes its one-way
    IDENTITY rather than its token — so the record is safe to append verbatim.

    The identity is what makes a wait diagnosable from its own journal. Without
    it a row says a probe was refused and nothing about WHICH credential was
    refused, so an operator reading two consecutive rows cannot tell a
    credential that is genuinely still limited from a rotation that never
    reached the loop — the question the 2026-10-08 incident left unanswerable.
    `credential_source` sits beside it because the two have different remedies:
    the wrapper's current answer being limited is a provider problem, while the
    launch-time value carried forward means the wrapper supplied nothing and is
    itself what needs fixing.
    """
    return {
        "stage": CREDENTIAL_REPROBE_STAGE,
        "condition": status.condition,
        "http_status": status.http_status,
        "error_type": status.error_type,
        "credential_identity": reading.identity,
        "credential_source": reading.source,
        "reprobe_interval_seconds": interval,
    }
