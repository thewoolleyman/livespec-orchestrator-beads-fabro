# 011: Closing out the fork preservation, with nothing removed (2026-10-18)

This note covers work item bd-ib-433fcr. It closes the item under coordinator ruling R169, option (A). That option re-verifies the preservation recorded in research note 009, lists every kept branch with a one-line recovery purpose, and removes nothing.

The bundle that gated the item, bd-ib-sxcnj7, closed `host_verified` on 2026-10-18. Retiring disposable branches on `thewoolleyman/fabro` (option B) was NOT admitted. It is outward-facing and cannot be undone on the forge, so it is the maintainer's call, filed as maintainer item 35 on epic bd-ib-6tcjfx.

All measurements below were taken on vps on 2026-10-18 between 11:44Z and 11:50Z.

## Outgoing carrier tip and bullet 3

The Definition of Done asks that the outgoing carrier tip be retained as a tag on origin before `factory-integration` is rewritten.

- The tag is present on origin. `git ls-remote --tags` returns `refs/tags/carrier-8869e88-pre-rebuild-2026-10-10` as annotated tag object `9b5dc98b`. It dereferences to `8869e88b2f7e383ec6fceb8d3f6f928dd0339b34`, the 0.254 carrier that still serves production `:32276`.
- `factory-integration` was never rewritten. Fork PR 11 moved it to `28a65c091b814a4f52d6b31432fd239794b725bd`, a `git merge -s ours 8869e88b2` commit on top of `adeefec4c`, and that move is a fast-forward. `git merge-base --is-ancestor 8869e88b2 28a65c09` exits 0, so the outgoing tip is still reachable from the branch itself as well as from the tag.
- Bullet 3 is therefore satisfied in substance. The tag exists on origin, and the event it guarded against, losing the outgoing tip when the branch is rewritten, cannot occur on this history.

## Origin heads now, compared with the 009 freeze

`git ls-remote origin 'refs/heads/*'` returns 17 heads.

- Of the 15 distinct heads frozen in note 009, 14 are byte-unchanged.
- `factory-integration` moved from `8869e88b2` to `28a65c091`, as described above.
- Two heads are new since the freeze, and both come from the bundle work:
  - `carrier-petri-v0.382` at `adeefec4c`;
  - `integrate-v0.382-adeefec` at `28a65c091`, which is fork PR 11's head branch.
- No head was removed.

## Preservation artifacts

All of these live under `/home/ubuntu/.local/state/fabro-ref-backups/2026-10-10-pre-carrier-rebuild/`.

- `sha256sum -c SHA256SUMS` reports OK for all 15 listed files. `SHA256SUMS` itself hashes to `b1b7e11405055e006d56923465c949bf41af5daeb57f05ea32439e397653cb78`.
- `git bundle verify all-refs.bundle` reports a complete history.
- All eight `preserve-2026-10-10/<sha>` tags are present in the fork clone, and each resolves to its own commit: `2575ab85`, `2e002d51`, `3b378188`, `497aaba6`, `7b9b8b96`, `8869e88b`, `af624d5d` and `da277a4e`.
- 14 of the 17 current origin heads are commits in the bundle. The three that are not were created after the freeze and are live on origin: `carrier-petri-v0.382`, `factory-integration` and `integrate-v0.382-adeefec`.

## Restore test, re-run

I ran `git clone --no-checkout all-refs.bundle` into a scratch directory and checked out two worktrees from that clone.

- **instrument-v0254.** I detached at `497aaba6`, applied `instrument-v0254.unstaged.patch`, and extracted `instrument-v0254.untracked.tgz`. `git status --porcelain` then lists exactly the 16 paths recorded in note 009: 15 modified files plus the untracked `lib/crates/fabro-cli/src/otel.rs`. The `target-glibc239/` build cache is excluded by design.
- **trial-rebase.** I detached at `7b9b8b96` and extracted `trial-rebase.files.tgz`. `sha256sum -c trial-rebase.files.sha256` reports OK for all 10 recorded dirty paths. `trial-rebase.rebase-state.tgz` holds the recorded 17 `rebase-merge` entries.

## What was removed since the freeze, and what covers it

No branch was removed, locally or on origin.

The six fork worktrees below were unregistered between 2026-10-10 and 2026-10-16, before bd-ib-sxcnj7 closed, by an actor who has not been identified. The FINDING comment on bd-ib-433fcr (2026-10-16T20:21Z, ruling R82) records this. Every one of them is covered by a preserve tag and by `all-refs.bundle`. The two dirty ones are also covered by the restore-tested artifacts above.

