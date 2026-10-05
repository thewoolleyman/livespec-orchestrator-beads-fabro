# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""plan_close_proof — the archive proof leg, made visible after the fact.

Realizes the `plan_close_proof` verdict of this repository's own plan-record
conformance contract (`SPECIFICATION/contracts.md`, v115): an epic whose
`plan_slug` names a live or archived plan directory, closed later than the proof
leg's ratification date, is reported when its timeline carries no `verified` plan
Proof of Done record.

WHY THIS VERDICT SHIPS HERE AND NOT BESIDE THE ELEVEN OTHERS, recorded so the
split is not read as an oversight. The eleven shipped plan-record verdicts live
in the fleet's shared checks package, which is a DIFFERENT REPOSITORY. The
contract's own realization clause is permissive about the home — the family "MAY
live in the fleet's shared checks package" — and this repository is the one that
owns the contract. The twelfth verdict is therefore wired here, under the SAME
arming lever and the same credential the shared family self-skips on, so arming
the family arms all twelve. The DECISION is a primitive in the orchestrator
package (`commands/_plan_close_proof.py`), which is what makes a later move into
the shared package a re-wiring of this surface rather than a re-derivation of the
rule.

WHY THE LEDGER READ IS A SEAM. Comments have no on-disk export shape, so the
alternative to injecting the read is spawning `bd` from a test, which this tier
does not do — the same reason the shared family ships a `comment_reader` seam. The
default is the ordinary store client, so the production path is unstubbed.

WHY THE SCOPE FILTER RUNS AHEAD OF THE TIMELINE READ. An epic whose slug names no
directory is out of scope by the clause's own wording, and a tenant holds many of
them — every epic filed through `capture-work-item` rather than the plan
front-end. Reading each one's timeline first would spend a ledger round trip per
non-plan epic to discard the answer.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through the vendored `structlog` (JSON to stderr).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Protocol

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
from livespec_orchestrator_beads_fabro.commands._plan_close_proof import (  # noqa: E402
    ClosedPlanEpic,
    PlanCloseProofFinding,
    plan_close_proof_findings,
)

__all__: list[str] = ["LedgerReader", "main", "plan_record_slugs"]

_RUN_LEVER = "LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE"
_CRED_ENV = "BEADS_DOLT_PASSWORD"
_SKIP_MESSAGE = f"skipped — set {_RUN_LEVER} and provide {_CRED_ENV} to arm"
_PLAN_DIR = "plan"
_ARCHIVE_DIR = "archive"
_CLOSED_STATUS = "closed"


class LedgerReader(Protocol):
    """The narrow read-only ledger surface this check needs.

    Two verbs, because that is all the verdict reads. A seam shaped to the whole
    `BeadsClient` would make the test double carry write verbs no check may call.
    """

    def list_issues(self) -> list[dict[str, Any]]:
        """Every record in the tenant."""
        ...

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        """One record's timeline, oldest first."""
        ...


def plan_record_slugs(*, repo_root: Path) -> frozenset[str]:
    """Every slug naming a live or archived plan directory under `repo_root`.

    Both venues, because the clause names both: an archived record is the common
    case after a plan closes, and a LIVE directory anchoring a closed epic is the
    lifecycle violation the sibling parity check reports — which does not make it
    out of this check's scope.
    """
    plan = repo_root / _PLAN_DIR
    archive = plan / _ARCHIVE_DIR
    live = (one.name for one in _directories(path=plan) if one.name != _ARCHIVE_DIR)
    return frozenset(live) | frozenset(one.name for one in _directories(path=archive))


def main(*, client: LedgerReader | None = None) -> int:
    """Run the armed check over the tenant and this repository's plan records."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("plan_close_proof")
    if not (os.environ.get(_RUN_LEVER) and os.environ.get(_CRED_ENV)):
        log.info(_SKIP_MESSAGE, run_lever=_RUN_LEVER, credential=_CRED_ENV)
        return 0
    cwd = Path.cwd()
    findings = plan_close_proof_findings(
        epics=_closed_plan_epics(client=client or _store_client(cwd=cwd), repo_root=cwd)
    )
    for finding in findings:
        _report(log=log, finding=finding)
    return 1 if findings else 0


def _store_client(*, cwd: Path) -> LedgerReader:
    """The ordinary store client, so the production read is unstubbed."""
    return make_beads_client(config=resolve_store_config(cwd=cwd, work_items_arg=None))


def _closed_plan_epics(*, client: LedgerReader, repo_root: Path) -> list[ClosedPlanEpic]:
    """Each closed epic whose `plan_slug` names a plan directory, with its timeline.

    The slug and status narrowing happens BEFORE any timeline read, so a tenant's
    non-plan epics cost no ledger round trip.
    """
    slugs = plan_record_slugs(repo_root=repo_root)
    epics: list[ClosedPlanEpic] = []
    for record in client.list_issues():
        slug = _plan_slug(record=record)
        epic_id = record.get("id")
        if slug is None or slug not in slugs or not isinstance(epic_id, str):
            continue
        if record.get("status") != _CLOSED_STATUS:
            continue
        epics.append(
            ClosedPlanEpic(
                epic_id=epic_id,
                plan_slug=slug,
                closed_at=_closed_at(record=record),
                comments=tuple(client.list_comments(issue_id=epic_id)),
            )
        )
    return epics


def _plan_slug(*, record: dict[str, Any]) -> str | None:
    """One record's `plan_slug`, tolerating the `omitempty`-sparse shapes.

    A record holding no metadata omits the key entirely rather than carrying an
    empty object, and that sparse shape is what a subscripting reader raises on.
    """
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        return None
    slug = metadata.get("plan_slug")
    return slug if isinstance(slug, str) and slug.strip() else None


def _closed_at(*, record: dict[str, Any]) -> str:
    """The native close instant, or the empty string when the record carries none.

    The empty string is IN scope rather than out of it: the decision primitive
    treats an unreadable instant as unprovable-to-predate the clause, because a
    check that passed when it could not read its own input would make an absent
    `closed_at` the cheapest way past it.
    """
    value = record.get("closed_at")
    return value if isinstance(value, str) else ""


def _directories(*, path: Path) -> list[Path]:
    """Immediate subdirectories of `path`, or none when it does not exist."""
    if not path.is_dir():
        return []
    return [one for one in sorted(path.iterdir()) if one.is_dir()]


def _report(*, log: Any, finding: PlanCloseProofFinding) -> None:
    log.error(
        finding.event,
        check_id=finding.check_id,
        subject=finding.subject,
        verdict=finding.verdict,
        remediation=finding.remediation,
    )


# The shebang-less module is invoked via `just check-plan-close-proof`
# (`uv run python dev-tooling/checks/plan_close_proof.py`); the guard keeps the
# exit code propagating to the shell.
if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
