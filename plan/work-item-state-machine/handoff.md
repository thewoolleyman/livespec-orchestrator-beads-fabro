# Handoff — work-item-state-machine (L1a, livespec-orchestrator-beads-fabro)

**Thread:** `plan/work-item-state-machine/` · **Ledger anchor:** epic
`bd-ib-vvrxcb` (`livespec-orch-beads-fabro` beads tenant) · **Fleet
anchor (prose ref):** `livespec-35s3zo` (livespec core tenant — NEVER a
typed cross-tenant `depends_on`).

> Status is **derived from the ledger**, never stored here. To read it:
> ```bash
> with-livespec-env.sh python3 \
>   /home/ubuntu/.claude/plugins/cache/livespec-orchestrator-beads-fabro/livespec-orchestrator-beads-fabro/*/scripts/bin/list_work_items.py --json
> ```
> (`with-livespec-env.sh` injects the tenant password; the glob resolves
> the active orchestrator plugin root.) See the children with
> `with-livespec-env.sh bd children bd-ib-vvrxcb --json`. The epic + its
> children are filed under the CURRENT pre-migration schema
> (`open`/`priority`/no-`rank`); the 7-state shape lands at the L2
> migration.

## Autonomy posture

The design is LOCKED (decisions 1-46). This track **AUTO-PROCEEDS**
through its `revise` (ratify) and `groom` (cut) gates per the locked
design — it does NOT pause for maintainer approval. Halt + report ONLY on
a genuine blocker or a new decision the design does not resolve.
Discipline: worktree → PR → rebase-merge; `mise exec -- git`; never
`--no-verify`; halt + report on any hook failure; product `.py` follows
red-green-replay; co-edit `tests/heading-coverage.json` for any
`## `-heading change.

## Read-first chain (open these, in order)

1. `research/00-l1a-overview.md` — the slice, the anchor, the reframe,
   the cross-repo design-of-record paths.
2. `research/01-spec-deltas.md` — the exact `SPECIFICATION/contracts.md`
   (+ `scenarios.md` + `tests/heading-coverage.json`) deltas (the
   propose-change payload, human-readable). The `revise` gate ratifies
   this (AUTO-RATIFY).
3. `research/02-propose-change-findings.json` — the ready-to-feed
   `/livespec:propose-change` findings payload for `01`. The
   `impl_followups[].id_hint`s are the `spec_commitment_hint` values each
   groom child carries.
4. `research/03-code-slices.md` — the code-slice breakdown (S1-S7),
   cut into ready children of `bd-ib-vvrxcb` (DONE; ids below).
5. `research/04-implement-findings.md` — **the concrete resume guide for
   the implement phase**: the verified v0.5.0 runtime API, the re-vendor
   mechanics, the verified-uniform 244-test breakage + its single root
   cause, the store-adapter design, the `_cross_repo.py` shrink, the
   sibling-UNKNOWN consolidation, the legacy-status read note, and the
   red-green-replay approach for the foundational S1+S2 PR. **Start the
   implement phase here.**
6. Cross-repo design of record (authoritative on any conflict):
   `/data/projects/livespec/plan/work-item-state-machine/research/`
   {02-design.md, 03-decision-log.md, 04-slice-plan.md}.
7. L0 worked example (full propose-change→revise→groom→implement→release):
   `/data/projects/livespec-runtime/plan/work-item-state-machine/`.

## State as of this handoff

- ✅ Epic `bd-ib-vvrxcb` anchored (prose-linked to `livespec-35s3zo`; no
  typed cross-tenant `depends_on`).
