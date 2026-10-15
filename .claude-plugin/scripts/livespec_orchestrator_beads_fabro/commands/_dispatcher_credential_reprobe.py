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

THE WAIT IS RETIRED BY THE PROBE'S OWN NEXT RESULT, NEVER BY A CLOCK. Nothing
here reads, parses or honours a provider-stated reset instant, and the cadence
is this repository's own committed dial rather than anything a provider said.
That is the whole point of the clause: the incident it was written from
(plan `idle-factory-visibility`) lost two hours of factory time to resumers that
slept until a 429 body's reset time, while the credential had in fact recovered.

EVERY ROUND RE-RESOLVES THE CREDENTIAL THROUGH THE CONFIGURED WRAPPER. The wait
used to assess `os.environ` — the value the wrapper injected when the loop was
LAUNCHED — which makes it unretirable by the one event it exists to wait for. A
rotation lands in the wrapper and a parked process never reads the wrapper
again, so the probe re-asks the provider about a credential that has already
been replaced: measured 2026-10-08, four loops on this host kept journaling
`exhausted` from 08:54Z and 11:42Z through 23:10Z while other repositories'
dispatches ran on the same factory within minutes of the rotation, and the only
remedy was to kill and re-dispatch all four. `_dispatcher_credential_rotation`
is the re-resolution, and the record below names the credential it probed by a
one-way identity so two consecutive rows show whether the value changed at all.

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
admission-valve condition". The invocation's own budget bounds it in two ways —
an invocation with no dispatch slots to spend has nothing to wait for, so it
never enters the loop at all, and once inside it is the number of CONSECUTIVE
rounds the wait tolerates without having re-resolved the credential.

THAT SECOND BOUND IS KEYED ON UNRESOLVABLE ROUNDS AND NEVER ON ROUNDS. The
ratified clause says the loop MUST NOT exit on a provider-limit refusal while
its `--budget` is unspent, so a blanket round cap would break exactly the
behaviour this module exists to provide. What the bound governs is the other
failure the re-resolution makes possible: when the declared wrapper cannot run,
every round falls back to the same launch-time value, which nothing can change
while the process lives, so the wait is on an event that CANNOT arrive. The
counter resets on every successful re-resolution, which is why a healthy wait is
still unbounded and a transient wrapper fault costs nothing; and the bound is
tested AFTER the sleep, so a wait that has nothing to watch still journals its
refusal and serves its cadence before ending.

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
    assess_resolved_credential,
    projected_credential_env_name,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_rotation import (
    RotatedCredential,
    credential_identity,
    resolve_rotated_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
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


def await_usable_credential(  # noqa: PLR0913 — kw-only wait inputs; `runner` is the rotation seam, not a variant of the probe.
    *,
    repo: Path,
    journal: JournalFile,
    budget: int,
    probe: Callable[..., ClaudeCredentialStatus] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    preflight: AcpPreflightVerdict | None = None,
    runner: CommandRunner | None = None,
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

    The credential env NAME is resolved ONCE, for the same reason the cadence
    is: it is the caam pool-slot selection, and re-resolving it per round would
    let a mid-wait selection change mean the assessment and the re-resolution
    were asking about different credentials in one round.
    """
    if preflight is not None and not credential_reprobe_wait_applies(verdict=preflight):
        return
    interval = unsafe_perform_io(
        resolve_credential_reprobe_interval_seconds(cwd=repo).value_or(
            DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS
        )
    )
    env_name = projected_credential_env_name()
    command = ShellCommandRunner() if runner is None else runner
    unresolvable_rounds = 0
    while budget > 0:
        rotated = resolve_rotated_credential(
            repo=repo,
            env_name=env_name,
            launch_token=os.environ.get(env_name, ""),
            runner=command,
        )
        status = assess_resolved_credential(repo=repo, token=rotated.token, probe=probe)
        if status.condition != PROVIDER_LIMIT_CONDITION:
            return
        journal.append(
            record=_refused_probe_record(status=status, interval=interval, rotated=rotated)
        )
        sleep(interval)
        unresolvable_rounds = 0 if rotated.rotatable else unresolvable_rounds + 1
        if unresolvable_rounds >= budget:
            return


def _refused_probe_record(
    *, status: ClaudeCredentialStatus, interval: int, rotated: RotatedCredential
) -> dict[str, object]:
    """One refused probe, as the non-secret facts that explain the wait.

    The credential value and the probe's response body never reach here —
    `ClaudeCredentialStatus` carries only the classification and the two
    non-secret transport facts, and the credential travels as a ONE-WAY
    identity — so the record is safe to append verbatim.

    `credential_identity` is what makes a STALE value legible, which is the one
    question an operator watching a parked loop cannot otherwise answer: two
    consecutive rows carrying ONE identity say the wait has been re-probing the
    same credential all along, and a changed identity says a rotation reached
    it. A NULL identity is an absent credential rather than a changed one,
    which is why the fingerprint is not taken over the empty string.

    `credential_source` says WHERE this round's credential came from, which is
    what tells a wait that is watching the wrapper from one that has nothing to
    watch: a row naming the launch environment can never be retired by a
    rotation, however long the wait runs.
    """
    return {
        "stage": CREDENTIAL_REPROBE_STAGE,
        "condition": status.condition,
        "http_status": status.http_status,
        "error_type": status.error_type,
        "reprobe_interval_seconds": interval,
        "credential_identity": credential_identity(token=rotated.token),
        "credential_source": rotated.source,
    }
