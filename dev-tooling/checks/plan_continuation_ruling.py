# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""plan_continuation_ruling — a malformed continuation ruling, made visible.

Realizes the `plan_continuation_ruling` verdict of this repository's own
plan-record conformance contract (`SPECIFICATION/contracts.md`, v124): a
`plan-continuation: authorized` ruling lacking any of its `until:`, `by:`,
`directive:` or `recorded-attended: true` lines, or a `plan-continuation:
revoked` ruling lacking its `by:` line, is reported at error level.

WHY THIS SHIPS HERE, BESIDE `plan_close_proof.py`. The same reason as that
sibling: the contract is this repository's, its realization clause is
permissive about the home, and the DECISION is already a primitive in the
orchestrator package (`commands/_plan_continuation_ruling.py`). This script is
only the wiring — the arming gate, the scope narrowing to open epics whose
`plan_slug` names a LIVE plan directory, the timeline read and the structured
report — under the SAME lever and credential the plan-record family self-skips
on, so arming the family arms this verdict too.

WHY ONLY LIVE DIRECTORIES. The clause speaks of rulings that would govern a
resume, and only an open plan with a live `plan/<slug>/` directory can be
resumed. An archived plan's malformed ruling is history that can no longer be
acted under, and a ledger comment cannot be edited, so reporting it would be a
finding nobody can discharge.

WHY THE LEDGER IS A STORE CONFIG AND NOT A NARROW SEAM. The timeline parse is the
package's own `read_timeline`, which is what the resume reads too; a check that
re-parsed comment bodies itself could disagree with the resume about what a
ruling is. `read_timeline` takes a store configuration, so that is the seam, and
the tests hand in the in-memory fake the plan-lane tests already use.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through the vendored `structlog` (JSON to stderr).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
for _path in (_SCRIPTS, _SCRIPTS / "_vendor"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script; it is
# imported from the installed shared dev-tooling package's vendored copy.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
# APPEND, never insert at the front: that `_vendor` also carries a PARTIAL
# `livespec_runtime`, and putting it ahead of this repo's own `_vendor` shadows
# the full copy every plugin module imports.
if str(_DT_VENDOR) not in sys.path:
    sys.path.append(str(_DT_VENDOR))

import structlog  # noqa: E402
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client  # noqa: E402
from livespec_orchestrator_beads_fabro.commands._config import (  # noqa: E402
    resolve_store_config,
)
from livespec_orchestrator_beads_fabro.commands._plan_continuation_ruling import (  # noqa: E402
    OpenPlanEpic,
    PlanContinuationRulingFinding,
    plan_continuation_ruling_findings,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (  # noqa: E402
    read_timeline,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig  # noqa: E402

__all__: list[str] = ["live_plan_slugs", "main"]

_RUN_LEVER = "LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE"
_CRED_ENV = "BEADS_DOLT_PASSWORD"
_SKIP_MESSAGE = f"skipped — set {_RUN_LEVER} and provide {_CRED_ENV} to arm"
_PLAN_DIR = "plan"
_ARCHIVE_DIR = "archive"
_CLOSED_STATUS = "closed"


def live_plan_slugs(*, repo_root: Path) -> frozenset[str]:
    """Every slug naming a LIVE plan directory under `repo_root`, archive excluded."""
    plan = repo_root / _PLAN_DIR
    if not plan.is_dir():
        return frozenset()
    return frozenset(
        one.name for one in plan.iterdir() if one.is_dir() and one.name != _ARCHIVE_DIR
    )


def main(*, config: StoreConfig | None = None) -> int:
    """Run the armed check over the tenant and this repository's live plans."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("plan_continuation_ruling")
    if not (os.environ.get(_RUN_LEVER) and os.environ.get(_CRED_ENV)):
        log.info(_SKIP_MESSAGE, run_lever=_RUN_LEVER, credential=_CRED_ENV)
        return 0
    cwd = Path.cwd()
    store = config or resolve_store_config(cwd=cwd, work_items_arg=None)
    findings = plan_continuation_ruling_findings(
        epics=_open_live_plan_epics(config=store, repo_root=cwd)
    )
    for finding in findings:
        _report(log=log, finding=finding)
    return 1 if findings else 0


def _open_live_plan_epics(*, config: StoreConfig, repo_root: Path) -> list[OpenPlanEpic]:
    """Each open epic whose `plan_slug` names a live plan directory, with its timeline.

    The slug and status narrowing happens BEFORE any timeline read, so a tenant's
    non-plan and closed epics cost no ledger round trip.
    """
    slugs = live_plan_slugs(repo_root=repo_root)
    epics: list[OpenPlanEpic] = []
    for record in make_beads_client(config=config).list_issues():
        slug = _plan_slug(record=record)
        epic_id = record.get("id")
        if slug is None or slug not in slugs or not isinstance(epic_id, str):
            continue
        if record.get("status") == _CLOSED_STATUS:
            continue
        epics.append(
            OpenPlanEpic(
                epic_id=epic_id,
                plan_slug=slug,
                entries=read_timeline(config=config, epic_id=epic_id),
            )
        )
    return epics


def _plan_slug(*, record: dict[str, Any]) -> str | None:
    """One record's `plan_slug`, tolerating the `omitempty`-sparse shapes."""
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        return None
    slug = metadata.get("plan_slug")
    return slug if isinstance(slug, str) and slug.strip() else None


def _report(*, log: Any, finding: PlanContinuationRulingFinding) -> None:
    log.error(
        finding.event,
        check_id=finding.check_id,
        subject=finding.subject,
        verdict=finding.verdict,
        created_at=finding.created_at,
        missing=list(finding.missing),
        remediation=finding.remediation,
    )


# The shebang-less module is invoked via `just check-plan-continuation-ruling`
# (`uv run python dev-tooling/checks/plan_continuation_ruling.py`); the guard
# keeps the exit code propagating to the shell.
if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
