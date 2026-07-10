"""Full autonomous mode — two-factor arming (the S1 arm slice).

Full autonomous mode (specified in `SPECIFICATION/spec.md`,
`SPECIFICATION/contracts.md`, and `SPECIFICATION/constraints.md`) is a
global, DANGEROUS, DEFAULT-OFF override of the plugin's human-delegable
gates. Arming it is TWO-FACTOR: a persistent `dispatcher.autonomous_mode`
permission in the consumer project's `.livespec.jsonc` (default `false`, read
by `_dispatcher_valves.resolve_autonomous_mode_permission`) AND an explicit
per-run `--mode autonomous` opt-in on the Dispatcher `loop` subcommand. Per
the contract the Dispatcher MUST NOT arm the mode from the permission key
alone, MUST NOT infer it from context, and MUST NOT let the armed mode
persist beyond the invocation — each run re-passes the flag.

This module owns the arming DECISION and its surfacing only. It collapses NO
gate: the two-valve collapse (approve -> auto, acceptance -> ai-only), the
in-band needs-human resolution stage, and the per-decision audit record all
layer on top in later slices. When a run IS armed the Dispatcher surfaces an
explicit dangerous-mode acknowledgement and journals the arming; when it is
NOT armed the run is transparent — nothing is surfaced and every
human-delegable gate keeps its normal policy (a `--mode autonomous` drain
without the permission is the ordinary full-queue factory drain, not an armed
run).

The decision functions (`decide_arming`, `dangerous_autonomous_surface`) are
pure and carry no I/O; `arm_autonomous_for_loop` binds them to the live
permission read + journal + stderr at the `loop` entry point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    resolve_autonomous_mode_permission,
)
from livespec_orchestrator_beads_fabro.io import write_stderr

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

__all__: list[str] = [
    "ArmingDecision",
    "arm_autonomous_for_loop",
    "dangerous_autonomous_surface",
    "decide_arming",
]

# The one `--mode` value that opts a run into full autonomous mode (the other
# is `shadow`). This is the per-run FLAG factor; arming still ALSO requires the
# persistent permission.
_AUTONOMOUS_FLAG = "autonomous"

# The four arming outcomes, distinguished for the journal + the surfaced
# acknowledgement. Only `armed` collapses gates (in later slices); the three
# non-armed reasons all leave every human-delegable gate at its normal policy.
_REASON_ARMED = "armed"
_REASON_FLAG_WITHOUT_PERMISSION = "flag-without-permission"
_REASON_PERMISSION_WITHOUT_FLAG = "permission-without-flag"
_REASON_NEITHER = "neither"


@dataclass(frozen=True, kw_only=True)
class ArmingDecision:
    """The per-invocation full-autonomous-mode arming decision.

    `armed` is True IFF both factors hold — the per-run `--mode autonomous`
    flag AND the persistent `permission`. `reason` names which factor(s) were
    missing (or `armed`) for the surfaced acknowledgement and the journal.
    The decision is a pure function of the two inputs and is never persisted,
    honoring "MUST NOT persist beyond the current invocation".
    """

    armed: bool
    mode: str
    permission: bool
    reason: str


def decide_arming(*, mode: str, permission: bool) -> ArmingDecision:
    """Decide whether full autonomous mode is armed for this invocation.

    Two-factor: armed only when the per-run flag (`mode == "autonomous"`) AND
    the persistent `permission` both hold. The flag alone (permission off)
    MUST NOT arm — that is the ordinary full-queue factory drain, gates
    intact. The permission alone (no flag) MUST NOT arm — the mode is never
    inferred from the key. Pure; no I/O; nothing persisted.
    """
    flag = mode == _AUTONOMOUS_FLAG
    if flag and permission:
        reason = _REASON_ARMED
    elif flag:
        reason = _REASON_FLAG_WITHOUT_PERMISSION
    elif permission:
        reason = _REASON_PERMISSION_WITHOUT_FLAG
    else:
        reason = _REASON_NEITHER
    return ArmingDecision(
        armed=flag and permission, mode=mode, permission=permission, reason=reason
    )


def dangerous_autonomous_surface(*, decision: ArmingDecision) -> str:
    """Build the explicit dangerous-mode acknowledgement for an armed run.

    Surfaced (never silent) when a run arms full autonomous mode, per the
    "Explicit dangerous-mode confirmation" safety rail in
    `SPECIFICATION/constraints.md`. Names the danger, the two factors, and that
    the arming does NOT persist beyond this invocation. The `decision` is
    accepted (rather than inferred) so a caller cannot surface a non-armed
    run as armed.
    """
    _ = decision
    return (
        "SURFACE: DANGEROUS — full autonomous mode ARMED for this invocation "
        "only (persistent dispatcher.autonomous_mode permission + explicit "
        "--mode autonomous opt-in). Full autonomous mode is a default-off "
        "override of the human-delegable gates; this arming is NOT persisted "
        "beyond this run.\n"
    )


def arm_autonomous_for_loop(*, mode: str, repo: Path, journal: JournalFile) -> ArmingDecision:
    """Resolve + surface + journal the arming decision at the `loop` entry.

    Reads the persistent permission for `repo`, decides arming from it and the
    per-run `mode` flag, and — ONLY when armed — surfaces the explicit
    dangerous-mode acknowledgement and journals the arming event. A non-armed
    run is transparent: no surface, no journal record, every gate at its normal
    policy (collapsing NO gate is intentional here; the collapse layers on in
    later slices). Returns the decision so a later slice can gate the collapse
    on it.
    """
    permission = resolve_autonomous_mode_permission(cwd=repo)
    decision = decide_arming(mode=mode, permission=permission)
    if decision.armed:
        _ = write_stderr(text=dangerous_autonomous_surface(decision=decision))
        journal.append(
            record={
                "stage": "autonomous-armed",
                "mode": decision.mode,
                "permission": decision.permission,
                "reason": decision.reason,
            }
        )
    return decision
