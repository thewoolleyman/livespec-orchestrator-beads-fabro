# 009 — fork preservation before the carrier rebuild (2026-10-10)

Work item bd-ib-433fcr. Recorded by the fabro-currency plan session before `factory-integration` on thewoolleyman/fabro is rebuilt onto the candidate tag. Nothing was deleted; every artifact below exists so the rebuild and the later cleanup can be undone or audited. Deletion of worktrees and branches waits until bd-ib-sxcnj7 closes, per the item's Definition of Done.

## Outgoing carrier tip, retained as a tag on origin

- `factory-integration` tip at freeze: `8869e88b2f7e383ec6fceb8d3f6f928dd0339b34` (the 0.254 carrier serving hp).
- Annotated tag pushed to origin: `carrier-8869e88-pre-rebuild-2026-10-10`, pointing at that commit.

## Origin heads at freeze (18)

| SHA | ref |
| --- | --- |
| `f53096264c57830973591faef355f0f889927190` | `refs/heads/add-patch-cves-workflow` |
| `09e924b70d1f18debb1817eb7726fd834dd2b8d5` | `refs/heads/ci/add-dylint-try-io-result` |
| `4c4471e630dfe0fd311834de8d4e5f966d582f4b` | `refs/heads/fabro-core` |
| `8869e88b2f7e383ec6fceb8d3f6f928dd0339b34` | `refs/heads/factory-integration` |
| `89ecff48cb60a4736cf5033720b6650f1720312a` | `refs/heads/failing-tests-pr116` |
| `db453a11b253f04c102d70d300705427f96a41c0` | `refs/heads/feat/docker-worker-runtime-poc` |
| `4546e29b5f125f03508ce49a9b14995039a5e584` | `refs/heads/feat/llm-input-token-counting` |
| `74aaed26114aaee66fc9011e36b93704bceeb7b6` | `refs/heads/feat/vertex-adapter` |
| `10419c7264352d5b0f57cf940d8add05907b7ec2` | `refs/heads/fix/auto-pr-resolved-client` |
| `3b37818887c8daf80bbb28fb6e30056a32b22db1` | `refs/heads/fix/classify-provider-spend-limit-not-transient` |
| `3cdb7859ce4be08111371a88ca6a04076effb649` | `refs/heads/fix/openai-compaction-tool-pairs` |
| `2668d16799f3fae89e6e0cbc73d0e97ea47e7aa9` | `refs/heads/fix/remove-cli-dev-token-env` |
| `dfda2c558b48a8cad96d44a0dd2ef464db2b4c4a` | `refs/heads/homepage-github-cta-fixes` |
| `da277a4e5945e98827866fb407b7aa1d28a1d4d8` | `refs/heads/otlp-span-export` |
| `67b2f3d037bd84d733cce789103570997492cde3` | `refs/heads/rule-files-sync-733cf9ca` |
| `3b37818887c8daf80bbb28fb6e30056a32b22db1` | `refs/heads/fix/classify-provider-spend-limit-not-transient /data/projects/fabro` |
| `2e002d51308d9074c8e937e19185f490839f1b95` | `refs/heads/clone-creds-pull-requests-scope /home/ubuntu/.worktrees/fabro/clone-creds-pull-requests-scope` |
| `da277a4e5945e98827866fb407b7aa1d28a1d4d8` | `refs/heads/otlp-span-export /home/ubuntu/.worktrees/fabro/otlp-span-export` |

The two upstream PR heads are `otlp-span-export` (PR 576, needed again by bd-ib-njbg7j) and `fix/classify-provider-spend-limit-not-transient` (PR 688). The remaining ordinary branches are retained unchanged until the post-bundle triage, when each kept branch receives its one-line recovery purpose and the rest are deleted against this inventory.

## Local worktrees at freeze (5)

| HEAD | branch | path |
| --- | --- | --- |
| `8869e88b2f7e383ec6fceb8d3f6f928dd0339b34` | `(detached)` | `/home/ubuntu/.worktrees/fabro/factory-integration` |
| `af624d5db3da0548fb5d01aeffabfe2e6602951d` | `(detached)` | `/home/ubuntu/.worktrees/fabro/factory-wave-c` |
| `497aaba6f20c1fac052346c39f52e08fabadb179` | `(detached)` | `/home/ubuntu/.worktrees/fabro/instrument-v0254` |
| `7b9b8b96704f19aa6929bea84164d6138aa1a6fe` | `(detached)` | `/home/ubuntu/.worktrees/fabro/trial-rebase` |
| `2575ab85fc56cf248e4314d12926d2ee6823819b` | `(detached)` | `/home/ubuntu/.worktrees/fabro/verify-553` |

Eight distinct worktree heads are preserved as local tags `refs/tags/preserve-2026-10-10/<sha>` in the fork clone so the bundle below carries them; detached heads are otherwise not refs and a `--all` bundle would omit them (measured: the first bundle was 174 bytes).

## Dirty worktrees

