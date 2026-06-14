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
from typing import Any, Protocol, cast

from livespec_impl_beads.commands._dispatcher_engine import DispatchOutcome
from livespec_impl_beads.commands._dispatcher_plan import parse_run_id_for_work_item


class JournalWriter(Protocol):
    """Append-one-record seam (mirrors `_dispatcher_engine.JournalWriter`)."""

    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


__all__: list[str] = [
    "COST_MODE_ENFORCE",
    "COST_MODE_REPORT",
    "CostGateDecision",
    "CostObservation",
    "JournalWriter",
    "cap_value_decision",
    "cost_gate_decision",
    "gate_wave",
    "observe_run_cost",
    "resolve_cost_mode",
    "resolve_per_run_cap_usd",
    "resolve_per_session_cap_usd",
    "usd_micros_to_usd",
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

# The cost-mode lever (`LIVESPEC_COST_MODE`): the NAME of an env var, not a
# secret. `report` (the DEFAULT) derives + emits the API-equivalent cost as
# an observability signal and NEVER refuses / applies caps — the
# subscription-billing model the user runs on (provider-side spend limits,
# so a fail-closed dollar gate is the wrong model). `enforce` is the
# opt-in fail-closed gate (5v9 unobservable refusal + y0m cap-value
# breach), retained intact for anyone actually on API billing. An
# unset / unrecognized value resolves to `report` — the lever is always
# wired and only the explicit `enforce` value flips on enforcement.
_COST_MODE_ENV = "LIVESPEC_COST_MODE"
COST_MODE_REPORT = "report"
COST_MODE_ENFORCE = "enforce"
_DEFAULT_COST_MODE = COST_MODE_REPORT


def resolve_cost_mode(*, environ: dict[str, str]) -> str:
    """Resolve `LIVESPEC_COST_MODE` to `report` (default) or `enforce`.

    Mirrors the committed-default discipline of the cap resolvers: an
    unset, empty, or unrecognized value resolves to `report` (the
    subscription-friendly default), so the spend machinery is observe-only
    unless an operator explicitly opts into `enforce`. The lever is always
    wired — `report` is never a silent skip of the cost derivation, only of
    the refusal / cap application.
    """
    if environ.get(_COST_MODE_ENV, "").strip() == COST_MODE_ENFORCE:
        return COST_MODE_ENFORCE
    return _DEFAULT_COST_MODE


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


def usd_micros_to_usd(*, usd_micros: int) -> float:
    """Convert fabro's integer micro-USD cost to a USD float for cap comparison.

    fabro reports `total_usd_micros` as an integer count of millionths of a
    dollar; the cap defaults / env overrides are plain USD floats
    (`$25` / `$100`). This is the single conversion the cap-VALUE check
    funnels through, so the unit boundary lives in one place.
    """
    return usd_micros / 1_000_000


def cap_value_decision(
    *,
    run_id: str,
    usd_micros: int,
    per_run_cap_usd: float,
    session_usd_micros_after: int,
    per_session_cap_usd: float,
) -> CostGateDecision:
    """The per-run + per-session USD cap-VALUE gate (y0m's spend cap).

    The fail-CLOSED comparison 5v9 deferred: given an OBSERVED per-run cost
    (`usd_micros`) and the cumulative session cost INCLUDING this run
    (`session_usd_micros_after`), refuse when EITHER ceiling is exceeded —
    the per-run cap (this single run cost more than `per_run_cap_usd`) or
    the per-session cap (the running total has crossed `per_session_cap_usd`).
    A breach of either is a `critical` REFUSE so the loop halts / abandons
    rather than burn spend past the committed ceiling. Within both caps ⇒
    `info`, the loop proceeds.

    This path is DORMANT in the current fabro version: `total_usd_micros`
    is null on every run (the 5v9 finding), so `gate_wave` never reaches a
    cap-value comparison today and the unobservable gate
    (`cost_gate_decision`) fires instead. It is correct + unit-tested for
    the moment fabro begins reporting cost (tracked as
    livespec-impl-beads-efj), at which point the comparison goes live with
    no further code change. Caller resolves the caps from the committed
    env-overridable defaults (`resolve_per_run_cap_usd` /
    `resolve_per_session_cap_usd`).

    Leak-free: the reason carries only the run id and the scalar USD
    figures — no goal text, env values, or remote URLs.
    """
    run_usd = usd_micros_to_usd(usd_micros=usd_micros)
    session_usd = usd_micros_to_usd(usd_micros=session_usd_micros_after)
    if run_usd > per_run_cap_usd:
        return CostGateDecision(
            refuse=True,
            severity="critical",
            reason=(
                f"run {run_id} cost ${run_usd:.6f} EXCEEDS the per-run cap "
                f"${per_run_cap_usd:.2f}; halting rather than burn spend past "
                f"the committed ceiling (fail-closed)"
            ),
        )
    if session_usd > per_session_cap_usd:
        return CostGateDecision(
            refuse=True,
            severity="critical",
            reason=(
                f"run {run_id} pushes the session total to ${session_usd:.6f}, "
                f"EXCEEDING the per-session cap ${per_session_cap_usd:.2f}; halting "
                f"rather than burn spend past the committed ceiling (fail-closed)"
            ),
        )
    return CostGateDecision(
        refuse=False,
        severity="info",
        reason=(
            f"run {run_id} cost ${run_usd:.6f} within the per-run cap "
            f"${per_run_cap_usd:.2f}; session total ${session_usd:.6f} within "
            f"the per-session cap ${per_session_cap_usd:.2f}"
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


def gate_wave(  # noqa: PLR0913 — kw-only post-verdict gate/reporter; each field is an independent caller input.
    *,
    mode: str,
    outcomes: tuple[DispatchOutcome, ...],
    ps_json: str,
    journal: JournalWriter,
    environ: dict[str, str] | None = None,
    derived_cost_micros_by_work_item: dict[str, int] | None = None,
    cost_mode: str = COST_MODE_REPORT,
) -> tuple[str, ...]:
    """Apply the cost gate / reporter to a completed dispatch wave (5v9 + y0m + efj).

    Called AFTER the wave's verdict / exit code is computed (alongside
    `reflect` and the ntfy alarm), so it can never change the verdict.
    For each outcome that actually LAUNCHED a fabro run — a `green`
    terminal outcome (the only state with a confirmed run + a cost record
    to read; `failed`/`blocked` runs either never launched, like uvd's
    host-only refusal, or have no meaningful cost yet) — it resolves the
    run id from `ps_json` (`fabro ps -a --json`), observes the per-run
    cost, decides the gate, and journals one `cost-gate` record carrying
    ONLY leak-free scalars (work-item id, severity, refuse, observable,
    usd_micros). A run whose id cannot be resolved is journaled as
    `cost-gate-skipped` (the cost is unknown for an unknown run) and is
    NOT a refusal — fail-open. Returns the work-item ids that REFUSED,
    which the caller turns into a `spend-cap`-class ntfy alarm event.

    `cost_mode` (`LIVESPEC_COST_MODE`) selects the posture:

      * `report` (the DEFAULT, the subscription-billing model): the
        per-run + running per-session API-equivalent cost is STILL derived
        from the token sums, and one `cost-gate` record per run is still
        journaled, but the verdict is forced `refuse=False` /
        `severity="report"` — the fail-closed "unobservable ⇒ refuse"
        branch and the cap-breach refusal are BOTH suppressed, so this
        ALWAYS returns no refusals and never short-circuits dispatch. The
        derived cost is observability, not a gate.
      * `enforce` (opt-in, anyone on API billing): the original
        fail-closed two-layer verdict below runs intact.

    The `enforce` verdict is decided in two layers:

      * UNOBSERVABLE cost ⇒ `cost_gate_decision` (5v9): autonomous mode
        refuses, shadow warns. This is the fall-back when NO telemetry
        arrived for the run — the genuinely-dark condition the fail-closed
        refusal exists for.
      * OBSERVED cost ⇒ y0m's `cap_value_decision`: the per-run cost is
        accumulated into a running per-session total and BOTH are compared
        to the committed env-overridable caps (`resolve_per_run_cap_usd` /
        `resolve_per_session_cap_usd`); exceeding either ceiling refuses
        fail-closed. The session total accumulates across every observed
        run in the wave (the loop's per-session cumulative spend).

    `derived_cost_micros_by_work_item` (efj) is the PRIMARY observed-cost
    source: the per-dispatch cost the host OTLP receiver DERIVES from CC
    token telemetry (`_dispatcher_cost_sink`), keyed by work-item id. When
    a run has a derived cost it becomes the observed cost — so the common
    path is now OBSERVABLE and 5v9's autonomous fail-closed refusal NO
    LONGER fires, activating the (previously dormant) `cap_value_decision`.
    Per `cc-otel-gap-analysis.md` §"Conclusion 9", CC-token-derived cost is
    the primary signal; fabro's `total_usd_micros` (read from `ps_json`) is
    corroboration, used only when no derived cost is present. The
    fail-closed branch STILL fires (in `enforce` mode) when cost is
    genuinely unobservable (no telemetry arrived AND fabro's field is null)
    — the gate is not blinded, the common path is merely made observable.

    `environ` gates the cap-VALUE layer: when None (5v9's call shape) an
    observed cost is `info` and the cap comparison is skipped; when supplied
    (the dispatcher's live wiring passes `os.environ`) the caps resolve from
    it and the cap-value comparison runs.
    """
    refusals: list[str] = []
    session_usd_micros = 0
    derived = derived_cost_micros_by_work_item or {}
    enforcing = cost_mode == COST_MODE_ENFORCE
    per_run_cap = resolve_per_run_cap_usd(environ=environ) if environ is not None else None
    per_session_cap = resolve_per_session_cap_usd(environ=environ) if environ is not None else None
    for outcome in outcomes:
        if outcome.status != "green":
            continue
        run_id = parse_run_id_for_work_item(ps_json=ps_json, work_item_id=outcome.work_item_id)
        if run_id is None:
            journal.append(
                record={
                    "stage": "cost-gate-skipped",
                    "work_item_id": outcome.work_item_id,
                    "reason": "could not resolve the run id from `fabro ps -a --json`",
                }
            )
            continue
        observation = _observe_with_derived(
            ps_json=ps_json,
            run_id=run_id,
            derived_micros=derived.get(outcome.work_item_id),
        )
        usd_micros = observation.usd_micros
        if usd_micros is not None:
            # The running per-session total accumulates the observed cost in
            # BOTH modes (report needs the cumulative spend for its summary;
            # enforce needs it for the cap comparison).
            session_usd_micros += usd_micros
        # In `report` mode (the default) the cost is derived + journaled but
        # NEVER refused / capped — the verdict is a non-refusing `report`.
        # In `enforce` mode the original two-layer fail-closed verdict runs:
        # the cap-VALUE path (y0m) when the cost is OBSERVED and the caps are
        # resolved (environ supplied), else 5v9's unobservable gate. The
        # explicit non-None checks narrow the optional cost + caps for the
        # type checker.
        if not enforcing:
            decision = _report_decision(run_id=run_id, observation=observation)
        elif usd_micros is not None and per_run_cap is not None and per_session_cap is not None:
            decision = cap_value_decision(
                run_id=run_id,
                usd_micros=usd_micros,
                per_run_cap_usd=per_run_cap,
                session_usd_micros_after=session_usd_micros,
                per_session_cap_usd=per_session_cap,
            )
        else:
            decision = cost_gate_decision(mode=mode, observation=observation)
        journal.append(
            record={
                "stage": "cost-gate",
                "work_item_id": outcome.work_item_id,
                "run_id": run_id,
                "observable": observation.observable,
                "usd_micros": observation.usd_micros,
                "session_usd_micros": session_usd_micros,
                "refuse": decision.refuse,
                "severity": decision.severity,
                "reason": decision.reason,
            }
        )
        if decision.refuse:
            refusals.append(outcome.work_item_id)
    return tuple(refusals)


def _report_decision(*, run_id: str, observation: CostObservation) -> CostGateDecision:
    """The report-mode verdict: never refuse, never cap (subscription model).

    The derived cost is OBSERVABILITY, not a gate: this always returns
    `refuse=False` with a `report` severity, so report mode can never
    short-circuit dispatch — neither the 5v9 unobservable refusal nor the
    y0m cap-breach refusal fires. The reason carries only the run id + the
    derived micro-USD (or the dark condition), leak-free.
    """
    if observation.observable:
        return CostGateDecision(
            refuse=False,
            severity="report",
            reason=(
                f"run {run_id} cost reported "
                f"({observation.usd_micros} usd_micros); report-only, never enforced"
            ),
        )
    return CostGateDecision(
        refuse=False,
        severity="report",
        reason=(
            f"run {run_id} cost is unobservable (no CC token telemetry / fabro "
            f"total_usd_micros null); report-only, never enforced"
        ),
    )


def _observe_with_derived(
    *, ps_json: str, run_id: str, derived_micros: int | None
) -> CostObservation:
    """The per-run cost observation, CC-token-derived cost PRIMARY (efj).

    When a CC-token-derived cost is present for the run it is the observed
    cost (the primary signal per `cc-otel-gap-analysis.md` §"Conclusion 9")
    — so the common path is OBSERVABLE and the autonomous fail-closed
    refusal no longer fires. Absent a derived cost, falls back to fabro's
    `total_usd_micros` from `fabro ps -a --json` (corroboration); a null
    field there leaves the cost UNOBSERVABLE, the genuinely-dark condition
    5v9's fail-closed gate still fires on.
    """
    if derived_micros is not None:
        return CostObservation(run_id=run_id, usd_micros=derived_micros, observable=True)
    return observe_run_cost(ps_json=ps_json, run_id=run_id)


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
