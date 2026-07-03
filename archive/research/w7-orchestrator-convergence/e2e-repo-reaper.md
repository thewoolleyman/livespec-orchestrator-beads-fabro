# W7 e2e-repo Mechanical Fail-Safe Reaper

This note is the runbook for `orchestrator-image/reap-e2e-repos.sh` (ledger
item `livespec-zkmn.1.2`): the mechanical fail-safe that sweeps orphaned
throwaway GitHub repos left behind by W7 dark-factory end-to-end acceptance
runs.

## What it reaps

The acceptance runs create throwaway GitHub repos named `livespec-e2e-*` inside
a dedicated, disposable GitHub org named `livespec-e2e`. A crashed run, a killed
Fabro sandbox, or an interrupted teardown can leave such repos orphaned. The
reaper lists the org, selects only repos matching the throwaway pattern, and
deletes the eligible ones.

## Safety model

- **Org-scoped by construction.** The script only ever lists and deletes repos
  in the `livespec-e2e` org, and within that org only repos whose name matches
  `^livespec-e2e-`. It can never touch a repo outside that org or a non-matching
  repo inside it.
- **Age-gated by default.** A repo is eligible only when BOTH its `createdAt`
  and `pushedAt` are older than `--max-age` minutes (default `120`). The newest
  of the two timestamps gates eligibility, so a repo belonging to an in-progress
  acceptance run — freshly created OR freshly pushed — is NOT reaped.
  `--max-age 0` (alias `--force-all`) disables the age gate and deletes every
  matching repo; use it only for a deliberate full teardown of the disposable
  org.
- **Dry-run first.** `--dry-run` lists exactly what WOULD be deleted and deletes
  nothing. It is the safe preview.
- **Idempotent + race-tolerant deletes.** See the create-on-disk race below.
- **Secret hygiene.** The org-scoped fine-grained token is read by byte count
  only; its value is never printed. Any `github_pat_...` / `gh?_...` token-shaped
  substring in tool output is redacted before display.

## "Never reap during an active dispatch" discipline

This reaper is for **session-start, post-confirmed-merge, deliberate teardown,
and scheduled fail-safe** use — **NOT mid-dispatch**. Deleting a repo that a
live Fabro sandbox is still cloning / pushing / PRing against would corrupt an
in-flight run. The age gate is the mechanical guard (an active run's repo is
fresh, so it is skipped), but the operational rule stands regardless of the
threshold: run this only when no dispatch is in flight against the org. This is
the same timing discipline the orchestrator's worktree reaper follows — reap at
boundaries, never in the middle of work.

## The create-on-disk race

`gh repo delete` (and the equivalent `gh api -X DELETE /repos/<owner>/<name>`)
issued immediately after a repo create can fail with:

```
HTTP 403: Repository cannot be deleted until it is done being created on disk
```

GitHub provisions the repo asynchronously; the delete races the provisioning.
The reaper therefore retries the delete with **bounded backoff** (default 5
attempts, ~3s apart, overridable via `REAP_E2E_DELETE_ATTEMPTS` /
`REAP_E2E_DELETE_BACKOFF_SECONDS`). A delete that returns `HTTP 404 Not Found`
(the repo is already gone) is treated as success, so the reaper is idempotent
and safe to re-run.

## Destructive-CLI gate co-edit

`gh repo delete` is on the `no_direct_destructive_cli` check's banned tuple
(per `livespec/SPECIFICATION/non-functional-requirements.md` §"Destructive-default
CLI wrapping"). That check scans `dev-tooling/`, `.claude-plugin/`, and
`.claude/plugins/`; the reaper script lives in `orchestrator-image/`, outside
those trees, so it is not directly scanned. Even so, this script and this
runbook are explicitly entered in the `[tool.livespec_dev_tooling]`
`destructive_cli_allowlist` in the repo root `pyproject.toml` so the wrapping is
documented and the runbook stays exempt if ever relocated.

Introducing that `[tool.livespec_dev_tooling]` block forced a second co-edit:
`livespec_dev_tooling.config.load_config` falls back to the livespec-core
historical layout only when the whole block is absent. The block is now present,
so the full core layout (`source_trees`, `mirror_pairings`, etc.) is restated
verbatim alongside the new `destructive_cli_allowlist` key, keeping every other
`load_config`-driven check bit-identical.

## Required env

The script requires one environment variable, normally supplied by the
1Password wrapper:

- `LIVESPEC_E2E_GITHUB_TOKEN` — a fine-grained token scoped to the
  `livespec-e2e` org (Administration / Contents / Pull-requests / Workflows RW).
  Mapped to `GH_TOKEN` for the `gh` calls. Presence is checked by byte count
  only; the value is never printed.

## Running

Dry-run (preview, deletes nothing):

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/reap-e2e-repos.sh --dry-run
```

Or via the justfile target (args after `--`):

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  mise exec -- just reap-e2e-repos -- --dry-run
```

Real reap with the default 120-minute age gate:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  mise exec -- just reap-e2e-repos
```

Full teardown of the disposable org (no age gate — deletes every matching repo):

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  mise exec -- just reap-e2e-repos -- --force-all
```

The script prints a summary line set: org, scanned, eligible, deleted, skipped,
failed. A non-zero `failed` count (a repo that could not be deleted after all
retries) makes the script exit non-zero.

## Validation evidence

A self-contained create → reap integration check was run under the 1Password
wrapper inside the disposable org:

- created two tiny private repos `livespec-e2e-reaper-selftest-<rand>` via
  `gh api -X POST /orgs/livespec-e2e/repos`;
- `reap-e2e-repos.sh --dry-run --max-age 0` LISTED both as `WOULD-DELETE`
  and deleted nothing;
- the real reap (`--max-age 0`) DELETED both, exercising the delete path with
  retry/backoff;
- the org was confirmed back to 0 repos at the end
  (`gh api /orgs/livespec-e2e/repos --jq length` → `0`).

No selftest repos were left behind and no repo outside `livespec-e2e` was
touched. All token handling was byte-count-only; no secret value was printed.
