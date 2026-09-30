"""The projection-failure fact: its identity, its records, and what resolves it.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Read failure is not absence. It emits exactly one flat fact
per run/node with id `hygiene:model-fallback-projection:<repo>:<run>:<node>`
... Repeated failures aggregate into that id; it clears only after
successful idempotent projection for the run/node or an attributed,
reason-required, append-only operator clearance naming that exact fact
id. Clearance retires the fact only and MUST NOT mint, retire, or
reinterpret a hold; run absence alone is never resolution."

THE REASON IS A CLOSED TYPED TOKEN, NEVER THE ERROR ITSELF. The same
section forbids an "unredacted diagnostic" in any record, and a fetch
failure's most natural payload -- the adapter's stderr -- is exactly
that. The four tokens below are the four arms the clause enumerates, and
the record carries the process exit code beside them as the one numeric
detail that cannot leak text.

RUN ABSENCE IS A FAILURE, NOT A RESOLUTION, and that is the single most
invertible rule here. A run the factory has forgotten produces the
cleanest possible "no events" answer: a query that succeeds and returns
nothing. Reading that as a completed projection would clear the fact and
resume unattended picking on a repository whose event stream was never
read. So `RUN_NOT_FOUND` is in the failure set, and only a record that
actually PROJECTED -- or an attributed operator clearance -- resolves.

CLEARANCE NAMES THE FACT ID AND NOTHING ELSE. The clause says it "MUST
NOT mint, retire, or reinterpret a hold", so the record carries no
scope, no hold key and no candidate identity; there is no field on it a
later reader could mistake for a hold target. The typed hold valve in
`_acp_hold_clear` writes a different stage entirely, so neither valve can
reach the other's records.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_journal_records import journal_records
from livespec_orchestrator_beads_fabro.commands._acp_schema_fields import non_empty_text

__all__: list[str] = [
    "PROJECTION_FACT_PREFIX",
    "PROJECTION_FAILURE_CLEARED_STAGE",
    "PROJECTION_FAILURE_REASONS",
    "PROJECTION_FAILURE_STAGE",
    "PROJECTION_SUCCESS_STAGE",
    "REASON_FETCH_FAILED",
    "REASON_RUN_NOT_FOUND",
    "REASON_TIMED_OUT",
    "REASON_UNPARSEABLE",
    "AcpProjectionFailure",
    "AcpProjectionFailureTarget",
    "projection_failure_clearance_record",
    "projection_failure_fact_id",
    "projection_failure_record",
    "projection_success_record",
    "unresolved_projection_failures",
]

PROJECTION_FACT_PREFIX = "hygiene:model-fallback-projection"

PROJECTION_FAILURE_STAGE = "acp-projection-failure"
PROJECTION_SUCCESS_STAGE = "acp-projection-succeeded"
PROJECTION_FAILURE_CLEARED_STAGE = "acp-projection-failure-cleared"

REASON_FETCH_FAILED = "fetch-failed"
REASON_TIMED_OUT = "timed-out"
REASON_UNPARSEABLE = "unparseable-payload"
REASON_RUN_NOT_FOUND = "run-not-found"

PROJECTION_FAILURE_REASONS: tuple[str, ...] = (
    REASON_FETCH_FAILED,
    REASON_TIMED_OUT,
    REASON_UNPARSEABLE,
    REASON_RUN_NOT_FOUND,
)


@dataclass(frozen=True, kw_only=True)
class AcpProjectionFailureTarget:
    """The run, node and factory ONE failure line is recorded against.

    Grouped rather than passed as five parallel arguments because they
    always travel together and always come from one projection attempt:
    a call site that could pass this run's id beside that factory's name
    is a call site that can record a fact nobody can act on.
    """

    repo: str
    run_id: str
    node: str
    factory_name: str
    factory_server_url: str


@dataclass(frozen=True, kw_only=True)
class AcpProjectionFailure:
    """One unresolved projection failure, aggregated across its repeats."""

    fact_id: str
    repo: str
    run_id: str
    node: str
    factory_name: str
    factory_server_url: str
    reason: str
    exit_code: int | None
    occurrences: int

    @property
    def summary(self) -> str:
        """The deterministic run / node / factory / error line the fact reports.

        Deterministic means two invocations over an unchanged journal
        render identical bytes, so every value here is read off the
        record: no clock, no elapsed time, and no host-dependent text.
        """
        exit_text = "n/a" if self.exit_code is None else str(self.exit_code)
        repeats = "" if self.occurrences == 1 else f" ({self.occurrences} attempts)"
        return (
            f"ACP fallback event projection failed for run {self.run_id} node {self.node} "
            f"on factory {self.factory_name} ({self.factory_server_url}): {self.reason}, "
            f"exit {exit_text}{repeats}. The run's event stream was never read, so no hold "
            "or model-fallback warning can be trusted absent for it."
        )


def projection_failure_fact_id(*, repo: str, run_id: str, node: str) -> str:
    """The one stable attention id every repeat of this failure aggregates into."""
    return f"{PROJECTION_FACT_PREFIX}:{repo}:{run_id}:{node}"


def projection_failure_record(
    *, target: AcpProjectionFailureTarget, reason: str, exit_code: int | None
) -> dict[str, object]:
    """Build one appendable failure line for a run and node that would not read."""
    return {
        "stage": PROJECTION_FAILURE_STAGE,
        "fact_id": projection_failure_fact_id(
            repo=target.repo, run_id=target.run_id, node=target.node
        ),
        "repo": target.repo,
        "run_id": target.run_id,
        "node": target.node,
        "factory_name": target.factory_name,
        "factory_server_url": target.factory_server_url,
        "reason": reason,
        "exit_code": exit_code,
    }


def projection_success_record(
    *,
    repo: str,
    run_id: str,
    node: str,
    projected: int,
    unobservable: int,
) -> dict[str, object]:
    """Build the appendable line one successful idempotent projection writes.

    It is written on EVERY successful projection, not only on one that
    found events: "clears only after successful idempotent projection for
    the run/node" is a statement about the READ succeeding, and a run
    that legitimately emitted no transition still proves its stream was
    read.
    """
    return {
        "stage": PROJECTION_SUCCESS_STAGE,
        "fact_id": projection_failure_fact_id(repo=repo, run_id=run_id, node=node),
        "repo": repo,
        "run_id": run_id,
        "node": node,
        "projected_observations": projected,
        "unobservable_events": unobservable,
    }


def projection_failure_clearance_record(*, fact_id: str, reason: str) -> dict[str, object]:
    """Build the appended line an operator's clearance of ONE fact id writes.

    `at`, `invoker` and `invoker_source` are stamped by the append layer,
    which is what makes the attribution the clause requires a property of
    the record rather than of its writer's good intentions.
    """
    return {
        "stage": PROJECTION_FAILURE_CLEARED_STAGE,
        "fact_id": fact_id,
        "reason": reason,
    }


def unresolved_projection_failures(
    *, journal_path: Path | None
) -> tuple[AcpProjectionFailure, ...]:
    """Every projection failure still standing, newest state per fact id.

    The fold is forward and LAST-WRITE-WINS per fact id, which is the
    opposite of the hold ledger's first-write-wins and deliberately so:
    a hold must not have its expiry refreshed by a replay, while a
    repeated read failure should report the most recent reason rather
    than the first one an operator has already seen.
    """
    failures: dict[str, AcpProjectionFailure] = {}
    for record in journal_records(journal_path=journal_path):
        stage = record.get("stage")
        fact_id = non_empty_text(value=record.get("fact_id"))
        if fact_id is None:
            continue
        if stage in (PROJECTION_SUCCESS_STAGE, PROJECTION_FAILURE_CLEARED_STAGE):
            _ = failures.pop(fact_id, None)
            continue
        if stage != PROJECTION_FAILURE_STAGE:
            continue
        parsed = _parse_failure(record=record, fact_id=fact_id, prior=failures.get(fact_id))
        if parsed is not None:
            failures[fact_id] = parsed
    return tuple(failures[key] for key in sorted(failures))


def _exit_code(*, value: object) -> int | None:
    """The recorded process exit code, or `None` when none was readable."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _parse_failure(
    *, record: Mapping[str, Any], fact_id: str, prior: AcpProjectionFailure | None
) -> AcpProjectionFailure | None:
    """One stored failure line, carrying forward the count of its repeats."""
    texts: dict[str, str] = {}
    for name in ("repo", "run_id", "node", "factory_name", "factory_server_url", "reason"):
        value = non_empty_text(value=record.get(name))
        if value is None:
            return None
        texts[name] = value
    if texts["reason"] not in PROJECTION_FAILURE_REASONS:
        return None
    exit_code = record.get("exit_code")
    return AcpProjectionFailure(
        fact_id=fact_id,
        repo=texts["repo"],
        run_id=texts["run_id"],
        node=texts["node"],
        factory_name=texts["factory_name"],
        factory_server_url=texts["factory_server_url"],
        reason=texts["reason"],
        exit_code=_exit_code(value=exit_code),
        occurrences=1 if prior is None else prior.occurrences + 1,
    )
