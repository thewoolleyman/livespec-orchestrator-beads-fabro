# fabro-currency P0 — fork hygiene and carrier inventory (2026-09-30)

This is the execution record for `bd-ib-kqbuju`. It supersedes the
approximate fork-ref counts in
`001-currency-assessment-2026-09-30.md` with an exact live inventory.

The remote cleanup is complete. The fork now has 15 purposeful branch heads,
down from 1,448. Its default branch is `factory-integration`; the divergent
fork `main` was retired, while local `main` now tracks `upstream/main`.
No open-PR head, unpublished branch, dirty worktree, or published commit was
rewritten.

The remaining local condition was resolved on 2026-10-01 after the maintainer
authorized preservation. The two unpublished files are committed byte-for-byte
on a local safety branch and exported in a complete recovery bundle. The
`factory-integration` worktree is clean at `8869e88b2`, aligned with origin.

## Ref manifests

The checked manifests are:

| Manifest | Rows | SHA-256 |
| --- | ---: | --- |
| `002-before-origin-refs.tsv` | 1,448 | `14699afff4410f569b2e603808d42402df25187077eba387ff8d4af13d29f817` |
| `002-after-origin-refs.tsv` | 15 | `e18e782fea1b4732052e379e5d7db8b4871b2f0c890433954cf9b4176f17dd79` |
| `002-deleted-origin-refs.tsv` | 1,433 | `5b538e60a83fb6fa83c8166d59ad670b8e04f98c587b34df3fab1cde72a7a724` |
| `002-before-local-refs.tsv` | 14 | `4f2a26d77690f98fba045e10df30c521b2ff1e0cd7bab4fdefd4c6099d9b3ccb` |
| `002-after-local-refs.tsv` (refreshed 2026-10-01) | 8 | `8c2736aaae0b6dc1cc252803c67a269975c0b332414092058d71e3168c8489e5` |

The remote delta is exact:

| Ref class | Before | Deleted | After |
| --- | ---: | ---: | ---: |
| `fabro/run/*` | 593 | 593 | 0 |
| `fabro/meta/*` | 828 | 828 | 0 |
| `arc/run/*` | 1 | 1 | 0 |
| Ordinary branch heads | 26 | 11 | 15 |
| **Total** | **1,448** | **1,433** | **15** |

The 11 removed ordinary heads were:

- merged or carrier-folded:
  `ask-fabro-welcome-prompts`,
  `config-smoke-daytona-environment`,
  `factory-wave-c`,
  `feat/configurable-checkpoint-commit-timeout`,
  `fix-center-size-column`,
  `fix/cewr4-compare-not-push`,
  `p2-fabro-log-decouple`,
  `push-credential-refresh-ahead`,
  `virtual-weaving-firefly`, and
  `worker-otel-reinject`;
- retired policy branch: `main`.

