# 001 — What arming the plan-record conformance check needs, per tenant (2026-09-06)

This plan exists because `bd-ib-xpszyi` — the operator remainder transferred at
the archive of `console-control-plane-primitives` — had no plan slug to run
(maintainer, 2026-09-06: "You need to give me a plan slug to run. If there's no
plan, you need to create one that covers everything you need"). It anchors
xpszyi and the one prerequisite xpszyi did not know about.

## The goal

`LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE` set in every tenant's `just check`
environment, with the check green on master there. Arming before a tenant is
clean turns its master red (xpszyi leg 3), so the order below is the plan.

## The prerequisite xpszyi did not have

`livespec-dev-tooling-lnbf` (filed 2026-09-06, P1 bug): the check recognizes
NO epics on bd 1.x. `is_same_tenant_epic` reads `record["type"]`, but
`bd list --status all --json` (the reader's fallback when no
`.beads/issues.jsonl` export exists — none does) emits `issue_type`. Measured on
the console tenant with an armed hand run: 0 of 28 epics recognized, 28
`plan_slug_on_non_epic` and 16 `plan_anchor_consistent` errors, including live
directories whose anchor is verifiably correct. Until lnbf ships and the
tenant's pin carries it, an armed run cannot be clean anywhere, and leg 3
cannot start. Legs 1 and 2 do not wait on it.

## Leg 1 — the two livespec-overseer slug refusals

Both are title-derived collisions where the epic was left untagged:

- `overseer-tdfe.11` derives the slug already carried by `overseer-au3pt3.18`.
  tdfe.11 is a bucket-2 foreman epic under the overseer deprecation plan
  (`deprecate-unused-seats-simplify-to-overseerd-and-caam`, `overseer-5ugiuj.5`
  closes it). Resolve by tagging it with a distinct hand-chosen `plan_slug`
  now, or by that closure; the check grades closed epics too, so a closed
  untagged epic may still refuse — tag it.
- `overseer-xbxkrv` derives the slug carried by `overseer-byvxlp`; both are
  CLOSED and carry the same title ("Generated supervisor-prompt quality bar…").
  Pick the survivor (byvxlp already carries the slug) and retag xbxkrv with a
  distinct slug.

Tool: `tag_epic_plan_slug(config, epic_id, title, slug=<explicit>)` from the
orchestrator package, run from the overseer repo root under the wrapper.

## Leg 2 — per-tenant anchor reconciliation

Archived `plan/<slug>/associated_work_item_id` files that read `unassigned`
whose epics predate the tag and carry title-derived slugs ≠ directory name.
For each: retag the epic to the directory slug (when exactly one epic matches
by title-derived slug or title) and write the id into the anchor through the
repo's worktree → PR path, or record the directory as intentionally orphaned.

Counts from xpszyi: this tenant 17 (autonomous-mode, codex-credential-broker,
codex-factory-telemetry, codex-yolo-sandbox, dispatch-claim-liveness,
factory-hardening, factory-success-rate-remediation, force-factory,
lifecycle-front-end-retrofit, loop-reflection-gate,
orchestrator-plugin-self-containment, retire-host-dispatch-cap,
rop-sweep-consumer-cleanup, work-item-state-machine, scratch, plus two in
bd-ib-uf2c55's 05:59Z comment); openbrain 7 (tracked as ob-ck4nao); every
other tenant's count is in its anchor PR body. The pre-existing duplicate slug
`fix-review-disposition-context` here (bd-ib-65mycm and bd-ib-d2qyze, both
closed) needs a survivor picked.

Worked example, console tenant (`livespec-console-beads-fabro-pzbdbo.16`,
done 2026-09-06): 13 unassigned → 10 matched by title-derived slug, retagged
with `tag_epic_plan_slug` and read back, anchors written in one PR; 3 with no
candidate epic (`cockpit-ux-docs-release`, `console-autonomous-mode`,
`impl-dispatch`) await the maintainer's word "orphaned" or an epic id. The
matching heuristic: an epic whose `canonical_plan_slug(title)` starts with the
directory name, or whose title contains it — one candidate each time.

## Leg 3 — arming, per tenant, in order

For each tenant, only after lnbf is in its pin: run the check armed by hand
under the wrapper (`LIVESPEC_RUN_PLAN_RECORD_CONFORMANCE=1 just
check-plan-record-conformance`), fix what it names, and only when it exits 0
set the variable in that tenant's check environment in a commit that quotes
the clean run. The console already wires the recipe self-skipping; tenants
without the recipe wire it the same way first.
