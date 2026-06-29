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
4. `research/03-code-slices.md` — the code-slice breakdown (S1-S7). The
   `groom` gate cuts this into ready children of `bd-ib-vvrxcb`
   (AUTO-CUT).
5. Cross-repo design of record (authoritative on any conflict):
   `/data/projects/livespec/plan/work-item-state-machine/research/`
   {02-design.md, 03-decision-log.md, 04-slice-plan.md}.
6. L0 worked example (full propose-change→revise→groom→implement→release):
   `/data/projects/livespec-runtime/plan/work-item-state-machine/`.

## State as of this handoff

- ✅ Epic `bd-ib-vvrxcb` anchored (prose-linked to `livespec-35s3zo`; no
  typed cross-tenant `depends_on`).
- ✅ Thread + research drafts (`00`-`03`) committed.
- ⏳ `revise` (ratify) — NOT yet run.
- ⏳ `groom` (cut) — NOT yet run.
- ⏳ implement (S1-S7) — NOT yet started.
- ⏳ release — NOT yet cut.
- L0 (livespec-runtime v0.5.0) is DONE — the artifact this track vendors.

## Next action — run `propose-change` against `contracts.md`

Drive the L1a spec change into `SPECIFICATION/contracts.md` (+
`scenarios.md` + `tests/heading-coverage.json`):

1. In a fresh worktree off `master`, run the core propose-change CLI with
   the findings payload:
   ```bash
   python3 <livespec-core-plugin>/scripts/bin/propose_change.py \
     work-item-state-machine \
     --findings-json plan/work-item-state-machine/research/02-propose-change-findings.json \
     --project-root . --author wism-l1a-beads-fabro
   ```
   (resolves the active livespec core plugin root; writes
   `SPECIFICATION/proposed_changes/work-item-state-machine.md`).
2. Then `revise` (AUTO-RATIFY): assemble the revise-json with one `accept`
   decision per proposal whose `resulting_files[]` carry the FULL updated
   `contracts.md` + `scenarios.md` + `tests/heading-coverage.json`
   content (the deltas in `01-spec-deltas.md`), and invoke the core
   revise CLI with `--post-step-doctor`. This cuts the next `vNNN`
   history snapshot and applies the edits.
3. Then `groom` (AUTO-CUT): file S1-S7 as ready children of `bd-ib-vvrxcb`
   per `03-code-slices.md` (Option A: `capture-work-item` `append_work_item`
   with explicit `spec_commitment_hint` + parent-child + `depends_on`
   edges).
4. Then implement S1-S7 (red-green-replay) and cut the release.

Each milestone (ratified; groomed; implemented; released) is reported to
the coordinator.
