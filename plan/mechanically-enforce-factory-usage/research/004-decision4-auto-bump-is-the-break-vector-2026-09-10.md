# Decision #4 RESOLVED — the auto pin-bump IS the fleet-break vector, silently (2026-09-10)

Resolves the highest-risk Open decision flagged in `003-r1a-r2-fleet-rollout-runbook`.
Pure investigation, no rollout action taken. Every anchor verified on the live
repos on 2026-09-10.

## The question

Does the release-dispatch / auto pin-bump machinery advance consumer
`livespec-dev-tooling` pins past the body-changing release WITHOUT re-running the
installer — i.e. is the normal automation the path to a simultaneous fleet break?

## Answer: YES, and the break is SILENT (green auto-merge, not a red-PR flood)

The dev-tooling pin is auto-bumped fleet-wide by TWO mechanisms, and a bump PR
MERGES GREEN while leaving every live primary checkout to redden on its own:

1. **Release-dispatch fan-out.** `livespec-dev-tooling/.github/workflows/
   release-dispatch.yml` fires a `repository_dispatch` `sibling-released` event on
   each dev-tooling release. Each consumer's
   `.github/workflows/bump-pin-from-dispatch.yml` handles it: pin-autodiscovery
   across FOUR pin formats — explicitly including **`pyproject.toml
   [tool.uv.sources]`** — rewrites the matching pin to the new tag, runs
   `just check`, commits `chore(deps):`, and **opens an auto-merge PR via the
   livespec GitHub App**.
2. **Daily pin-freshness sweep (safety net).** `pin-freshness.yml` runs at
   13:00 UTC daily and opens a bump PR for any source pin ≥ `staleness_threshold_releases`
   (default 1) behind the latest release tag. So even if the dispatch is missed,
   the dev-tooling pin is force-bumped within ~24h.

**Why the bump PR merges GREEN rather than going red** (the insidious part): the
consumer CI installs the canonical hooks from the just-resolved wheel BEFORE the
byte-identity check runs. `ci.yml:822-823`:

```
- name: Install commit-refuse hook (satisfy invariant)
  run: just install-commit-refuse-hooks
```

then `ci.yml:849` runs `check-primary-checkout-commit-refuse-hook-installed`. So
on a bump PR: `uv sync` resolves the NEW wheel (new `CANONICAL_HOOK_BODY`) →
`just install-commit-refuse-hooks` writes the NEW body into CI's `.git/hooks/` →
the byte-identity check compares NEW-installed against NEW-constant → **identical,
passes**. The PR auto-merges.

The break therefore does NOT appear in CI. It lands on every **live primary
checkout** — a developer's box, a long-lived agent session — the next time it
pulls the merged master and runs `uv sync`: that primary now has the NEW wheel but
its `.git/hooks/` still carries the OLD body (`.git/hooks/` is untracked and
per-primary; no merged PR can rewrite it). `just check` and the pre-push hook then
FAIL with `worktree_pack_body_mismatch` / byte-different until someone runs
`just install-commit-refuse-hooks` on that primary. Silent, asynchronous,
fleet-wide.

## Correction to a tempting assumption: warn-default does NOT shield this

One might think shipping the refuse branch in **warn** mode (pxsr7w's default)
makes the landing safe. It does not. The fleet-wide red is produced by the
byte-identity **check** (`primary_checkout_commit_refuse_hook_installed`), which
fires purely because the installed hook bytes differ from the wheel constant — it
has NO knowledge of the gate's warn/fail mode. Warn mode governs only whether the
gate REFUSES a commit for missing provenance; it does nothing about the installed
hooks failing byte-identity. So the `just check`/pre-push breakage arrives the
moment the body changes, mode notwithstanding. The mode file matters for Phase 3
(fail flip); it is irrelevant to the Phase-0/Phase-1 landing break.

## Severity, honestly

Not catastrophic: no data loss, the fix is ONE idempotent command
(`just install-commit-refuse-hooks`), and the check narration names it exactly.
But it is fleet-wide friction hitting every active primary/session
simultaneously and silently — a session mid-task suddenly cannot commit or push
until it reinstalls, with no advance warning, because the triggering PR merged
green elsewhere.

## Recommended mitigation (option B): suppress the auto-bump for the rollout window

Mirror the bd-guard "deliberate, sequenced" posture. Before cutting the
dev-tooling release that carries the new body:

1. **Suppress the dev-tooling pin from the auto-bump fan-out for the rollout
   window.** Concretely: ensure the body-changing dev-tooling release does not
   trigger the `sibling-released` auto-merge bump across consumers, and that the
   daily `pin-freshness.yml` sweep will not force the dev-tooling pin within the
   window — by pausing/adjusting the sweep or holding the release tag until the
   fleet is staged. (Exact levers — a dispatch opt-out vs. holding the tag vs. a
   temporary staleness-threshold bump — are a maintainer/automation-owner call;
   the requirement is that NO consumer's dev-tooling pin advances past the
   body-changing release except deliberately.)
2. **Bump each consumer deliberately, paired with an installer re-run on that
   primary**, in a sequence where each primary's owner/session is ready for the
   one-command reinstall: dev-tooling's own primary first, then the six
   byte-identity-subject primaries (livespec, livespec-dev-tooling,
   livespec-driver-claude, livespec-orchestrator-beads-fabro, livespec-overseer,
   livespec-console-beads-fabro), then the four non-local members on their own
   hosts (driver-codex, driver-pi, orchestrator-git-jsonl, runtime). Leave
   openbrain/homelab alone (not byte-identity subject).
3. **Re-enable the auto-bump** once every primary is on the new body and
   reinstalled, so pin-freshness resumes its normal safety-net role.

Rejected alternatives, briefly: (A) let it flow and broadcast a
"run `just install-commit-refuse-hooks` after your next sync" heads-up — cheaper
but accepts silent fleet-wide local red hitting concurrent sessions mid-task;
(C) make the check tolerate old+new bodies during a migration window — contradicts
the ratified byte-identity decision that explicitly REMOVED migration tolerance as
a "fail-open hole" (the check's own docstring), so unavailable without a spec
change; (D) carry the reinstall inside the bump PR — impossible, because
`.git/hooks/` is a per-primary local artifact a merged PR cannot touch.

## One residual item (not blocking the decision)

This analysis rests on the inference that the daily sweep's pin-autodiscovery
treats `livespec-dev-tooling` as a discoverable source for the `[tool.uv.sources]`
format (the dispatch handler demonstrably does — its autodiscovery enumerates that
format). If the maintainer wants belt-and-suspenders before Phase 0, confirm the
sweep's source list includes the dev-tooling git source; but the
`sibling-released` dispatch path alone already establishes the auto-bump, so the
decision does not hinge on it.

## Scope boundary

Investigation only. No automation was paused, no pin bumped, no release cut, no
installer re-run. The plan stays paused at `next_action: human`; this note exists
so the maintainer's Phase-0 go/no-go is made with decision #4 resolved rather than
flagged.
