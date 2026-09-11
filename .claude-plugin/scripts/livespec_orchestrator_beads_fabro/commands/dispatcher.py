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
  dispatcher.py claude-cred-status [--json]
  dispatcher.py spec-check [--project-root <path>] [--spec-root <path>] [--json]
  dispatcher.py janitor-check [--repo <path>] [--json]
  dispatcher.py reconcile-runs [--repo <path>] [--factory <name>]
                                [--fabro-bin <path>] [--journal <path>]
                                [--invoker <id>] [--dry-run] [--json]
  dispatcher.py clear-provider-exhaustion --provider <name> --reason <text>
                                          [--repo <path>] [--invoker <id>]
                                          [--journal <path>]
  dispatcher.py clear-acp-availability-hold --scope <scope> --hold-key <key>
                                            --reason <text>
                                            [--candidate-key <key>]
                                            [--repo <path>] [--invoker <id>]
                                            [--journal <path>]
  dispatcher.py reconcile-merged --repo <path> --item <id> [--invoker <id>]
                                 [--regrade] [--json]
  dispatcher.py probe --repo <path> --item <id> [common flags]
  dispatcher.py dispatch --repo <path> --item <id> [common flags]
  dispatcher.py loop --repo <path> --budget <n> [--parallel <k>]
                     [--dry-run] [--item <id>]... [common flags]

`spec-check` runs the three re-homed spec-context work-item invariants
(no-stalled-epic / no-stale-gap-tied / unresolved-spec-commitment; see
`_dispatcher_spec_checks.py`) against the tenant rows plus the spec
tree at `--spec-root` (default `<project-root>/SPECIFICATION`).
`janitor-check` runs the three re-homed stale-cleanup checks
(no-stale-merged-branch / no-stale-merged-pr-branch / no-stale-worktree;
see `_dispatcher_janitor_checks.py`) against the repo's git/gh state.
`reconcile-runs` is the single authority over every configured factory's
non-terminal run inventory. It surveys each declared factory through that
factory's own resolved target, considers every non-terminal status kind —
`blocked` and `paused` included, which is what the narrower sweep it
replaces could not see — and joins each run against the
Ledger plus the dispatch journal's run ids. A run whose item is not `active`,
whose item is `active` under a DIFFERENT journaled run, or whose item is
absent from the Ledger is an ORPHAN: its record is exported and read back
first, then it is terminated (a blocked run by answering its interview
Abandon, anything else by cancel, `fabro rm -f` only after both fail), and the
reconciliation is journaled. It NEVER writes the item's status,
`blocked_reason`, or labels — the decision stays in the Ledger. `--dry-run
--json` is the read-only projection over the same join.
The pre-dispatch hard gate inside `dispatch`/`loop` stays the pure-Ledger
dispatch-safety trio.
`reconcile-merged` is the guarded recovery valve for an already-merged
active item whose dispatch process died before post-run disposition: it
resolves the merged PR from GitHub, re-runs only the post-merge janitor,
and then enters the existing acceptance path without relaunching Fabro.
`--regrade` selects its second arm, for the OTHER stranding: an item whose
dispatch completed, whose PR merged, and whose acceptance then failed on
criteria that have since been repaired. That item carries `rework:pending`
and the ordinary arm refuses it, because re-implementing already-merged work
cuts an empty branch and spends an `acceptance_rework_cap` attempt to fail.
The regrade arm re-grades instead: it proceeds only when the merged PR
resolves AND its merge commit is an ancestor of `origin/<default branch>`,
runs the same acceptance pass against the item's current effective criteria,
closes the item on PASS (which clears the marker through the lifecycle write
seam), and on any other verdict leaves the item's status, labels and
`acceptance_failed_ai_passes` exactly as it found them. It launches no Fabro
run, cuts no branch, and runs no janitor (see
`_dispatcher_reconcile_regrade`).
`probe` is the loop probe of contracts.md: the take-never-file health command
that drives ONE designated, ALREADY-FILED work-item through the whole cycle
with an assertion at each stage. It refuses
without `--item` and creates, files, or clones nothing; it refuses an item whose
effective `acceptance_policy` is not `ai-only` (terminal `done` is otherwise not
machine-reachable) and an invocation whose invoker resolves to the fallback
mark; it confines the driven change to `.livespec-probe/`, verified BEFORE the
merge with the post-merge diff check as the backstop; and its HARD residue
assertions key only on the reserved identifier set
(`probe:<item>:<utc-start>` plus the item id), with the unrelated before/after
delta REPORTED and never asserted. An attention or ledger source that cannot be
read fails the probe with a source-unavailable outcome rather than reading the
unread surface as clear.
`clear-provider-exhaustion` is the operator's early-clearance valve for an
observed provider-exhaustion record. An observed record otherwise retires only
when its bounded expiry elapses or a successful dispatch against the same
provider falsifies it, and the admission gate refuses the very dispatch that
would falsify it — so an operator who has just restarted a self-hosted or free
provider has no way to say so. This subcommand appends one
`provider-exhaustion-cleared` line the admission scan reads as a retirement;
it rewrites and deletes nothing. It refuses a blank `--reason` and refuses
outright any invocation resolving to the unattributed invoker mark, so it stays
a human act rather than becoming a second automatic-expiry path (see
`_dispatcher_provider_exhaustion_clear`).
`clear-acp-availability-hold` is the TYPED sibling of that valve, and a
separate one: it retires the schema-v1 observed-availability records of the
"Factory-configurable ACP fallback priority" contract, which are scoped to an
exact `(scope, hold_key[, candidate_key])` target rather than to a whole
vendor. It carries the same two human-only refusals (blank `--reason`,
unattributed invoker) plus an exactness refusal — a candidate-scoped clearance
must name its `--candidate-key` and a domain-scoped one must not — and it
refuses a target holding no live observation. It writes its own
`acp-availability-cleared` stage, which the legacy provider scan never reads,
so neither valve can retire the other's records (see `_acp_hold_clear`).
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