- ✅ Thread + research drafts committed (PR #201).
- ✅ **`revise` (ratify) DONE** — history **v020**, `contracts.md` +
  `scenarios.md` + `tests/heading-coverage.json` ratified (PR #202; core
  revise CLI with `--post-step-doctor`, all checks green). **Do NOT
  re-run propose-change / revise.**
- ✅ **`groom` (cut) DONE** — S1-S7 filed as `ready` children of
  `bd-ib-vvrxcb`, parent-linked + dep-layered, each carrying its
  `spec_commitment_hint`. **Do NOT re-file.** Ids:
  S1 `bd-ib-ojlmr6` · S2 `bd-ib-7mounw` · S3 `bd-ib-dnw2ei` ·
  S4 `bd-ib-3wjakl` · S5 `bd-ib-6gwl23` · S6 `bd-ib-6zndit` ·
  S7 `bd-ib-jysmuu`.
- ✅ **implement S1 + S2 DONE** — the coordinated foundation PR merged to
  `master` as **`dfbb21e`** (PR #203; rebase-merge landed the re-vendor
  chore `6d5cbd5` + the `feat(work-items)` commit). Duplicate PR #200
  closed. The build is green at 100% coverage on the new v0.5.0
  rank/7-state model. Ledger children **S1 `bd-ib-ojlmr6` and S2
  `bd-ib-7mounw` are CLOSED** (`status=done`, `resolution=completed`,
  `AuditRecord.merge_sha=dfbb21e…`). Their deps cleared, so **S3
  `bd-ib-dnw2ei`, S4 `bd-ib-3wjakl`, and S6 `bd-ib-6zndit` are now
  READY** (largely parallel); S5 `bd-ib-6gwl23` waits on S4; S7
  `bd-ib-jysmuu` (release) waits on S1-S6.
- ⏳ **implement S3-S6 — NOT yet started.**
- ⏳ release — NOT yet cut (S7).
- L0 (livespec-runtime v0.5.0) is DONE — the artifact this track vendors.

### Critical note for S3+ implementers — repo vs. live-tenant schema skew

`master` now carries the **post-migration** L1a code (rank, 7-state,
`done`↔`closed`). The **live beads tenant is still PRE-migration**
(legacy `open`/`in_progress`/`closed`/`deferred`, `priority`, no `rank`) —
the fleet's L2 status migration has NOT run. The released code is
designed to run against the tenant only AFTER L2 (lockstep — decisions
37/46). The post-migration READ path tolerates legacy rows (a legacy
`open` passes through as `open`; a rank-less row reads `BOTTOM_SENTINEL`),
and `bd close` is schema-agnostic, which is how S1/S2 were closed above.
S3-S6 are hermetic (`FakeBeadsClient`, new-schema fixtures) so they are
unaffected; just do NOT assume the live tenant matches the new schema.

## Next action — implement S3 (dispatcher valves + WIP cap + acceptance)

S3-S6 are additive on the S1+S2 foundation. Recommended order: **S3, then
S4, then S6** (all unblocked, largely parallel), then **S5** (after S4),
then **S7** (release). Per slice, per `research/04-implement-findings.md`:

- **S3 `bd-ib-dnw2ei`** — `## Dispatcher admission, WIP cap, and
  post-merge acceptance` + Scenarios 22-25. `dispatcher.py` +
  `_dispatcher_engine.py`: `dispatcher.wip_cap` (default 5); admit
  highest-`rank` ready item when `count(active) < cap`, set `assignee`;
  hold `admission_policy=manual`; `complete`=merge→`acceptance`;
  `accept` per `acceptance_policy`; `reject`=revert/fix-forward.
  Re-express Scenario-10 human-gated as `admission_policy=manual` and
  Scenario-11 non-convergence as bounce-to-`backlog`.
- **S4 `bd-ib-3wjakl`** — lane emission + next rank (Scenarios 26-27):
  `list_work_items.py` add flat `lane`/`lane_reason` keys via
  `lifecycle.lane_of`; refine `--filter=ready/blocked` to lane semantics.
- **S6 `bd-ib-6zndit`** — doctor rank/assignee/blocked invariants.
- **S5 `bd-ib-6gwl23`** — `rebalance-ranks` command (`rank.n_keys_between`)
  + the legacy-seed entry path for L2's backfill.
- **S7 `bd-ib-jysmuu`** — cut the release (release-please opens the PR;
  merge + tag). This release is what L2 + the console consume.

Close each child via the freeform close path as its PR merges, carrying
merge-evidence in the `AuditRecord` (see the S1/S2 close: a small script
through the store seam, run from the repo root under
`with-livespec-env.sh`, builds the closure WorkItem with
`status="done"`, `resolution="completed"`, and an `AuditRecord` whose
`merge_sha` is the squashed/rebased merge commit on `master`).

Discipline (non-negotiable): worktree → PR → rebase-merge; `mise exec --
git`; never `--no-verify`; halt + report on any hook failure; product
`.py` follows red-green-replay; keep per-file 100% coverage. The
host-only `check-codex-skill-picker` gate may fail locally on a "trust
hooks" Codex-TUI prompt — it is skipped in pre-commit/pre-push/CI, so run
the full aggregate as `just skip="check-codex-skill-picker" check` when
validating locally. The spec already landed (v020) — implement slices
change NO `## ` heading, so no further `heading-coverage.json` co-edit is
required (the L1a Scenario 22-28 heading-coverage entries are TODO-bound
warnings, expected until their acceptance tests land in S3-S6).

Each milestone (implemented; released) is reported to the coordinator.
