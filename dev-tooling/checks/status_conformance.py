# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""status_conformance — beads-private status-conformance doctor check.

Wires the Dispatcher's `status-conformance` Ledger invariant into
`just check` / `/livespec:doctor`. That invariant lives in the Ledger-check
registry (`commands/_dispatcher_ledger_checks.py`, run by the Dispatcher's
hard pre-dispatch gate); this script is the thin enforcement-suite surface
that runs the SAME registry over the configured tenant so the gate also
fires from the aggregate — not only at dispatch time.

The invariant: every LIVE (non-`done`) work-item's stored beads status
MUST be one of `ALLOWED_BEADS_STATUSES` — the canonical 7-state lifecycle
projected through the adapter's `done` → `closed` rename, DERIVED from the
`WorkItemStatus` Literal (never hand-typed). Beads' native `open`/`deferred`
or an ad-hoc `bd update --status foo` is out-of-lifecycle: `lane_of` parks
it in an unknown lane where it silently never dispatches. This check NAMES
the offending item id(s) and the bad status and fails (exit 1).

The check walks every materialized work-item from the configured store
descriptor through the same beads client the runtime uses. In hermetic mode
(`LIVESPEC_BEADS_FAKE` truthy, the default `just check` tier) the tenant is
empty, so the walk yields nothing and the check passes trivially; a
live-tier audit runs out-of-band with the connection env configured. The
check performs NO git or network I/O.

Per-finding diagnostics flow through structlog (JSON to stderr) — the only
output surface the `no_write_direct` ban permits for an enforcement script;
structlog is imported from the installed `livespec_dev_tooling` package's
vendored copy (it is not vendored in this repo's own tree). The exit code
(0 pass / 1 fail) is the load-bearing signal the `just` target propagates.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
_SCRIPTS_VENDOR = _SCRIPTS / "_vendor"
for _path in (_SCRIPTS, _SCRIPTS_VENDOR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script
# (per the `no_write_direct` ban on direct `sys.stderr.write`). It is not
# vendored in this repo's own tree, so it is imported from the installed
# `livespec_dev_tooling` package's vendored copy, whose path is added to
# `sys.path` here. The file-level pyright pragma above silences the
# untyped-structlog diagnostics this import would otherwise raise.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
if str(_DT_VENDOR) not in sys.path:
    sys.path.insert(0, str(_DT_VENDOR))

import structlog  # noqa: E402
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config  # noqa: E402
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import (  # noqa: E402
    STATUS_CONFORMANCE_CHECK,
    LedgerFinding,
    run_ledger_checks,
)
from livespec_orchestrator_beads_fabro.store import (  # noqa: E402
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import WorkItem  # noqa: E402

__all__: list[str] = ["main", "status_conformance_findings"]


def status_conformance_findings(*, items: list[WorkItem]) -> list[LedgerFinding]:
    """The `status-conformance` subset of the Ledger checks over `items`.

    Runs the shared Ledger-check registry (so the invariant has ONE source
    of truth) and keeps only its status-conformance findings.
    """
    return [
        finding
        for finding in run_ledger_checks(items=items)
        if finding.check == STATUS_CONFORMANCE_CHECK
    ]


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("status_conformance")
    cwd = Path.cwd()
    config = resolve_store_config(cwd=cwd, work_items_arg=None)
    index = materialize_work_items(records=read_work_items(path=config))
    findings = status_conformance_findings(items=list(index.values()))
    for finding in findings:
        log.error(
            "work-item status is out of lifecycle",
            work_item=finding.item_id,
            check=finding.check,
            detail=finding.message,
        )
    return 1 if findings else 0


# The shebang-less module is invoked via `just check-status-conformance`
# (`uv run python dev-tooling/checks/status_conformance.py`); the guard keeps
# the exit code propagating to the shell.
if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
