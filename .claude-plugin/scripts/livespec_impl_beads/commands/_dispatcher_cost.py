"""Fail-closed cost-observability seam for the Dispatcher (work-item 5v9).

0jxs operability precondition, leg (b) part 1 (the prerequisite to y0m's
fail-closed spend cap, a USER-RATIFIED HARD requirement before the W6
dark-factory cutover, epic livespec-4moata). This module establishes the
per-run cost SIGNAL and the fail-closed gate that fires when that signal
is dark — y0m then builds the per-run + per-session USD cap on the seam
here.

The 5v9 investigation (fabro v0.254.0, ACP backend, 31 runs probed
2026-06-13) found per-run cost FUNDAMENTALLY UNOBSERVABLE at dispatch
time:

  * `fabro ps -a --json` carries `total_usd_micros` on every run record,
    but it is `null` on ALL of them (0/31 populated);
  * `fabro inspect <run> --json` does NOT carry `total_usd_micros` at
    all — it carries a `conclusion.timing` block (wall / inference /
    tool / active ms) and a per-node `usage` slot that is `null` for
    every node;
  * `fabro events <run> --json` carries no cost or token-usage fields
    (the ACP `agent.acp.completed` event reports only `duration_ms` /
    `stop_reason`; `run.completed` reports `artifact_count = 0`);
  * there is no `fabro run` / `inspect` / `events` / `settings` flag and
    no server config that turns cost reporting on in this version.

Conclusion: this fabro version + the ACP (Claude Code adapter) backend
does not surface a usage struct from the agent, so fabro has nothing to
price and `total_usd_micros` stays null. A populated field would need a
fabro upgrade or a server-side change — a USER / infra decision, NOT a
host-side code fix — so 5v9 implements the warranted path: the
fail-closed gate (preconditions.md leg (b), §"Fail-closed means").

The canonical observable-cost source is therefore `fabro ps -a --json`
(matched on the engine's already-parsed run id), NOT `fabro inspect`.
`observe_run_cost` is a PURE function over that JSON text: it surfaces a
real `total_usd_micros` as an observable cost the moment fabro starts
populating it (forward-compat, no gate change), and reports
`observable=False` whenever the field is null / absent / unparseable.

`cost_gate_decision` is the fail-closed rule (preconditions.md
§"Fail-closed means"): in `autonomous` (unattended) mode an unobservable
cost is itself a cap-accounting failure — the loop REFUSES to keep
picking rather than burning spend cost-blind; in `shadow` mode (an
explicit `--item` dispatch with a human present) a `warn` suffices. An
OBSERVED cost never trips this gate — cap-VALUE enforcement (the per-run
/ per-session ceilings) is y0m's job; 5v9's gate fires only on the
unobservable condition.

`resolve_per_run_cap_usd` / `resolve_per_session_cap_usd` carry the
committed env-overridable cap defaults (`LIVESPEC_MAX_RUN_USD` /
`LIVESPEC_MAX_SESSION_USD`, $25 / $100 placeholders pending the first
populated cost data) so an unset env never means uncapped — the
ready-made values y0m's cap comparison consumes.

Credential hygiene: the cost signal is a single integer (micro-USD) and
the decision carries only scalar id / class / reason fields — no goal
text, no env values, no `detail` blobs, no remote URLs (the 5v9 probe
saw fabro inspect JSON leak a CLAUDE_CODE_OAUTH_TOKEN value in its
run-spec env table, so this module reads ONLY the cost field by name and
never echoes the broader record).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

__all__: list[str] = [
    "CostGateDecision",
    "CostObservation",
    "cost_gate_decision",
    "observe_run_cost",
    "resolve_per_run_cap_usd",
    "resolve_per_session_cap_usd",
]

# Env-var NAMES (not secret values) for the cap overrides. Committed
# defaults so an unset env never means uncapped (preconditions.md leg
# (b): "defaults committed in the Dispatcher so unset-env does not mean
# uncapped"). Placeholders pending the first populated cost data.
_MAX_RUN_USD_ENV = "LIVESPEC_MAX_RUN_USD"
_MAX_SESSION_USD_ENV = "LIVESPEC_MAX_SESSION_USD"
_DEFAULT_MAX_RUN_USD = 25.0
_DEFAULT_MAX_SESSION_USD = 100.0

# The mode in which the dark-cost condition is a hard refusal. In
# `shadow` (explicit `--item`, human present) the same condition is a
# warn — preconditions.md §"Fail-closed means".
_AUTONOMOUS_MODE = "autonomous"


@dataclass(frozen=True, kw_only=True)
class CostObservation:
    """The per-run cost signal for one dispatched run (leak-free).

    `usd_micros` is fabro's `total_usd_micros` (integer micro-USD) when
    populated, else None. `observable` is True iff a real numeric cost
    was read — the single fact the fail-closed gate keys off. The run id
    is a non-credential-bearing correlation key (ULID-shaped).
    """

    run_id: str
    usd_micros: int | None
    observable: bool


@dataclass(frozen=True, kw_only=True)
class CostGateDecision:
    """The fail-closed gate verdict for one completed run (leak-free).

    `refuse` is True only when the loop must stop picking (autonomous +
    unobservable cost). `severity` is `critical` / `warn` / `info`.
    `reason` is a human, blob-free sentence naming the actionable
    condition + the run id.
    """

    refuse: bool
    severity: str
    reason: str


def observe_run_cost(*, ps_json: str, run_id: str) -> CostObservation:
    """Extract the per-run cost from `fabro ps -a --json` (the cost seam).

    Pure function over the `fabro ps -a --json` text. Finds the run
    record whose `run_id` matches, reads its `total_usd_micros`, and
    returns an observable cost iff that field is a real integer. A null /
    absent field, a run id not present in the output, or unparseable JSON
    all yield `observable=False` (never raises) — the unobservable
    condition the fail-closed gate fires on. When fabro starts populating
    the field, the same call surfaces the real value with no other
    change, which is exactly the forward-compatible seam y0m's cap reads.
    """
    micros = _total_usd_micros_for(ps_json=ps_json, run_id=run_id)
    return CostObservation(
        run_id=run_id,
        usd_micros=micros,
        observable=micros is not None,
    )


def cost_gate_decision(*, mode: str, observation: CostObservation) -> CostGateDecision:
    """The fail-closed cost gate (preconditions.md §"Fail-closed means").

    Autonomous (unattended) mode + an unobservable cost ⇒ REFUSE: the
    loop must stop picking rather than burn spend cost-blind. Shadow mode
    (a human is present) + the same condition ⇒ a `warn`, never a
    refusal. An OBSERVED cost (either mode) ⇒ `info`, never a refusal —
    cap-VALUE enforcement is y0m's job; 5v9's gate fires only on the
    unobservable condition, "fix the gate, not the bypass": the
    precondition is "cost is observable", not "a cap flag exists".
    """
    if observation.observable:
        return CostGateDecision(
            refuse=False,
            severity="info",
            reason=(
                f"run {observation.run_id} cost observable "
                f"({observation.usd_micros} usd_micros); cap-value check is y0m's"
            ),
        )
    if mode == _AUTONOMOUS_MODE:
        return CostGateDecision(
            refuse=True,
            severity="critical",
            reason=(
                f"run {observation.run_id} cost is UNOBSERVABLE (fabro "
                f"total_usd_micros null) in autonomous mode; refusing to keep "
                f"picking rather than burn spend cost-blind (fail-closed)"
            ),
        )
    return CostGateDecision(
        refuse=False,
        severity="warn",
        reason=(
            f"run {observation.run_id} cost is unobservable (fabro "
            f"total_usd_micros null); shadow mode has a human present, so "
            f"this is a warning rather than a refusal"
        ),
    )


def resolve_per_run_cap_usd(*, environ: dict[str, str]) -> float:
    """The per-run USD cap: `LIVESPEC_MAX_RUN_USD` or the committed default.

    The committed default ($25) means an unset env never reads as
    uncapped. An unparseable value falls back to the default rather than
    crashing. This is the cap VALUE y0m's per-run breach check consumes.
    """
    return _resolve_cap(environ=environ, name=_MAX_RUN_USD_ENV, default=_DEFAULT_MAX_RUN_USD)


def resolve_per_session_cap_usd(*, environ: dict[str, str]) -> float:
    """The per-session USD cap: `LIVESPEC_MAX_SESSION_USD` or the default ($100).

    Same committed-default discipline as the per-run cap. This is the cap
    VALUE y0m's per-session (sum-of-completed-runs) breach check consumes.
    """
    return _resolve_cap(
        environ=environ, name=_MAX_SESSION_USD_ENV, default=_DEFAULT_MAX_SESSION_USD
    )


def _resolve_cap(*, environ: dict[str, str], name: str, default: float) -> float:
    raw = environ.get(name, "")
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _total_usd_micros_for(*, ps_json: str, run_id: str) -> int | None:
    """Read `total_usd_micros` for `run_id` from `fabro ps -a --json` text.

    None on unparseable JSON, a non-array payload, a missing run, or a
    null / non-integer field. `bool` is excluded explicitly (a JSON
    `true` is an `int` in Python but is never a valid micro-USD count).
    """
    try:
        parsed_raw: object = json.loads(ps_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed_raw, list):
        return None
    for entry_raw in cast("list[object]", parsed_raw):
        if not isinstance(entry_raw, dict):
            continue
        entry = cast("dict[str, Any]", entry_raw)
        if entry.get("run_id") != run_id:
            continue
        micros_raw: object = entry.get("total_usd_micros")
        if isinstance(micros_raw, bool):
            return None
        if isinstance(micros_raw, int):
            return micros_raw
        return None
    return None
