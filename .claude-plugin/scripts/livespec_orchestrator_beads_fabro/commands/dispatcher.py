"""`dispatcher` — the thin Dispatcher of the Beads/Dolt + Fabro orchestrator.

Per livespec spec.md
(orchestrator-internal decomposition: Ledger / Loop / Dispatcher) and the
Dispatcher guidance in livespec non-functional-requirements.md, this CLI
polls the beads Ledger for ready work-items, invokes the Fabro Loop (the
`.fabro/workflows/implement-work-item/` phase graph) once per item —
launched from the target repo's primary checkout; Fabro clones fresh
inside its docker sandbox (Architecture C), so the host owns no git
working state — confirms the PR merge, runs the post-merge janitor hard
gate in a fresh detached worktree of merged master (never the host
primary's working tree, whose environment rot once false-redded a
confirmed-green merge — work-item livespec-impl-beads-cgd), writes
status/PR evidence back to the Ledger, and journals every step. It is
orchestrator-PRIVATE tooling: core's contract sees only the three
`orchestrator.py` CLIs.

  dispatcher.py ledger-check [--project-root <path>] [--json]
  dispatcher.py ledger-normalize [--project-root <path>] [--dry-run] [--gate] [--json]
  dispatcher.py codex-cred-refresh [--dry-run] [--json]
  dispatcher.py codex-cred-status [--json]
  dispatcher.py spec-check [--project-root <path>] [--spec-root <path>] [--json]
  dispatcher.py janitor-check [--repo <path>] [--json]
  dispatcher.py dispatch --repo <path> --item <id> [common flags]
  dispatcher.py loop --repo <path> --budget <n> [--parallel <k>]
                     [--mode shadow|autonomous] [--item <id>]... [common flags]

`spec-check` runs the three re-homed spec-context work-item invariants
(no-stalled-epic / no-stale-gap-tied / unresolved-spec-commitment; see
`_dispatcher_spec_checks.py`) against the tenant rows plus the spec
tree at `--spec-root` (default `<project-root>/SPECIFICATION`).
`janitor-check` runs the three re-homed stale-cleanup checks
(no-stale-merged-branch / no-stale-merged-pr-branch / no-stale-worktree;
see `_dispatcher_janitor_checks.py`) against the repo's git/gh state.
Both are standalone check surfaces — the pre-dispatch hard gate inside
`dispatch`/`loop` stays the pure-Ledger dispatch-safety trio.
`ledger-normalize` is the standalone self-heal surface: it reuses the
dispatch-path status normalizer (`open` → `backlog`, `in_progress` →
`active`; every other status is left for the status-conformance check)
to remap ANY tenant's beads-native statuses WITHOUT needing a dispatch,
then reports the residual non-conformant rows. `--dry-run` plans and
reports the remaps without writing anything. `--gate` is the always-run
pre-push mode: auto-heal-loud — it heals the two safe transient remaps IN
PLACE, PRINTS each remap it writes, and exits 0 (clean or healed) / 1
(residual drift needing a human lane decision) / 2 (could-not-check). A
heal-write or tenant-read that raises an expected beads error SKIPS the push
rather than bricking it, the same fail-soft exit-code contract the
`check-ledger-conformance-live` recipe consumes (see
`_dispatcher_ledger_gate`).

Common flags: [--workflow <toml>] [--fabro-bin <path>]
[--janitor <json-argv>] [--journal <path>] [--poll-attempts <n>]
[--poll-interval-seconds <s>] [--no-close-on-merge]
[--skip-ledger-check] [--json]

Credential channel (Architecture C): the per-dispatch UNCOMMITTED
run-config overlay materialized under the temp dir is the RUN-SCOPED
credential projection (per the family-secrets scoped
transient-materialization rule): it appends an
`[environments.<id>.env]` table carrying the CLAUDE_CODE_OAUTH_TOKEN
value read from the Dispatcher's process environment plus a GITHUB_TOKEN
freshly minted from the GitHub App installation-token provider (the FULL
name, not the short GH_TOKEN — see render_run_config_overlay: gh prefers
GH_TOKEN, and fabro re-projects its own re-minted token per exec under
GITHUB_TOKEN, so a projected GH_TOKEN would shadow fabro's fresh value
and expire past the ~60-min TTL at a long run's publish node), is
written mode-600, and is deleted when the run returns. The committed workflow
config carries NO secret VALUE and NO `{{ env }}` interpolation —
interpolation can NOT deliver credentials to server-mediated runs (do
not re-attempt it): resolution happens in the WORKER process, which
fabro-server spawns with a fail-closed env allowlist
(fabro-server/src/spawn_env.rs), so the token never reaches the
resolver and the LITERAL `{{ env.X }}` string flows into the sandbox
(proven empirically 2026-06-12: API 401 with the token present in
both the dispatcher's and the server daemon's env). The Dispatcher is
invoked under the dispatch TARGET's configured credential_wrapper, which
must inject the full per-wrapper set: GITHUB_APP_ID, GITHUB_PRIVATE_KEY,
BEADS_DOLT_PASSWORD, and CLAUDE_CODE_OAUTH_TOKEN. Per the
github-app-auth design there is NO fleet-PAT fallback, and the
Dispatcher refuses to dispatch when a credential is absent — there
would be nothing to project. The engine's
subprocess runner re-resolves GH_TOKEN from the caching provider
before EVERY command, so the ~76-minute merge-poll and any >1-hour
operation re-mint transparently instead of dying on a once-at-start
export. Token values are never logged, echoed, or journaled.

Sandbox sibling clones: the same overlay appends one depth-1
prepare-step clone per fleet member (from livespec master's
.livespec-fleet-manifest.jsonc, fetched host-side via `gh api` at run-config
generation; the dispatch target is excluded) and projects the
non-secret LIVESPEC_SIBLING_CLONES_ROOT=/workspace/siblings into the
sandbox env table, so cross-repo checks under `just check` resolve
family siblings inside the sandbox — mirroring livespec CI. An
unreachable or malformed manifest fails the dispatch fast at the
`run-config-overlay` stage.

Connection + consent model: the Ledger connection resolves from the
TARGET repo's `.livespec.jsonc` (cwd-style `--repo` addressing) plus
`BEADS_DOLT_PASSWORD` for that tenant in the environment — one tenant
per process. Modes per the Dispatcher guidance: `shadow` (default)
dispatches ONLY items explicitly named via `--item`; `autonomous` takes
the ready queue. The Dispatcher is the sole enforcer of the two
human-delegable policy valves bracketing the WIP-limited autonomous
middle: ADMISSION (admit the highest-`rank` admission-eligible `ready`
items up to the per-repo `dispatcher.wip_cap`, set the assignee,
transition `ready → active`; a manual / unresolvable-assignee item is
held + surfaced) and POST-MERGE ACCEPTANCE (`complete` merges on green
into `acceptance`, then `accept` confirms per the effective
`acceptance_policy` — `ai-only` → `done`, else park in `acceptance` for a
human; `reject` routes `rework → active` / `re-groom → backlog`). Store
writes (admit / complete / accept / reject / close-on-confirmed-merge
with PR/merge-sha evidence) are machine-path dispositions of already-filed
items, exempt from the per-operation consent discipline that governs
user-facing capture front-ends (livespec-impl-beads-nip);
`--no-close-on-merge` turns the post-merge acceptance writes off entirely.
A `blocked` outcome (run parked at the phase graph's in-loop human gate)
closes nothing and frees the slot: the operator answers via `fabro attach
<run-id>`; the Dispatcher never auto-resumes.

Exit codes: 0 success / all dispatched green; 1 non-skipped findings
present or any dispatch not green (failed OR blocked — both need the
operator's eyes); 2 usage error; 3 precondition error (missing repo /
workflow / item not ready). `skipped`-severity findings (unmet
preconditions) are reported but never flip the exit code.

Cost-observability seam (work-item livespec-impl-beads-5v9, the
prerequisite to y0m's fail-closed spend cap): the 5v9 investigation found
per-run cost FUNDAMENTALLY UNOBSERVABLE in this fabro version (v0.254.0,
ACP backend) — `fabro ps -a --json`'s `total_usd_micros` is null on every
run and no token/usage signal is populated anywhere. The warranted
fail-closed gate lives in `_dispatcher_cost`: `observe_run_cost(ps_json,
run_id)` is the cost SIGNAL (reads `total_usd_micros` from `fabro ps -a
--json`, surfacing a real value the moment fabro populates it),
`cost_gate_decision(mode, observation)` is the fail-closed rule
(autonomous + unobservable cost ⇒ refuse; shadow ⇒ warn), and
`gate_wave(...)` applies it across a completed wave — journaling one
leak-free `cost-gate` record per launched run and returning the work-item
ids that refused.

The gate is LIVE (work-item livespec-impl-beads-y0m): `_cost_gate_after_verdict`
runs `fabro ps -a --json` (via `ShellCommandRunner`, the same seam the
watchdog uses) ONCE after the wave's verdict is computed — alongside
`reflect` / `_alarm_on_terminal_failure`, FAIL-OPEN so a probe error or any
exception is journaled as `cost-gate-error` and the verdict is never
changed — passes the output to `gate_wave` (with `os.environ` so the caps
resolve), and turns each returned refusal into a `spend-cap-breach`-class
`NotifyEvent` through the existing `notify_terminal` seam. y0m extends the
gate from the "unobservable" verdict to the per-run + per-session USD
cap-VALUE comparison (`cap_value_decision`) using the committed
env-overridable defaults `resolve_per_run_cap_usd` /
`resolve_per_session_cap_usd` ($25 / $100, `LIVESPEC_MAX_RUN_USD` /
`LIVESPEC_MAX_SESSION_USD`), accumulating the per-session total across the
wave's observed runs. The cap-VALUE path is DORMANT until fabro reports a
populated cost (`total_usd_micros` null today; tracked as
livespec-impl-beads-efj) but is correct + tested; the
fail-closed-when-unobservable behavior 5v9 built stays the live path.
"""

