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

## Review-fix telemetry Red correction

The later review-fix telemetry Red needs a separate provenance account. The
initial test copied from the sandbox at approximately 02:14Z called
`size_justified_at_admission(..., dispatch_id=...)` directly. Git object
`5d4cdaea023c49d0c493dff9be0dce2b739d926d` preserves that exact test-only
commit over parent `dd436b9c5d54b00ce2944ce9c3cb13381548b782`; its test SHA-256 is
`04e9a3cb739d49872bd258368f015f608c78ff12c04495117975e09ebc6dce8f`.
The commit's 02:15:41Z hook trailers record a collection error (captured-output
SHA-256 `5dd847689e6dc5b516c0966817f74045ffea4f3edff8cdee0cd264d0f47407a2`),
not a behavioral failure.

An operator replay against the exact retained 45,005-byte WIP overlay (SHA-256
`20c5c80579c2c57a2cbe6ae3f6f83f36226d507ef5ad9b87441b94cf972407e1`)
failed at line 135 with `TypeError: unexpected keyword argument 'dispatch_id'`
(exit 1; one failed in 3.94 seconds). That initial attempt is an interface
failure, not a behavioral Red, and the successful 02:15:41 commit alone is not
evidence otherwise. An independent replay of the same test bytes over the same
verified WIP bytes reproduced that TypeError (exit 1; one failed in 1.24
seconds). Neither replay is classified as behavioral Red.

The later test-only object `56db7b3c6b4d1ab2fe53849306bcedd15447e123`
contains a signature adapter that the initial test did not. Its parent is
`dd436b9c5d54b00ce2944ce9c3cb13381548b782`; that bare parent does not export
the reader, so a bare-tree replay is also not behavioral evidence. Replaying
the adapted object over the retained WIP reached assertions but first failed
`None is False` for a different ordinary item. This is a later correction, not
the initial Red and not the required stale-true discriminator.

The corrected frozen regression now calls the recovered WIP's existing
two-argument API directly. It records one justified decision, observes the
positive control, then offers ordinary decisions for an interleaved item and
the original item. The WIP writer omits both false decisions and its item-scoped
reader reuses the earlier true. A minimal interface-compatible prerequisite
retaining exactly that writer and reader is preserved verbatim in
`s5-telemetry-red-prerequisite-2026-10-10.py.txt`; its SHA-256 is
`343e26659c97e96bb96233506a967b0c544a3f6355f398c4082c186a82d4eb04`.
The corrected test's pre-hook SHA-256 was
`a12b7704b55912e57e66faf2e76798b583e5db2873573c360fbf8d8945fe2d60`.

The resulting behavioral failure is retained in human-readable form in
`s5-telemetry-red-output-2026-10-10.txt` (normalized-text SHA-256
`9c2f3191b1000a1945a7b8d7036e4658b9964679f3d2009fe63e285866f35299`).
The exact bytes, including pytest's whitespace-only source lines, are retained
as Base64 in `s5-telemetry-red-output-2026-10-10.txt.b64`; decoding them yields
SHA-256 `30d2da70d7cc986ef7e420b857a69dd8290717cdc1f9f5c8f47c01c9ee0d5bfa`.
The later ordinary admission reads the earlier justified admission and fails
with `AssertionError: assert True is False`. That manual replay is evidence for
the corrected assertion and prerequisite only.

The normal Red hook then formatted the test without changing its behavior and
committed the frozen test alone as
`d89352cf2ea5a7fb02d6b53aaa6103d60e14b039`. Its current-time trailers record
the frozen test SHA-256
`391bee019e8eb6ab2d4a37d03e56ae40dde9c0d2d4b6f0833565508d2082c8f0`,
captured-output SHA-256
`32d42a42c972f2a3fd3ec26ce0e42b61c4f85d4c973984b29690413a02f610d5`,
and capture time `2026-10-10T03:59:03Z`. A post-commit replay failed at line
78 with the same `AssertionError: assert True is False`. This is the behavioral
review-fix Red; no TypeError, import error, or `None is False` result is being
substituted for it.

The exact initial interface-failure object is anchored separately at
`refs/recovery/bd-ib-pwqxso/initial-interface-failure-red`. That preservation
does not promote its collection failure or its WIP-overlay TypeError into the
behavioral Red established by the corrected two-argument regression.
The hook-captured behavioral object is anchored at
`refs/recovery/bd-ib-pwqxso/review-fix-behavioral-red`.
