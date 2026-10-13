# Checkpoint-commit-hook-failures plan reference artifacts

These are preserved, unmerged work products. They are kept as REFERENCE for
re-dispatched factory runs. They are not code to apply blindly and not proof
of any behavior.

## `6jkjzm-run-01M4TNNJR0XR3BBRV7QDV4BBXV-implement.diff`

- **Source:** `stages/003-implement@1/diff.patch` of Fabro run
  `01M4TNNJR0XR3BBRV7QDV4BBXV` for `bd-ib-6jkjzm`. It was retrieved on
  2026-10-13 with `fabro dump 01M4TNNJR0XR3BBRV7QDV4BBXV --server
  https://hp-xubuntu.perch-rudd.ts.net:32276`.
- **Integrity:** SHA256
  `80a04bf2be9073c1a8c6860e4d562a9884d74dfe6e458db1a7cc355b5d7505cb`. The
  item carries no preserve-by-reference record for this run, because the
  run's Dispatcher died during a ledger outage before journaling an outcome,
  so this digest was taken at retrieval.
- **Base:** commit `0475b130e1688dfae82a2d21da52c64e7dc49983`. Against master
  `dedb2b09` (10 commits later), `git apply --check` fails ONLY on
  `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/CLAUDE.md`,
  the directory index; every other file applies cleanly.
- **How the run ended:** implement finished (two attempts), and the run's
  janitor `just check` passed all 93 targets on this tree. `publish_draft`
  then failed refreshing onto origin/master on a content conflict in that
  same `CLAUDE.md` index, and nothing was pushed. The commit structure,
  including its Red and Green trailers, was not preserved. Only this tree
  diff survives.
- **Contents:** the Scenario 170 failed engine checkpoint commit attribution:
  the `Failed targets` / failed-hook-command recognizer
  (`_fabro_failed_targets.py`), the `checkpoint.failed` event and engine
  failure-message readers, the typed checkpoint-failure record and its
  attribution, the outcome detail, the `livespec-checkpoint-failure` ledger
  comment, the `checkpoint-failure` journal row, the blocked / needs-human
  disposition wired into the fabro terminal mapping, and seven test files.

It was never reviewed. Re-implement from it through ordinary Red/Green on
current master, re-resolving the `CLAUDE.md` index entries against the
current file; never commit it wholesale.
