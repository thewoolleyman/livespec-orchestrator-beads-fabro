# Watching master CI for a dispatch window — the gating job is `ci-green`

This note records which job the dispatcher's green-master preflight actually
gates on, and the three ways a hand-rolled master-CI watcher gets a confident
wrong answer about it. It exists because none of this is derivable from
`AGENTS.md`: nothing there names `ci-green`, so an agent watching master CI for
a dispatch window has no way to learn which job decides the dispatch short of
reading a dispatch-journal record.

## The gating job

The green-master preflight resolves the pipeline it proves green from the typed
repository-integration contract: the workflow from `dispatcher.master_ci.workflow`
and the aggregate job from `dispatcher.master_ci.job`. For this repository those
resolve to `CI` and `ci-green`.

Be precise about WHERE `ci-green` comes from, because the two arms print
differently in a refusal and in the journal. This repository does **not** commit
a `dispatcher.master_ci` block in `.livespec.jsonc`; the key is absent, so both
halves resolve on the `fleet-default` arm to the declared fleet convention —
whose committed values, in
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_integration_defaults.py`,
are `MASTER_CI_WORKFLOW_DEFAULT = "CI"` and `MASTER_CI_JOB_DEFAULT = "ci-green"`.
Measured 2026-09-07 by calling `resolve_master_ci_pipeline(cwd=Path("."))`:
`MasterCiPipeline(workflow='CI', job='ci-green', resolution='default', defect=None)`.
The effective gating job is `ci-green` either way; only the arm differs.

The same two values ride every dispatch record. In a `stage: dispatch-id` row of
`tmp/fabro-dispatch-journal.jsonl` they are
`integration_contract.fields.master_ci_job` and `.master_ci_workflow`, each
carrying its `key` (`dispatcher.master_ci.job`), its `arm` (`declared`,
`fleet-default`, or `defective`) and its `value`.

## The near miss: an anchored filter that cannot match the gating job

Measured 2026-09-06 by the plan `pluggable-factory-workflow-configs` session.
Watching master CI for a dispatch window, the watcher filtered check-runs with
the anchored pattern `^(check-|e2e|acceptance)`. That pattern **cannot match**
`ci-green`. The watcher reported GREEN and master was in fact green, so the
answer was right and the instrument was blind: had `ci-green` failed while the
`check-` family passed, it would have reported GREEN falsely, and the dispatch
would then have met a preflight refusal the watcher said could not happen.

This is the catalogued "instrument that cannot return a hit, reporting no hits"
family from `AGENTS.md`. The remedy is cheap and has two acceptable forms: name
the gating job explicitly, or filter nothing.

## The full check-run population on a master commit

A master-branch head carries 21 check-runs. Twenty come from the `CI` workflow
and one from `Release Please`:

- `check-lint (root)`, `check-lint (nonroot)`, `check-format (root)`,
  `check-format (nonroot)`, `check-types (root)`, `check-types (nonroot)` — the
  `check-python` matrix, whose display name is `<target> (<uid>)`.
- `check-per-file-coverage (root)`, `check-per-file-coverage (nonroot)`.
- `check-coverage (root)`, `check-coverage (nonroot)`.
- `check-python-batch (root)`, `check-python-batch (nonroot)`.
- `check-doctor-static`.
- `check-red-green-replay`, `check-check-coverage-incremental` — the
  `check-metadata` matrix, whose display name is the bare target.
- `check-metadata-batch`.
- `e2e-cli`.
- `acceptance`.
- `export-telemetry` — push-only, and deliberately NOT in `ci-green`'s `needs:`,
  so it is not a gate.
- `ci-green` — the aggregate, and the sole required context on branch
  protection. It `needs:` every gating job and fails if any of them failed or
  was cancelled.
- `release-please` — from `.github/workflows/release-please.yml`, a separate
  workflow, so it never appears in a `--workflow=CI` reading at all.

Note what that list does to a name filter. `ci-green` shares no prefix with the
`check-` family, `e2e-cli`, `acceptance`, `export-telemetry` or `release-please`,
so any pattern assembled from the names an operator happens to remember is
overwhelmingly likely to exclude the one job that decides the dispatch.

## Query the check-runs endpoint, and filter nothing

Read every check-run on the commit, sorted, with no name filter — the gating job
cannot be excluded by a pattern that does not exist:

```bash
gh api "repos/{owner}/{repo}/commits/$(git rev-parse origin/master)/check-runs?per_page=100" \
  --jq '.check_runs[] | "\(.status)\t\(.conclusion // "-")\t\(.name)"' | sort -k3
```

Cross-check the population size against the endpoint's own count, so a truncated
page reads as a truncated page rather than as a clean set:

```bash
gh api "repos/{owner}/{repo}/commits/$(git rev-parse origin/master)/check-runs?per_page=100" \
  --jq '.total_count'
```

If you do want a one-line answer rather than the full listing, name the gating
job — never an anchored family pattern:

```bash
gh api "repos/{owner}/{repo}/commits/$(git rev-parse origin/master)/check-runs?per_page=100" \
  --jq '.check_runs[] | select(.name == "ci-green") | "\(.status)\t\(.conclusion)"'
```

An empty result from that last query is itself a finding: it means `ci-green` is
not on the commit yet, which is not the same as green.

## `gh run list` and the check-runs endpoint can disagree

Measured 2026-09-06 in the same session: `gh run list --workflow=CI --branch master`
reported the run `in_progress` while all 21 check-runs on that same commit,
`ci-green` included, were already `completed` / `success`. When the two surfaces
disagree, the per-commit check-runs endpoint —
`repos/{owner}/{repo}/commits/<sha>/check-runs` — is the one the preflight's
question maps onto, because the preflight's question is per-commit and
per-job: did the aggregate job `ci-green` conclude `success` on the default
branch head.

Know the second-order consequence before you act on the check-runs reading,
because it cuts the other way. The preflight's own instrument is
`gh run list --branch <default-branch> --limit 1 --workflow CI --json status,conclusion,databaseId`
followed by `gh run view <id> --json jobs`, and it treats a latest run whose
status is `queued`, `in_progress`, `waiting`, `pending` or `requested` as an
UNPROVABLE refusal — "the latest run `<id>` is still `<status>`" — not as a
pass. So a watcher that sees green check-runs while `gh run list` still says
`in_progress` should expect the dispatch to be refused as unprovable, not
admitted. Read both surfaces: the check-runs endpoint answers whether the
gating job passed, and the run-list surface answers whether the preflight will
consider the question settled.

## A merge to master re-queues CI, so a green window is perishable

Every merge to master starts a new `CI` run on the new head, so a green window
closes the moment any pull request lands. During the 2026-09-06 session a green
window on one head was consumed by the next merge before a dispatch could take
it.

Two practical consequences. First, a green reading is bound to the SHA it was
taken on: record the SHA with the reading, and re-take it if master has moved
before you dispatch. Second, "master is green" is not a stable state to wait
for on a busy branch — pair the reading with the dispatch attempt rather than
treating it as a precondition you can establish and then rely on.
