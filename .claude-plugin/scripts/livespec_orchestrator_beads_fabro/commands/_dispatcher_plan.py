"""Pure planning layer for the Dispatcher: plans, argv builders, parsers.

Everything here is a pure function of its inputs so the hermetic test
tier covers the Dispatcher's decision surface without subprocesses. The
side-effecting execution of these argvs lives in `_dispatcher_engine`
(sequencing) and `_dispatcher_io` (the subprocess seam).

The argv builders encode the Architecture C dispatch discipline
(livespec non-functional-requirements.md + livespec/tmp/fabro-architecture-c-design.md):
`fabro run` executes from the target repo's PRIMARY checkout and Fabro
clones fresh inside its docker sandbox (the host owns no git working
state — no worktree prep, no reaping), the work publishes under
`feat/<work-item-id>` (never the Fabro-managed run-branch name),
`gh pr view` confirms the merge, and the janitor argv is injected from
configuration (never hardcoded).

The run-config helper (`render_run_config_overlay`) materializes the
RUN-SCOPED credential projection (the family-secrets scoped
transient-materialization rule): the committed config carries NO
secret, and the rendered overlay appends an `[environments.<id>.env]`
table carrying the caller-supplied CLAUDE_CODE_OAUTH_TOKEN value (read
from the Dispatcher's process environment) and GITHUB_TOKEN value (a
fresh App installation token minted by the caller's provider — never a
fleet PAT; the FULL name GITHUB_TOKEN, not the short GH_TOKEN, so Fabro's
per-exec re-minted GITHUB_TOKEN is not shadowed), alongside the `graph`
path rewritten absolute so the overlay resolves from outside the workflow
directory. The same overlay provisions the sandbox sibling clones:
per-fleet-member depth-1 `[[run.prepare.steps]]` clone blocks plus the
non-secret `LIVESPEC_SIBLING_CLONES_ROOT` env key (riding in the same
appended env table — TOML allows only one declaration of that table),
so cross-repo checks under `just check` resolve family siblings inside
the sandbox exactly like livespec CI provisions them.

Fabro `{{ env.* }}` interpolation can NOT carry the
credential for server-mediated runs — do not re-attempt it: the
interpolation resolves in the WORKER process, which fabro-server
spawns with a fail-closed env allowlist (fabro-server/src/spawn_env.rs
— PATH/HOME/TMPDIR/USER/RUST_*/FABRO_*/TERM etc. only), so the token
never reaches the resolver and the LITERAL `{{ env.X }}` string flows
into the sandbox (proven empirically 2026-06-12: API 401 with the
token present in both the dispatcher's and the server daemon's env).
"""

from __future__ import annotations