```text
# dirty files per worktree
## /data/projects/fabro (0)
## /home/ubuntu/.worktrees/fabro/clone-creds-pull-requests-scope (0)
## /home/ubuntu/.worktrees/fabro/factory-integration (0)
## /home/ubuntu/.worktrees/fabro/factory-wave-c (0)
## /home/ubuntu/.worktrees/fabro/instrument-v0254 (17)
 M Cargo.lock
 M Cargo.toml
 M lib/crates/fabro-cli/Cargo.toml
 M lib/crates/fabro-cli/src/logging.rs
 M lib/crates/fabro-cli/src/main.rs
 M lib/crates/fabro-cli/src/shared/github.rs
 M lib/crates/fabro-github/src/lib.rs
 M lib/crates/fabro-sandbox/src/daytona/mod.rs
 M lib/crates/fabro-sandbox/src/docker.rs
 M lib/crates/fabro-sandbox/src/sandbox.rs
 M lib/crates/fabro-server/src/spawn_env.rs
 M lib/crates/fabro-workflow/src/github_token_source.rs
 M lib/crates/fabro-workflow/src/handler/llm/acp.rs
 M lib/crates/fabro-workflow/src/pipeline/initialize.rs
 M lib/crates/fabro-workflow/src/services.rs
?? lib/crates/fabro-cli/src/otel.rs
?? target-glibc239/
## /home/ubuntu/.worktrees/fabro/otlp-span-export (0)
## /home/ubuntu/.worktrees/fabro/trial-rebase (10)
M  Cargo.lock
M  lib/apps/fabro-cli/src/commands/run/mod.rs
M  lib/apps/fabro-cli/src/otel.rs
M  lib/apps/fabro-server/src/lib.rs
UA lib/apps/fabro-server/src/otel_propagation.rs
UU lib/apps/fabro-server/src/server.rs
UU lib/apps/fabro-server/src/server/tests.rs
M  lib/apps/fabro-server/src/worker_runtime.rs
DU lib/crates/fabro-server/Cargo.toml
M  lib/foundation/fabro-static/src/env_vars.rs
## /home/ubuntu/.worktrees/fabro/verify-553 (0)
```

`instrument-v0254`: 16 tracked modifications plus one untracked source file (`lib/crates/fabro-cli/src/otel.rs`); its untracked `target-glibc239/` build cache (7,312 files) is excluded by design. `trial-rebase`: an interactive rebase in progress onto `2575ab85f` with 7 of its commands done, index entries `DU`, `UA`, `UU` and six staged modifications; its state is preserved as a content snapshot plus the index and rebase directory, because a conflicted index cannot be reproduced by `git apply`.

## Preservation artifacts

Directory: `/home/ubuntu/.local/state/fabro-ref-backups/2026-10-10-pre-carrier-rebuild/`. Digests (sha256, first 16 hex) from `SHA256SUMS`:

| sha256 | file |
| --- | --- |
| `66d2df18be78943b` | `all-refs.bundle` |
| `e3b0c44298fc1c14` | `instrument-v0254.staged.patch` |
| `962a5135b8715d98` | `instrument-v0254.unstaged.patch` |
| `01428abb5308e23b` | `trial-rebase.staged.patch` |
| `79e6f341ed01cd82` | `trial-rebase.unstaged.patch` |
| `bd8b162e92612dea` | `instrument-v0254.untracked.tgz` |
| `9e4bb2f8729bf308` | `trial-rebase.files.tgz` |
| `b49c47b7cd6de5f4` | `trial-rebase.rebase-state.tgz` |
| `85cea451eec057fa` | `trial-rebase.untracked.tgz` |
| `27f1bd384816d3f3` | `instrument-v0254.untracked.list` |
| `6f0877dde72676be` | `trial-rebase.dirty-paths.list` |
| `e3b0c44298fc1c14` | `trial-rebase.untracked.list` |
| `31a63dad0995fdf0` | `trial-rebase.index` |
| `835e36d7c35810b1` | `trial-rebase.files.sha256` |
| `58addfcc5ab14ecc` | `inventory.md` |

- `all-refs.bundle`: every ref of the fork clone plus the eight preserve tags (1,750 heads, 182,144,974 bytes); `git bundle verify` passes.
- `instrument-v0254.unstaged.patch`, `.untracked.list`, `.untracked.tgz`: the worktree's modifications and its one untracked source file.
- `trial-rebase.files.tgz` + `trial-rebase.files.sha256`: content snapshot of all 10 dirty paths; `trial-rebase.index`: the worktree index; `trial-rebase.rebase-state.tgz`: the `rebase-merge` directory (17 entries); the `.staged.patch` and `.unstaged.patch` are kept for reference but do not apply cleanly on a conflicted index.

## Restore test

Run 2026-10-10 into a scratch clone of `all-refs.bundle`:

- `instrument-v0254`: checkout `497aaba6f`, apply the unstaged patch, extract the untracked archive; the restored dirty path set equals the recorded one (16 paths, build cache excluded by design).
- `trial-rebase`: checkout `7b9b8b967`, extract `files.tgz`; `sha256sum -c` over all 10 files passes. The rebase can be resumed by restoring the index and `rebase-merge` directory into a linked worktree's git directory (`git rev-parse --git-path`).

## Earlier preservation this note does not replace

Research note 002 (2026-09-30): `factory-integration-dirty-2026-09-30.patch` (sha256 2532004c…), `factory-integration-unpublished-2026-10-01.bundle` (sha256 4a7d15b1…) and the pre-P0 origin bundle (sha256 da8685d9…) remain valid and are not superseded.