| Worktree | Recorded HEAD | Covering artifact |
| --- | --- | --- |
| `factory-integration` | `8869e88b2` | `preserve-2026-10-10/8869e88b…`, the origin tag `carrier-8869e88-pre-rebuild-2026-10-10`, and `all-refs.bundle` |
| `factory-wave-c` | `af624d5db` | `preserve-2026-10-10/af624d5d…` and `all-refs.bundle`. The directory still holds the shared cargo `target/` cache |
| `instrument-v0254` | `497aaba6f` | `preserve-2026-10-10/497aaba6…`, `all-refs.bundle`, and the `instrument-v0254.*` patch, list and archive. The directory still holds `target-glibc239/` |
| `trial-rebase` | `7b9b8b967` | `preserve-2026-10-10/7b9b8b96…`, `all-refs.bundle`, and the `trial-rebase.*` snapshot, index and rebase state |
| `verify-553` | `2575ab85f` | `preserve-2026-10-10/2575ab85…` and `all-refs.bundle` |
| `otlp-span-export` | `da277a4e5` | `preserve-2026-10-10/da277a4e…` and `all-refs.bundle`. The branch itself is still on origin |

Five worktrees are registered now. Four are clean: `/data/projects/fabro` on `fix/classify-provider-spend-limit-not-transient`, `carrier-petri-v0.382`, `clone-creds-pull-requests-scope` and `k8s-plugin-wiring-proto`. The fifth, `k8s-plugin-wiring`, carries one modified path. That is live work for bd-ib-n7zj4a, owned by the kubernetes-sandbox-backend session, and it is outside this item.

## Kept branches and their recovery purposes

All 17 origin heads are kept.

| Branch | Head | Recovery purpose |
| --- | --- | --- |
| `factory-integration` | `28a65c091` | The carrier the factory pins: the v0.382 bundle (sxcnj7), with legacy `8869e88b2` reachable as the second parent while `:32276` still serves it. |
| `carrier-petri-v0.382` | `adeefec4c` | The bundle's integration commit as its own branch, so the Petri carry set can be rebuilt or rebased without touching the carrier. |
| `integrate-v0.382-adeefec` | `28a65c091` | Head branch of merged fork PR 11. It identifies how the carrier reached its current tip. |
| `otlp-span-export` | `da277a4e5` | Head of the open upstream PR 576. bd-ib-njbg7j rewrites it after the cutover. |
| `fix/classify-provider-spend-limit-not-transient` | `3b3781888` | Head of upstream PR 688, which was closed on 2026-10-10. It keeps the closed proposal's code reachable. Retirement candidate under maintainer item 35. |
| `add-patch-cves-workflow` | `f53096264` | A maintainer branch from before this plan, not referenced by it. Kept for item 35's triage. |
| `ci/add-dylint-try-io-result` | `09e924b70` | A maintainer branch from before this plan, not referenced by it. Kept for item 35's triage. |
| `fabro-core` | `4c4471e63` | A maintainer branch from before this plan, not referenced by it. Kept for item 35's triage. |
| `failing-tests-pr116` | `89ecff48c` | A maintainer branch from before this plan, not referenced by it. Kept for item 35's triage. |
| `feat/docker-worker-runtime-poc` | `db453a11b` | A maintainer branch from before this plan, not referenced by it. Kept for item 35's triage. |
| `feat/llm-input-token-counting` | `4546e29b5` | A maintainer branch from before this plan, not referenced by it. Kept for item 35's triage. |
| `feat/vertex-adapter` | `74aaed261` | A maintainer branch from before this plan, not referenced by it. Kept for item 35's triage. |
| `fix/auto-pr-resolved-client` | `10419c726` | A maintainer branch from before this plan, not referenced by it. Kept for item 35's triage. |
| `fix/openai-compaction-tool-pairs` | `3cdb7859c` | A maintainer branch from before this plan, not referenced by it. Kept for item 35's triage. |
| `fix/remove-cli-dev-token-env` | `2668d1679` | A maintainer branch from before this plan, not referenced by it. Kept for item 35's triage. |
| `homepage-github-cta-fixes` | `dfda2c558` | A maintainer branch from before this plan, not referenced by it. Kept for item 35's triage. |
| `rule-files-sync-733cf9ca` | `67b2f3d03` | A maintainer branch from before this plan, not referenced by it. Kept for item 35's triage. |

Every head in the table that existed at the freeze is also in `all-refs.bundle`. So none of them depends on origin alone for recovery if item 35 later retires it.
