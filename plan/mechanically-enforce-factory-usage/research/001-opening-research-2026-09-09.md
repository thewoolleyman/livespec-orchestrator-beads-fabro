# mechanically-enforce-factory-usage — opening research

Captured 2026-09-09. Plan owner: `livespec-orchestrator-beads-fabro` (it owns
the factory and the plan logic). Predecessor: the archived `force-factory`
plan (`plan/archive/force-factory/findings.md`, epic `bd-ib-y2xro4`, closed
2026-07-15). This plan is that plan's **escalation arm** — a successor, not a
reopening (see "Relationship to force-factory").

Notation used below: `R<n>` = a requirement carrier this plan commits to;
`D<n>` = an explicit deferral (named so it is reconsidered somewhere, never
lost); `ladder A–D` = the enforcement ladder force-factory recorded for
escalation; `file:line` = evidence read from the live repositories by the
independent review of 2026-09-09.

## 1. Why this plan exists — the incident

On 2026-09-09 the session `k3s-on-gmktec-for-vps-usage` hand-cranked four
phases of a provisioning migration touching five repositories through its own
subagents writing into hand-made worktrees. Zero work-items were filed; the
factory sat idle the whole time (16 ready items in the `livespec-dev-tooling`
tenant, zero Fabro runs). The janitor gate never ran; the only safety net was
the pre-push hooks; the record was comments on one item in another tenant;
lifecycle never closed (an item read `ready` after its pull request merged).

Root cause: the session read "work item X" as "be the worker." The Phase-0
decomposition it produced was a correct work breakdown and was routed to
subagent prompts instead of ledger items. Each step was locally reasonable and
the aggregate bypassed every property the factory exists to provide.

Two further transcripts from the same window sharpen the boundary:

- A `/livespec:revise` spec-op run locally in a `spec/*` worktree — correct,
  because the factory has no spec-op dispatch path and spec work is
  interactive, discussion-bearing, and light on compute.
- Host work on `poweredge-xubuntu` (ssh + sudo, `factory-safety:
  mutates-host-machinery`) done locally — correct, factory-ineligible. But two
  defects filed with raw `bd create` stranded in backlog and never reached the
  factory — an intake failure, distinct from the hand-crank failure.

Maintainer testimony (2026-09-09): this recurs repeatedly, and prose guidance
in `AGENTS.md`/`CLAUDE.md` fails at exactly the read-and-conclude step. A
promise is worth nothing here; the deliverable is mechanism.

## 2. Relationship to force-factory — what it did, what happened since

