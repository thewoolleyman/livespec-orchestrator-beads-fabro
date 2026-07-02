# L1a code slices — the `groom` cut (children of `bd-ib-vvrxcb`)

The code-slice breakdown for the L1a implementation. The `groom` gate
cuts these into ready, dependency-layered children of epic
`bd-ib-vvrxcb`, each carrying its `spec_commitment_hint =` the matching
`id_hint` from `02-propose-change-findings.json`
(`spec_commitments.impl_followups[]`), pairing it back to the ratified
propose-change.

All slices target the **`livespec-orchestrator-beads-fabro`** repo. All
are `factory` (autonomously dispatchable). None is `is_spec_change` (the
spec lands via `revise`). `depends_on` below uses draft-local **titles**
resolved to minted ids at file time. Children are filed under the
**current** pre-migration schema (status=open, priority); the live tenant
migration is L2.

## Dependency layering

```
layer 0:  S1 (revendor) ── S2 (custom-status encoding)      ← S2 rides S1 (same runtime adoption)
layer 1:  S3 (dispatcher valves)  S4 (lane+rank)            ← depend on S1+S2
layer 2:  S5 (rebalance-ranks)    S6 (doctor invariants)    ← depend on S1+S2 (+S4 for rank surface)
layer 3:  S7 (cut release)                                  ← depends on S1-S6 (EXIT GATE)
```

**Coupling note (S1+S2).** Re-vendoring v0.5.0 changes the shared
`WorkItem` (7-state status; `+rank: str` required; `−priority`), which
the orchestrator re-exports and every store read/write + construction
site uses. So the package cannot be `just check`-green on the new runtime
UNTIL the store adapter is adapted (S2's rank↔metadata.rank, 2-step
append, done↔closed, custom-status registration) AND every
`WorkItem(...)` construction site supplies `rank`. S1 and S2 therefore
land as a **coordinated pair** (one PR, or S2 immediately after S1 on the
same branch) so master stays green; they are filed as two children only
to honor the 1:1 `spec_commitment_hint` ↔ `id_hint` mapping.

## The slices (CandidateSlice-shaped)

