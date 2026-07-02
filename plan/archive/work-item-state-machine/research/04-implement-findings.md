# L1a implement findings — the concrete resume guide (S1-S7)

Spec is RATIFIED (v020, PR #202) and the epic is GROOMED into 7 ready
children of `bd-ib-vvrxcb` (S1-S7; see `03-code-slices.md` + the ledger).
This note captures the CONCRETE implementation findings from scoping the
re-vendor + adapter migration, so the implement phase is mechanical to
resume. **All findings below were verified against the v0.5.0 source +
the live test suite.**

## The vendored v0.5.0 runtime API (what the orchestrator consumes)

`livespec_runtime.work_items.types.WorkItem` (v0.5.0, 20 fields, frozen/
slotted/kw_only) — the orchestrator re-exports it via
`livespec_orchestrator_beads_fabro.types`. Field order: `id, type,
status, title, description, origin, gap_id, rank, assignee, depends_on,
captured_at, resolution, reason, audit, superseded_by` (15 required) +
`spec_commitment_hint, supersedes, admission_policy, acceptance_policy,
blocked_reason` (5 optional, `= None`). **`priority: int` is GONE;
`rank: str` is required.** `WorkItemStatus = Literal["backlog",
"pending-approval","ready","active","acceptance","blocked","done"]`. New
aliases: `AdmissionPolicy`, `AcceptancePolicy`, `StoredBlockedReason`.

`livespec_runtime.work_items.rank` — `key_between(*, a, b) -> str`,
`n_keys_between(*, a, b, n) -> list[str]`, `BOTTOM_SENTINEL = "~"` (sorts
after every base-62 key). The verbatim CC0 `_fractional_indexing.py`
backs it.

`livespec_runtime.work_items.lifecycle` —
`lane_of(*, item, index, manifest) -> Lane`,
`is_item_ready(*, item, index, manifest) -> bool` (= `lane_of(...).name
== "ready"`), `ready_sort_key(item) -> (rank, id)`, plus `Lane`/`LaneName`
/`BlockedReason`. **Critical:** these resolve LOCAL deps via the in-memory
`index` (a dep is CLEARED iff the target item's status is `"done"`) and
resolve SIBLING (cross-repo) work-item deps to `UNKNOWN` (non-blocking) —
no `runtime → beads` back-edge (decision 42; the lifecycle.py docstring
states "the orchestrator keeps its own beads-backed sibling reading").
This repo's `.livespec.jsonc` has NO `cross_repo_targets` block, so
sibling resolution is already a no-op here — adopting the runtime's
sibling-UNKNOWN behavior changes nothing observable for this tenant.

## Re-vendor mechanics (S1 — `bd-ib-ojlmr6`)

Source-only copy of the v0.5.0 `livespec_runtime/` package over
`.claude-plugin/scripts/_vendor/livespec_runtime/` (adds `work_items/
{lifecycle,rank,_fractional_indexing}.py`; rewrites `work_items/
{types,reduce,store,__init__}.py`; refresh `cross_repo/*`):

```bash
git -C /data/projects/livespec-runtime archive v0.5.0 livespec_runtime \
  | tar -x -C <tmp>/ && cp -r <tmp>/livespec_runtime/* \
  <repo>/.claude-plugin/scripts/_vendor/livespec_runtime/
```

Then:
- `.vendor.jsonc`: `livespec_runtime.upstream_ref` `v0.4.0 → v0.5.0` +
  refresh `vendored_at`.
- `.livespec.jsonc`: `compat.pinned` is ALREADY `v0.5.0` (bumped before
  the spec ratification) — no change needed.
- `pyproject.toml`: add the verbatim `_fractional_indexing.py` to the
  three gate exclusions exactly like L0's runtime did — ruff
  `extend-exclude`, pyright `exclude`, coverage `omit`
  (`*/work_items/_fractional_indexing.py`). The custom AST checks
  (keyword-only/no-inheritance/no-raise) need an exclusion too IF this
  repo's `[tool.livespec_dev_tooling].source_trees` includes `_vendor`
  (verify; L0 found them no-op for its flat layout — this repo differs,
  so CHECK and exclude if needed).
- A `NOTICES` entry for the CC0 port (verify whether the vendored tree
  already carries attribution; the runtime's NOTICES is not auto-copied).

## The breakage scope — verified: ONE uniform root cause

Re-vendoring alone leaves the suite at **244 failed, 952 passed**. EVERY
failure is the identical `TypeError: WorkItem.__init__() got an
unexpected keyword argument 'priority'` (248 `priority` references; 15
`rank` references). So the construction migration is a uniform sweep:
**remove `priority=<n>`, add `rank=<key>` to every `WorkItem(...)`
construction**, plus reroute the handful of `.priority` reads. There is
NO varied/semantic test rewrite — it is mechanical.

### Product construction/read sites (S1+S2)
- `store.py:246` (`_create_work_item` draft) + `:372` (read-path
  `WorkItem(...)`) — the adapter (S2, below).
- `commands/groom.py:322`, `commands/_orchestrator_gap_capture.py:120/125/
  144` — WorkItem construction; supply `rank` (groom/gap-capture must
  assign a rank, e.g. `key_between(a=<top>, b=None)` for a bottom append
  or per the create-position param — see decision 13/the spec's required
  `position` parameter; for the L1a code, the minimal correct choice is
  to generate a rank via `rank.key_between`).
- `commands/next.py:179-181` — `_urgency_for(priority=...)` + the reason
  string + the emitted `priority` field → rank ordering + `urgency:
  "medium"` (S4).
- `commands/_cross_repo.py:241` — `ready_sort_key` uses `item.priority`
  → DELETE (relocated to runtime; S1).
- `commands/_dispatcher_plan.py:343` — `f"Priority: P{item.priority}"`
  display → drop or show rank.
- `commands/list_work_items.py:145` — `[{status}/P{priority}/{origin}]`
  display → drop priority (S4).
- `commands/_dispatcher_reflector_oob.py:966` — `priority=
  severity_priority(...)` constructs a WorkItem for an OOB finding →
  supply `rank` instead.
- `_beads_client.py:254` (`IssueDraft.priority` → record) + `:590`
  (`bd create ... priority` argv) — the beads native priority column
  still exists; `IssueDraft` MAY keep a `priority` for the native column,
  but the WorkItem→IssueDraft mapping no longer sources it from
  `item.priority`. Simplest: drop `priority` from `IssueDraft` and the
  argv, OR default it. (The native column is no longer read into the
  logical record per the ratified mapping.)

### Test sites (S1+S2)
~17 test files, most with a single local `WorkItem(...)` factory helper
(e.g. `_make_work_item`) — fix each factory once (remove `priority=`, add
`rank=`), then fix the ~21 files referencing `priority=` in assertions.
`tests/conftest.py` + `tests/livespec_orchestrator_beads_fabro/conftest.py`
may hold shared fixtures.

## `_cross_repo.py` shrink (S1 — `bd-ib-ojlmr6`)

DELETE from `commands/_cross_repo.py`: `is_item_ready`, `ready_sort_key`,
`_local_lookup_for`, `_entry_blocks`, `_sibling_lookup_for`,
`_try_read_sibling`, and the `_GAP_TIED_RANK`/`_FREEFORM_RANK` constants.
KEEP: `load_manifest`, `parse_entry`. Update `__all__` to
`["load_manifest", "parse_entry"]`. The callers (`next.py`,
`list_work_items.py`, the Dispatcher) now `from
livespec_runtime.work_items.lifecycle import is_item_ready,
ready_sort_key, lane_of`. They build the `index: dict[str, WorkItem]`
from the tenant read (`{i.id: i for i in read_work_items(...)}`) and pass
it. (The runtime's `is_item_ready` no longer takes an injected sibling
lookup — sibling deps resolve UNKNOWN; fine for this repo.) Update the
`commands/CLAUDE.md` `_cross_repo.py` bullet accordingly.

## The beads store adapter (S2 — `bd-ib-7mounw`) — the real logic

`store.py` + `_beads_client.py` per the ratified `## Work-item
beads-issue mapping`:

- **status read map** (beads → livespec): the 5 custom statuses pass
  through verbatim (`backlog`/`pending-approval`/`ready`/`active`/
  `acceptance`); beads `blocked` → `blocked`; beads **`closed` → `done`**
  (the one adapter name-mapping). **write map** is the inverse (`done` →
  `closed`).
- **2-step append**: `append_work_item` for a non-closed create does `bd
  create` (lands `open`) then `bd update --status <custom-state>`. The
  `_beads_client` `create_issue` + `update_issue(status=...)` already
  exist; sequence them. Closure stays the in-place `bd close` path
  (which sets `closed` ≡ livespec `done`).
- **custom-status registration**: a bootstrap step runs `bd config set
  status.custom "backlog,pending-approval,ready:active,active:wip,
  acceptance:wip"`. Add a `register_custom_statuses` client verb (shell:
  `bd config set ...`; fake: no-op/record) called from the bootstrap
  path. Idempotent.
- **rank**: write `item.rank` into `metadata.rank`; read it back from
  `metadata.rank`, substituting `rank.BOTTOM_SENTINEL` ("~") when the key
  is absent (legacy issue). The `_work_item_metadata`/`_audit_from_metadata`
  helpers are the pattern to follow.
- **policy fields**: write `admission:<v>`/`acceptance:<v>`/
  `blocked-reason:<v>` labels; read them back (absent → `None`). Mirror
  the existing `origin:`/`gap-id:`/`resolution:` label helpers.
- **assignee** stays native (unchanged). **priority**: drop from the
  WorkItem mapping (native column may stay unused or be defaulted).
- The read path's `_record_to_work_item` constructs `WorkItem(...)` —
  remove `priority=`, add `rank=` (from metadata + sentinel), map status
  via the done↔closed adapter, read the policy labels.

### Legacy-status read note (transition window)
The new read path maps the 5 custom statuses + `blocked` + `closed`→`done`.
Pre-L2 the live tenant still holds `open`/`in_progress`/`deferred`
records. The L1a-released code is intended to run against the tenant only
AFTER L2 migrates statuses (the fleet migrates in lockstep — decision
37/46). So the read path maps the canonical post-migration set; an
un-migrated legacy status surfacing on a head is the L2 migration's
concern. Tests use the `FakeBeadsClient` seeded with new-schema data.
(If a defensive legacy-status read fallback is wanted, that is an
explicit add — the design assumes lockstep migration.)

## Dispatcher valves + WIP cap + acceptance (S3 — `bd-ib-dnw2ei`)
Per the ratified `## Dispatcher admission, WIP cap, and post-merge
acceptance` + Scenarios 22-25. `commands/dispatcher.py` +
`_dispatcher_engine.py`: read `dispatcher.wip_cap` (default 5) from
`.livespec.jsonc`; admit highest-`rank` eligible `ready` item when
`count(active) < cap`, set `assignee`; hold `admission_policy=manual`
items; `complete`=merge-on-green→`acceptance`; `accept` per
`acceptance_policy`; `reject`=revert/fix-forward. Re-express the existing
`human-gated` refusal (Scenario 10) as `admission_policy=manual` and the
non-convergence bounce (Scenario 11) as bounce-to-`backlog`, updating
those bound integration tests' vocabulary.

## Lane emission + next rank (S4 — `bd-ib-3wjakl`)
`list_work_items.py`: per item compute `lane`/`lane_reason` via
`lane_of(item=, index=, manifest=)` and add them as flat keys to the
`--json` item (the emitter is `asdict`-based — add the two computed keys).
Update `--filter=ready`/`blocked` to lane semantics. `next.py`: rank via
`ready_sort_key` (= `(rank, id)`); `urgency: "medium"`; drop the priority
display. Scenarios 26-27.

## rebalance-ranks (S5 — `bd-ib-6gwl23`) + doctor invariants (S6 — `bd-ib-6zndit`)
S5: a new `rebalance-ranks` command using `rank.n_keys_between` to re-key
in `rank` order; a legacy-seed entry path (seed by `priority →
captured_at → id`) for L2's backfill; on-demand only. S6: doctor checks —
every live head has a non-sentinel `rank` (fail-soft, NAMED); a
rank-key-length WARNING; `active ⟹ assignee`; stored `blocked ⟹
blocked_reason`.

## Release (S7 — `bd-ib-jysmuu`)
The product `.py` of S1-S6 lands under `feat:` red-green-replay commits →
release-please opens a release PR → merge + tag. This release is what L2
+ the console consume.

## Red-Green-Replay approach for the foundational PR (S1+S2)
The re-vendor + adapter is mostly behavior-PRESERVING adaptation to a new
shared type (eligible for the green-verified `TDD-Suite-Green-*` leg, as
L0's S4 used) EXCEPT the genuinely new store behaviors (2-step append,
custom-status registration, rank persistence + sentinel, done↔closed,
policy labels) which need Red tests. Stage ONE new failing store test at
Red (e.g. "append lands a custom status via 2-step" or "legacy rank-less
read returns BOTTOM_SENTINEL"), then Green-amend with the full re-vendor +
adapter + the uniform construction sweep + remaining tests + ride-along
doc edits, preserving the `TDD-Red-*` trailer block via `--amend
--no-edit`. Co-edit `tests/heading-coverage.json` only if a `## ` heading
changes (S1+S2 change no spec headings — the spec already landed in v020).
Keep per-file 100% coverage (the new adapter branches: sentinel fallback,
each status map arm, the 2-step path, each policy label).

## Slice → ledger child map
S1 `bd-ib-ojlmr6` (revendor-runtime-v050) · S2 `bd-ib-7mounw`
(beads-custom-status-encoding) · S3 `bd-ib-dnw2ei` (dispatcher-valves-wip-cap)
· S4 `bd-ib-3wjakl` (lane-emission-and-rank-next) · S5 `bd-ib-6gwl23`
(rebalance-ranks-command) · S6 `bd-ib-6zndit` (doctor-rank-invariants) ·
S7 `bd-ib-jysmuu` (cut-l1a-release). S1+S2 land as a coordinated green
PR; S3/S4/S6 depend on S1+S2 and are largely parallel; S5 depends on
S1/S2/S4; S7 (release) depends on S1-S6. Close each child via the
`implement` freeform path as its PR merges, carrying merge-evidence in
the `AuditRecord`.
