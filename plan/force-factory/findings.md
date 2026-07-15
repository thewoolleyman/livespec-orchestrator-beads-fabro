# force-factory — findings

Captured 2026-07-15. Maintainer decisions recorded inline.

## The incident (2026-07-15)

An OpenAI Codex session (gpt-5.5, YOLO permissions) in
`livespec-dev-tooling` was handed `plan/shell-logic-hardening/handoff.md`
as a bare prompt. It read the handoff, loaded the orchestrator plugin's
`plan` / `implement` / `groom` prose unprompted, then implemented
`livespec-dev-tooling-9j8.1` manually in-session: dedicated worktree,
Red→Green through the hooks, full `just check-scoped` green. Nothing
merged — it held before the PR step when the maintainer intervened.

Root cause was NOT agent disobedience. The handoff's "Next action"
section literally defined "the normal factory path" as the in-session
`implement` operation run in its own worktree — manual implementation.
The agent followed defective instructions with high fidelity (it
honored the worktree root, the Red-Green-Replay ritual, `mise exec`,
and never reached for `--no-verify`). Every surface it consulted either
endorsed the manual route or was ambiguous about what "factory path"
means.

## The three distinct failures

1. **Authoring** — the handoff names the in-session `implement` route
   as "the factory path".
2. **Sanctioned-surface ambiguity** — the `implement` prose is an
   unconditional in-session Red→Green driver; nothing states when
   dispatch through the factory is mandatory.
3. **No mechanical backstop** — nothing at worktree/commit/push/PR time
   distinguishes factory work from manual work, so nothing can refuse.

## Maintainer decision (2026-07-15): right-sized, prose-first

The observed failure class is *faithful execution of wrong
instructions*, not instruction-defiance — so instruction fixes address
the dominant class. The violation cost is low (duplicated effort in a
disposable worktree; quality is still gated by Red-Green-Replay,
`just check`, and PR review regardless of who implements). A planned
operator-console switch will further shrink the raw-session entry
point. Decision: fix the instruction layer plus two cheap mechanical
pieces; defer heavyweight enforcement unless evidence shows prose was
insufficient.

In scope (the epic's children):

1. **Fix the defective handoff** (`livespec-dev-tooling`
   `plan/shell-logic-hardening/handoff.md`): the next action names the
   dispatch route; in-session implement is de-listed as "factory path".
2. **`implement` prose dispatch-first** (this repo,
   `.claude-plugin/prose/implement.md`): new Step 0 — factory-eligible
   items route to the `drive` operation / Dispatcher drain and STOP;
   in-session Red→Green becomes the explicit exception path (factory
   outage, factory-ineligible item, explicit maintainer direction),
   with the taken exception recorded in the closure audit.
3. **`plan` prose handoff gate** (this repo,
   `.claude-plugin/prose/plan.md`): the Step 4 self-sufficiency gate
   gains a fourth check — dispatch routing. A handoff whose next action
   is ledger-backed implementation must name the dispatch route and
   must not direct the reader to in-session implement; "factory path"
   refers exclusively to dispatch through the Dispatcher/`drive`.
4. **Handoff dispatch-routing lint** (shared `livespec_dev_tooling`
   package): a mechanical check refusing in-session-implement phrasing
   as the next action in active `plan/*/handoff.md` files. Handoff
   authoring is the recurring surface where the defect regenerates; the
   lint pins it.
5. **Factory-bypass audit counter** (this repo, attention surface):
   report-only — surface merged product-code PRs not authored by the
   factory's GitHub App identity. An empirical violation counter to
   decide whether the prose fixes sufficed. Network-using, so it lives
   on the on-demand attention surface, never inside `just check`.

## Why this cannot break the factory worker

The Fabro workflow's implement stage consumes its own bespoke prompt
(`.claude-plugin/.fabro/workflows/implement-work-item/prompts/implement.md`),
NOT the plugin's `implement` prose — different artifacts, different
consumers. The sandbox runs the bootstrap-equivalent hooks with the
declared `git config livespec.sandboxExempt true` marker
(`workflow.toml`), so the Red-Green-Replay gates run there unchanged.
Nothing in scope adds commit-time enforcement, so no in-sandbox path
can newly fail.

## Why legitimate in-session work keeps working

Nothing in scope blocks at commit time. The prose exception path stays
open (factory outage / factory-ineligible item / maintainer-directed,
reason recorded); the lint polices handoff *phrasing* only; the audit
counter only reports.

## The deferred enforcement ladder (recorded so escalation never re-derives it)

If the audit counter shows violations after the prose fixes land,
escalate in this order (each layer designed 2026-07-15, session
"force-factory"):

- **A. Dispatcher provenance stamp** — a dispatch-injected marker
  (`livespec.factoryRunId` git config or sandbox env) plus a
  `Factory-Run-Id:` commit trailer, following the existing
  `livespec.sandboxExempt` declared-marker pattern.
- **B. Commit-hook factory gate** — a new refuse branch in the
  canonical `livespec_dev_tooling` hook body, AND-ed in front of the
  untouched Red-Green-Replay logic: staged product-`.py` changes
  require the provenance marker or an explicit recorded override
  (`Factory-Override:` trailer + telemetry). Rolls out warn→fail via a
  host-wide mode file — the bd-guard playbook (hermetic hook tests; a
  warn-phase OTLP census of every context that would have been blocked;
  the sandbox runs fail-mode first, proven by a throwaway proof
  dispatch).
- **C. Server-side PR gate** — a required status check keyed on the
  factory GitHub App's PR authorship (non-spoofable by any local
  agent), with release-please/revert exemptions and a maintainer
  override label.
- **D. bd-guard claim gate** — `bd update --status active` outside a
  factory context warns/fails (extends the existing bd-guard mode-file
  machinery).

Key design rules if escalated: the gate and Red-Green-Replay stay
orthogonal AND-ed conditions (the gate decides *who may commit here*,
Red-Green-Replay decides *is it test-driven*, neither touches the
other); the hook stays hermetic (env + staged tree only, never
ledger/network at commit time); local markers are spoofable-but-audited
while the App-identity check is the hard wall.

## Where things live

- The plan thread, `implement`/`plan` prose, the audit counter, the
  Dispatcher: **livespec-orchestrator-beads-fabro** (owns the plan
  logic and the factory).
- The handoff fix and the handoff lint: **livespec-dev-tooling** (the
  defective artifact; the fleet check/hook distribution point).
- Family-contract promotion (livespec core `contracts.md`) deliberately
  deferred until the pattern proves out here.

Cross-tenant tracking: children in the dev-tooling repo are filed in
the `livespec-dev-tooling` tenant with prose cross-references to this
thread's epic (never a typed cross-tenant `depends_on`).
