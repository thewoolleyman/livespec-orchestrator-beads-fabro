# S5 valid-exception Red chronology

This note preserves the actual Red chronology for the valid attributed-size
exception assertion in `bd-ib-pwqxso`. The final Green commit's standard
`TDD-Red-*` trailers describe the last corrected replay; they do not, by
themselves, identify the original pre-product Red. Downstream proof must use
the chronology below and must not credit either later replay as a newly
authored pre-product Red.

## Git evidence and event order

| Time (UTC) | Evidence |
| --- | --- |
| 2026-10-09T23:05:17Z | Git created test-only Red commit `712653dc75ef0aadeabcc1ecb74f584648daed53`, whose parent is `88259ff4ef944b19a3ca64fb943279e402bc21eb`. Its only changed path is `tests/integration/test_factory_size_justification_gate_scenario153.py`. |
| 2026-10-09T23:06:36Z | The Red hook captured the failure for `test_valid_exception_waives_only_size_and_marks_successful_dispatch_telemetry`. The test-file checksum is `sha256:41d96e26172ff237fc64d8f59955be5539a87d9b0a8953b7c315a6211ddb1cc2`; the captured-output checksum is `sha256:54106d59a13fc45da6fb4726e0d7e98f09a77a0ce6ed521441fc1a7c54d8b496`. This is the original pre-product Red. |
| 2026-10-09T23:07–23:08Z | Factory tool events record the corresponding product edits after the original Red. Tool-event completion is not being used as evidence that a commit landed. |
| 2026-10-09T23:09:08Z | The reflog records a reset from `712653dc` to `88259ff4`; the original Red object remained recoverable. |
| 2026-10-09T23:09:12Z | Git created test-only commit `01a93b8b152d381344ed19bf4db41999750e4247`. Relative to `712653dc`, it changes only the disposable scenario fixture heading so that it includes `without waiving other gates`. Its hook capture time is 2026-10-09T23:10:28Z. This is a fixture-correction replay after product work had begun, not a new pre-product Red. |
| 2026-10-09T23:21:44Z | The reflog records a second reset to `88259ff4`. |
| 2026-10-09T23:21:56Z | Git created test-only commit `150f42d358cf1d4e812c4f3f73b77664cfcc3902`. Relative to `01a93b8b`, it removes the `_NoCommandRunner` test double and supplies an inert typed object to the already-unreached runner seam. Its hook capture time is 2026-10-09T23:23:53Z. This is a later test/style replay, not a new pre-product Red. |
| 2026-10-09T23:41:15Z | The retained Red was Green-amended to `0054290028c8299128ab96c05a75a292f5c22c25`. Its `TDD-Green-Parent-Reflog` names `150f42d3`, accurately describing that final replay while not superseding the original chronology above. |

The commit command completion events align with real Git objects and reflog
entries, but the objects and their trailers are the authority. No claim here
is based on command completion alone.

## Classification of the original failure

The original `712653dc` tree was exported to a disposable directory and its
single valid-exception test was replayed against the product tree that existed
at that commit. Pytest executed the test and failed at
`_assert_valid_size_decision` before reaching the scenario fixture:

```text
tests/integration/test_factory_size_justification_gate_scenario153.py:468:
    assert decision.disposition == "proceed"
E   AssertionError: assert 'decompose' == 'proceed'
1 failed
```

Therefore the first Red is a genuine behavioral failure: an attributed valid
exception did not waive the conditional size gate. It is not an unrelated
fixture failure. The scenario-heading correction fixed a latent disposable
fixture defect encountered later as the implementation advanced; it does not
rewrite or replace what the original Red proved. The runner-double removal is
likewise a later test/style correction.

The final test separately verifies that the same attributed exception does
not waive the ordinary acceptance-policy gate: an item with ungradeable
acceptance criteria remains `pending-approval` with
`ungradeable-acceptance-criteria`. Independent proof should exercise that
discriminator rather than inferring it from the size-gate success alone.

## Preservation

The implementation sandbox preserves the three objects at:

- `refs/recovery/bd-ib-pwqxso/original-valid-exception-red` → `712653dc75ef0aadeabcc1ecb74f584648daed53`
- `refs/recovery/bd-ib-pwqxso/fixture-correction-red` → `01a93b8b152d381344ed19bf4db41999750e4247`
- `refs/recovery/bd-ib-pwqxso/retained-replay-red` → `150f42d358cf1d4e812c4f3f73b77664cfcc3902`

This note is the durable branch-visible evidence. The recovery refs preserve
the exact local objects without changing the product history or presenting a
later replay as earlier work.
