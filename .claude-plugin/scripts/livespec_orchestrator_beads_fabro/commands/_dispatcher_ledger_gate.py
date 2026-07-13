"""Pre-push ledger-conformance gate: fail-soft, auto-heal-loud.

The gate is the always-run pre-push companion to `ledger-normalize`. It
AUTO-HEALS the two definitionally-safe beads-native transient statuses in THIS
repo's beads tenant IN PLACE (`open` -> `backlog`, `in_progress` -> `active`),
PRINTS every remap it applies (loud, never silent), and FAILS the push (exit 1)
ONLY when a RESIDUAL non-lifecycle status remains that no remap can map — those
need a human lane decision. It REUSES the dispatch-path status normalizer
(`plan_native_status_remaps` / `apply_native_status_remaps`) and the shared
Ledger-check registry (`run_ledger_checks`); it never re-implements the remap
table or drift detection.

WHY auto-heal, not detect-and-fail. On a SHARED tenant the two transient
statuses appear CONTINUOUSLY (any active session's raw `bd create` lands `open`;
any raw `bd update --claim` lands `in_progress`). A detect-and-fail gate blocks
every session on any OTHER session's fresh transient item — constant
cross-session friction. Healing the two safe states in place removes that
friction; the loud per-remap print keeps a full audit trail (this is the answer
to the "no silent DB writes" objection: every write is printed).

CRITICAL SAFETY — fail-soft. The gate runs on EVERY push (it is deliberately
NOT part of the tree-cached aggregate, because tenant state is not
tree-derived). A false-fail would brick every push to the repo. Therefore the
gate exits NON-zero ONLY when it has POSITIVELY confirmed a RESIDUAL
non-lifecycle work-item exists; ANY problem that is not confirmed residual drift
(creds unavailable, 1Password locked, Dolt server unreachable, unparseable
output, missing tenant config, OR a heal WRITE that raised an expected beads
error) resolves to the could-not-check path, which SKIPS (exit 2). A heal write
that fails mid-plan leaves the already-applied remaps in place (safe partial
progress that re-converges on the next push) and skips rather than blocks.

Exit-code contract (consumed by the `check-ledger-conformance-live` recipe):

- ``0`` — the tenant read succeeded and, after healing every auto-mappable
  status, the ledger is conformant. Prints the ``CLEAN`` marker (nothing to do)
  or the ``HEALED`` marker followed by each applied remap.
- ``1`` — the tenant read + heal succeeded but a RESIDUAL non-lifecycle status
  remains that no remap can map. Prints the ``DRIFT`` marker, any healed remaps
  (loud), then the residual rows + the human-lane `bd update` remedy.
- ``2`` — could-not-check: the tenant read OR a heal write raised an EXPECTED
  beads/store error. Prints the ``SKIP`` marker + the reason to stderr. The
  recipe maps this (and every non-1 code) to a fail-soft skip.

The stdout ``LIVESPEC_LEDGER_GATE: DRIFT`` marker is the machine-checkable
belt to the exit-code suspenders: the recipe blocks a push ONLY when exit 1
AND the DRIFT marker are BOTH present, so even an unhandled crash (exit 1, no
marker) fails soft instead of bricking the push.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import (
    LedgerFinding,
    run_ledger_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    apply_native_status_remaps,
    load_items,
    plan_native_status_remaps,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
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
    "LEDGER_GATE_HEALED_MARKER",
    "LEDGER_GATE_SKIP_MARKER",
    "LedgerGateDecision",
    "decide_ledger_gate",
    "run_ledger_gate",
]

# Machine-checkable markers. The recipe greps stdout for the DRIFT marker; the
# CLEAN / HEALED / SKIP markers are informational for a human reading the push
# output.
LEDGER_GATE_DRIFT_MARKER = "LIVESPEC_LEDGER_GATE: DRIFT"
LEDGER_GATE_HEALED_MARKER = "LIVESPEC_LEDGER_GATE: HEALED"
LEDGER_GATE_CLEAN_MARKER = "LIVESPEC_LEDGER_GATE: CLEAN"
LEDGER_GATE_SKIP_MARKER = "LIVESPEC_LEDGER_GATE: SKIP"

_EXIT_CLEAN = 0
_EXIT_DRIFT = 1
_EXIT_COULD_NOT_CHECK = 2

# The EXPECTED beads/store errors a tenant read OR a heal write can raise. Each
# is a could-not-check condition, NEVER confirmed drift: catching them keeps the
# gate fail-soft. A bug (any OTHER exception) propagates and exits 1 WITHOUT the
# DRIFT marker, so the recipe still fails soft on it.
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
_HEALED_HEADER = "\nAuto-healed beads-native statuses in place (safe transient remaps):\n"
_DRIFT_HEADER = "Pre-push blocked: work-item statuses are outside the livespec lifecycle.\n"
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
    """A successful tenant read (or post-heal reload)."""

    items: list[WorkItem]


@dataclass(frozen=True, kw_only=True)
class _LoadUnavailable:
    """A could-not-check tenant read/write: `reason` is the expected-error detail."""

    reason: str


def decide_ledger_gate(
    *,
    healed: list[dict[str, str]],
    residual: list[LedgerFinding],
) -> LedgerGateDecision:
    """Decide the gate verdict from the APPLIED remaps + residual findings (PURE).

    `healed` are the auto-mappable beads-native rows already written in place
    (`open` -> `backlog`, `in_progress` -> `active`); `residual` are the
    post-heal non-conformant findings no remap can map. A non-skipped residual
    finding is confirmed drift → exit 1 with the human-lane remedy (any healed
    remaps are still printed loud in that message). With no residual, a
    non-empty `healed` → exit 0 with the HEALED marker, and an empty `healed` →
    exit 0 with the CLEAN marker.
    """
    actionable = [finding for finding in residual if finding.severity != "skipped"]
    if actionable:
        return LedgerGateDecision(
            message=_drift_message(healed=healed, residual=actionable),
            exit_code=_EXIT_DRIFT,
        )
    if healed:
        return LedgerGateDecision(
            message=_healed_message(healed=healed),
            exit_code=_EXIT_CLEAN,
        )
    return LedgerGateDecision(
        message=f"{LEDGER_GATE_CLEAN_MARKER} ledger conformant\n",
        exit_code=_EXIT_CLEAN,
    )


def _healed_lines(*, healed: list[dict[str, str]]) -> list[str]:
    """One indented `id: from -> to` line per applied remap (PURE)."""
    return [f"  {remap['item_id']}: {remap['from']} -> {remap['to']}\n" for remap in healed]


def _healed_message(*, healed: list[dict[str, str]]) -> str:
    """The loud exit-0 message: the HEALED marker + every applied remap (PURE)."""
    parts: list[str] = [f"{LEDGER_GATE_HEALED_MARKER}\n", _HEALED_HEADER]
    parts.extend(_healed_lines(healed=healed))
    return "".join(parts)


def _drift_message(
    *,
    healed: list[dict[str, str]],
    residual: list[LedgerFinding],
) -> str:
    """Assemble the residual-block message (PURE).

    Prints any auto-healed remaps loud first (they are already fixed and
    written), then the residual rows a remap cannot map, and explicitly warns
    that re-running normalize will NOT fix them so an agent never loops.
    """
    parts: list[str] = [f"{LEDGER_GATE_DRIFT_MARKER}\n", _DRIFT_HEADER]
    if healed:
        parts.append(_HEALED_HEADER)
        parts.extend(_healed_lines(healed=healed))
    parts.append(_RESIDUAL_HEADER)
    parts.extend(f"  {finding.item_id}: {finding.message}\n" for finding in residual)
    parts.append(_RESIDUAL_REMEDY)
    parts.append(f"  bd update <id> --status <{_LIFECYCLE_HINT}>\n")
    return "".join(parts)


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


def _heal_fail_soft(
    *,
    project_root: Path,
    remaps: list[dict[str, str]],
) -> _LoadedItems | _LoadUnavailable:
    """Apply the planned remaps in place, then reload — fail-soft on any write error.

    A write that raises an EXPECTED beads/store error becomes `_LoadUnavailable`
    (could-not-check): any remaps already applied stay applied (safe partial
    progress that re-converges next push), and the gate skips rather than blocks.
    Only ever called with a non-empty plan (a clean tenant skips the write).
    """
    try:
        apply_native_status_remaps(remaps=remaps, config=store_config(repo=project_root))
        items = load_items(repo=project_root)
    except _GATE_COULD_NOT_CHECK_ERRORS as exc:
        return _LoadUnavailable(reason=str(exc))
    return _LoadedItems(items=items)


def run_ledger_gate(*, project_root: Path) -> int:
    """Run the auto-heal-loud pre-push gate over `project_root`'s tenant.

    Reads the tenant, applies the two safe beads-native remaps IN PLACE (loud),
    then computes residual non-lifecycle findings over the post-heal rows. Emits
    the CLEAN / HEALED / DRIFT / SKIP marker and returns 0 / 0 / 1 / 2 per the
    module's exit-code contract; every write is printed and every expected
    read/write error skips (never blocks).
    """
    loaded = _load_items_fail_soft(project_root=project_root)
    if isinstance(loaded, _LoadUnavailable):
        _ = write_stderr(text=f"{LEDGER_GATE_SKIP_MARKER} {loaded.reason}\n")
        return _EXIT_COULD_NOT_CHECK
    remaps = plan_native_status_remaps(items=loaded.items)
    if remaps:
        healed = _heal_fail_soft(project_root=project_root, remaps=remaps)
        if isinstance(healed, _LoadUnavailable):
            _ = write_stderr(text=f"{LEDGER_GATE_SKIP_MARKER} {healed.reason}\n")
            return _EXIT_COULD_NOT_CHECK
        resulting = healed.items
    else:
        resulting = loaded.items
    residual = run_ledger_checks(items=resulting)
    decision = decide_ledger_gate(healed=remaps, residual=residual)
    _ = write_stdout(text=decision.message)
    return decision.exit_code