The 15 retained remote heads are the carrier
(`factory-integration`), the two open upstream PR heads
(`otlp-span-export` for #576 and
`fix/classify-provider-spend-limit-not-transient` for #688), and 12
branches whose unpublished or independent value was not disproved:
`add-patch-cves-workflow`, `ci/add-dylint-try-io-result`,
`fabro-core`, `failing-tests-pr116`,
`feat/docker-worker-runtime-poc`, `feat/llm-input-token-counting`,
`feat/vertex-adapter`, `fix/auto-pr-resolved-client`,
`fix/openai-compaction-tool-pairs`, `fix/remove-cli-dev-token-env`,
`homepage-github-cta-fixes`, and `rule-files-sync-733cf9ca`.

## Local cleanup and preserved work

The following seven redundant local branches were removed:
`factory-wave-b`, `factory-wave-c`,
`feat/configurable-checkpoint-commit-timeout`,
`fork-0254-backport`, `p2-fabro-log-decouple`,
`push-credential-refresh-ahead`, and `worker-otel-reinject`.
The clean `factory-wave-b` worktree was removed with its branch.

Local `main` was moved from stale `b5885b15d` to
`upstream/main` at `5879ebf09` and now tracks that authority.
`trial/factory-rebase` could not and was not removed because its worktree is
in an unresolved rebase. The following state was intentionally preserved:

- the original `factory-integration` modifications to
  `fabro-manifest/src/lib.rs` and `fabro-workflow/src/git.rs`, now preserved
  on `safety/factory-integration-unpublished-2026-10-01` at
  `61e6a4dfed458a4cb5b8c61b8734973d78f3982c`, with original parent
  `8de661118f24c43ad5b3516b9b7820525f5a5932`;
- `clone-creds-pull-requests-scope`, one unpublished commit ahead of its
  old base;
- open-PR worktrees `otlp-span-export` and
  `fix/classify-provider-spend-limit-not-transient`;
- unpublished `fork-selfhost`;
- the dirty `instrument-v0254` and `trial-rebase` worktrees;
- the clean detached `factory-wave-c` worktree used by the shared target
  cache and the `verify-553` measurement worktree.

The two dirty carrier-worktree files were additionally exported, without
changing the worktree, to:

`/home/ubuntu/.local/state/fabro-ref-backups/factory-integration-dirty-2026-09-30.patch`

Its SHA-256 is
`2532004c4b0b48260684d79b795c256631f0f446fe51fc42eb161e2e18fc0942`
and its size is 22,263 bytes.

On 2026-10-01 the live diff still matched that checksum. The safety commit's
diff matches it too, and its two blob ids match the original working files:
`73dcbf3bf86f5dcd3090c530cbc2d1c8341cabf8` (manifest) and
`2ab1493f1c410e90ce2a3893fbe3731acc34dd05` (workflow Git). The archival commit
was intentionally not merged or pushed: it preserves unpublished work, not a
reviewed change to the carrier. After verification, switching back to
`factory-integration` and merging `origin/factory-integration --ff-only`
advanced it by 18 already-published commits without a conflict.

The safety branch also has a verified complete-history bundle:
`/home/ubuntu/.local/state/fabro-ref-backups/factory-integration-unpublished-2026-10-01.bundle`,
SHA-256 `4a7d15b193fbea3100f2be13ee91aa7c63563e3323e2b0f77058ac37f91dd0c9`.
Restore it without publishing:

```bash
git fetch \
  /home/ubuntu/.local/state/fabro-ref-backups/factory-integration-unpublished-2026-10-01.bundle \
  refs/heads/safety/factory-integration-unpublished-2026-10-01:refs/heads/recovered/unpublished-origin-check
```

## Fork-main policy and recovery

The fork's default branch is now `factory-integration`. Remote `main` was
retired rather than kept as a second, misleading integration line. Local
`main` is the explicit upstream mirror and tracks `upstream/main`.

Every deleted remote ref remains in the complete Git bundle:

`/home/ubuntu/.local/state/fabro-ref-backups/fabro-origin-before-p0-2026-09-30.bundle`

Bundle SHA-256:
`da8685d9507530e9253c9a8b07f69e47cfd2a5da7cb854a85777bdd52b09fd22`.
`git bundle verify` reports complete history and 1,448 heads.

Restore one ref without publishing it:

```bash
git fetch \
  /home/ubuntu/.local/state/fabro-ref-backups/fabro-origin-before-p0-2026-09-30.bundle \
  refs/remotes/origin/main:refs/heads/recovered/main
```

Replace `main` in both positions with the required deleted branch. Inspect
the recovered branch, then republish only an intentional target with an
explicit refspec. To restore every head into a non-publishing namespace:

```bash
git fetch \
  /home/ubuntu/.local/state/fabro-ref-backups/fabro-origin-before-p0-2026-09-30.bundle \
  'refs/remotes/origin/*:refs/heads/recovered/origin/*'
```

The original patch can also be applied to a clean checkout of its original
base `8de661118`. The safety branch and bundle preserve that base explicitly;
applying the patch to today's carrier is not required for recovery.

## Carrier patch inventory

Observation anchor: `upstream/main` at `5879ebf09`
(`v0.371.0-nightly.0`). The live carrier is
`origin/factory-integration` at `8869e88b2`. It has 28 commits, not the
24 measured before `bd-ib-afcn3d` landed. At this anchor,
`git cherry upstream/main origin/factory-integration` reports 28 `+` and
zero `-`; merged-equivalent claims below therefore come from linked PR and
current-source evidence rather than patch-id equality.

Every review date below is within 30 days of this inventory. “Drop” means
exclude the legacy commit from the P6 release carrier after its named owner
has supplied the stated evidence; it does not authorize rewriting the
published branch.

| # | Commit | Capability | Upstream status at anchor | Proposed disposition | Owner | Review by |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | `f630c935` | Push-credential refresh | Upstream PR #568 merged; the pre-Petri workflow path was later replaced | Drop from the next carrier; validate native current credential handling | `bd-ib-sxcnj7` | 2026-10-14 |
| 2 | `f7ff19ee` | Configurable daemon readiness | No current upstream equivalent found | Reproduce on the qualified tag, then upstream to the owning component or keep only a dated temporary carry | `bd-ib-ik7sbn` | 2026-10-14 |
| 3 | `15b89ab0` | OTLP/HTTP export base | Upstream PR #576 remains open and is based on the old layout | Update, replace, or close #576 with a Petri-era owner and current tests | `bd-ib-lic3n3` | 2026-10-14 |
| 4 | `a4bcb3ff` | Forward OTLP config to workers | Fork-only follow-on; original worker seam changed | Replace through the selected Petri/Fabro telemetry design, then drop the legacy patch | `bd-ib-wo4m6o` | 2026-10-14 |
| 5 | `c543446f` | OTLP review hardening | Fork-only correction to #4 | Fold its assertions into the successor tests, then drop | `bd-ib-wo4m6o` | 2026-10-14 |
| 6 | `062abfa1` | Readiness clippy correction | Maintenance-only follow-on to #2 | Fold into the readiness successor or drop with the old implementation | `bd-ib-ik7sbn` | 2026-10-14 |
| 7 | `b651dbab` | Server/worker W3C traceparent | No patch-equivalent; original propagation seam changed | Re-establish correlation on the qualified architecture, then drop | `bd-ib-wo4m6o` | 2026-10-14 |
| 8 | `9048a8d5` | Decouple OTLP from `FABRO_LOG` | No patch-equivalent; the old logging integration changed | Preserve the behavioral assertion in successor telemetry tests, then drop | `bd-ib-wo4m6o` | 2026-10-14 |
| 9 | `b9b63a8a` | `run_turn` ACP span | No equivalent found; the old workflow engine was replaced | Implement at the current ACP/Petri seam and reconcile `bd-ib-z13s` | `bd-ib-wo4m6o` | 2026-10-14 |
| 10 | `8de66111` | Checkpoint commit timeout | Upstream PR #552 merged; checkpoint hooks are no longer used in the same way | Drop from the release carrier after candidate qualification | `bd-ib-sxcnj7` | 2026-10-14 |
| 11 | `56a14c87` | Traceparent capture-site guard | Test targets the replaced server seam | Port the invariant into current telemetry coverage, then drop | `bd-ib-wo4m6o` | 2026-10-14 |
| 12 | `23f137a4` | Wave A control-plane bundle | Host crates and several underlying seams were removed | Measure each surviving requirement in P3; route replacements to P4/P5 and drop the bundled patch | `bd-ib-4jzql3` | 2026-10-14 |
| 13 | `de5daadf` | Wave A review corrections | Corrections to the obsolete bundle | Preserve applicable assertions in P3/P4 tests, then drop | `bd-ib-4jzql3` | 2026-10-14 |
| 14 | `f3666a44` | Wave A hardening | Hardening for the obsolete bundle | Preserve applicable assertions in P3/P4 tests, then drop | `bd-ib-4jzql3` | 2026-10-14 |
| 15 | `90814196` | Legacy event documentation | Petri event payloads and ownership differ | Replace with typed current fixtures and documentation; drop the legacy-only edit | `bd-ib-227cbw` | 2026-10-14 |
| 16 | `18c4791e` | Wave B events/publish/permission bundle | Original workflow and ACP seams were replaced | Measure the three behaviors separately; retain only tested current successors | `bd-ib-4jzql3` | 2026-10-14 |
| 17 | `7b4e3f3d` | Wave B adversarial corrections | Corrections to #16, with no current patch-equivalent | Carry the fail-closed assertions into successor tests, then drop | `bd-ib-4jzql3` | 2026-10-14 |
| 18 | `29db0a23` | ACP ask-policy task and timeout | Old `fabro-acp` host seam was removed | Re-measure current ACP behavior; reimplement only a demonstrated gap | `bd-ib-4jzql3` | 2026-10-14 |
| 19 | `441854ae` | Wave C adversarial corrections | Corrections to #18 on the removed seam | Preserve applicable boundedness tests, then drop | `bd-ib-4jzql3` | 2026-10-14 |
| 20 | `af624d5d` | Wave C cancellation re-review | Corrections to #18 on the removed seam | Preserve cancellation assertions in current tests, then drop | `bd-ib-4jzql3` | 2026-10-14 |
| 21 | `977cb67a` | Compare origin instead of pushing | Partially superseded upstream; the stale tracking-ref case still needs a current-tag test | Re-test live-origin reachability; retain temporarily only if the current candidate still fails | `bd-ib-sxcnj7` | 2026-10-14 |
| 22 | `4b8cc85e` | Contain background ACP tasks | No equivalent established; old ACP implementation was removed | Reproduce under Petri/codex-acp and replace only if leakage remains | `bd-ib-4jzql3` | 2026-10-14 |
| 23 | `b5a329d1` | `acp.fallback_chain` | No upstream equivalent; Petri rejects this legacy attribute | Rebase onto a supported Petri extension or revise the commitment; do not deploy legacy S4 by default | `bd-ib-r5cnjd` | 2026-10-14 |
| 24 | `20bf91e0` | Fallback-chain clippy fix | Maintenance-only follow-on to #23 | Fold into the approved successor or drop with S4 | `bd-ib-r5cnjd` | 2026-10-14 |
| 25 | `908116cc` | Candidate model/effort selection | No Petri equivalent established; depends on legacy S4 | Re-examine with P3 evidence; port through a supported protocol or route spec revision | `bd-ib-r5cnjd` | 2026-10-14 |
| 26 | `933c0e32` | Typed refusal and advertisement check | Review correction to #25 | Fold into any approved successor's typed tests; otherwise drop | `bd-ib-r5cnjd` | 2026-10-14 |
| 27 | `2d23fa96` | Null refusal/model-reset check | Review correction to #25 | Fold into any approved successor's typed tests; otherwise drop | `bd-ib-r5cnjd` | 2026-10-14 |
| 28 | `8869e88b` | Final candidate-config hardening | Review correction to #25 | Fold into any approved successor's typed tests; otherwise drop | `bd-ib-r5cnjd` | 2026-10-14 |

## Verification and remaining action

Verified after cleanup:

- GitHub reports `factory-integration` as the default branch.
- `git ls-remote --heads origin` returns exactly 15 heads.
- No `fabro/run/*`, `fabro/meta/*`, or `arc/run/*` head remains.
- Both open upstream PR heads remain reachable.
- Local `main` is clean at `upstream/main`.
- Local `factory-integration` is clean and equals its origin authority.
- The safety commit preserves both original blobs and the original diff hash.
- The temporary cleanup worktree and branch were removed.
- The recovery bundle verifies as complete.

No product source changed, so no Fabro product test was warranted for this
ref-only operation.

The local alignment and preservation complete P0's ref-hygiene assertions.
The work item's lifecycle and acceptance remain authoritative in the ledger.
The in-session exception is `mutates-host-machinery`: this work changes host
Git references and research records, not factory product source.