Common flags: [--invoker <id>] [--workflow <toml>] [--fabro-bin <path>]
[--janitor <json-argv>] [--journal <path>] [--poll-attempts <n>]
[--poll-interval-seconds <s>] [--no-close-on-merge]
[--skip-ledger-check] [--json]

Invoker attribution (the journal invoker attribution contract in
contracts.md): every state-changing entry point here — `loop`, `dispatch`,
`reconcile-merged` — accepts `--invoker <id>` and otherwise honors the
`LIVESPEC_INVOKER` environment variable, falling back to the
`unattributed:<os-user>@<hostname>` MARK when neither is asserted. The resolved
identity is stamped onto every journal record by the append layer
(`_dispatcher_io.JournalFile.append`), never by a writer. With the committed
`dispatcher.require_invoker` true, a fallback-only invocation is refused at
startup as a precondition error (exit 3) before any store mutation, journal
write, or run creation. That dial is
deliberately absent from the API-configurable key manifest: a setting that
relaxes attribution must not be reachable over the surface whose acts it
attributes.

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
per process. There are NO run modes: `dispatch --item` drives one
explicitly named item as an operator override (no WIP-cap
enforcement), while `loop` with no `--item` drains the ranked ready
queue up to `--budget` and the WIP cap. Dispositions are governed by the
`dispatcher.*` policy settings read from `.livespec.jsonc`, never by a
per-run mode argument. The Dispatcher is the sole enforcer of the two
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
A `blocked` outcome (the phase graph's `needs_human` terminal fired: the
run preserved its tree and ended) closes nothing: the item rests at
`blocked / needs-human` and the human decides through the ledger's
valves (`resolve-blocked:<id>:ready`); no run waits, nothing is resumed.

Exit codes: 0 success / all dispatched green; 1 non-skipped findings
present or any terminal failed dispatch; 2 usage error; 3 precondition
error (missing repo / workflow / item not ready); 4 dispatch completed with the
work-item routed to the ledger's human gate and no terminal failures; 5
ungradeable-acceptance-criteria refusal (the effective-acceptance-criteria
clause of contracts.md — an AI-dispositive item whose effective criteria parse
to zero gradeable assertions, refused before any run is created).
`skipped`-severity findings (unmet preconditions) are reported but never
flip the exit code.

