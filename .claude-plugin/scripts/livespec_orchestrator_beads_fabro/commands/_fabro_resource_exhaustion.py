"""Typed resource-exhaustion state and the sandbox-termination reading behind it.

`SPECIFICATION/contracts.md` section "Provider-limit permanence and root-cause
surfacing" -> "A sandbox killed for memory is named." (`bd-ib-jnstxo`,
Scenario 335). The condition is carried as typed state rather than left for each
consumer to re-match against cause text, and it is a DIFFERENT state from the
provider-limit one: a sandbox the kernel killed for memory is permanent, but it
is not a spend ceiling, so the admission gate must never read it as one.

Dependency-free on purpose, so both the failure record and the outcome can carry
these types without importing the module that reads the sandbox provider.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "SANDBOX_OOM_KILLED",
    "ResourceExhaustion",
    "SandboxTermination",
    "sandbox_termination_statement",
]

SANDBOX_OOM_KILLED = "sandbox-oom-killed"

_LIMIT_UNOBSERVABLE = "memory limit unobservable"


@dataclass(frozen=True, kw_only=True)
class ResourceExhaustion:
    """The sandbox provider reported this run's container killed for memory.

    `memory_limit_bytes` is None exactly when the provider reported no limit; a
    limit nobody could read is recorded as unobservable, never guessed or omitted.
    """

    kind: str
    run_id: str
    memory_limit_bytes: int | None


@dataclass(frozen=True, kw_only=True)
class SandboxTermination:
    """One reading of how a run's sandbox container terminated.

    `observed` is False exactly when the sandbox provider's report could not be
    read on that pass, and `oom_killed` is then False too: an unreadable report
    says nothing about an OOM kill, so a consumer must test `observed` before it
    reads an absence of `oom_killed` as "not OOM-killed".
    """

    run_id: str
    observed: bool
    oom_killed: bool
    memory_limit_bytes: int | None
    detail: str


def sandbox_termination_statement(*, termination: SandboxTermination) -> str | None:
    """The sentence the outcome carries for this reading, or None when it has none.

    A readable report that shows no OOM kill says nothing: the failure keeps the
    account it arrived with.
    """
    if not termination.observed:
        return (
            f"sandbox termination unobservable for run {termination.run_id}: {termination.detail}"
        )
    if not termination.oom_killed:
        return None
    limit = (
        _LIMIT_UNOBSERVABLE
        if termination.memory_limit_bytes is None
        else f"memory limit {termination.memory_limit_bytes} bytes"
    )
    return f"sandbox OOM-killed: run {termination.run_id} container {limit}"
