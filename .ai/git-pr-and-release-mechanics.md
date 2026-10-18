# Git, pull-request and release mechanics in this repository

Traps in the worktree, pull-request, merge and release path that have each
shipped a change without its content, or reported landed work as unlanded.
Migrated from Claude Code auto-memory notes on 2026-10-18 (plan
`block-auto-memory-coverage`); dates are those of the original measurement.

## Arm auto-merge only after the last push

Never arm `gh pr merge --rebase --auto` until the branch is final. A commit
pushed after auto-merge is armed can miss the merge, which fires on the earlier
tip. It fails in the direction that looks like success: the PR shows
`state=MERGED`, `gh pr view --json commits` lists only what merged, and the
orphaned commit stays on the remote branch. Measured 2026-08-22 on PR #1752:
two commits pushed, one merged, `2367db02` left on origin, noticed only because
a grep for the second note's heading on master returned 0.

If it has happened, the commit is not lost; it is on `origin/<branch>`.
Cherry-pick it onto a fresh branch from master and open a second PR; do not
force-push the merged branch. Delete the stale remote branch afterwards from a
worktree, because `git push --delete` from the primary checkout is refused by
the commit-refuse hook. Verify every landing with a content grep on master,
never with the PR's merged state.

## `CLAUDE.md` is a symlink: stage `AGENTS.md`

The root `CLAUDE.md` (and `.claude/CLAUDE.md`) is a symlink to `AGENTS.md`.
Editing through the `CLAUDE.md` path changes `AGENTS.md`, but
`git add CLAUDE.md` stages only the unchanged link, so the commit lands
without the edit while `git status` still shows ` M AGENTS.md`. Measured
2026-10-01: plan-archive commit `e1969af4` shipped without its guidance
paragraph and needed a second PR (#2543) after the first had auto-merged.
Always `git add AGENTS.md` and read `git show --stat HEAD` for `AGENTS.md`
before pushing. Do not remove a worktree or branch until the PR reports
MERGED: a push after auto-merge deleted the branch is refused with "cannot lock
ref".

## Every `spec/*` branch reads unmerged; verify a proposal by its history directory

The propose-change in-flight survey (`git branch -r --list 'origin/spec/*'`,
then `--no-merged origin/master`) listed all 19 remote `spec/*` branches as
unmerged on 2026-09-06, including `typed-repo-integration-contract` (landed as
v092) and `adopter-neutral-janitor-bootstrap` (landed as v087). This repository
rebase-merges, so branch SHAs never reach master and containment reports every
branch as unmerged forever; this is the same family as AGENTS.md's
"rebase-merged PR read through its series tip" trap. Treat the branch list as
the candidate set only, and decide each with a content check:
`find SPECIFICATION/history -path '*proposed_changes*' -name '<topic>*.md'`.
A hit means landed.

## Scenario reservations can be indented inside fenced blocks

To extract which scenario numbers each pending proposal in
`SPECIFICATION/proposed_changes/` reserves, allow leading whitespace:

    grep -oE '^[[:space:]]*## Scenario [0-9]+' <file>

An anchored `grep -o '^## Scenario [0-9]*'` returns a clean `none` for any
proposal that declares its scenarios indented inside a fenced block. Measured
2026-08-29: that pattern reported `none` for `factory-headroom-preflight.md`,
which reserved 62 and 63, while being correct on the other three pending files,
which is why it read as reliable; the resulting false claim reached three
sessions. Do not grep for mere mentions either, which sweeps up prose
citations of ratified scenarios. Read what each file claims, and re-derive the
gap set from `scenarios.md` directly; riders inside proposals name stale gap
lists.

## An agent cannot land a `.github/workflows/` change

Any change under `.github/workflows/` is refused at pre-push by
`dev-tooling/check-no-workflow-edits.sh` (maintainer rule 2026-09-04) unless it
carries a tracked `.livespec-workflow-edit-exemption` (one `work_item=` line,
one `reason=` line) AND that item carries the label `approval:workflow-edit`,
which the footgun hook denies to agents. The guard has no environment or flag
escape, by design: the factory must never land workflow edits autonomously.
When a fix needs a workflow edit, split it: land everything else, declare the
CI-visible gap the sanctioned way (for `check-ci-matrix-completeness`,
`repo_local_ci_skips` entries marked PROVISIONAL naming the follow-up), and
file the workflow edit as a blocked needs-human item for the maintainer to
label. Discovered 2026-09-30 (`bd-ib-74sqh7` holds that instance's wiring).

## Consumers pin this plugin to the moving `release` branch

"Pin the plugin in all fleet repos" needs no committed change in those repos.
Measured 2026-08-27 across all 12 consumers, and re-checked here on
2026-10-18: each `.claude/settings.json` pins
`{"source":"github","repo":"thewoolleyman/livespec-orchestrator-beads-fabro","ref":"release"}`,
a moving branch rather than a tag or SHA. Propagation is automatic: a merge to
master leads release-please to publish a release; `release: published` fires
`.github/workflows/fast-forward-release-branch.yml`, which fast-forwards
`refs/heads/release` to the released commit (a plain push, so it fails loudly
rather than rewriting); consumers resolve the new commit when their
project-scope plugin install refreshes. To verify a fix reached a consumer,
confirm `release` advanced, then content-grep that repo's installed plugin
cache; do not hunt for a pin file or open bump PRs. `pin-freshness.yml` and
`bump-pin-from-dispatch.yml` serve sources pinned by tag, not this plugin.
