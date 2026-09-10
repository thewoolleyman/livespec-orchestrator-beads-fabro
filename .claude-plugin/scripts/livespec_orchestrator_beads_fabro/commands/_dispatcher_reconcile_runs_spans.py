"""OTLP spans that make reconciliation and every cancellation queryable."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._otel_scrub import attr as _attr

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_pass import (
        ReconcilePassSummary,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_records import (
        ReconciledRun,
    )

__all__: list[str] = [
    "emit_reconcile_pass_span",
    "emit_reconcile_termination_spans",
    "reconcile_pass_request_line",
    "reconcile_termination_request_line",
]

_SERVICE_NAME = "livespec-dispatcher"
_SERVICE_NAMESPACE = "livespec-family"
_SCOPE_NAME = "livespec.dispatcher.reconcile-runs"
_SCOPE_VERSION = "0.1.0"
_SPAN_KIND_INTERNAL = 1


def emit_reconcile_pass_span(
    *,
    summary: ReconcilePassSummary,
    tenant: str,
    cancelling_actor: str,
    spans_path: Path,
    now_ns: int,
) -> None:
    """Append the one span proving a reconciliation pass actually ran."""
    _append(
        path=spans_path,
        line=reconcile_pass_request_line(
            summary=summary,
            tenant=tenant,
            cancelling_actor=cancelling_actor,
            now_ns=now_ns,
        ),
    )


def emit_reconcile_termination_spans(
    *,
    run: ReconciledRun,
    cancelling_actor: str,
    spans_path: Path,
    now_ns: int,
) -> None:
    """Append a termination span and the victim-keyed calibration signal."""
    _append(
        path=spans_path,
        line=reconcile_termination_request_line(
            run=run,
            cancelling_actor=cancelling_actor,
            now_ns=now_ns,
        ),
    )


def reconcile_pass_request_line(
    *, summary: ReconcilePassSummary, tenant: str, cancelling_actor: str, now_ns: int
) -> str:
    attrs: dict[str, object] = {
        "livespec.tenant": tenant,
        "reconcile.factories_surveyed": summary.factories_surveyed,
        "reconcile.orphans_found": summary.orphans_found,
        "reconcile.orphans_reconciled": summary.orphans_reconciled,
        "reconcile.dry_run": summary.dry_run,
        "reconcile.errors": summary.errors,
        "reconcile.cancelling_actor": cancelling_actor,
    }
    span = _span(
        name="dispatcher.reconcile-runs-pass",
        key=f"pass:{tenant}:{now_ns}",
        attrs=attrs,
        now_ns=now_ns,
    )
    return _request_line(spans=[span])


def reconcile_termination_request_line(
    *, run: ReconciledRun, cancelling_actor: str, now_ns: int
) -> str:
    shared: dict[str, object] = {
        "fabro.run_id": run.run_id,
        "work.item.id": run.work_item_id,
        "livespec.tenant": run.tenant,
        "reconcile.orphan_reason": run.orphan_reason,
        "fabro.status.kind": run.status_kind,
        "reconcile.termination_route": run.termination_route,
        "reconcile.termination_succeeded": run.termination_succeeded,
        "reconcile.attribution_source": run.attribution_source,
        "reconcile.cancelling_actor": cancelling_actor,
    }
    termination = _span(
        name="dispatcher.reconcile-runs-termination",
        key=f"termination:{run.run_id}:{now_ns}",
        attrs=shared,
        now_ns=now_ns,
    )
    calibration = _span(
        name="dispatcher.calibration",
        key=f"cancellation-calibration:{run.run_id}:{now_ns}",
        attrs={
            **shared,
            "converged": False,
            "outcome_class": "failed:fabro-run",
            "fabro.failure.category": "canceled",
            "fabro.failure.cause": f"reconcile-runs cancellation by {cancelling_actor}",
            "fabro.failure.signature": (f"reconcile-runs|canceled|{run.termination_route}"),
        },
        now_ns=now_ns,
    )
    return _request_line(spans=[termination, calibration])


def _span(*, name: str, key: str, attrs: dict[str, object], now_ns: int) -> dict[str, object]:
    return {
        "traceId": _hex_id(key=f"trace:{key}", nbytes=16),
        "spanId": _hex_id(key=f"span:{key}", nbytes=8),
        "name": name,
        "kind": _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": str(now_ns),
        "endTimeUnixNano": str(now_ns),
        "attributes": [_attr(key=key, value=value) for key, value in attrs.items()],
    }


def _request_line(*, spans: list[dict[str, object]]) -> str:
    request: dict[str, object] = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": _SERVICE_NAME}},
                        {
                            "key": "service.namespace",
                            "value": {"stringValue": _SERVICE_NAMESPACE},
                        },
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": _SCOPE_NAME, "version": _SCOPE_VERSION},
                        "spans": spans,
                    }
                ],
            }
        ]
    }
    return json.dumps(request, separators=(",", ":"), sort_keys=True)


def _append(*, path: Path, line: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            _ = handle.write(line + "\n")
    except OSError:
        return


def _hex_id(*, key: str, nbytes: int) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[: nbytes * 2]