Cost-observability seam (work-item livespec-impl-beads-5v9, the
prerequisite to y0m's fail-closed spend cap): the 5v9 investigation found
per-run cost FUNDAMENTALLY UNOBSERVABLE in this fabro version (v0.254.0,
ACP backend) — `fabro ps -a --json`'s `total_usd_micros` is null on every
run and no token/usage signal is populated anywhere. The warranted
fail-closed gate lives in `_dispatcher_cost`: `observe_run_cost(ps_json,
run_id)` is the cost SIGNAL (reads `total_usd_micros` from `fabro ps -a
--json`, surfacing a real value the moment fabro populates it),
`cost_gate_decision(unattended, observation)` is the fail-closed rule
(unattended drain + unobservable cost ⇒ refuse; hand-picked item ⇒ warn), and
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

from livespec_orchestrator_beads_fabro.commands._acp_hold_clear import (
    add_clear_acp_availability_hold_arguments,
    run_clear_acp_availability_hold_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    admit_and_select,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_emit import (
    emit_calibration,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential_command import (
    run_claude_cred_status,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_args import (
    add_dispatch_common,
    add_probe_arguments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    add_invoker_argument,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_probe import run_probe_command
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion_clear import (
    add_clear_provider_exhaustion_arguments,
    run_clear_provider_exhaustion_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged import (
    run_reconcile_merged_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_command import (
    run_reconcile_runs_command,
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
    "run_claude_cred_status",
    "run_clear_acp_availability_hold_command",
    "run_clear_provider_exhaustion_command",
    "run_codex_cred_refresh",
    "run_codex_cred_status",
    "run_id",
    "run_janitor_check",
    "run_ledger_check",
    "run_ledger_normalize",
    "run_probe_command",
    "run_reconcile_merged_command",
    "run_reconcile_runs_command",
    "run_spec_check",
    "warn_item_sizing",
]


_SUBCOMMAND_HANDLERS: dict[str, Callable[..., int]] = {
    "claude-cred-status": run_claude_cred_status,
    "clear-acp-availability-hold": run_clear_acp_availability_hold_command,
    "clear-provider-exhaustion": run_clear_provider_exhaustion_command,
    "codex-cred-refresh": run_codex_cred_refresh,
    "codex-cred-status": run_codex_cred_status,
    "dispatch": run_dispatch_command,
    "janitor-check": run_janitor_check,
    "ledger-check": run_ledger_check,
    "ledger-normalize": run_ledger_normalize,
    "probe": run_probe_command,
    "reconcile-merged": run_reconcile_merged_command,
    "reconcile-runs": run_reconcile_runs_command,
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
    _add_ledger_check(parser=subparsers.add_parser("ledger-check"))
    _add_ledger_normalize(parser=subparsers.add_parser("ledger-normalize"))
    _add_codex_cred_refresh(parser=subparsers.add_parser("codex-cred-refresh"))
    _add_cred_status(parser=subparsers.add_parser("codex-cred-status"))
    _add_cred_status(parser=subparsers.add_parser("claude-cred-status"))
    add_clear_provider_exhaustion_arguments(
        parser=subparsers.add_parser("clear-provider-exhaustion")
    )
    add_clear_acp_availability_hold_arguments(
        parser=subparsers.add_parser("clear-acp-availability-hold")
    )
    _add_spec_check(parser=subparsers.add_parser("spec-check"))
    _add_janitor_check(parser=subparsers.add_parser("janitor-check"))
    _add_reconcile_runs(parser=subparsers.add_parser("reconcile-runs"))
    _add_reconcile_merged(parser=subparsers.add_parser("reconcile-merged"))
    add_probe_arguments(parser=subparsers.add_parser("probe"))
    dispatch = subparsers.add_parser("dispatch")
    add_dispatch_common(parser=dispatch)
    _ = dispatch.add_argument("--item", dest="item", required=True)
    loop = subparsers.add_parser("loop")
    add_dispatch_common(parser=loop)
    _ = loop.add_argument("--budget", dest="budget", type=int, required=True)
    _ = loop.add_argument("--parallel", dest="parallel", type=int, default=1)
    _ = loop.add_argument("--dry-run", dest="dry_run", action="store_true")
    _ = loop.add_argument("--item", dest="items", action="append", default=None)
    return parser


def _add_ledger_check(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def _add_ledger_normalize(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    _ = parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    # `--gate` is the always-run pre-push mode: auto-heal-loud — it heals the
    # two safe transient remaps in place, prints each, and sets a fail-soft
    # exit-code contract (0 clean/healed / 1 residual drift / 2 could-not-check).
    # See `_dispatcher_ledger_gate.run_ledger_gate`.
    _ = parser.add_argument("--gate", dest="gate", action="store_true")


def _add_spec_check(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    _ = parser.add_argument("--spec-root", dest="spec_root", default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def _add_codex_cred_refresh(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    _ = parser.add_argument("--dry-run", dest="dry_run", action="store_true")


def _add_cred_status(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def _add_janitor_check(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--repo", dest="repo", default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def _add_reconcile_runs(*, parser: argparse.ArgumentParser) -> None:
    # `--factory` NARROWS the survey to one declared factory. Omitting it is
    # the correct default: reconciliation is an inventory question, and an
    # inventory taken of one factory says nothing about the others.
    _ = parser.add_argument("--repo", dest="repo", default=None)
    _ = parser.add_argument("--factory", dest="factory", default=None)
    _ = parser.add_argument("--fabro-bin", dest="fabro_bin", default=None)
    _ = parser.add_argument("--journal", dest="journal", default=None)
    _ = parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    add_invoker_argument(parser=parser)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def _add_reconcile_merged(*, parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--item", dest="item", required=True)
    _ = parser.add_argument("--janitor", dest="janitor", default=None)
    _ = parser.add_argument("--journal", dest="journal", default=None)
    add_invoker_argument(parser=parser)
    _ = parser.add_argument(
        "--force",
        dest="force",
        action="store_true",
        help=(
            "bypass only the live-dispatch heartbeat refusal after confirming the "
            "original dispatcher process is dead"
        ),
    )
    _ = parser.add_argument(
        "--regrade",
        dest="regrade",
        action="store_true",
        help=(
            "re-grade an already-merged rework:pending item against its current "
            "effective acceptance criteria instead of refusing it; proceeds only "
            "when the merged PR resolves and its merge commit is an ancestor of the "
            "default branch, and leaves the item untouched on any non-PASS verdict"
        ),
    )
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