import re
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import (
    CODEX_ADAPTER_BASE,
    CODEX_ADAPTER_COMMAND,
    CODEX_AGENT_MODE_READ_ONLY,
    CODEX_AGENT_MODE_WRITE,
    CODEX_IMPLEMENTER_ADAPTER,
    FleetMembers,
    codex_adapter,
    janitor_argv,
    janitor_bootstrap_argv,
    janitor_checkout_path,
    janitor_checkout_provision_argv,
    janitor_core_checkout_path,
    janitor_core_clone_argv,
    janitor_core_ref_from_config,
    janitor_core_repo_url_from_config,
    janitor_reconcile_checkout_path,
    janitor_trust_argv,
    janitor_venue_contains_merge_argv,
    janitor_worktree_add_argv,
    janitor_worktree_remove_argv,
    parse_fleet_members,
    pr_arm_argv,
    pr_update_branch_argv,
    pr_view_argv,
    pull_primary_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    GoalBriefMiniJinjaFinding,
    minijinja_findings_detail,
    minijinja_openers_in_goal_sources,
    minijinja_openers_in_text,
    render_goal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_only import (
    WORKFLOW_SCOPE_OVERRIDE_LABEL,
    declares_workflow_scope_refusal,
    host_only_refusal_detail,
    is_host_only_item,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    CORE_PLUGIN_ROOT_ENV_VAR,
    CURRENCY_GATE_ENV_VALUE,
    CURRENCY_GATE_ENV_VAR,
    SIBLING_CLONES_ROOT_ENV_VAR,
    SiblingClones,
    escape_minijinja_literal,
    render_run_config_overlay,
    workflow_graph_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import (
    DispatchPlan,
    build_plan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_MARGIN_SECONDS,
    CODEX_NON_ROTATABLE_REFRESH_SENTINEL,
    DEFAULT_SANDBOX_OTEL_ENDPOINT,
    SANDBOX_OTEL_ENDPOINT_ENV_VAR,
    CodexFreshnessVerdict,
    assess_codex_credential_freshness,
    cc_otel_overlay_env,
    project_codex_auth_snapshot,
    resolve_sandbox_otel_endpoint,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_status import (
    PrView,
    parse_pr_view,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "CODEX_ADAPTER_BASE",
    "CODEX_ADAPTER_COMMAND",
    "CODEX_AGENT_MODE_READ_ONLY",
    "CODEX_AGENT_MODE_WRITE",
    "CODEX_FRESHNESS_MARGIN_SECONDS",
    "CODEX_IMPLEMENTER_ADAPTER",
    "CODEX_NON_ROTATABLE_REFRESH_SENTINEL",
    "CORE_PLUGIN_ROOT_ENV_VAR",
    "CURRENCY_GATE_ENV_VALUE",
    "CURRENCY_GATE_ENV_VAR",
    "DEFAULT_SANDBOX_OTEL_ENDPOINT",
    "NEEDS_HUMAN_MARKER",
    "NON_CONVERGED_MARKER",
    "SANDBOX_OTEL_ENDPOINT_ENV_VAR",
    "SIBLING_CLONES_ROOT_ENV_VAR",
    "WORKFLOW_SCOPE_OVERRIDE_LABEL",
    "CodexFreshnessVerdict",
    "DispatchPlan",
    "FleetMembers",
    "GoalBriefMiniJinjaFinding",
    "PrView",
    "SiblingClones",
    "assess_codex_credential_freshness",
    "build_plan",
    "cc_otel_overlay_env",
    "codex_adapter",
    "declares_workflow_scope_refusal",
    "escape_minijinja_literal",
    "host_only_refusal_detail",
    "is_host_only_item",
    "is_needs_human_outcome",
    "is_non_convergence_outcome",
    "item_sizing_warnings",
    "janitor_argv",
    "janitor_bootstrap_argv",
    "janitor_checkout_path",
    "janitor_checkout_provision_argv",
    "janitor_core_checkout_path",
    "janitor_core_clone_argv",
    "janitor_core_ref_from_config",
    "janitor_core_repo_url_from_config",
    "janitor_reconcile_checkout_path",
    "janitor_trust_argv",
    "janitor_venue_contains_merge_argv",
    "janitor_worktree_add_argv",
    "janitor_worktree_remove_argv",
    "minijinja_findings_detail",
    "minijinja_openers_in_goal_sources",
    "minijinja_openers_in_text",
    "parse_fleet_members",
    "parse_pr_view",
    "pr_arm_argv",
    "pr_update_branch_argv",
    "pr_view_argv",
    "project_codex_auth_snapshot",
    "pull_primary_argv",
    "render_goal",
    "render_run_config_overlay",
    "resolve_sandbox_otel_endpoint",
    "workflow_graph_path",
]

# Sizing heuristics (warn-only; see `item_sizing_warnings`). Calibrated on
# the 2026-06-12 shakedown evidence: the two ACP-turn-timeout casualties
# (dev-tooling p60, git-jsonl tenpup) were both heavy multi-part /
# multi-RGR items with long enumerated descriptions, and both succeeded
# immediately once split out to host sub-agents.
_SIZING_DESCRIPTION_CHAR_LIMIT = 1500
_SIZING_PART_MARKER_RE = re.compile(r"multi[-\s]?(?:part|rgr)", re.IGNORECASE)
_SIZING_ENUMERATED_RE = re.compile(r"\(\d+\)|^\s*\d+[.)]\s", re.MULTILINE)
_SIZING_ENUMERATED_LIMIT = 3

# The stable non-convergence sentinel the Fabro workflow-DOT's
# "non-converged" terminal node emits to stderr (work-item
# livespec-impl-beads-rw75ym, Scenario 14) when a slice hits the fix-loop
# cap without converging. The terminal node exits non-zero (no outgoing
# edge), so the run ends non-green and the Dispatcher's engine surfaces
# this marker in the failed outcome's detail; `is_non_convergence_outcome`
# matches it to drive the n5kina bounce-to-`backlog`. Keeping the
# sentinel here makes the DOT-side producer and the Dispatcher-side
# consumer share ONE literal (the DOT references this exact string).
NON_CONVERGED_MARKER = "LIVESPEC_NON_CONVERGED"

# The needs-human sentinel the `needs_human` TERMINAL node emits to stderr
# (plan ledger-is-the-only-gate, epic bd-ib-n77djm; contracts.md "A factory
# run never awaits a human", v093, Scenario 103). The node replaced the
# in-loop `escalate` hexagon: instead of parking the run in Fabro's native
# blocked status until a human attached, the run preserves its tree on
# `refs/heads/needs-human/<run id>`, prints this marker and exits 1 with no
# outgoing edge. The Dispatcher recognises the marker and produces the SAME
# `blocked` outcome the gate used to — the item rests at blocked /
# needs-human and the decision reaches a human through the ledger's valves —
# while the run itself is already gone. One literal shared by producer and
# consumer, exactly as NON_CONVERGED_MARKER.
NEEDS_HUMAN_MARKER = "LIVESPEC_NEEDS_HUMAN"


def item_sizing_warnings(*, item: WorkItem) -> tuple[str, ...]:
    """Warn-only sizing heuristics applied at dispatch/loop-feed time.

    Pure function of the item; the Dispatcher journals + stderr-WARNs the
    hits and proceeds regardless (never blocking). Three heuristics:
    description length, explicit multi-part/multi-RGR markers, and
    enumerated part counts.
    """
    warnings: list[str] = []
    if len(item.description) > _SIZING_DESCRIPTION_CHAR_LIMIT:
        length_warning = (
            f"description is {len(item.description)} chars "
            f"(> {_SIZING_DESCRIPTION_CHAR_LIMIT}): heavy items have exceeded one "
            "unattended ACP turn; consider splitting before loop-feeding"
        )
        warnings.append(length_warning)
    if _SIZING_PART_MARKER_RE.search(f"{item.title}\n{item.description}") is not None:
        marker_warning = (
            "title/description carries a multi-part/multi-RGR marker: such items "
            "have exceeded one unattended ACP turn; consider splitting"
        )
        warnings.append(marker_warning)
    enumerated = len(_SIZING_ENUMERATED_RE.findall(item.description))
    if enumerated >= _SIZING_ENUMERATED_LIMIT:
        enumerated_warning = (
            f"description carries {enumerated} enumerated parts: consider one "
            "work-item per part before loop-feeding"
        )
        warnings.append(enumerated_warning)
    return tuple(warnings)


class _NonConvergenceOutcome(Protocol):
    """Structural view of a terminal outcome's non-convergence signals.

    The pure planning layer cannot import `DispatchOutcome` from
    `_dispatcher_engine` (that module imports THIS one — a concrete import
    would be circular), so the predicate reads only the two fields it
    needs through this Protocol. `DispatchOutcome` satisfies it
    structurally, so the Dispatcher passes the dataclass straight through.
    """

    @property
    def status(self) -> str: ...

    @property
    def detail(self) -> str: ...


def is_non_convergence_outcome(*, outcome: _NonConvergenceOutcome) -> bool:
    """Recognise a non-convergence terminal the Dispatcher must bounce (n5kina).

    Per SPECIFICATION/contracts.md and
    SPECIFICATION/scenarios.md "Scenario 11 — Dispatcher bounces a
    non-converging slice to backlog": a dispatched slice that will
    not converge through the janitor gate within the bounded fix-loop cap
    MUST be bounced to `backlog` and surfaced, never infinite-retried.
    The Dispatcher reads this predicate AFTER the terminal outcome to
    decide whether to bounce the item to `backlog`.

    Two mechanical signals mark non-convergence, both already produced by
    the existing dispatch path:

    - `stalled-no-progress` — the coarse wall-clock watchdog confirmed the
      run made no progress for the full stall window and `fabro rm -f`-ed
      it (the 7us.6 hang class). A stalled run will not converge and would
      otherwise be retried; it is the empirical non-convergence terminal
      already in the engine's vocabulary.
    - the DOT non-converged sentinel — the single Fabro workflow-DOT tweak
      (work-item livespec-impl-beads-rw75ym, Scenario 14) routes a
      fix-loop-cap exhaustion to a terminal `non_converged` node that exits
      non-zero with `NON_CONVERGED_MARKER` on stderr. The run ends non-green
      and the engine surfaces that marker in the failed outcome's `detail`,
      so a substring match recovers the DOT's non-converged exit edge as a
      Dispatcher-side bounce trigger.

    Ordinary failures (a `host-only-refused` / `human-gated-surfaced`
    routing refusal, a `blocked` human-gate park, a one-off `pr-view`
    failure) are NOT non-convergence and must not be bounced, so the match
    is deliberately narrow — the watchdog status plus the explicit DOT
    sentinel only.
    """
    if outcome.status == "stalled-no-progress":
        return True
    return outcome.status == "failed" and NON_CONVERGED_MARKER in outcome.detail


def is_needs_human_outcome(*, outcome: _NonConvergenceOutcome) -> bool:
    """Recognise the `needs_human` terminal's sentinel on a failed outcome.

    Deliberately narrow, like `is_non_convergence_outcome`: only a `failed`
    status whose detail carries the exact marker. A green or blocked outcome
    that happens to quote the marker is not a needs-human terminal.
    """
    return outcome.status == "failed" and NEEDS_HUMAN_MARKER in outcome.detail
