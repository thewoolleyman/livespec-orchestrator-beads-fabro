"""Gap-tied closure verification: check-path-anchored, never gap_id-anchored.

Replaces the unsatisfiable `implement` Step 5a re-detection gate (F3):
detection is spec-only (`detect-impl-gaps` reads spec text, never
implementation state), so a `gap_id` disappears only when spec TEXT
changes — the old gate rewarded editing the spec instead of implementing.

Closure of a `gap-tied` work-item is instead anchored to a check PATH
recorded on the work-item's own beads metadata (never `gap_id`: F4 —
`gap_id` hashes a hard-wrapped source line, so reflowing a paragraph with
zero semantic change re-keys it and orphans the anchor exactly when the
clause is edited). The recorded check is a generic executable —
`main() -> int` convention, invoked once normally (must exit 0 to pass)
and once with `--negative-control` (must exit non-zero, proving the check
can fail and is therefore discriminating, not vacuously true). If the
check file's content differs from the baseline blob hash recorded when it
was cited, that is machine-detectable evidence the check was modified —
the common and most dangerous case being "loosen the check to make it
pass" — and closure is refused until a targeted drift propose-change is
recorded for this item.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "GAP_CHECK_BASELINE_BLOB_KEY",
    "GAP_CHECK_PATH_KEY",
    "GAP_DRIFT_PROPOSE_CHANGE_KEY",
    "GapClosureDecision",
    "GapClosureVerdict",
    "decide_gap_closure",
    "evaluate_gap_closure",
    "record_drift_propose_change",
    "record_gap_check",
]

GAP_CHECK_PATH_KEY = "gap_check_path"
GAP_CHECK_BASELINE_BLOB_KEY = "gap_check_baseline_blob"
GAP_DRIFT_PROPOSE_CHANGE_KEY = "gap_drift_propose_change"

_NEGATIVE_CONTROL_FLAG = "--negative-control"

GapClosureVerdict = Literal[
    "close",
    "refuse-no-check-recorded",
    "refuse-check-failed",
    "refuse-drift-required",
]


@dataclass(frozen=True, kw_only=True)
class GapClosureDecision:
    """The closure verdict plus a human-readable detail explaining it."""

    verdict: GapClosureVerdict
    detail: str

    @property
    def may_close(self) -> bool:
        return self.verdict == "close"


def decide_gap_closure(
    *,
    check_recorded: bool,
    check_passed: bool,
    negative_control_failed: bool,
    check_modified: bool,
    drift_propose_change_recorded: bool,
) -> GapClosureDecision:
    """Pure decision function — no I/O, no `gap_id` input at all.

    Anchoring to `gap_id` is unsound (F4); this function cannot anchor to
    it because it is never passed one.
    """
    if not check_recorded:
        return GapClosureDecision(
            verdict="refuse-no-check-recorded",
            detail="no gap_check_path recorded on this work-item; closure cannot be verified",
        )
    if check_modified and not drift_propose_change_recorded:
        # Checked BEFORE the pass/fail legs: a modified-but-unreviewed
        # check's current pass/fail result cannot be trusted at all (the
        # dangerous case is loosening the check until it happens to pass).
        return GapClosureDecision(
            verdict="refuse-drift-required",
            detail=(
                "the recorded check file was modified on this item's branch; a targeted "
                "capture-spec-drift --for-work-item run and a resulting propose-change "
                "are required before closure"
            ),
        )
    if not check_passed:
        return GapClosureDecision(
            verdict="refuse-check-failed",
            detail="the recorded check did not pass",
        )
    if not negative_control_failed:
        return GapClosureDecision(
            verdict="refuse-check-failed",
            detail=(
                "the recorded check's negative control did not fail; "
                "the check is not discriminating"
            ),
        )
    detail = "check passed, negative control failed"
    if check_modified:
        detail += ", drift propose-change recorded"
    return GapClosureDecision(verdict="close", detail=detail)


def evaluate_gap_closure(
    *,
    config: StoreConfig,
    project_root: Path,
    item_id: str,
) -> GapClosureDecision:
    """Gather the live inputs (check run, negative control, blob diff) and decide."""
    client = make_beads_client(config=config)
    record = client.show_issue(issue_id=item_id)
    metadata = dict(record.get("metadata") or {})
    check_path = metadata.get(GAP_CHECK_PATH_KEY)
    if not isinstance(check_path, str) or not check_path:
        return decide_gap_closure(
            check_recorded=False,
            check_passed=False,
            negative_control_failed=False,
            check_modified=False,
            drift_propose_change_recorded=False,
        )
    abs_path = project_root / check_path
    check_returncode = _run_check(abs_path=abs_path, negative_control=False)
    negative_control_returncode = _run_check(abs_path=abs_path, negative_control=True)
    check_passed = check_returncode == 0
    negative_control_failed = negative_control_returncode not in {None, 0, 126, 127}
    baseline_blob = metadata.get(GAP_CHECK_BASELINE_BLOB_KEY)
    current_blob = _git_blob_hash(repo_root=project_root, rel_path=check_path)
    check_modified = (
        isinstance(baseline_blob, str)
        and current_blob is not None
        and current_blob != baseline_blob
    )
    drift_recorded = bool(metadata.get(GAP_DRIFT_PROPOSE_CHANGE_KEY))
    return decide_gap_closure(
        check_recorded=True,
        check_passed=check_passed,
        negative_control_failed=negative_control_failed,
        check_modified=check_modified,
        drift_propose_change_recorded=drift_recorded,
    )


def record_gap_check(
    *,
    config: StoreConfig,
    project_root: Path,
    item_id: str,
    check_path: str,
) -> None:
    """Record the cited check's path + its current blob hash as the baseline.

    Called once when the check is first cited on a gap-tied work-item
    (never re-called on a whim — re-baselining after the fact would defeat
    the drift-detection this anchors).
    """
    client = make_beads_client(config=config)
    baseline_blob = _git_blob_hash(repo_root=project_root, rel_path=check_path)
    record = client.show_issue(issue_id=item_id)
    metadata = dict(record.get("metadata") or {})
    metadata[GAP_CHECK_PATH_KEY] = check_path
    if baseline_blob is not None:
        metadata[GAP_CHECK_BASELINE_BLOB_KEY] = baseline_blob
    client.update_issue(issue_id=item_id, metadata=metadata)


def record_drift_propose_change(
    *,
    config: StoreConfig,
    item_id: str,
    propose_change_topic: str,
) -> None:
    """Record that a targeted drift propose-change now covers this item's check modification."""
    client = make_beads_client(config=config)
    record = client.show_issue(issue_id=item_id)
    metadata = dict(record.get("metadata") or {})
    metadata[GAP_DRIFT_PROPOSE_CHANGE_KEY] = propose_change_topic
    client.update_issue(issue_id=item_id, metadata=metadata)


def _run_check(*, abs_path: Path, negative_control: bool) -> int | None:
    """Run an executable through its shebang, retaining legacy Python checks."""
    try:
        argv = (
            [str(abs_path)] if abs_path.stat().st_mode & 0o111 else [sys.executable, str(abs_path)]
        )
        if negative_control:
            argv.append(_NEGATIVE_CONTROL_FLAG)
        completed = subprocess.run(argv, capture_output=True, check=False)  # noqa: S603
    except OSError:
        return None
    return completed.returncode


def _git_blob_hash(*, repo_root: Path, rel_path: str) -> str | None:
    completed = subprocess.run(  # noqa: S603
        ["git", "hash-object", rel_path],  # noqa: S607
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()
