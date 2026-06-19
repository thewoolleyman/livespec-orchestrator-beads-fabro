"""The periodic calibration analysis pass — advisory size-ceiling proposals.

This is the grooming realization's calibration leg (behavior 7,
SPECIFICATION/scenarios.md "Scenario 13 — Calibration analysis pass proposes
advisory thresholds"), the authoritative normative clause being
contracts.md §"Grooming and slice-size calibration" → "Gap-detectable
behavior clauses":

    A periodic calibration analysis pass MUST correlate run outcomes against
    the recorded mechanical size proxies and MUST propose ceiling thresholds
    that remain advisory until a maintainer adopts them (it MUST NOT
    auto-enforce a threshold and MUST NOT run as an always-on service).

It consumes EXACTLY the calibration telemetry behavior 6
(`commands/_dispatcher_calibration.py`, work-item `livespec-impl-beads-yfsv4j`)
records onto the existing Dispatcher journal: one flat `calibration`-stage
record per terminal dispatch carrying the run-outcome signal (`converged`,
`bounced_to_regroom`, `outcome_class`, …) plus the mechanical size proxies
(`acceptance_count`, `merged_pr_diff_size`, `dependency_fan_out`,
`dispatch_context_size`, …). This pass reads that accumulated journal,
correlates the size proxies against non-convergence, and proposes a ceiling
for each proxy whose larger values empirically predict non-convergence.

Two design commitments hold the spec's guardrails:

  * **Advisory only — never auto-enforced.** The pass is a pure correlation
    that RETURNS a `CalibrationProposal`. It writes nothing, mutates no gate
    config, touches no ledger. `CalibrationProposal.advisory` is `True` and
    `adopted` is `False` by construction; adoption is a separate maintainer
    act this module never performs. Nothing here flags, blocks, or routes a
    work-item — it only proposes numbers a maintainer MAY later wire into the
    intake size-gate (which itself stays advisory per
    §"Gate type determines hard versus advisory").
  * **On-demand, not a daemon.** The entry point is a synchronous pure
    function a maintainer (or a periodic invocation) calls over an
    already-accumulated journal. There is no loop, no scheduler, no
    background thread, no always-on service — the pass runs, proposes, and
    returns. The accumulation cadence is the Dispatcher's existing journal
    writes; this pass merely reads the snapshot it is handed.

`load_calibration_records` is the only IO seam (a fail-soft journal read
mirroring `dispatcher._read_journal_records_for`); the correlation core
(`analyze_calibration`) is pure and never raises, so the same proposal is
reproducible from the same records.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

__all__: list[str] = [
    "CalibrationProposal",
    "ProxyThreshold",
    "analyze_calibration",
    "load_calibration_records",
]

# The mechanical size proxies the Dispatcher journals (the numeric subset of
# `_dispatcher_calibration.CalibrationRecord` — the proxies a scalar ceiling
# can be proposed over). `spec_surface_touched` (bool), `archetype` / `repo`
# (categorical) carry no orderable ceiling and are correlated context, not
# threshold candidates. Order is the stable proposal order.
_NUMERIC_SIZE_PROXIES: tuple[str, ...] = (
    "acceptance_count",
    "merged_pr_diff_size",
    "dependency_fan_out",
    "dispatch_context_size",
)

# A ceiling is proposed only when both partitions either side of the cutoff
# carry at least this many runs — below this the lift is noise, not signal,
# and the pass declines to propose (insufficient data, never a false zero).
_MIN_PARTITION_RUNS = 2

# A cutoff is proposed only when the above-cutoff non-convergence rate
# exceeds the below-cutoff rate by at least this margin — a smaller lift is
# not a confident ceiling.
_MIN_LIFT = 0.25


@dataclass(frozen=True, kw_only=True)
class ProxyThreshold:
    """One size proxy's proposed advisory ceiling (or the no-signal verdict).

    `ceiling` is the proposed advisory cutoff: an item whose proxy value is
    at or above `ceiling` is the empirically oversized region the intake
    size-gate MAY later flag (advisorily). `ceiling` is `None` when the
    accumulated runs carry no confident signal for this proxy — declined,
    never a false zero. The supporting fields narrate WHY a maintainer might
    adopt it: the non-convergence rate at/above versus below the cutoff, and
    the run counts behind each rate.
    """

    proxy: str
    ceiling: int | None
    non_convergence_rate_at_or_above: float
    non_convergence_rate_below: float
    runs_at_or_above: int
    runs_below: int


@dataclass(frozen=True, kw_only=True)
class CalibrationProposal:
    """The analysis pass's advisory output over an accumulated journal.

    `thresholds` is one `ProxyThreshold` per numeric size proxy (in the
    stable `_NUMERIC_SIZE_PROXIES` order), each either proposing an advisory
    ceiling or declining for want of signal. `advisory` is `True` and
    `adopted` is `False` by construction — this pass NEVER enforces a
    threshold and NEVER adopts one; adoption is a separate maintainer act.
    `total_runs` / `non_converged_runs` summarize the correlated journal.
    """

    advisory: bool
    adopted: bool
    total_runs: int
    non_converged_runs: int
    thresholds: tuple[ProxyThreshold, ...]


@dataclass(frozen=True, kw_only=True)
class _Observation:
    """One calibration run reduced to (size proxy values, non-convergence).

    `proxies` maps each numeric proxy name to its observed value for this
    run, omitting any proxy the record recorded as unobservable (`None`) so
    absence is treated as missing data, never as zero. `non_converged` is the
    run-outcome correlation target.
    """

    proxies: dict[str, int]
    non_converged: bool


def load_calibration_records(*, journal_path: Path) -> tuple[dict[str, object], ...]:
    """Read the `calibration`-stage records back from a Dispatcher journal.

    The one IO seam: a fail-soft read of the on-disk journal JSONL (mirroring
    `dispatcher._read_journal_records_for`) that returns only the flat
    `calibration`-stage records the analysis pass correlates. A missing or
    unreadable journal yields an empty tuple, and malformed or non-`calibration`
    lines are skipped — the pass declines to propose on no data rather than
    raising. `calibration-error` records (the fail-open wiring breadcrumbs) are
    not calibration data and are skipped here.
    """
    if not journal_path.is_file():
        return ()
    records: list[dict[str, object]] = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        try:
            parsed: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        mapping = cast("dict[object, object]", parsed)
        record = {str(key): value for key, value in mapping.items()}
        if record.get("stage") == "calibration":
            records.append(record)
    return tuple(records)


def analyze_calibration(*, records: tuple[dict[str, object], ...]) -> CalibrationProposal:
    """Correlate run outcomes against size proxies; propose advisory ceilings.

    The pure correlation core (no IO, never raises). For each numeric size
    proxy it partitions the observed runs at every candidate cutoff and
    proposes the cutoff whose at-or-above region most strongly predicts
    non-convergence (subject to the minimum-sample and minimum-lift guards),
    declining for want of signal otherwise. Every proposed ceiling is
    advisory by construction — the returned proposal enforces nothing.
    """
    observations = tuple(_to_observation(record=record) for record in records)
    non_converged = sum(1 for observation in observations if observation.non_converged)
    thresholds = tuple(
        _propose_threshold(proxy=proxy, observations=observations)
        for proxy in _NUMERIC_SIZE_PROXIES
    )
    return CalibrationProposal(
        advisory=True,
        adopted=False,
        total_runs=len(observations),
        non_converged_runs=non_converged,
        thresholds=thresholds,
    )


def _to_observation(*, record: dict[str, object]) -> _Observation:
    """Reduce one `calibration` journal record to a correlatable observation.

    A run is `non_converged` when it did not converge OR it bounced back to
    `needs-regroom` (the empirical "too big" signal). Each numeric proxy is
    carried only when its recorded value is a usable `int` — a `None` (the
    Dispatcher's unobservable marker) or a non-numeric is omitted so the proxy
    simply has one fewer sample, never a false zero pulling the cutoff down.
    """
    converged = record.get("converged") is True
    bounced = record.get("bounced_to_regroom") is True
    proxies: dict[str, int] = {}
    for proxy in _NUMERIC_SIZE_PROXIES:
        value = record.get(proxy)
        # bool is an int subclass; a stray boolean is not a size value.
        if isinstance(value, int) and not isinstance(value, bool):
            proxies[proxy] = value
    return _Observation(proxies=proxies, non_converged=(not converged) or bounced)


def _propose_threshold(*, proxy: str, observations: tuple[_Observation, ...]) -> ProxyThreshold:
    """Propose the most-predictive advisory ceiling for one size proxy.

    Considers every distinct observed value as a candidate cutoff and keeps
    the one whose at-or-above non-convergence rate most exceeds its
    below-cutoff rate, subject to the minimum-partition and minimum-lift
    guards. Declines (a `None` ceiling) when no candidate clears the guards —
    too few runs, or no cutoff that separates non-convergence.
    """
    samples = tuple(
        (observation.proxies[proxy], observation.non_converged)
        for observation in observations
        if proxy in observation.proxies
    )
    candidates = sorted({value for value, _ in samples})
    best: ProxyThreshold | None = None
    for cutoff in candidates:
        evaluated = _evaluate_cutoff(proxy=proxy, cutoff=cutoff, samples=samples)
        if evaluated is None:
            continue
        if best is None or _lift(threshold=evaluated) > _lift(threshold=best):
            best = evaluated
    if best is not None:
        return best
    return ProxyThreshold(
        proxy=proxy,
        ceiling=None,
        non_convergence_rate_at_or_above=0.0,
        non_convergence_rate_below=0.0,
        runs_at_or_above=0,
        runs_below=0,
    )


def _evaluate_cutoff(
    *,
    proxy: str,
    cutoff: int,
    samples: tuple[tuple[int, bool], ...],
) -> ProxyThreshold | None:
    """Score one candidate cutoff; return a `ProxyThreshold` or `None`.

    Returns `None` when either partition is below the minimum-run guard or
    the lift (at-or-above rate minus below rate) is under the minimum-lift
    guard — i.e. the cutoff is not a confident ceiling. Otherwise returns the
    threshold carrying the proposed `ceiling` and its supporting rates/counts.
    """
    at_or_above = tuple(non_converged for value, non_converged in samples if value >= cutoff)
    below = tuple(non_converged for value, non_converged in samples if value < cutoff)
    if len(at_or_above) < _MIN_PARTITION_RUNS or len(below) < _MIN_PARTITION_RUNS:
        return None
    rate_at_or_above = sum(at_or_above) / len(at_or_above)
    rate_below = sum(below) / len(below)
    if rate_at_or_above - rate_below < _MIN_LIFT:
        return None
    return ProxyThreshold(
        proxy=proxy,
        ceiling=cutoff,
        non_convergence_rate_at_or_above=rate_at_or_above,
        non_convergence_rate_below=rate_below,
        runs_at_or_above=len(at_or_above),
        runs_below=len(below),
    )


def _lift(*, threshold: ProxyThreshold) -> float:
    """The cutoff's separating power — at-or-above minus below rate."""
    return threshold.non_convergence_rate_at_or_above - threshold.non_convergence_rate_below
