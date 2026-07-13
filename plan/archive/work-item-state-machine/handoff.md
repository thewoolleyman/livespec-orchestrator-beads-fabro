# Handoff — work-item-state-machine (L1a, livespec-orchestrator-beads-fabro)

**Thread:** `plan/work-item-state-machine/` · **Ledger anchor:** epic
`bd-ib-vvrxcb` (`livespec-orch-beads-fabro` beads tenant) · **Fleet
anchor (prose ref):** `livespec-35s3zo` (livespec core tenant — NEVER a
typed cross-tenant `depends_on`).

> Status is **derived from the ledger**, never stored here. To read it:
> ```bash
> with-livespec-env.sh bd children bd-ib-vvrxcb --json
> ```
> (`with-livespec-env.sh` injects the tenant password.) The epic + its
> children are filed under the CURRENT pre-migration schema
> (`open`/`priority`/no-`rank`); the 7-state shape lands at the L2
> migration.

## ✅ STATUS: L1a COMPLETE (2026-06-29)

All seven slices are merged and their ledger children closed
(`status=done`, `resolution=completed`), and the L1a release is cut:

- ✅ **S1** `bd-ib-ojlmr6` (revendor-runtime-v050) — merge `dfbb21e` (PR #203).
- ✅ **S2** `bd-ib-7mounw` (beads-custom-status-encoding) — merge `dfbb21e` (PR #203).
- ✅ **S3** `bd-ib-dnw2ei` (dispatcher-valves-wip-cap) — merge `da61be6` (PR #210).
- ✅ **S4** `bd-ib-3wjakl` (lane-emission-and-rank-next) — merge `da3c46c` (PR #206).
- ✅ **S5** `bd-ib-6gwl23` (rebalance-ranks-command) — merge `5d49d2b` (PR #208).
- ✅ **S6** `bd-ib-6zndit` (doctor-rank-invariants) — merge `8bb59d5` (PR #207).
- ✅ **S7** `bd-ib-jysmuu` (cut-l1a-release) — **release v0.3.0** cut by
  release-please (PR #168, merge `9cf1de2`). This release is the L1a exit
  gate that L2 + the console consume.

The epic `bd-ib-vvrxcb` is **closed** (`status=done`, `resolution=completed`;
all 7 children done). **This thread is done** — the sections below are the
historical resume guide kept for the record; nothing remains to implement.
The live beads tenant is still PRE-migration (legacy
`open`/`priority`/no-`rank`); the 7-state status migration is L2's concern.

## Local-Memory Migration Provenance

This archived handoff is the durable destination for the Claude local-memory
source record `wism-l1a-rollout-state.md` from
`/home/ubuntu/.claude/projects/-data-projects-livespec-orchestrator-beads-fabro/memory/`
(inventory SHA-256 prefix `17f8b35c3786`). The source record was classified by
the livespec cloud-local-memory cleanup inventory as a project runbook that
should preserve or archive the work-item-state-machine rollout completion state
after checking current repo docs/spec.

The checked current repo record is already authoritative here: this file records
the L1a completion date, release, slice ledger ids, merge evidence, and closure
state; [l2-tenant-migration.md](l2-tenant-migration.md) records the follow-on
tenant migration result. No active instruction is copied from harness-local
memory.

## Autonomy posture

The design is LOCKED (decisions 1-46). This track **AUTO-PROCEEDS** — it
does NOT pause for maintainer approval. Halt + report ONLY on a genuine
blocker or a new decision the design does not resolve. Discipline:
worktree → PR → rebase-merge; `mise exec -- git`; never `--no-verify`;
halt + report on any hook failure; product `.py` follows red-green-replay;
keep per-file 100% coverage. The host-only `check-codex-skill-picker` gate
may fail locally on a Codex-TUI trust prompt — it is skipped in
pre-commit/pre-push/CI, so validate locally with
`mise exec -- just skip="check-codex-skill-picker" check`.

## Read-first chain (open these, in order)

1. `research/00-l1a-overview.md` — the slice, the anchor, the reframe.
2. `research/01-spec-deltas.md` — the ratified `contracts.md` deltas.
3. `research/03-code-slices.md` — the S1-S7 slice breakdown + ledger ids.
4. `research/04-implement-findings.md` — the implement resume guide.
5. **This handoff's "S3 resume guide" below** — the concrete, already-mapped
   surface + design decisions for the one remaining implementation slice.
6. Cross-repo design of record (authoritative on conflict):
   `/data/projects/livespec/plan/work-item-state-machine/research/`
   {02-design.md, 03-decision-log.md, 04-slice-plan.md}.

## State as of this handoff (2026-06-29)

`master` is at `5d49d2b`. The spec is RATIFIED (v020) and the epic is
GROOMED into 7 children. **Five of seven slices are merged + their ledger
children closed (`status=done`, `resolution=completed`, `AuditRecord.merge_sha`
set):**

- ✅ **S1** `bd-ib-ojlmr6` (revendor-runtime-v050) — merge `dfbb21e` (PR #203, with S2).
- ✅ **S2** `bd-ib-7mounw` (beads-custom-status-encoding) — merge `dfbb21e` (PR #203).
- ✅ **S4** `bd-ib-3wjakl` (lane-emission-and-rank-next) — merge `da3c46c` (PR #206).
  `list-work-items --json` emits computed `lane`/`lane_reason`; `--filter=blocked`
  is lane semantics. (Scenario-27 `next` rank order was ALREADY satisfied by the
  S1/S2 sweep — `next.py` ranks by `ready_sort_key` with `urgency: medium`.)
- ✅ **S6** `bd-ib-6zndit` (doctor-rank-invariants) — merge `8bb59d5` (PR #207).
  New `dev-tooling/checks/work_item_state_invariants.py` + `check-work-item-state-invariants`
  in the `just check` private block: fail-soft non-sentinel-rank + rank-key-length
  WARNINGS; hard `active⟹assignee` / stored `blocked⟹blocked_reason` ERRORS.
- ✅ **S5** `bd-ib-6gwl23` (rebalance-ranks-command) — merge `5d49d2b` (PR #208).
  New `commands/rebalance_ranks.py` (`rebalanced` order-preserving re-key +
  `legacy_seed` L2-backfill primitive) + `store.update_work_item_rank` (in-place
  re-key). On-demand only; never auto-fires.
- ⏳ **S3** `bd-ib-dnw2ei` (dispatcher-valves-wip-cap) — **NOT started. The one
  remaining implementation slice. See the S3 resume guide below.**
- ⏳ **S7** `bd-ib-jysmuu` (cut-l1a-release) — depends on S1-S6; cut AFTER S3 merges.

**Close mechanism (per slice, as its PR merges):** run the small close
script from the repo root under the wrapper —
`with-livespec-env.sh mise exec -- uv run python <scratch>/close_slice.py <id> <full-merge-sha> <pr#> "<reason>"`
— which reads the item via the store seam and persists a `status=done`,
`resolution=completed` copy carrying an `AuditRecord(merge_sha=...)`. (The
script lives in the session scratchpad; its body: sys.path-bootstrap the
`.claude-plugin/scripts` + `_vendor` dirs, `resolve_store_config(cwd=Path.cwd())`,
`materialize_work_items(read_work_items(...))`, `dataclasses.replace(item,
status="done", resolution="completed", reason=..., audit=AuditRecord(...))`,
`append_work_item`. Re-author it if the scratch copy is gone — it is ~35 lines.)

### Critical note — repo vs. live-tenant schema skew (unchanged)

`master` carries post-migration L1a code (rank, 7-state, `done`↔`closed`).
The **live beads tenant is still PRE-migration** (legacy
`open`/`in_progress`/`closed`/`deferred`, `priority`, no `rank`) — the L2
status migration has NOT run. The post-migration READ path tolerates legacy
rows (a legacy `open` passes through; a rank-less row reads `BOTTOM_SENTINEL`),
and `bd close` is schema-agnostic, which is how every slice above was closed.
S3 is hermetic (`FakeBeadsClient`, new-schema fixtures), so it is unaffected.

---

## S3 resume guide — dispatcher admission valve + WIP cap + post-merge acceptance

**Ledger child:** `bd-ib-dnw2ei`. **Contract:** `SPECIFICATION/contracts.md`
"Dispatcher admission, WIP cap, and post-merge acceptance" (~line 916).
**Acceptance:** Scenarios 22-25 (`SPECIFICATION/scenarios.md` ~line 415) pass
against the `FakeBeadsClient`; `just check` green at 100% coverage.

This is the LARGEST, highest-churn slice — it adds the first behavioral
consumers of the `active`/`acceptance` states, `assignee`, and the
`admission_policy`/`acceptance_policy` fields (all are schema+store-supported
today but have ZERO dispatch consumers). Plan it carefully; it is mostly
careful multi-file editing, NOT research — the full surface is mapped below.

### Files (all relative to `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/`)

- `commands/dispatcher.py` (2097 lines) — the driver. Today the green path is
  `_run_loop_command` → `_candidates` → `_ready_items` (filters the `ready`
  lane, sorts by `ready_sort_key`; does NOT consult `admission_policy`) →
  `_dispatch_one` → `_pre_launch_refusal` (`_host_only_refusal` or
  `_human_gated_surface`) → `run_dispatch` → `_post_run_dispositions` →
  `_close_item` (**goes straight `ready→done`**; status="done",
  resolution="completed", audit). Nothing sets `status="active"` or `assignee`;
  there is NO `admit`/`complete`/`accept` verb and NO transition into `acceptance`.
- `commands/_dispatcher_plan.py` — carries `is_human_gated_item` (regex on
  title/description for a word-bounded `human-gated`/`human_gated` token — NOT a
  field), `human_gated_surface_detail`, `is_host_only_item`,
  `is_non_convergence_outcome` (`status=="stalled-no-progress"` OR
  `status=="failed"` and `NON_CONVERGED_MARKER` in detail).
- `store.py` — `append_work_item` (create or close-in-place), `update_work_item_rank`
  (new, S5 — the in-place metadata update pattern to mirror for an `admit`/`accept`
  state write), the policy-label encode/decode (`admission:`/`acceptance:`/
  `blocked-reason:`), `assignee` native round-trip. NOTE: `append_work_item` only
  CREATES (2-step) or CLOSES-in-place; an `admit`/`complete`/`accept`/`reject`
  state write of an EXISTING non-done item needs a new in-place update path
  (mirror `update_work_item_rank`: `client.update_issue(issue_id=..., status=...,
  add_labels=...)` — and for `assignee`, check whether `update_issue` carries an
  assignee param; if not, add one to the `BeadsClient` Protocol + both impls).
- `regroom.py` — `enter` (adds the `needs-regroom` LABEL), `is_needs_regroom`.

### Design decisions (already worked out — do not re-derive)

1. **WIP cap read.** Add a `.livespec.jsonc` reader mirroring
   `dev-tooling/checks/work_item_merge_evidence.py::_resolve_canonical_branch`
   (plugin block `livespec-orchestrator-beads-fabro`), but descend one more level:
   `block.get("dispatcher", {}).get("wip_cap")`, validate it's an `int`, default
   **5** on any miss/typo/non-int. There is NO generic nested-key helper in
   `_config.py` today; write a small dedicated reader (a new `_dispatcher_valves.py`
   pure module is the clean home).
2. **Admission eligibility = effective `admission_policy == "auto"`.** Effective
   policy = `item.admission_policy or "manual"` (None defaults to **manual** per the
   contract's safe-default-via-inherit; full epic-inheritance is NOT needed for the
   scenarios — item-level resolution suffices). A `manual` (or None) ready item is
   HELD at the valve (surfaced, not admitted) — this is Scenario 23 AND the
   re-expression of Scenario 10's human-gated refusal.
3. **`admit` (ready→active).** When `count(active) < wip_cap`, admit the
   highest-`rank` admission-eligible (auto + deps-clear + assignee-resolvable)
   ready items up to the free-slot count, set `assignee`, transition to `active`.
   Scenario 22 (wip_cap=2, ranks a0/a1/a2 → admit a0,a1; a2 waits). Use a pure
   planner `plan_admissions(*, ready_items, active_count, wip_cap, resolve_assignee)`
   returning `(admitted: [(item, assignee)], held_manual: [item])`.
4. **`complete` (active→acceptance).** The merge-on-green terminal. **Replace the
   `_close_item` `ready→done` jump:** a green dispatch now transitions the item to
   `acceptance` (merged+live), NOT straight to `done`. Scenario 24.
5. **`accept` (acceptance→done) per effective `acceptance_policy`** (default
   `ai-then-human`): `ai-only` → AI pass confirms → `done`; `human-only` /
   `ai-then-human` → park in `acceptance` (AI pass surfaces findings, journaled;
   final `done` awaits a human). "No release with zero verification" — every
   acceptance carries ≥1 AI pass (in L1a a deterministic read-and-judge that
   confirms). Scenario 25.
6. **`reject` from acceptance:** rework → `active` (fix-forward); re-groom →
   `backlog` (revert). Scenario 25.
7. **Non-convergence bounce → `backlog` (not the `needs-regroom` label).**
   Re-express `_bounce_non_convergence_to_regroom` to set `status="backlog"`
   instead of `regroom.enter`. Scenario 11.

### Blast radius (the existing tests that change)

The green→done terminal change (decision 4/5) means existing "green closes to
done" assertions become "green → acceptance (parked) OR done (ai-only)". Touched:
- `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher.py`
- `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_item_mode.py`
- `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_calibration.py`
- `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_reflection.py`
- `tests/integration/test_dispatcher_non_convergence_scenario11.py`

Re-express (vocabulary change):
- `tests/integration/test_dispatcher_human_gated_scenario10.py` — the 6 predicate
  tests + 3 journey tests (`..._surfaces_human_gated_item...` @L212,
  `..._journals_human_gated_surface` @L252, `..._does_not_surface_ordinary_item`
  @L277). Re-express `human-gated` (title/desc marker) → `admission_policy=manual`.
  The journeys pin the JSON outcome contract `status="failed"`,
  `stage="human-gated-surfaced"` — decide whether to keep that stage name or rename
  to an admission-hold stage; scenarios 10/11 stay as H2s (no heading-coverage churn).
- `tests/integration/test_dispatcher_non_convergence_scenario11.py` — predicate tests
  @L162-189 + journeys @L198-303 assert via `regroom.is_needs_regroom`; re-express to
  assert `status=="backlog"`. Plus the unit fail-soft test
  `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_non_convergence.py::test_bounce_failsoft_journals_error_when_ledger_write_raises` @L66.

New (Scenarios 22-25): add `tests/integration/test_dispatcher_admission_acceptance_scenarios22_25.py`
(or per-scenario files), driving `main(["dispatch"/"loop", ...])` against the
`FakeBeadsClient`. **Bind each new scenario's heading-coverage entry** (they are
currently `TODO`-bound in `tests/heading-coverage.json` — entries for Scenarios
22-25 + the "## Dispatcher admission, WIP cap, and post-merge acceptance" H2) to
the landing test node id once the acceptance tests exist. (Scenarios 26/27/28 from
S4 also remain `TODO`-bound — optionally bind them too; this is NOT required by the
heading_coverage check, which tolerates `TODO`+reason, but it closes the loop.)

### Integration test harness (the pattern to copy)

No `conftest.py` in `tests/integration/`. Each scenario file owns an autouse
`_hermetic_dispatch_env` fixture (see `test_dispatcher_human_gated_scenario10.py`
@L59-88): monkeypatch `tempfile.gettempdir`; set `CLAUDE_CODE_OAUTH_TOKEN`/`GH_TOKEN`;
set `LIVESPEC_BEADS_FAKE="1"`; scrub the ntfy env; monkeypatch
`dispatcher._fetch_fleet_manifest_text`; `reset_fake_singleton()` before/after.
Seed via `append_work_item(path=_config()/*fake*/, item=...)`; `_repo_with_workflow`
writes `repo/.livespec.jsonc` (`{"livespec-orchestrator-beads-fabro": {"connection":
{"prefix": "bd-ib"}}}` — extend with a `"dispatcher": {"wip_cap": N}` block to test
the cap) + a committed `workflow.toml`. Stub the launch with
`monkeypatch.setattr(dispatcher, "run_dispatch", recording)` returning a canned
`DispatchOutcome`. Invoke `main(["dispatch", "--repo", str(repo), "--item", id,
"--workflow", str(workflow), "--json"])`; assert via `capsys` + the journal at
`repo/tmp/fabro-dispatch-journal.jsonl`.

### WorkItem policy fields (vendored `_vendor/livespec_runtime/work_items/types.py`)

`AdmissionPolicy = Literal["auto","manual"]`; `AcceptancePolicy =
Literal["ai-only","human-only","ai-then-human"]`; `StoredBlockedReason =
Literal["needs-human","infra-external"]` (`dependency` is DERIVED, never stored).
`assignee: str | None` is a REQUIRED constructor field (no default). The policy
fields are `… | None = None` (None → inherit/safe-default). Store labels:
`admission:`/`acceptance:`/`blocked-reason:`.

### Suggested commit shape

Likely ONE coordinated PR (the valve + acceptance + cap + re-expressions are
coupled through `_post_run_dispositions`/`_close_item`). Red-green-replay: stage
ONE new failing test file at Red (a new scenario-22 admission test is a clean
genuine-assertion Red against a stub valve), then Green-amend the full impl +
the remaining new/changed test files + ride-along docs (`commands/CLAUDE.md`,
the `dispatcher.py` module docstring, `tests/heading-coverage.json` bindings).
A new pure `_dispatcher_valves.py` module keeps the planner/disposition logic
testable + small (mind the <250 LLOC ceiling per file; `dispatcher.py` is already
large — prefer the helper module). If a lockstep edit precludes a clean Red, the
green-verified `TDD-Suite-Green-*` leg is the documented alternative.

---

## S7 resume guide — cut the L1a release (the exit gate)

**Ledger child:** `bd-ib-jysmuu`. After S3 merges (so all of S1-S6 product `.py`
is on `master` under `feat:` commits), release-please will have an open release
PR (or will open one on the next push). Merge it, let it cut the new
`livespec-orchestrator-beads-fabro` tag, and bump any in-repo self-refs
release-please dictates. This release is what the L2 migration + the console
consume. Close `bd-ib-jysmuu` with the release tag/merge as evidence. Then the
epic `bd-ib-vvrxcb` can close (all children done) and the thread archives.

## Reporting

Report to the coordinator at each PR merge and at the release.