`force-factory` (2026-07-15) made a deliberate "right-sized, prose-first"
bet after a Codex session faithfully executed a defective handoff that
*defined* the in-session `implement` route as "the factory path." Its five
children all landed (pull requests #635/#637 in
`livespec-orchestrator-beads-fabro`, #403/#406 in `livespec-dev-tooling`): a
handoff fix, dispatch-first `implement` prose, a `plan`-prose routing gate, a
handoff-phrasing lint, and a **report-only factory-bypass audit counter** as
the evidence instrument. Commit-time enforcement was explicitly kept out of
scope, and an escalation ladder A→D was recorded "so escalation never
re-derives it," gated on: *if the counter shows violations after the prose
fixes land, escalate.*

Two things happened since:

1. **The bet did not fully pay off.** The drift recurred (section 1). This is
   the contingency the epic itself planned for, not a failure of the epic.
2. **The evidence instrument regressed.** The counter's product classifier is
   a hardcoded orchestrator-only tuple
   (`commands/factory_bypass_audit.py:63-67`) whose comment cites
   `red_green_replay._IMPL_PREFIXES`, a symbol later removed when
   Red-Green-Replay moved to per-repo derivation
   (`red_green_replay.py:131-141`). It therefore **cannot see `livespec` or
   `livespec-dev-tooling`** — the repositories where the drift happens.
   Measured 2026-09-09 by the independent reviewer: 1 bypass in 60 merged
   orchestrator pull requests (PR #2331), in the only repository it can see.
   The tripwire that was supposed to trigger escalation went blind, and
   nothing noticed. That is a genuine regression and a standalone bug.

**Decision — successor, not reopen.** Archiving is terminal by design (the
`plan` operation has no reopen step); the five children genuinely completed;
the ladder was explicitly deferred scope, i.e. new work. A forward-pointer
comment on `bd-ib-y2xro4` (R8) closes the loop so anyone landing on the
archived record finds this continuation.

**Evidence-gate disposition.** The counter cannot currently supply the
quantitative signal the gate asks for. The escalation evidence on record is
the maintainer's direct observation of repeated recurrence plus the documented
2026-09-09 incidents. The counter is fixed as a first-wave child (R3) so every
future escalation decision is measured rather than asserted. The maintainer
may veto this disposition at the scope event.

## 3. The design that was REJECTED — recorded so it is never re-derived

The 2026-09-09 design dialogue considered and rejected, in order:

- Prose-only layers (a `next_action` verb, a plan precondition): they depend on
  the read-and-conclude step that failed.
- A `PreToolUse` hook on `Agent` dispatch: a brief is prose, so the hook either
  parses intent (the failed step again) or blocks coarsely; it also misses the
  inline hand-crank.
- A write-time `PreToolUse` hook on Edit/Write: per-edit friction and a
  stateful, forgeable "am I claimed" marker, to save only the sliver of work
  between first edit and first commit.
- An auto-salvage valve ("push the branch, hand it to the factory"): a
  sabotage valve — it normalizes hand-cranking-first, imports session state
  into the clean-room, and inverts specification-before-implementation.
- **A commit-side check that reads the ledger** to verify the cited item is
  claimed, factory-ineligible, or dispatch-stamped. This was the design about
  to be drafted. An independent read-only Fable adversarial review
  (2026-09-09) returned **BLOCKERS**:

  1. **Circular dependency.** `livespec-dev-tooling` is the upstream
     foundational library; the orchestrator is downstream. The dispatch-stamp
     keys exist only as private constants in the orchestrator
     (`_store_dispatch_factory.py:35-36`), appear in no contract, and the
     sibling orchestrator `livespec-orchestrator-git-jsonl` carries no stamp
     at all — a ledger-reading upstream check would refuse every product
     commit on that backend. Banned by `livespec/.ai/no-circular-dependency.md`.
  2. **Contradicts force-factory's recorded design rules**: the hook stays
     hermetic (env + staged tree only, never ledger/network at commit time);
     local markers are spoofable-but-audited while the App-identity check is
     the hard wall; rollout is warn→fail via a host-wide mode file.
  3. **Eligibility grounding was false.** `set-admission` writes
     `admission:auto|manual` (approval), not host-only. Host-only is the
     orthogonal `factory_safety` axis (label `factory-safety:<needs-host-
     secrets|mutates-host-machinery|needs-privileged-host>`, orchestrator
     `SPECIFICATION/contracts.md:5117-5131`), an intrinsic capture-time
     classification that never clears. **No `set-factory-safety` valve
     exists**; the only current path is a raw `bd label add` — the very
     hand-edit shape the design claimed was banned. `driver-dispatch:<id>`
     (`contracts.md:2567-2575`), the journaled door for host-only work, is
     specified but unrealized.
  4. **Low-friction bypasses remain.** The dispatch stamp is never cleared
     (`_dispatcher_run_stamp.py:127-133`; overwrite-only,
     `_store_dispatch_factory.py:139-141`), so a failed / needs-human item —
     exactly the one a session is told to take over — passes. "Flag host-only
     with a reason" resolves to a hand label. A session can dispatch and
     hand-crank in parallel.
  5. **A commit-time ledger read fails open or closed, both unacceptable.**
     Every existing dev-tooling ledger check is armed-only behind a
     `LIVESPEC_RUN_*` lever and `BEADS_DOLT_PASSWORD` because hook / CI /
     sandbox contexts lack tenant credentials. The stamp write itself fails
     silently on ledger errors or a missing `.livespec.jsonc`
     (`_dispatcher_run_stamp.py:127-138`).
  6. **"Hooks move to a separate gate machine" was unanchored**: the nearest
     records defer a gate host and concern pre-push `just check`, not
     commit-msg hooks, which are intrinsically local.
  7. **The intake-hygiene premise was wrong**: `intake:triaged` is an
     observability marker, not an admission gate — dispatch reads the status
     (`work_item_status_vocabulary.py:37-41`). A raw `bd create` strands
     because it lands at beads status `open`, outside the runtime's status
     vocabulary. Loudness already exists twice (that armed check; the
     orchestrator's `untriaged_backlog_items` needs-attention lane).
  8. Minor: the scope signal's exact semantics (section 4A); the
     `plan_anchor_declared.py` sibling is retired — anchor to
     `plan_epic_parity.py` / `red_green_replay.py`; the emergency lever named
     no detection mechanism and the sandbox is itself unattended; several
     status-descriptive claims would expire at ratification.

  The reviewer varied the instrument — it ran the bypass counter and read the
  archived force-factory record, neither of which the design summary
  mentioned — and that is where the blocking evidence came from.

## 4. The corrected design — follows the force-factory ladder

Three parts, split by dependency direction so no upstream repository reads
into a downstream one.

### 4A. `livespec-dev-tooling` (upstream, HERMETIC) — ladder steps A + B

- **Provenance marker.** The Dispatcher injects a declared marker into the
  sandbox: `git config livespec.factoryRunId <run-id>`, set in the sandbox
  prepare step beside the existing `livespec.sandboxExempt` marker
  (`.claude-plugin/.fabro/workflows/implement-work-item/workflow.toml:21,295`).
  Same declared-marker pattern, same direction: upstream defines and reads the
  contract, downstream writes it (`install_commit_refuse_hooks.py:130-138,
  164-168`). Cycle-free.
- **Commit-hook factory gate.** A new refuse branch in the canonical
  commit-refuse hook body, AND-ed in front of the untouched Red-Green-Replay
  logic (the gate decides *who may commit here*; Red-Green-Replay decides *is
  it test-driven*; neither touches the other). Staged product `.py` — the same
  scope Red-Green-Replay uses: `.py`, under a declared prefix from
  `config.derive_source_prefixes` (`config.py:1491-1521`), not vendored, not a
  deletion (`red_green_replay.py:207-213, 280, 320-326`) — REQUIRES the marker,
  and the hook writes a `Factory-Run-Id:` trailer that travels with the
  commit. Absent the marker: refuse, UNLESS a `Factory-Override: <reason>`
  trailer with a non-empty reason is present, which is telemetry-recorded as
  an explicit, audited exception. **No ledger, no network** — env and staged
  tree only.
- **Rollout warn→fail via a host-wide mode file** — the bd-guard playbook:
  hermetic hook tests; a warn-phase OTLP census of every context that would
  have been blocked; the sandbox runs fail-mode first, proven by a throwaway
  proof dispatch.
- **Scope consequences, stated so they are commitments.** Spec-only commits
  (spec prose, `tests/heading-coverage.json`), `.github/workflows/`, shell,
  and config carry no product `.py` and are out of scope by construction —
  spec-ops stay local with zero new friction, and workflow edits (which the
  factory is forbidden to land) are untouched. A commit mixing product `.py`
  with spec is a product commit. Note the honest edge: these paths are
  *invisible* to the gate rather than *exempted*, so a `mutates-host-
  machinery` item that is mostly shell plus one `.py` is gated on the `.py`
  alone — its legitimate route is the `Factory-Override` trailer with its
  reason, or the `driver-dispatch` door (4B).
- **Refusal message** names why (staged product `.py`, no factory provenance)
  and the routes: dispatch via `drive impl:<id>` / the Dispatcher, or record
  the exception with `Factory-Override: <reason>`.

### 4B. `livespec-orchestrator-beads-fabro` (downstream, LEDGER-BINDING)

- **Fix the bypass counter (the evidence instrument).** Derive product
  prefixes per repository via `config.derive_source_prefixes`, honor `--repo`
  across the fleet, and treat a `Factory-Override`-trailered commit as a
  recorded exception rather than a bypass. Standalone bug regardless of the
  rest of this plan.
- **Realize `driver-dispatch:<id>`** (`contracts.md:2567-2575`): the journaled
  door for host-only work — actor + driver-session reference, `ready` →
  `active` — so factory-ineligible work has a *recorded* entry rather than a
  bare label.
- **Add a `set-factory-safety:<id>:<reason>` valve** with a mandatory
  rationale. Default is factory-eligible; opting an item out is possible only
  through this valve, with the reason on the record. This is the real
  training friction. A first-class operator verb requires specification
  coverage (`contracts.md:2562-2565`).
- **Ladder C — the non-spoofable wall.** A server-side required status check
  keyed on the factory GitHub App's pull-request authorship, with
  release-please / revert exemptions and a maintainer override label. Local
  markers are spoofable-but-audited; this is what makes the whole ladder
  hold.

### 4C. Drivers — `livespec-driver-claude` first

- A Driver-side `PreToolUse` guard on raw `bd create` that routes the session
  to `capture-work-item` (the shape already ships as
  `.claude-plugin/hooks/no_shadow_ledger.py`). `capture-work-item` runs the
  intake Definition-of-Ready gate (`intake_dor.py:145-196`) and routes the
  status, which is what makes an item dispatchable. Cite the two existing
  loud surfaces rather than adding a third.

## 5. Standalone defects exposed (fileable regardless of enforcement)

1. The factory-bypass audit counter is blind to the fleet (regression; 4B).
2. `driver-dispatch:<id>` is specified and unrealized (4B).
3. No `set-factory-safety` valve; the only path today is a hand label (4B).
4. An empty `source_trees` declaration silently empties the Red-Green-Replay
   universe and the gate goes quiet — `config.py:1500-1509` records three
   fleet repositories doing exactly that. Owner: `livespec-dev-tooling`.
5. The dispatch stamp write fails silently on ledger error or missing
   `.livespec.jsonc` (`_dispatcher_run_stamp.py:127-138`). Owner: orchestrator.

## 6. Requirement carriers (input to the scope event)

- **R1** Hermetic provenance marker + `Factory-Run-Id:` trailer + AND-ed
  refuse branch with `Factory-Override:` exception — `livespec-dev-tooling`
  (ladder A+B).
- **R2** Warn→fail mode-file rollout with warn-phase census and sandbox
  fail-mode proof — `livespec-dev-tooling`.
- **R3** Fleet-aware, override-aware bypass counter — orchestrator (evidence
  instrument).
- **R4** `set-factory-safety` valve with mandatory rationale + specification
  coverage — orchestrator.
- **R5** `driver-dispatch:<id>` realization — orchestrator.
- **R6** Ladder C server-side factory-App authorship check — orchestrator +
  repository settings.
- **R7** Driver `bd create` guard routing to `capture-work-item` —
  `livespec-driver-claude`.
- **R8** Forward-pointer comment on `bd-ib-y2xro4` naming this plan.

## 7. Explicit deferrals

- **D1** Ladder D (bd-guard claim gate on `bd update --status active` outside
  a factory context). Reconsider after R1–R3 land and the counter has
  measured a warn-phase window.
- **D2** Codex and pi Driver guards mirroring R7. After R7 proves the shape.
- **D3** Promotion of the provenance-marker pattern into livespec core
  `contracts.md` as a family contract. Deferred per force-factory until the
  pattern proves out here.
- **D4** Binding a commit's diff to its item's declared path scope (to defeat
  deliberate misattribution). Only if the audited override trail shows
  misattribution is real; a drift-guard does not chase an adversary.

## 8. Sequencing recommendation

- **Wave 1 (no-regret, parallel):** R3 counter fix; R8 forward-pointer;
  standalone defects 4 and 5.
- **Wave 2 (parallel across repositories):** R1+R2 in warn mode ∥ R4+R5 ∥ R7.
- **Wave 3:** R6; then flip R1 to fail once the warn-phase census is clean.

Every implementation child is dispatched through the factory — `drive
--action impl:<id>` or a Dispatcher drain — never in-session. This plan is
subject to its own discipline; that is the demonstration.

## 9. Where things live

- This plan, the orchestrator children (R3–R6, defect 5), and R8: the
  `livespec-orchestrator-beads-fabro` tenant.
- R1, R2, defect 4: the `livespec-dev-tooling` tenant, with prose
  cross-references to this epic — never a typed cross-tenant `depends_on`
  (the force-factory convention).
- R7: the `livespec-driver-claude` tenant.