### S1 — `revendor-runtime-v050`  ·  layer 0  ·  deps: none (L0 release satisfied)
- **title:** `L1a/S1: re-vendor livespec_runtime v0.5.0 + shrink _cross_repo.py (DI)`
- **spec_commitment_hint:** `revendor-runtime-v050`
- **scope:** Re-vendor the v0.5.0 source-only `livespec_runtime` tree into
  `.claude-plugin/scripts/_vendor/livespec_runtime/` (adds
  `work_items/{lifecycle.py,rank.py,_fractional_indexing.py}` + the
  7-state `types.py`); bump `.vendor.jsonc` `upstream_ref` → `v0.5.0` +
  `vendored_at`, and `.livespec.jsonc` `compat.pinned`. Add the verbatim
  `_fractional_indexing.py` to the ruff/pyright/coverage exclusions
  (mirror L0's S1 exclusion pattern) + a `NOTICES` ride-along if not
  inherited. Shrink `commands/_cross_repo.py`: stop defining
  `is_item_ready`/`ready_sort_key`/the dep-blocking predicate locally;
  IMPORT them from `livespec_runtime.work_items.lifecycle` and INJECT the
  beads status-lookup callables (`local_status_lookup` /
  `sibling_status_lookup`) so there is no `runtime → beads` back-edge
  (decision 42); keep `load_manifest`/`parse_entry` orchestrator-local.
  Update `types.py`'s re-export to the new 7-state shape.
- **acceptance:** `livespec_runtime.work_items.{lifecycle,rank}`
  importable from the vendored tree; `_cross_repo.py` imports the lane
  authority and injects lookups (no local re-derivation); `just check`
  green (paired with S2 for the construction-site updates).

### S2 — `beads-custom-status-encoding`  ·  layer 0  ·  deps: S1
- **title:** `L1a/S2: beads custom-status encoding + 2-step append + done<->closed + rank/policy homes`
- **spec_commitment_hint:** `beads-custom-status-encoding`
- **deps (titles):** S1.
- **scope:** `store.py`/`_beads_client.py`: register the 5 custom
  statuses at bootstrap (`bd config set status.custom
  "backlog,pending-approval,ready:active,active:wip,acceptance:wip"`);
  make `append_work_item` a 2-step `create`→`update --status <state>` for
  every initial state (even `file`/`backlog`); map livespec `done` ↔
  beads `closed` in the adapter (the one name-mapping); persist `rank` in
  `metadata.rank` and read it back, substituting
  `livespec_runtime.work_items.rank.BOTTOM_SENTINEL` for a legacy issue
  whose metadata lacks `rank`; map `admission_policy`/`acceptance_policy`/
  `blocked_reason` to `admission:`/`acceptance:`/`blocked-reason:` labels
  (read absent label → `None`); keep `assignee` native. Update every
  `WorkItem(...)` construction site (capture-work-item, plan, groom, the
  read path) to supply `rank`.
- **acceptance:** round-trips a 7-state item through the
  `FakeBeadsClient` + (live tier) the real tenant; the 2-step append
  lands a custom status; `done`→`closed` closes in place; a legacy
  rank-less record reads `BOTTOM_SENTINEL`; matches ratified
  `## Work-item beads-issue mapping`; `just check` green.

### S3 — `dispatcher-valves-wip-cap`  ·  layer 1  ·  deps: S1, S2
- **title:** `L1a/S3: Dispatcher admission valve + per-repo WIP cap + post-merge acceptance`
- **spec_commitment_hint:** `dispatcher-valves-wip-cap`
- **deps (titles):** S1, S2.
- **scope:** `commands/dispatcher.py` + `_dispatcher_engine.py`: admission
  valve (admit the highest-`rank` admission-eligible `ready` item when a
  slot frees; `admission_policy=manual` holds until approved into
  `ready`; `auto` admits; set `assignee` on `admit`); per-repo WIP cap
  from `.livespec.jsonc` `dispatcher.wip_cap` (default 5;
  `count(active) < cap`); post-merge acceptance (`complete` =
  merge-on-green → `acceptance`; `accept` = post-ship confirm per
  `acceptance_policy`; `reject` = revert/fix-forward). Re-express the
  human-gated refusal as `admission_policy=manual` and the
  non-convergence bounce as bounce-to-`backlog`. Update the bound
  integration tests for Scenario 10/11's new vocabulary.
- **acceptance:** the new scenarios (WIP-capped highest-rank admission;
  manual-admission hold; complete-merges-on-green; accept-per-policy)
  pass against the `FakeBeadsClient`; matches ratified `## Dispatcher
  admission, WIP cap, and post-merge acceptance`; `just check` green.

### S4 — `lane-emission-and-rank-next`  ·  layer 1  ·  deps: S1, S2
- **title:** `L1a/S4: list-work-items lane/lane_reason emission + next rank order`
- **spec_commitment_hint:** `lane-emission-and-rank-next`
- **deps (titles):** S1, S2.
- **scope:** `commands/list_work_items.py`: emit flat `lane` +
  `lane_reason` per item via `livespec_runtime.work_items.lifecycle.lane_of`
  (consume, never re-derive); auto-emit the new fields; track the new
  lane vocabulary in `--filter=ready`/`blocked`. `commands/next.py`: rank
  ready items by `rank` then `id` (retire the priority/origin/captured_at
  heuristic); `urgency` → `medium` for ranked candidates.
- **acceptance:** the lane-emission + next-ranks-by-rank scenarios pass;
  matches ratified `#### list-work-items` / `#### next`; `just check`
  green.

### S5 — `rebalance-ranks-command`  ·  layer 2  ·  deps: S1, S2, S4
- **title:** `L1a/S5: rebalance-ranks command (+ legacy-seed backfill path)`
- **spec_commitment_hint:** `rebalance-ranks-command`
- **deps (titles):** S1, S2, S4.
- **scope:** New `rebalance-ranks` command (a deterministic,
  order-preserving bulk re-key via
  `livespec_runtime.work_items.rank.n_keys_between`): walk items in
  `rank` order, reassign evenly-spaced fresh keys → N updated records.
  Add a **legacy-seed entry path** (seed order = `priority → captured_at
  → id`) that L2's one-time backfill reuses. On-demand only; never
  auto-fires.
- **acceptance:** `rebalance-ranks` preserves order and re-keys; the
  legacy-seed path produces evenly-spaced keys from the pre-migration
  order; `just check` green.

### S6 — `doctor-rank-invariants`  ·  layer 2  ·  deps: S1, S2
- **title:** `L1a/S6: doctor rank/assignee/blocked-reason invariants + rank-key-length warning`
- **spec_commitment_hint:** `doctor-rank-invariants`
- **deps (titles):** S1, S2.
- **scope:** doctor checks: every live (head) issue has a real
  non-sentinel `rank` (fail-soft — a stray sentinel-rank item is NAMED,
  never crashes the listing); a rank-key-length WARNING threshold; `active
  ⟹ assignee`; stored `blocked ⟹ blocked_reason ∈ {needs-human,
  infra-external}`.
- **acceptance:** doctor fails/warns per invariant on seeded violations;
  `just check` green.

### S7 — `cut-l1a-release`  ·  layer 3  ·  deps: S1-S6  (EXIT GATE)
- **title:** `L1a/S7: cut the livespec-orchestrator-beads-fabro release (the L1a exit gate)`
- **spec_commitment_hint:** `cut-l1a-release`
- **deps (titles):** S1-S6.
- **scope:** The product `.py` of S1-S6 lands under `feat:`-subject
  red-green-replay commits, so release-please opens a release PR. Merge
  it, cut the tag, bump in-repo self-refs as release-please dictates.
- **acceptance:** release-please PR merged; new
  `livespec-orchestrator-beads-fabro` tag; the new contract surface
  (custom statuses, valves, lane emission, rank) shipped. **This release
  is what the L2 migration + the console consume.**

## Filing mechanism (per the L0 precedent — Option A)

The native `groom` `file_approved_slices` hardcodes
`spec_commitment_hint=None`, so file each child via the
`capture-work-item` `append_work_item` path with `spec_commitment_hint`
set explicitly, then wire the beads `parent-child` edge to `bd-ib-vvrxcb`
and the `depends_on` layering (the orchestrator's `_beads_client` exposes
`add_dependency`). Children are filed under the CURRENT pre-migration
schema; the `spec_commitment_hint` field exists in that schema.

## Red-Green-Replay discipline (non-negotiable)

Every product-`.py` slice lands via the repo's red-green-replay ritual
(Red: one staged test file failing on a genuine assertion; Green amend:
impl + remaining tests + ride-along docs; preserve the `TDD-Red-*`
trailer block via `--amend --no-edit`). Worktree → PR → rebase-merge;
`mise exec -- git`; never `--no-verify`; halt + report on any hook
failure. Co-edit `tests/heading-coverage.json` for any `## `-heading
change.
