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
- ⏳ **implement (S1-S7) — NOT yet started** (scoped; see
  `research/04-implement-findings.md`).
- ⏳ release — NOT yet cut (S7).
- L0 (livespec-runtime v0.5.0) is DONE — the artifact this track vendors.

## Next action — implement S1+S2 (the coordinated foundation PR)

Execute the implement phase per **`research/04-implement-findings.md`**
(the concrete, verified resume guide). Start with the coordinated
**S1+S2** PR (re-vendor v0.5.0 + the `_cross_repo.py` shrink + the beads
custom-status/2-step/rank/policy store adapter + the uniform
`priority→rank` construction sweep across ~6 product modules + ~17 test
files), which is irreducibly one green PR (re-vendor breaks the build
until the adapter is migrated; the breakage is a verified-uniform
`priority`-keyword `TypeError`). Then S3 (dispatcher valves), S4
(lane/rank), S5 (rebalance-ranks), S6 (doctor invariants), and S7 (cut
the release). Status is derived from the ledger (`bd children
bd-ib-vvrxcb`); close each child via the `implement` freeform path as its
PR merges, carrying merge-evidence in the `AuditRecord`.

Discipline (non-negotiable): worktree → PR → rebase-merge; `mise exec --
git`; never `--no-verify`; halt + report on any hook failure; product
`.py` follows red-green-replay; keep per-file 100% coverage. The spec
already landed (v020) — implement slices change NO `## ` heading, so no
further `heading-coverage.json` co-edit is required.

Each milestone (implemented; released) is reported to the coordinator.
