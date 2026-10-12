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