import argparse
from collections.abc import Callable

from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    admit_and_select,
    autonomous_armed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous import (
    arm_autonomous_for_loop,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_emit import (
    emit_calibration,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import (
    run_codex_cred_refresh,
    run_codex_cred_status,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    bounce_non_convergence_to_backlog,
    complete_and_accept,
    host_only_refusal,
    warn_item_sizing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    emit_outcomes,
    ledger_blocked_after_normalization,
    load_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop import dispatch_one
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_command import (
    run_loop_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    candidates,
    is_dispatch_candidate,
    janitor_core_ref,
    post_run_dispositions,
    prepare,
    ready_items,
    run_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring import (
    ensure_otel_receiver,
    parse_janitor,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_post_verdict import (
    reflector_oob_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection import reflect
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_checks import (
    dispatch_preamble,
    requested_items_preflight_error,
    run_janitor_check,
    run_ledger_check,
    run_ledger_normalize,
    run_spec_check,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_commands import (
    run_dispatch_command,
)

# Keep pre-existing dispatcher mini-hub attributes available without changing __all__.
_COMPATIBILITY_REEXPORTS: tuple[object, ...] = (
    admit_and_select,
    arm_autonomous_for_loop,
    autonomous_armed,
    emit_outcomes,
    ensure_otel_receiver,
    ledger_blocked_after_normalization,
    reflect,
)

__all__: list[str] = [
    "bounce_non_convergence_to_backlog",
    "candidates",
    "complete_and_accept",
    "dispatch_one",
    "dispatch_preamble",
    "emit_calibration",
    "host_only_refusal",
    "is_dispatch_candidate",
    "janitor_core_ref",
    "load_items",
    "main",
    "parse_janitor",
    "post_run_dispositions",
    "prepare",
    "ready_items",
    "reflector_oob_after_verdict",
    "requested_items_preflight_error",
    "run_codex_cred_refresh",
    "run_codex_cred_status",
    "run_id",
    "run_janitor_check",
    "run_ledger_check",
    "run_ledger_normalize",
    "run_spec_check",
    "warn_item_sizing",
]


_SUBCOMMAND_HANDLERS: dict[str, Callable[..., int]] = {
    "codex-cred-refresh": run_codex_cred_refresh,
    "codex-cred-status": run_codex_cred_status,
    "dispatch": run_dispatch_command,
    "janitor-check": run_janitor_check,
    "ledger-check": run_ledger_check,
    "ledger-normalize": run_ledger_normalize,
    "spec-check": run_spec_check,
}


def main(*, argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = _SUBCOMMAND_HANDLERS.get(args.subcommand, run_loop_command)
    return handler(args=args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dispatcher")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    ledger = subparsers.add_parser("ledger-check")
    _ = ledger.add_argument("--project-root", dest="project_root", default=None)
    _ = ledger.add_argument("--json", dest="as_json", action="store_true")
    norm = subparsers.add_parser("ledger-normalize")
    _ = norm.add_argument("--project-root", dest="project_root", default=None)
    _ = norm.add_argument("--json", dest="as_json", action="store_true")
    _ = norm.add_argument("--dry-run", dest="dry_run", action="store_true")
    # `--gate` is the always-run pre-push mode: auto-heal-loud — it heals the
    # two safe transient remaps in place, prints each, and sets a fail-soft
    # exit-code contract (0 clean/healed / 1 residual drift / 2 could-not-check).
    # See `_dispatcher_ledger_gate.run_ledger_gate`.
    _ = norm.add_argument("--gate", dest="gate", action="store_true")
    _add_codex_cred_refresh(parser=subparsers.add_parser("codex-cred-refresh"))
    codex_cred_status = subparsers.add_parser("codex-cred-status")
    _ = codex_cred_status.add_argument("--json", dest="as_json", action="store_true")
    spec = subparsers.add_parser("spec-check")
    _ = spec.add_argument("--project-root", dest="project_root", default=None)
    _ = spec.add_argument("--spec-root", dest="spec_root", default=None)
    _ = spec.add_argument("--json", dest="as_json", action="store_true")
    janitor = subparsers.add_parser("janitor-check")
    _ = janitor.add_argument("--repo", dest="repo", default=None)
    _ = janitor.add_argument("--json", dest="as_json", action="store_true")
    dispatch = subparsers.add_parser("dispatch")
    _add_dispatch_common(parser=dispatch)
    _ = dispatch.add_argument("--item", dest="item", required=True)
    loop = subparsers.add_parser("loop")
    _add_dispatch_common(parser=loop)
    _ = loop.add_argument("--budget", dest="budget", type=int, required=True)
    _ = loop.add_argument("--parallel", dest="parallel", type=int, default=1)
    _ = loop.add_argument("--mode", dest="mode", choices=["shadow", "autonomous"], default="shadow")
    _ = loop.add_argument("--item", dest="items", action="append", default=None)
    return parser


def _add_codex_cred_refresh(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    _ = parser.add_argument("--dry-run", dest="dry_run", action="store_true")


def _add_dispatch_common(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--workflow", dest="workflow", default=None)
    # Default None (NOT the bare name "fabro"): a None sentinel means "not
    # explicitly passed -> resolve from LIVESPEC_FABRO_BIN / the .livespec.jsonc
    # dispatcher.fabro_bin key / the absolute default at command entry". An
    # explicit `--fabro-bin <path>` still wins over resolution.
    _ = parser.add_argument("--fabro-bin", dest="fabro_bin", default=None)
    _ = parser.add_argument("--janitor", dest="janitor", default=None)
    _ = parser.add_argument("--journal", dest="journal", default=None)
    _ = parser.add_argument("--poll-attempts", dest="poll_attempts", type=int, default=80)
    _ = parser.add_argument(
        "--poll-interval-seconds",
        dest="poll_interval_seconds",
        type=float,
        default=30.0,
    )
    _ = parser.add_argument(
        "--no-close-on-merge",
        dest="close_on_merge",
        action="store_false",
    )
    _ = parser.add_argument(
        "--skip-ledger-check",
        dest="skip_ledger_check",
        action="store_true",
    )
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
