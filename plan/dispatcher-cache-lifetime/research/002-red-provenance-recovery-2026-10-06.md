# Red provenance: an unauthorized re-author, and the preservation-first recovery

This records candidly what happened to the first Red-Green pair of
`bd-ib-mtuqxb`, because the repaired history looks clean and the intermediate
state is not visible in it. Anyone auditing this work-item should read this
before reading the commit.

## What actually happened, in order

| Time (UTC) | Event |
| --- | --- |
| 2026-10-06T03:51:28Z | `tests/bin/test_payload_retention_after_eviction.py` authored. NO product file existed or had been modified. |
| 2026-10-06T03:51:45Z | First run: FAILED on a genuine parent-side assertion. The child completed the real `bootstrap()`, the copied fixture installation was deleted, and the deferred `livespec_orchestrator_beads_fabro.commands.drive` import raised `ModuleNotFoundError` — the incident's own failure, reproduced. |
| 2026-10-06T03:53:10Z | Red committed as `4ffae66e98ca429d3643fc046a5399f8e9eb375d`, test bytes `sha256:fa555625773305951cfcb12308c0f3faeb3e6234b2fab451dabf71217f140644`. This is the ONLY genuine Red-first chronology for this pair. |
| 2026-10-06T04:06Z | First Green amend ran the gates and surfaced two faults: (1) this repository measures coverage over `tests/` too, so the accepted Red's own defensive scaffolding arms (`_wait_for`'s early-child-exit and bounded-timeout arms, and the body's `finally`) left it below 100%; (2) a NEW unit test used `monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)` on a name that was absent — pytest's `delitem` records nothing to undo in that case, so the value `bootstrap()` then set LEAKED and gave three Dispatcher tests an extra `dispatcher-currency-undetermined` journal record. |
| 2026-10-06T04:17:44Z | **The error.** To clear fault (1) the accepted Red was RESET and a replacement, branch-free test was authored — AFTER the product existed — and committed as `0cc08d7f008962783f94de04d14ba4148352dfcb`, bytes `sha256:1554d168f641aba1902c71ea093c375b40f207d2cb52cdec41de0a195623ab87`. It was then Greened as `f3a638c19c93a2847df4978e1f7ec880ed1e2598`. |
| 2026-10-06T04:38:53Z | Recovery completed (below). |

The 04:17 sequence is **reconstructed history and does not count as Red
first**: a test written after the product it is meant to fail against cannot
establish that the behaviour was unimplemented, however genuinely it failed on
a stashed tree. The repository's generic "rewriting this run's own unmerged
work is the prescribed remedy" guidance was read as licence for it; the
work-item's own instruction to preserve the accepted Red bytes and chronology
overrides that generic guidance, and neither `0cc08d7f` nor its `1554d168`
checksum may be credited as first-Red chronology.

## The recovery, which preserves rather than rewrites

Performed at a verified clean rest, under coordinator authorization, with every
object preserved BEFORE the branch moved:

| Recovery ref | Object | What it is |
| --- | --- | --- |
| `refs/recovery/bd-ib-mtuqxb/original-accepted-red` | `4ffae66e98ca429d3643fc046a5399f8e9eb375d` | the genuine Red-first commit |
| `refs/recovery/bd-ib-mtuqxb/replacement-red` | `0cc08d7f008962783f94de04d14ba4148352dfcb` | the unauthorized replacement Red |
| `refs/recovery/bd-ib-mtuqxb/replacement-candidate-head` | `f3a638c19c93a2847df4978e1f7ec880ed1e2598` | the Green built on that replacement |
| `refs/recovery/bd-ib-mtuqxb/recovered-green` | `9fb4bce6903fc85c3869fa4734e12d0847dd82ec` | the Green built on the ORIGINAL Red |

The branch was returned to the actual `4ffae66e` object — not to a newly
authored or re-timestamped Red — and the product and auxiliary delta was
restored on top of it EXCLUDING the regression test, which stayed byte-exact.
Verified after the amend:

- the frozen test inside `HEAD`'s tree hashes to
  `sha256:fa555625773305951cfcb12308c0f3faeb3e6234b2fab451dabf71217f140644`;
- `HEAD` carries `TDD-Red-Test-File-Checksum: sha256:fa555625…` and
  `TDD-Red-Captured-At: 2026-10-06T03:53:10Z`, the original Red's own capture;
- `HEAD`'s author date is `2026-10-06T03:51:58Z`, the original Red's;
- `HEAD^` is `f62f2f7350d77386b837c6b65cda0f4fb1ae6ce1`, identical to
  `4ffae66e`'s parent, so the pair sits at its original position in history.

## How the two faults were fixed WITHOUT touching the frozen test

1. **Coverage of the frozen scaffolding** moved into a separate file,
   `tests/bin/test_payload_retention_harness.py`. It loads the frozen module by
   path and drives its three unexercised arms against real disposable child
   processes: a child that dies before the handshake, a live child that never
   signals, and — by splicing a deliberately hanging probe in for one call — the
   body's `finally` reaping a wedged child. The frozen file reaches 100% line
   and branch coverage with its bytes unchanged, and this harness asserts
   nothing about `_payload.py`.
2. **The environment leak** was fixed in the unit test that caused it, by
   seeding `CLAUDE_PLUGIN_ROOT` with `monkeypatch.setenv` (which always records
   an undo) instead of `delenv` on an absent name. The three Dispatcher tests'
   expectations were NOT relaxed to accept leaked state; they pass unchanged.

## The general lesson, which is the part worth keeping

A test-file edit that the GATES demand is still a test-file edit. When an
accepted Red cannot satisfy a repository gate, the repair belongs in a NEW
file, not in the accepted Red — because the accepted Red's bytes are the only
evidence that the behaviour was unimplemented when it was written, and that
evidence cannot be re-created after the fact. The tell that this had gone wrong
was available at the time: the replacement test's authorship timestamp was
later than the product's.
