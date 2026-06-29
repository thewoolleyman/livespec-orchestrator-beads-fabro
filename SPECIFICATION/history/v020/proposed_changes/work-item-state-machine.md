---
topic: work-item-state-machine
author: wism-l1a-beads-fabro
created_at: 2026-06-29T14:08:02Z
spec_commitments:
  impl_followups:
    - id_hint: revendor-runtime-v050
      description: |
        Re-vendor livespec_runtime v0.5.0 into .claude-plugin/scripts/_vendor/livespec_runtime/ (source-only; brings work_items.{lifecycle,rank,_fractional_indexing} + the 7-state types) and bump .vendor.jsonc upstream_ref to v0.5.0 + .livespec.jsonc compat.pinned. Shrink commands/_cross_repo.py: relocate is_item_ready/ready_sort_key/the dep-blocking predicate to the runtime's lifecycle.py (already there post-L0); the orchestrator IMPORTS them and INJECTS its beads status-lookup callables (local_status_lookup/sibling_status_lookup) so there is no runtime->beads back-edge (decision 42); keep load_manifest/parse_entry orchestrator-local. Update types.py re-export to the new 7-state shape.
    - id_hint: beads-custom-status-encoding
      description: |
        store.py/_beads_client.py: register the 5 custom statuses at bootstrap (bd config set status.custom 'backlog,pending-approval,ready:active,active:wip,acceptance:wip'); make append_work_item a 2-step create->update for every initial state (bd create lands open, then bd update --status <state>); map livespec done<->beads closed in the adapter; persist rank in metadata.rank with the BOTTOM_SENTINEL fallback for legacy rank-less issues; map admission_policy/acceptance_policy/blocked_reason to labels; keep assignee native. Per decision 36/39.
    - id_hint: dispatcher-valves-wip-cap
      description: |
        Dispatcher (commands/dispatcher.py + _dispatcher_engine.py): add the admission valve (admission_policy=manual holds until approved into ready; auto admits; set assignee on admit), the per-repo WIP cap from .livespec.jsonc (dispatcher.wip_cap, default 5; count(active) < cap), and post-merge acceptance (complete = merge-on-green -> acceptance state; accept = post-ship confirm per acceptance_policy; reject = revert/fix-forward). Re-express the human-gated refusal as admission_policy=manual and the non-convergence bounce as bounce-to-backlog. Per decisions 7/9/10/22/26/33/34.
    - id_hint: lane-emission-and-rank-next
      description: |
        list_work_items.py: emit flat lane + lane_reason per item by calling the runtime's lane_of (consume, never re-derive); auto-emit the new WorkItem fields; track the new lane vocabulary in --filter=ready/blocked. next.py: rank ready items by rank then id (retire the priority/origin/captured_at heuristic); urgency no longer priority-derived. Per decisions 39/40.
    - id_hint: rebalance-ranks-command
      description: |
        New rebalance-ranks command (a deterministic, order-preserving bulk re-key using livespec_runtime.work_items.rank.n_keys_between): walk items in rank order, reassign evenly-spaced fresh keys -> N superseding/updated records. Add a legacy-seed entry path (seed by priority -> captured_at -> id) that L2's one-time backfill reuses. On-demand only; never auto-fires (decision 38 G-2).
    - id_hint: doctor-rank-invariants
      description: |
        doctor checks: every live (head) issue has a real non-sentinel rank (fail-soft: a stray sentinel-rank item sorts last and is NAMED, never crashes the listing); a rank-key-length WARNING threshold ('rank keys exceed N chars - run rebalance-ranks'); active => assignee set; stored blocked => blocked_reason in {needs-human, infra-external}. Per decisions 38/39.
    - id_hint: cut-l1a-release
      description: |
        GATE: cut a livespec-orchestrator-beads-fabro release (a feat: push triggers release-please) once the schema/dispatcher/lane/rank code lands. This release artifact is what the L2 migration and the console consume.
---

