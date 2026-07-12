"""Pre-push ledger-conformance gate: fail-soft, case-aware heal guidance.

The gate is the always-run pre-push companion to `ledger-normalize`: it
detects out-of-lifecycle work-item statuses in THIS repo's beads tenant and
FAILS the push (exit 1) with a case-aware heal instruction, so an agent or a
human runs the fix and retries. It REUSES the dispatch-path status normalizer
(`plan_native_status_remaps` / `project_native_status_remaps`) and the shared
Ledger-check registry (`run_ledger_checks`) — it never re-implements drift
detection.

CRITICAL SAFETY — fail-soft. The gate runs on EVERY push (it is deliberately
NOT part of the tree-cached aggregate, because tenant state is not
tree-derived). A false-fail would brick every push to the repo. Therefore the
gate exits NON-zero ONLY when it has POSITIVELY confirmed non-lifecycle
work-items exist; ANY problem that is not confirmed drift (creds unavailable,
1Password locked, Dolt server unreachable, unparseable output, missing
tenant config) resolves to the could-not-check path, which SKIPS.

Exit-code contract (consumed by the `check-ledger-conformance-live` recipe):

- ``0`` — the tenant read succeeded and the ledger is conformant (or there is
  nothing to normalize). Prints the ``CLEAN`` marker.
- ``1`` — the tenant read succeeded and CONFIRMED drift exists (auto-mappable
  remaps present, or residual non-lifecycle statuses present). Prints the
  ``DRIFT`` marker followed by the case-aware heal guidance.
- ``2`` — could-not-check: the tenant read raised an EXPECTED beads/store
  error. Prints the ``SKIP`` marker + the reason to stderr. The recipe maps
  this (and every non-1 code) to a fail-soft skip.

The stdout ``LIVESPEC_LEDGER_GATE: DRIFT`` marker is the machine-checkable
belt to the exit-code suspenders: the recipe blocks a push ONLY when exit 1
AND the DRIFT marker are BOTH present, so even an unhandled crash (exit 1, no
marker) fails soft instead of bricking the push.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_credential_wrapper
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import (
    LedgerFinding,
    run_ledger_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    load_items,
    plan_native_status_remaps,
    project_native_status_remaps,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    MalformedRecordLineError,
    SchemaViolationError,
    StoreFileMissingError,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "LEDGER_GATE_CLEAN_MARKER",
    "LEDGER_GATE_DRIFT_MARKER",
    "LEDGER_GATE_SKIP_MARKER",
    "LedgerGateDecision",
    "decide_ledger_gate",
    "run_ledger_gate",
]

# The pre-push heal command targets THIS repo's dispatcher wrapper. Its path is
# fixed under the plugin root; the credential-wrapper prefix is read from
# `.livespec.jsonc` so the printed command is the exact one the operator runs.
_DISPATCHER_RELPATH = ".claude-plugin/scripts/bin/dispatcher.py"

# Machine-checkable markers. The recipe greps stdout for the DRIFT marker; the
# CLEAN / SKIP markers are informational for a human reading the push output.
LEDGER_GATE_DRIFT_MARKER = "LIVESPEC_LEDGER_GATE: DRIFT"
LEDGER_GATE_CLEAN_MARKER = "LIVESPEC_LEDGER_GATE: CLEAN"
LEDGER_GATE_SKIP_MARKER = "LIVESPEC_LEDGER_GATE: SKIP"

_EXIT_CLEAN = 0
_EXIT_DRIFT = 1
_EXIT_COULD_NOT_CHECK = 2

# The EXPECTED beads/store errors a tenant read can raise. Each is a
# could-not-check condition, NEVER confirmed drift: catching them keeps the
# gate fail-soft. A bug (any OTHER exception) propagates and exits 1 WITHOUT
# the DRIFT marker, so the recipe still fails soft on it.
_GATE_COULD_NOT_CHECK_ERRORS: tuple[type[Exception], ...] = (
    BeadsConnectionError,
    BeadsCommandError,
    BeadsCredentialMissingError,
    BeadsTenantMissingError,
    BeadsMappingError,
    ConnectionPrefixMissingError,
    StoreFileMissingError,
    MalformedRecordLineError,
    SchemaViolationError,
)

# The seven livespec lifecycle states an operator picks from when a residual
# status has no auto-map. Kept as a literal hint string (not derived) so the
# printed remedy stays a stable, readable operator instruction.
_LIFECYCLE_HINT = "backlog|ready|active|acceptance|blocked|pending-approval|done"

# Case-aware message fragments. Single-line literals (no implicit or explicit
# concatenation) so ruff ISC and pyright's implicit-concat ban both pass.
_DRIFT_HEADER = "Pre-push blocked: work-item statuses are outside the livespec lifecycle.\n"
_AUTO_MAPPABLE_HEADER = "\nAuto-mappable beads-native statuses (this repo can self-heal these):\n"
_HEAL_LEAD = "\nRun the heal command, then re-push:\n"
_RESIDUAL_HEADER = "\nResidual non-lifecycle statuses need a human lane decision (no auto-map):\n"
_RESIDUAL_REMEDY = (
    "\nSet each to a lifecycle status, then re-push (normalize will NOT fix these):\n"
)


@dataclass(frozen=True, kw_only=True)
class LedgerGateDecision:
    """The gate's verdict: a human-facing message plus the process exit code."""

    message: str
    exit_code: int


