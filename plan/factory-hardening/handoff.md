# Handoff — factory-hardening

## What this thread is

Reliability hardening of the **dark-factory dispatch path** — the two failure
modes that each cost a real dispatch cycle during the `codex-credential-broker`
track (epic `bd-ib-rck`, CLOSED) and were filed as out-of-scope follow-ups. Both
are **factory-safe** (in-repo Python/prose/config, no outward-facing upstream
fabro work), so per the maintainer's standing directive they should be **dispatched
through the factory, not hand-built**. Neither touches credential logic; this
thread is independent of `credential-freshness-redesign`.

## ▶ CURRENT STATE + NEXT ACTION (read this first)

**Status: both items filed, BLOCKED on autonomy-tiering.** They pass the intake
Definition-of-Ready on every axis except one — they carry **no explicit autonomy
tier** yet (`autonomy_tiered = False`), which is a deliberate human sign-off gate
before an unattended factory dispatch. That is why they are not already running.

**Next action (maintainer):** assign an autonomy tier to each so they clear the
Definition-of-Ready → `ready`, then dispatch each through the factory
(`dispatcher.py dispatch --item <id>`). They do not depend on each other.

## Ledger items

| Item | Status | What |
|---|---|---|
| **`bd-ib-bwgko4`** | BLOCKED (needs-tier) | pr node: rebase onto fresh `origin/master` before push — kill the stale-workflow push-gate race. |
| **`bd-ib-wmqsn7`** | BLOCKED (needs-tier) | `check-master-ci-green`: tolerate a transient/re-runnable master-CI flake instead of fail-closing every dispatch. |

## Root cause #1 — stale-workflow push-gate race (`bd-ib-bwgko4`)

The `implement-work-item` **pr node**
(`.claude-plugin/.fabro/workflows/implement-work-item/prompts/pr.md`) does a plain
`git push HEAD:refs/heads/feat/<id>` with **no rebase** onto latest master. GitHub
rejects a pushed branch whose `.github/workflows/` state differs from the **current
default branch** unless the push token carries `workflows:write` — and the fabro
git-push origin token is **hardcoded to `{contents:write}`** in
`resolve_clone_credentials` (`fabro-github/src/lib.rs`), independent of
`github_permissions`. So neither `workflow.toml
[run.integrations.github.permissions]` NOR an App/installation `workflows:write`
grant reaches the push token. When a pin-bump (e.g. `bump-pin-from-dispatch.yml`)
lands on master **during** a run, the branch's workflow file goes stale and the
push is rejected: *"GitHub App cannot create or update workflow ... without
workflows permission."*

- **First hit:** W2 `bd-ib-fcipkv`, 2026-07-15 — recovered only by re-dispatch in a
  quiet window (`fabro rm -f` + reset + re-dispatch → PR #662).
- **Fix:** have the pr node fetch + rebase the branch onto fresh `origin/master`
  before pushing (prose-only change to `pr.md`) so workflow files always match
  master and the gate never fires.
- **Acceptance:** a dispatch whose run straddles a `.github/workflows/` change on
  master still publishes cleanly.

## Root cause #2 — inherited master-CI flake fail-closes all dispatches (`bd-ib-wmqsn7`)

The janitor's `just check` includes **`check-master-ci-green`**, which reads the
**latest** master CI run's conclusion. A single transient CI-infra flake — commonly
`uv sync` timing out downloading cpython from GitHub — on the latest master run
reddens it and **fail-closes every dispatch's janitor**, regardless of the branch
under test.

- **First hit:** W3 `bd-ib-6xv5l5`, 2026-07-15 — recovered by `gh run rerun <id>`
  (FULL re-run; the `--failed` variant was refused *"run cannot be rerun; its
  workflow file may be broken"*) to green, then re-dispatch → PR #664.
- **Fix (options to evaluate):** retry the flaky network fetch in `ci.yml`
  (uv/cpython download), and/or make the gate distinguish a **stale/re-runnable red
  run** from a genuine repo failure.
- **Acceptance:** a transient master-CI network flake no longer stalls all factory
  dispatches.

## Related

- Parent track (closed): `plan/archive/codex-credential-broker/handoff.md` (epic
  `bd-ib-rck`). Both items were surfaced there but are out of that epic's scope.
- Sibling thread: `plan/credential-freshness-redesign/handoff.md` — independent; no
  code dependency.