## Proposal: Work-item beads-issue mapping — 7-state status via 5 custom statuses + 2 built-in reuses, 2-step append, rank/policy field homes, priority dropped

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Rewrite the logical-field -> beads-home map in `## Work-item beads-issue mapping` for the deterministic lifecycle: `status` maps the 7 livespec states (backlog, pending-approval, ready, active, acceptance, blocked, done) to 5 custom statuses (backlog, pending-approval, ready:active, active:wip, acceptance:wip) + 2 built-in reuses (blocked name-matched; done->closed) per the verified beads v1.0.5 source; require per-tenant custom-status registration; make append_work_item a 2-step create+update because bd create forces open/deferred; move rank to metadata.rank with the shared bottom-sentinel for legacy rank-less issues; drop priority as a logical field; map admission_policy/acceptance_policy/blocked_reason to labels; keep assignee native with the active=>assignee invariant.

### Motivation

L1a orchestrator realization of the fleet-wide work-item-lifecycle epic (fleet anchor livespec-35s3zo; L1a epic bd-ib-vvrxcb). The beads realization is the only place backend terms appear (decision 2); the encoding is finalized in decisions 36/39 against the pinned beads v1.0.5 source.

### Proposed Changes

See plan/work-item-state-machine/research/01-spec-deltas.md Delta 1 for the exact mapping table and bullet text. status -> 5 custom statuses (backlog, pending-approval, ready:active, active:wip, acceptance:wip) + 2 built-in reuses (blocked name-matched; done->closed, the one adapter name-mapping); ready is the only active-category status so native bd ready surfaces the admission-eligible set. Bootstrap MUST register the 5 custom statuses via `bd config set status.custom`. append_work_item becomes a 2-step path (bd create lands open, then bd update --status <state>) for every initial state, even a plain file (backlog is custom). rank -> metadata.rank (a structured value in the metadata JSON column); a legacy issue whose metadata lacks rank reads the shared BOTTOM_SENTINEL the store adapter substitutes (keeping the domain rank: str strictly non-null). priority is removed as a logical field (decision 39; legacy native priority kept harmlessly, no longer read into the record). admission_policy -> label admission:<auto|manual>; acceptance_policy -> label acceptance:<value>; blocked_reason -> label blocked-reason:<value> (stored values {needs-human, infra-external} only; dependency is derived, never stored); absent label reads back None. assignee stays the beads native assignee field, REQUIRED once status==active. Restate the doctor-checkable invariants (active=>assignee; stored blocked=>reason; reaching ready requires transiting pending-approval; every live issue has a real non-sentinel rank). The load-bearing 2-step-append behavior is paired to a new scenarios.md scenario (authoring discipline (i)).

## Proposal: Dispatcher admission valve, per-repo WIP cap, and post-merge acceptance (new H2)

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a new H2 `## Dispatcher admission, WIP cap, and post-merge acceptance` documenting the two human-delegable valves and the per-repo WIP cap. The Dispatcher is the sole enforcer: it admits the highest-rank admission-eligible ready item when a slot frees (under a per-repo wip_cap from .livespec.jsonc, default 5), setting assignee on admit; admission_policy (auto|manual, default manual via inherit) replaces the host-only/human-gated text markers; acceptance is post-merge (complete = merge-on-green into the live acceptance state; accept = post-ship confirm per acceptance_policy; reject = revert/fix-forward). just check stays the hard pre-merge floor.

### Motivation

Decisions 7/9/10/22/26/33/34: two human-delegable valves bracket the WIP-limited autonomous middle; safe-by-default; per-repo WIP cap; acceptance verified post-merge in production (observability + reversibility), the correct reading of the Gas Town cautionary tale. The risk dial sits at admission + reversibility, not a pre-merge acceptance hold.

### Proposed Changes

See plan/work-item-state-machine/research/01-spec-deltas.md Delta 2 for the exact section text, plus the new scenarios in the Scenarios block. Admission valve (ready->active): approval == ready membership (decision 26); permission settled at the pending-approval->ready approve transition (admission_policy auto auto-approves once at groom; manual waits for a human approve); capacity = a free slot under count(active) < wip_cap; assignee resolvable. The Dispatcher pulls the highest-rank eligible ready item, sets assignee, transitions to active. Per-repo WIP cap from .livespec.jsonc dispatcher.wip_cap (default 5; decision 22). Post-merge acceptance: complete (active->acceptance) merges-on-green (keeps gh pr merge --rebase --auto); accept (acceptance->done) confirms post-ship per acceptance_policy (ai-only autonomous; human-only console; ai-then-human default parks in acceptance until a human confirms); reject from acceptance = revert/fix-forward (reject(rework)->active fix-forward; reject(re-groom)->backlog revert+re-decompose). The Machine-path exemption covers these dispositions of already-filed items; the Dispatcher creates no net-new work-items. New scenarios.md scenarios: WIP-capped highest-rank admission; manual-admission hold; complete-merges-on-green; accept-per-policy. heading-coverage co-edit adds the one new contracts.md H2 + the new scenario H2s (test: TODO).