@dataclass(frozen=True, kw_only=True)
class _LoadedItems:
    """A successful tenant read."""

    items: list[WorkItem]


@dataclass(frozen=True, kw_only=True)
class _LoadUnavailable:
    """A could-not-check tenant read: `reason` is the expected-error detail."""

    reason: str


def decide_ledger_gate(
    *,
    remaps: list[dict[str, str]],
    residual: list[LedgerFinding],
    heal_command: str,
) -> LedgerGateDecision:
    """Decide the gate verdict from the remap plan + residual findings (PURE).

    `remaps` are the auto-mappable beads-native rows (`open` → `backlog`,
    `in_progress` → `active`); `residual` are the post-projection
    non-conformant findings a remap cannot map. Confirmed drift is either a
    non-empty remap plan OR a non-skipped residual finding; either yields exit
    1 with a case-aware message. A clean ledger yields exit 0.
    """
    actionable = [finding for finding in residual if finding.severity != "skipped"]
    if not remaps and not actionable:
        return LedgerGateDecision(
            message=f"{LEDGER_GATE_CLEAN_MARKER} ledger conformant\n",
            exit_code=_EXIT_CLEAN,
        )
    return LedgerGateDecision(
        message=_drift_message(remaps=remaps, residual=actionable, heal_command=heal_command),
        exit_code=_EXIT_DRIFT,
    )


def _drift_message(
    *,
    remaps: list[dict[str, str]],
    residual: list[LedgerFinding],
    heal_command: str,
) -> str:
    """Assemble the case-aware drift message (PURE).

    Distinguishes the two lanes so an agent never loops: auto-mappable rows
    name the exact heal+retry command; residual rows say a human lane decision
    is required and explicitly warn that re-running normalize will NOT fix them.
    """
    parts: list[str] = [f"{LEDGER_GATE_DRIFT_MARKER}\n", _DRIFT_HEADER]
    if remaps:
        parts.append(_AUTO_MAPPABLE_HEADER)
        parts.extend(
            f"  {remap['item_id']}: {remap['from']} -> {remap['to']}\n" for remap in remaps
        )
        parts.append(_HEAL_LEAD)
        parts.append(f"  {heal_command}\n")
    if residual:
        parts.append(_RESIDUAL_HEADER)
        parts.extend(f"  {finding.item_id}: {finding.message}\n" for finding in residual)
        parts.append(_RESIDUAL_REMEDY)
        parts.append(f"  bd update <id> --status <{_LIFECYCLE_HINT}>\n")
    return "".join(parts)


def _heal_command(*, project_root: Path) -> str:
    """The exact `ledger-normalize` heal command, credential-wrapper included.

    Reads THIS repo's `credential_wrapper` from `.livespec.jsonc` so the
    printed command is copy-pasteable; when no wrapper is configured the bare
    `python3 …` form is printed (the dispatcher self-heals through the wrapper
    on its own when a secret is absent).
    """
    wrapper = resolve_credential_wrapper(cwd=project_root)
    prefix = f"{' '.join(wrapper)} " if wrapper else ""
    return f"{prefix}python3 {_DISPATCHER_RELPATH} ledger-normalize --project-root {project_root}"


def _load_items_fail_soft(*, project_root: Path) -> _LoadedItems | _LoadUnavailable:
    """Load the tenant rows, mapping every EXPECTED read error to could-not-check.

    The try/except is the fail-soft boundary: an expected beads/store error
    (creds absent, server unreachable, tenant/config missing, unparseable
    output) becomes `_LoadUnavailable` rather than a raised exception, so the
    gate skips instead of bricking the push.
    """
    try:
        items = load_items(repo=project_root)
    except _GATE_COULD_NOT_CHECK_ERRORS as exc:
        return _LoadUnavailable(reason=str(exc))
    return _LoadedItems(items=items)


def run_ledger_gate(*, project_root: Path) -> int:
    """Run the pre-push gate over `project_root`'s tenant; return the exit code.

    Implies dry-run: the tenant is read and the remap plan is projected in
    memory, never written. Emits the CLEAN / DRIFT / SKIP marker and returns
    0 / 1 / 2 per the module's exit-code contract.
    """
    loaded = _load_items_fail_soft(project_root=project_root)
    if isinstance(loaded, _LoadUnavailable):
        _ = write_stderr(text=f"{LEDGER_GATE_SKIP_MARKER} {loaded.reason}\n")
        return _EXIT_COULD_NOT_CHECK
    remaps = plan_native_status_remaps(items=loaded.items)
    projected = project_native_status_remaps(items=loaded.items, remaps=remaps)
    residual = run_ledger_checks(items=projected)
    decision = decide_ledger_gate(
        remaps=remaps,
        residual=residual,
        heal_command=_heal_command(project_root=project_root),
    )
    _ = write_stdout(text=decision.message)
    return decision.exit_code
