# Relay plan reference artifacts

These are preserved, unmerged work products. They are kept as REFERENCE for
re-dispatched factory runs. They are not code to apply blindly and not proof
of any behavior.

## `zi5ygh-run-01M4HQQZJCNP5HZ89M80PYCHXK-implement.diff`

- **Source:** `stages/003-implement@1/diff.patch` of Fabro run
  `01M4HQQZJCNP5HZ89M80PYCHXK` for `bd-ib-zi5ygh`. It was retrieved on
  2026-10-12 with `fabro dump 01M4HQQZJCNP5HZ89M80PYCHXK --server
  https://hp-xubuntu.perch-rudd.ts.net:32276`.
- **Integrity:** SHA256
  `912547bd44e7029e6966d6581d45f31be2b1a4d2d7ed5143e7da62a32645dea9`, which
  equals the preservation record on `bd-ib-zi5ygh`.
- **Base:** commit `71d4e6a38c4295e5b1db26fe356c7af843e84f36`, 156 commits
  behind master on 2026-10-12. It does not apply cleanly to current master
  (`.claude-plugin/prose/plan.md` conflicts).
- **How the run ended:** "ACP turn failed", a transient agent failure, after
  which the run was routed to needs-human. The commit structure, including
  its Red and Green trailers, was not preserved. Only this tree diff
  survives.
- **Contents:** Scenario 147 and 148 work across the plan pointer writers, the
  progress event, decision, resume and recovery modules, the drive diagnosis
  action, and five integration test files.
- **Known invalid or defective parts, as recorded on the item:**
  - `plan_progress_lock` in `_plan_progress_operation.py` binds a Linux
    abstract socket. That fence is host-scoped and is invalid under the
    2026-10-12 multi-host ruling (see `.ai/ledger-writers-are-multi-host.md`).
  - The diagnosis handler crashes on a missing `next_action` and on a legacy
    pointer.
  - Causal host recovery was registered but never executed.
  - Earlier review: `validate_causal_recovery` accepted unsupported operations.

Re-implement from this through ordinary Red/Green on current master, on top
of the token-chain foundation `bd-ib-wdl577`. Never commit it wholesale.

## `lhzpam-run-01M4V41PFPB6Q3YZN4WDXSMQM9-implement.diff`

- **Source:** `stages/003-implement@1/diff.patch` of Fabro run
  `01M4V41PFPB6Q3YZN4WDXSMQM9` for `bd-ib-lhzpam`. It was retrieved on
  2026-10-13 with `fabro dump 01M4V41PFPB6Q3YZN4WDXSMQM9 --server
  https://hp-xubuntu.perch-rudd.ts.net:32276`.
- **Integrity:** SHA256
  `01ab825ae6c8dc27ea6e3432be72f70057242f15523831571ec5be4369b1932d`.
- **Base:** commit `3083427c08456539603778fdfd67d28546944347` (v0.196.0). It
  applies cleanly to master `26523727`.
- **How the run ended:** the implement stage hit the Claude subscription
  session limit at 2026-10-13T20:44Z and the run was routed to needs-human.
  Nothing was pushed. Only this tree diff survives; no Red and Green commit
  structure was preserved.
- **Contents:** a new `_plan_record_genesis.py`, genesis calls from
  `create_thread` in `plan.py` and from the plan-record migration, and unit
  and integration tests for both paths.

## `22yfvh-run-01M4V41PD6GSQ01PQ7XJ0ATZH7-implement.diff`

- **Source:** `stages/003-implement@1/diff.patch` of Fabro run
  `01M4V41PD6GSQ01PQ7XJ0ATZH7` for `bd-ib-22yfvh`, retrieved the same way on
  2026-10-13.
- **Integrity:** SHA256
  `183664864c5bbf75df1af4c2c92d282b956dd64f9a635aaa5145623e1467373c`.
- **Base:** commit `3083427c08456539603778fdfd67d28546944347` (v0.196.0). It
  applies cleanly to master `26523727`.
- **How the run ended:** the same session limit, at 2026-10-13T20:50Z. Nothing
  was pushed.
- **Contents:** new `_plan_recovery_receipts.py` and
  `_plan_recovery_receipt_write.py` modules and one test file. The diff does
  not yet wire the receipt writes into the executed recovery path, so the
  re-run must finish that wiring.

Neither diff was reviewed or checked by `just check`. Re-implement from them
through ordinary Red/Green; never commit either wholesale.