## Proposal: Dispatcher grooming behavior reconciliation — admission_policy replaces human-gated; bounce-to-backlog replaces needs-regroom marker

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Re-express `### Dispatcher grooming behavior` in the new lifecycle vocabulary: the Dispatcher refuses to ADMIT an item whose effective admission_policy is manual until it is approved into ready (admission_policy is the first-class realization of the old human-gated marker); a non-converging slice bounces to the backlog state (decision 32 bounce / re-decomposition), surfaced (escalate-don't-drop), never infinite-retried. The compose-next clause stands (now ranks by rank). Update Scenario 10 (human-gated -> admission_policy==manual) and Scenario 11 (needs-regroom -> bounce-to-backlog) text accordingly.

### Motivation

The lifecycle redesign makes admission_policy a first-class field (decision 8/26) and folds needs-regroom into the backlog state (decision 32), so the existing prose markers must be reconciled to avoid spec/code drift.

### Proposed Changes

See plan/work-item-state-machine/research/01-spec-deltas.md Delta 3. Replace 'refuse to auto-dispatch a human-gated (spec-change) item' with 'refuse to ADMIT an item whose effective admission_policy is manual until it is explicitly approved into ready'. Replace 'mark the item needs-regroom and surface it' with 'bounce the item to the backlog state (re-decomposition) and surface it'. The compose-next clause is retained and now ranks by rank. Update the scenarios.md Scenario 10 + Scenario 11 prose to the new vocabulary; their bound integration tests are rewritten in the implement phase (the scenario text is the spec half; the test is code).

## Proposal: list-work-items emits flat lane + lane_reason; filters track the lane vocabulary

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

`#### list-work-items` --json output additionally carries two computed flat keys per item -- lane (one of the 7 rendered lanes) and lane_reason (needs-human/infra-external/dependency/null) -- plus the auto-emitted new WorkItem fields. lane/lane_reason are computed by the runtime's lane_of (consume-don't-recompute, decision 40); the console reads them directly and retires its bd ready re-derivation. --filter=ready becomes lane==ready; --filter=blocked becomes lane==blocked (stored blocked OR ready+open-dep).

### Motivation

Decision 40: lane_of is the single authority in the runtime; the orchestrator EMITS the lane and the console CONSUMES it (no Rust re-derivation). The emitted flat shape matches the existing flat asdict emitter + the Rust flat-field parser.

### Proposed Changes

See plan/work-item-state-machine/research/01-spec-deltas.md Delta 4. Add lane + lane_reason as computed flat keys to the list-work-items --json item shape, computed via livespec_runtime.work_items.lifecycle.lane_of. Update --filter=ready (lane==ready: stored ready AND deps clear) and --filter=blocked (lane==blocked: stored blocked OR stored ready with an open dependency). gap-tied/freeform/closed/all unchanged. New scenarios.md scenario: list-work-items emits lane/lane_reason (ready+open-dep -> blocked:dependency; stored blocked -> its stored reason; otherwise <status>/null).

## Proposal: next ranks by rank then id (priority retired)

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

`#### next` re-keys its ranking: identify ready items (lane==ready), order by rank (lexicographic ascending, the sole ordering authority) then id (deterministic tie-break), apply offset/limit. The old priority -> gap-tied -> oldest-captured_at heuristic is retired (decision 12). urgency is no longer priority-derived; ranked candidates emit urgency: medium (the rank order is the urgency signal). action/reason/work_item_ref and pagination unchanged.

### Motivation

Decision 39: rank is the sole ordering authority; priority is removed. next is the single ranking authority the Dispatcher composes, so its ranking must key on rank.

### Proposed Changes

See plan/work-item-state-machine/research/01-spec-deltas.md Delta 5. Ranking: (1) ready = lane==ready (stored ready, depends_on empty or all-closed); (2) order by rank then id; (3) offset/limit. Retire the priority/origin/captured_at scoring. urgency derivation: drop the P0->high/P1,P2->medium/P3,P4->low mapping (priority is gone); emit urgency: medium for ranked candidates. New scenarios.md scenario: next ranks ready items by rank.
