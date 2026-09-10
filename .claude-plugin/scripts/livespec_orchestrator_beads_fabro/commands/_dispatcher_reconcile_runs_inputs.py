"""Everything one reconciliation pass reads or writes through.

The seams live apart from the pass that drives them because they are a
different kind of thing: this module says what the reconciler is allowed to
touch, and `_dispatcher_reconcile_runs.py` says what it does with that. The
split is what makes the module docstring's central guarantee checkable at a
glance — the ledger seam handed in is COMMENTS-ONLY, so reconciliation
structurally cannot write a work-item's status, `blocked_reason` or labels.

`port_for` sits here rather than beside the survey loop for the same reason:
opening a Fabro port onto a factory is reading a seam, and every field it
needs is a field of the bundle above it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    JournaledRuns,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
    LedgerComments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_grace import (
    DEFAULT_BLOCKED_RUN_GRACE_SECONDS,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import (
    FabroHttpTransport,
    UrllibFabroHttpTransport,
)
from livespec_orchestrator_beads_fabro.commands._run_attribution import (
    GOAL_TEXT_ONLY,
    RunAttribution,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "ReconcileInputs",
    "port_for",
]


@dataclass(frozen=True, kw_only=True)
class ReconcileInputs:
    """Everything one reconciliation pass reads or writes through.

    `now_epoch` is a seam rather than a call site: the grace arm compares a
    measured park against a configured bound, and a test that cannot say what
    time it is can only assert the boundary by sleeping.
    """

    repo: Path
    fabro_bin: str
    id_prefix: str
    items: Sequence[WorkItem]
    journaled: JournaledRuns
    runner: CommandRunner
    journal: JournalWriter
    ledger: LedgerComments
    # The run-to-item evidence this repo has recorded. Defaulted to the
    # regex-only value so a caller that cannot reach the ledger still reconciles
    # rather than refusing; the join composes it with the journal index.
    attribution: RunAttribution = GOAL_TEXT_ONLY
    http: FabroHttpTransport = field(default_factory=UrllibFabroHttpTransport)
    # Narrows the pass to runs attributed to ONE work-item. The default (None)
    # is the whole-inventory sweep; a lifecycle-write hook sets it so closing
    # item A can never reap item B's run as a side effect of A's disposition.
    # It narrows what is ACTED ON, never what is classified: the join still
    # sees every item's status, so a targeted pass and a sweep agree about
    # every run they both look at.
    only_work_item_id: str | None = None
    # How long a run parked at a human gate may hold a slot while its item is
    # still live. `0` disables that arm outright — nothing is inspected and
    # nothing is held — and the moot-question join stands alone.
    blocked_run_grace_seconds: int = DEFAULT_BLOCKED_RUN_GRACE_SECONDS
    now_epoch: float | None = None
    # Reconciliation telemetry shares calibration's already-tailed OTLP file.
    # Both values are optional so pure/read-only callers keep no IO obligation.
    telemetry_spans_path: Path | None = None
    cancelling_actor: str | None = None
    # Observation-only callers may use goal text as a hint. Destructive and
    # destructive-projection callers retain the fail-safe default.
    allow_goal_text_attribution: bool = False


def port_for(*, inputs: ReconcileInputs, factory: FactoryTarget) -> FabroPort:
    """Open a Fabro port onto one declared factory's server."""
    return FabroPort(
        fabro_bin=inputs.fabro_bin,
        target=FabroTarget(server_url=factory.server, dev_token=factory.dev_token),
        runner=inputs.runner,
        cwd=inputs.repo,
        http=inputs.http,
    )
