# Red provenance, cycles 9 to 11: two late baseline replays, and one clean pair

This is ADDITIVE to `002-red-provenance-recovery-2026-10-06.md`, which records
the cycle-1 incident and its preservation-first recovery. Nothing here
reconstructs history: every object named below still exists under
`refs/recovery/bd-ib-mtuqxb/`, and the corrections are made in prose rather
than by moving any ref.

Read this before crediting any Red in cycles 9 or 10 as Red-first. Two of them
are not, and the commit messages on them say otherwise.

## Why this record is necessary

The commit trailers cannot settle chronology. `red_green_replay` inspects the
STAGED TREE at commit time: it proves the staged test failed against the
on-disk product at that moment, which a test authored after the product and
run against a reverted working tree satisfies perfectly. So a mechanically
valid `TDD-Red-*` block is consistent with both a genuine Red-first cycle and
a late replay against a restored baseline. Only a timeline distinguishes them,
and only prose can carry it.

## Cycle 9 — a flawed Red, corrected late

| Time (UTC) | Event |
| --- | --- |
| before 2026-10-06T06:52:52Z | The product for this cycle ALREADY EXISTED on disk. |
| 2026-10-06T06:52:52Z | That product was saved aside and the working tree reverted to a product-unmodified baseline. |
| — | Original Red `23fe6f11`, frozen test bytes `3ccfbdbe`, was FLAWED: it carried an assertion about a sibling that could not hold, and its `TMPDIR` fallback case failed at the wrong stage, so what it demonstrated was not what it claimed. |
| — | Corrected test authored; replacement Red `01a6729d` / `e91b33a1`. |
| 2026-10-06T07:05:27Z | Green `9103dd40`, clean. |

**`01a6729d` / `e91b33a1` is a LATE BASELINE REPLAY, not original Red first.**
The corrected test was authored after the product for the cycle had already
been written once, and it was run against a reverted tree rather than against
a tree that had never carried the implementation. The evidence it produces is
useful — it does establish that the corrected assertions fail without the
product — but it cannot establish that the behaviour was unimplemented when
the test was conceived. Preserved objects: `cycle-9-red-mispremised`,
`cycle-9-corrected-red`, `cycle-9-corrected-green`.

## Cycle 10 — a Red that configured no floor, and a false chronology claim

The original Red here had two genuine executing-identity failures, so it was
not worthless. But its third case was inert, and the reason is worth recording
because it is a fixture trap that returns a clean pass:

**the floor key was written at the TOP LEVEL of `.livespec.jsonc`, where it is
not read.** The floor resolves at `<plugin-block>.dispatcher.minimum_release`.
A top-level `dispatcher` block configures NO floor at all, so
`minimum_release_verdict` returned `None`, and the case asserted nothing while
looking exactly like a case that asserted something.

| Time (UTC) | Event |
| --- | --- |
| — | Original Red `3cd7c2af`, frozen bytes `2e179f7e`. Two genuine executing-identity failures; the floor case configured no floor. |
| 2026-10-06T07:11:18Z | Product for the cycle WRITTEN. |
| 2026-10-06T07:12:33Z | Product saved aside and reverted. |
| 2026-10-06T07:13:26Z | Corrected test authored — i.e. AFTER the product had been written. |
| 2026-10-06T07:14:55Z | Replacement Red `6ffc077e` accepted, with the product unmodified on disk. |
| 2026-10-06T07:49:13Z | Green `c795a789`. Full aggregate: all 89 targets passed, 2 of 91 declared skipped. |

### The correction

`6ffc077e`'s own commit body says the correction was made "with the product
UNMODIFIED, before any implementation". **The second half of that is false
chronology.** The product had been written at 07:11:18 and reverted at
07:12:33, and the corrected test was authored at 07:13:26. The working tree
was indeed product-unmodified when the Red was captured — that part is true,
and it is what the hook verified — but "before any implementation" describes a
state that had already been passed through.

So cycle 10's corrected Red is, like cycle 9's, a **late baseline replay**. Its
positive value is real and worth stating precisely: the corrected fixture now
PROVES the floor is armed (it asserts `floor_configured`) rather than assuming
it, which is exactly the check whose absence made the original case inert. That
is a genuine improvement in the evidence. It is not Red-first chronology.

Preserved objects: `cycle-10-red-mispremised`, `cycle-10-corrected-red`,
`cycle-10-green-c795a789`, and `cycle-10-green10b-stash`.

## Cycle 11 — a clean Red-first pair

Recorded here as the contrast, and because its method is the one the two
incidents above lacked: **the defect was measured against the unmodified
product before any test was written.**

| Time (UTC) | Event |
| --- | --- |
| 2026-10-06T07:58Z | With the product unmodified, `retain_payload` was measured directly: install A at release 7.1.0 published its payload, and a call explicitly naming install B at 9.9.9 returned A's payload — 7.1.0 executing where 9.9.9 was named. A second measurement showed an inherited payload displacing this project's own source checkout. Both measurements also confirmed the legitimate hand-down still worked, so the fixture was known sound before it was a test. |
| 2026-10-06T07:58:05Z | Test authored; run with the product unmodified (only the untracked test file present). Two cases failed on genuine assertions; the two hand-down controls passed. |
| 2026-10-06T07:59:59Z | Red `d7ad3740`, `pytest_returncode: 1`, "test failed at Red moment as required". |
| 2026-10-06T08:20:29Z | Green `921654da`. Full aggregate: all 89 targets passed, 2 of 91 declared skipped. |

