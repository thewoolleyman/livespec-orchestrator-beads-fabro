# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""work_item_state_invariants — beads-private work-item-state doctor check.

Enforces the doctor-checkable work-item-state invariants the
SPECIFICATION/contracts.md work-item-beads-issue-mapping invariants block
restates for the consumer, scoped to the L1a slice S6 (`bd-ib-6zndit`):

- **non-sentinel `rank` (live heads).** Every live (non-`done`) head
  issue SHOULD carry a real, non-sentinel `rank`. A legacy beads issue
  whose `metadata` lacks `rank` reads back through the shared
  `BOTTOM_SENTINEL`; the listing tolerates it (it sorts strictly last),
  so this surfaces as a fail-SOFT WARNING that NAMES the offender rather
  than failing the build — the L2 backfill / `rebalance-ranks` assigns a
  real key. Until the lockstep L2 status+rank migration runs, the live
  tenant legitimately holds rank-less rows, so a hard failure here would
  be wrong.
- **rank-key-length WARNING.** A `rank` key longer than the warning
  threshold is a fragmentation signal (many single-inserts at one
  position without a rebalance); surfaced as a WARNING suggesting
  `rebalance-ranks`, never a failure.
- **`active ⟹ assignee`.** An `active` work-item MUST carry a non-empty
  `assignee` (the reused claimed-by field the Dispatcher sets on `admit`).
  A violation is a hard ERROR (exit non-zero).
- **stored `blocked ⟹ blocked_reason ∈ {needs-human, infra-external}`.**
  A stored-`blocked` work-item MUST carry one of the two STORED blocked
  reasons (`dependency` is DERIVED and never stored). A violation is a
  hard ERROR (exit non-zero).

The check walks every materialized work-item from the configured store
descriptor through the same beads client the runtime uses. In hermetic
mode (`LIVESPEC_BEADS_FAKE` truthy, the default `just check` tier) the
tenant is empty, so the walk yields nothing and the check passes
trivially. The check performs NO git or network I/O.

Per-finding diagnostics flow through structlog (JSON to stderr) — the only
output surface the `no_write_direct` ban permits for an enforcement
script; structlog is imported from the installed `livespec_dev_tooling`
package's vendored copy (it is not vendored in this repo's own tree). The
exit code (0 pass / 1 fail) is the load-bearing signal the `just` target
propagates: a WARNING-only run exits 0 (advisory), an ERROR-bearing run
exits 1.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
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
from livespec_orchestrator_beads_fabro.store import (  # noqa: E402
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import WorkItem  # noqa: E402
from livespec_runtime.work_items.rank import BOTTOM_SENTINEL  # noqa: E402

__all__: list[str] = ["Finding", "item_findings", "main"]

_STORED_BLOCKED_REASONS = frozenset({"needs-human", "infra-external"})

# A `rank` key longer than this is a fragmentation WARNING (a rebalance
# hint), never a failure. Fresh `key_between` keys are 1-2 chars; only a
# run of single-inserts at one position without a rebalance grows them.
_RANK_KEY_LENGTH_WARN_THRESHOLD = 10

_SEVERITY_ERROR = "error"
_SEVERITY_WARNING = "warning"


@dataclass(frozen=True, kw_only=True)
class Finding:
    """One work-item-state invariant violation, NAMED by work-item id.

    `severity` is `error` (a hard invariant breach — flips the exit code
    to 1) or `warning` (advisory / fail-soft — NAMED but exit 0).
    """

    work_item_id: str
    invariant: str
    severity: str
    detail: str


def _rank_findings(*, item: WorkItem) -> list[Finding]:
    """Rank invariants for one LIVE (non-`done`) head; `done` items exempt."""
    if item.status == "done":
        return []
    if item.rank == BOTTOM_SENTINEL:
        return [
            Finding(
                work_item_id=item.id,
                invariant="non-sentinel-rank",
                severity=_SEVERITY_WARNING,
                detail=(
                    "live head carries the bottom-sentinel rank (no real rank key); "
                    "an L2 backfill or rebalance-ranks must assign one"
                ),
            )
        ]
    if len(item.rank) > _RANK_KEY_LENGTH_WARN_THRESHOLD:
        return [
            Finding(
                work_item_id=item.id,
                invariant="rank-key-length",
                severity=_SEVERITY_WARNING,
                detail=(
                    f"rank key length {len(item.rank)} exceeds the warning threshold "
                    f"{_RANK_KEY_LENGTH_WARN_THRESHOLD}; consider rebalance-ranks"
                ),
            )
        ]
    return []


def _assignee_findings(*, item: WorkItem) -> list[Finding]:
    """`active ⟹ assignee` set (a hard invariant)."""
    if item.status == "active" and (item.assignee is None or item.assignee == ""):
        return [
            Finding(
                work_item_id=item.id,
                invariant="active-requires-assignee",
                severity=_SEVERITY_ERROR,
                detail="active work-item has no assignee (active ⟹ assignee)",
            )
        ]
    return []


def _blocked_reason_findings(*, item: WorkItem) -> list[Finding]:
    """stored `blocked ⟹ blocked_reason ∈ {needs-human, infra-external}`."""
    if item.status == "blocked" and item.blocked_reason not in _STORED_BLOCKED_REASONS:
        return [
            Finding(
                work_item_id=item.id,
                invariant="blocked-requires-reason",
                severity=_SEVERITY_ERROR,
                detail=(
                    f"stored blocked work-item has blocked_reason {item.blocked_reason!r} "
                    "∉ {needs-human, infra-external}"
                ),
            )
        ]
    return []


def item_findings(*, item: WorkItem) -> list[Finding]:
    """All work-item-state invariant findings for one work-item."""
    return [
        *_rank_findings(item=item),
        *_assignee_findings(item=item),
        *_blocked_reason_findings(item=item),
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
    log = structlog.get_logger("work_item_state_invariants")
    cwd = Path.cwd()
    config = resolve_store_config(cwd=cwd, work_items_arg=None)
    index = materialize_work_items(records=read_work_items(path=config))
    findings: list[Finding] = []
    for item in index.values():
        findings.extend(item_findings(item=item))
    has_error = False
    for finding in findings:
        if finding.severity == _SEVERITY_ERROR:
            has_error = True
            log.error(
                "work-item-state invariant violation",
                work_item=finding.work_item_id,
                invariant=finding.invariant,
                detail=finding.detail,
            )
        else:
            log.warning(
                "work-item-state invariant warning",
                work_item=finding.work_item_id,
                invariant=finding.invariant,
                detail=finding.detail,
            )
    return 1 if has_error else 0


# The shebang-less module is invoked via `just check-work-item-state-invariants`
# (`uv run python dev-tooling/checks/work_item_state_invariants.py`); the guard
# keeps the exit code propagating to the shell.
if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