One thing this cycle got wrong and the suite caught, which belongs on the
record: the first implementation compared the selected source only against the
payload's recorded ORIGIN, which broke every owned helper. A `scripts/bin/`
helper spawned from inside the payload resolves its own plugin root to the
payload tree, so it names the payload as its source and matched nothing — it
copied the copy. The frozen end-to-end lifetime regression failed on exactly
that, and the fix was to accept the payload itself as a qualifying source. A
unit-only cycle would have shipped the flaw.

## What is NOT a Red, stated plainly

Four artifacts in this work-item are supplemental and must never be cited as
Red-Green evidence:

| Artifact | Status |
| --- | --- |
| `_dispatcher_currency_probe.py` extraction (in cycle 10's Green) | Size-forced cohesion extraction. No nested Red commit. Structural guard only. |
| `_payload_grading.py` extraction (in cycle 11's Green) | Same: recording the payload's source took `_payload.py` past its 250 LLOC hard ceiling, so the grading layer was cut out by cohesion. `test_payload_grading.py` is a structural guard, not a Red. |
| `test_payload_public_cli_routes_after_eviction.py` | Authored after the pairs it covers; passed on first write. Its own docstring says so. |
| `test_payload_public_route_exact_outcomes.py` | Same. Its value is the pre-fix control, not a Red. |

A structural file-presence assertion is not public behaviour proof, and none of
the above should be read as one.

## Mis-aimed instruments hit this session, and what discriminated them

Each produced a clean, plausible, WRONG answer at exit 0. Recorded because the
cost of each was a wrong conclusion, not an error message.

- **An interrupted aggregate read as a result.** The 07:39:13 run died with its
  actor mid-pytest at ~60%. Its log ends without a verdict. It was re-run
  rather than credited; the greens cited above are from runs that printed a
  verdict on the bytes being committed.
- **A 751-pass belonging to a previous candidate.** Pass counts do not transfer
  across candidate trees. Each Green above was gated on its own aggregate.
- **A probe that could not reach what it was aimed at.** The first public-route
  probe exported only `BEADS_DOLT_PASSWORD`, so the direct Dispatcher route
  died in the credential stage at exit 3 — the SAME exit code the floor refusal
  produces. It looked like a floor result and was not. Discriminated by reading
  the stderr rather than the exit code, which named the two missing secrets.
- **A refusal reached before the one under test.** With secrets fixed, both
  routes stopped at the factory-binary gate and then at the git-worktree
  preflight, both in `dispatch_preamble`, AHEAD of the floor — again at exit 3.
  Discriminated by the refusal text; cleared with the repository's own
  committed `dispatcher.step_waivers` escape.
- **A diagnostic glob that matched pytest's `current` symlink.** A `cat` over
  `basetemp/*/...` concatenated two copies of the same file, which read as a
  config written twice (invalid JSON) and a child that ran twice. Both were
  artifacts of the glob. Discriminated by byte-counting the individual files.
- **A `.git` at the pytest basetemp root.** `git -C <tmp_path>/install rev-parse
  --absolute-git-dir` answered `<basetemp>/.git`, so EVERY `tmp_path` install
  resolved as a git checkout and took the currency gate's checkout exemption —
  the floor was never evaluated, and the intact control read as a product
  failure. It also meant the evicted cases were dodging the exemption by
  deletion rather than by genuinely not being a checkout. Fixed by placing the
  fixture installation outside the pytest tree, and the fixture now ASSERTS the
  installation is not a checkout so this cannot recur unnoticed.

## Operational disclosure

While diagnosing the checkout exemption, `env | grep -i '^GIT'` was run in this
sandbox. The repository's own verification discipline forbids exactly that —
a line-oriented filter over environment variables cannot distinguish a value's
internal newlines from record boundaries, and the prescribed form is
`printenv NAME | wc -c`. The command printed a live `GITHUB_TOKEN` and a
single-line `GITHUB_PRIVATE_KEY` into the session transcript. No secret was
written to any file in the repository, and none appears in any commit; the
exposure is the transcript. **Those two credentials should be treated as
disclosed and rotated.** Recorded here rather than left in the transcript
alone, because a disclosure that only exists where it leaked is not a
disclosure.

## What a successor should take from this

1. **Measure the defect against the unmodified product before writing the
   test.** That is the only thing that makes a Red genuine, and it is what
   cycles 9 and 10 skipped and cycle 11 did.
2. **Prove the fixture is ARMED.** Cycle 10's inert floor case is the pattern:
   assert the precondition you depend on (`floor_configured`, "this install is
   not a checkout") or your case can assert nothing while passing.
3. **An exit code is not an outcome.** Exit 3 was produced in this work-item by
   a credential failure, a factory-binary gate, a worktree preflight, a floor
   refusal, and a floor that could not be evaluated. Only the text separates
   them.
4. **Do not credit a trailer as chronology.** The hook grades the staged tree,
   not the order in which the work actually happened.
