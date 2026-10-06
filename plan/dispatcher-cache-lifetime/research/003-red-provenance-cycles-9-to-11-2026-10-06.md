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

## Cycle 10 — a Red whose floor case failed on a wrong premise

The original Red ran **3 failed, 1 passed**. Two of those three were genuine
executing-identity failures, so the Red was not worthless. The third was the
floor case, and the distinction between it and the other two is the whole
point of this entry.

**The floor key was written at the TOP LEVEL of `.livespec.jsonc`, where it is
not read.** The floor resolves at `<plugin-block>.dispatcher.minimum_release`;
a top-level `dispatcher` block configures NO floor at all, so
`minimum_release_verdict` returned `None`.

That case therefore **FAILED on a WRONG PREMISE** — it did not silently pass,
and it did not assert nothing. An earlier revision of this report said both of
those things; **both are retracted.** The case failed because the fixture had
armed no floor, not because the behaviour under test was unimplemented, which
is a failing test measuring the wrong thing. That is a different fault from a
vacuous pass and it has a different remedy: a vacuous case needs an assertion,
whereas this one needed its FIXTURE corrected — which is what the replacement
did by asserting `floor_configured` rather than assuming it.

Keep that separate from the two genuine identity failures in the same run. A
reader tallying "the original Red failed" would otherwise credit all three as
evidence the behaviour was unimplemented, when only two of them were.

| Time (UTC) | Event |
| --- | --- |
| — | Original Red `3cd7c2af`, frozen bytes `2e179f7e`. Result 3 failed / 1 passed: two genuine executing-identity failures, plus the floor case failing on a wrong premise because no floor was configured. |
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
it, which is exactly the check whose absence let the original case fail on a
wrong premise. That is a genuine improvement in the evidence. It is not
Red-first chronology.

ONE SUPERSEDED FRAMING SURVIVES IN A PLACE THIS REPORT CANNOT EDIT. The frozen
cycle-10 Red (`tests/bin/test_payload_executing_release_identity.py`, bytes
`ab15b57c…`) carries an inline comment describing the first draft of its floor
case as having "asserted nothing at all". That wording is superseded by the
correction above — the draft case FAILED, on a wrong premise — but the file's
bytes are frozen across its Red-Green pair and MUST NOT be edited to say so.
A reader who meets the two accounts should take THIS report as authoritative
and leave the frozen bytes alone.

Preserved objects: `cycle-10-red-mispremised`, `cycle-10-corrected-red`,
`cycle-10-green-c795a789`, and `cycle-10-green10b-stash`.

## Cycle 11 — a clean Red-first pair

Recorded here as the contrast. What makes it Red-first is the thing the rule
actually requires: **a VALID behavioural failing test was authored and run
before the first corresponding product edit.** Cycles 9 and 10 did not have
that; this cycle did.

The disposable measurements it happens to have run beforehand are NOT what
qualifies it, and an earlier revision of this report said they were. See the
rule correction below.

| Time (UTC) | Event |
| --- | --- |
| before 07:57:59.649Z | Disposable measurements against the unmodified product: install A at release 7.1.0 published its payload, and a call explicitly naming install B at 9.9.9 returned A's payload — 7.1.0 executing where 9.9.9 was named; a second showed an inherited payload displacing this project's own source checkout; both confirmed the legitimate hand-down still worked. Useful for aiming the fixture. NOT a precondition of Red-first. |
| 2026-10-06T07:57:59.649Z | Test file WRITTEN. |
| 2026-10-06T07:58:07.016Z | First pytest result, product unmodified (only the untracked test file present). Two cases failed on genuine assertions; the two hand-down controls passed. |
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

## Cycle 12 — a second clean Red-first pair, on the Codex candidate root

Red-first in the same sense cycle 11 was — a valid behavioural failing test
authored and run before the first corresponding product edit — and it found a
defect the whole existing candidate-boundary regression structurally could not
see. (It also probed first, as cycle 11 did. That remains a fixture-aiming
technique, not what makes either cycle conforming.)

`test_payload_candidate_and_credential_boundary.py` asserts that `plugin_root()`
keeps naming the INSTALLED tree while assets resolve inside the payload — but it
sets `CLAUDE_PLUGIN_ROOT` on every child, so it only ever exercises the Claude
path, where the harness hands us the installation. **Normal Codex exports
nothing.** There `plugin_root()` fell through to `parents[3]`, which after
retention walks up from a module loaded out of the PAYLOAD.

| Time (UTC) | Event |
| --- | --- |
| 2026-10-06T08:49Z | Measured against the unmodified launcher with a real child and no `CLAUDE_PLUGIN_ROOT`: `plugin_root` and `executing_payload_root` BOTH reported `/tmp/…-payload-7.1.0-46ij91l5/payload`, while the installation at `/tmp/probe-codex-root-…/0123abc` was named by neither. |
| 2026-10-06T08:52:03Z | Red `dfdcde8d`, `pytest_returncode: 1`. One genuine assertion failure; three controls passing. |
| 2026-10-06T09:05:08Z | Green `5c54e83c`. Full aggregate: all 89 targets passed, 2 of 91 declared skipped. |

The collapse is what `plugin_root()`'s own docstring warns of — "every one of
those comparisons the running build against itself". The downstream costs are
REASONED CONSEQUENCES of the two roots being equal, not outcomes this cycle
observed: the self-update canary cannot validate the update it exists for, the
registered-install finding compares the registry against the payload, a floor
refusal names a disposable temporary directory as the installation to update,
and `executing_cache_build_id` reads the fixed string `payload` instead of a
build id. What the cycle MEASURED is the root equality itself.

EVIDENCE DISTINCTION, kept deliberately narrow. The asset control in the frozen
cycle-12 test CONSTRUCTS a path from `executing_payload_root()` and asserts
where that path sits. It does NOT call the packaged-asset accessor
(`workflow_toml`), does not READ an asset, and does not observe an actual canary
outcome. Those are separate observations: an asset CONTENT read after eviction
is covered by `tests/bin/test_payload_public_route_exact_outcomes.py` and by
`tests/bin/test_payload_parent_reads_asset_after_helper_exit.py`, and no test in
this work-item observes a real canary verdict. Do not read the path assertion as
either.

The launcher now records the installation it copied aside
(`LIVESPEC_INSTALLED_PLUGIN_ROOT`), and `plugin_root()` consults it between the
harness export and the `__file__` fall-through. Two deliberate properties: the
record is a SEPARATE variable from the payload hand-down, because the two
answer opposite questions and conflating them is this whole defect class; and
it was written with `setdefault`, so a parent's record survived into its
children.

That second property was WRONG for a re-selection and cycle 13 corrects it —
see below. The right separation is not "first writer wins" but ADOPTION versus
SELECTION, and control flow already expresses it.

Honest limit, stated because it is a degradation rather than a fix: a
credential re-exec that scrubs the environment drops the record too, and
`plugin_root()` then falls back to the payload exactly as before. That is the
previous behaviour, not a new failure, and forwarding the record through the
re-exec the way the unattended marker is forwarded would be scope this
work-item did not declare.

The name is restated in both modules rather than imported, because the writer
is a pre-import launcher module that runs before the package is importable. Two
literals drift silently in the dangerous direction — a reader looking for a
name nobody writes just falls through — so they are pinned together by
`test_installed_root_env_name_matches_the_launchers_writer_constant`, the same
device the unattended-resume marker already uses.

## Cycle 14 — coherence at the provisioning boundary, and an invalid probe retracted

MY FIRST PROBE FOR THIS WAS INVALID, and the retraction is the useful part. It
mutated the SOURCE after a clean copy and reported the surviving original as an
undetected gap. A complete coherent payload whose source later changes is a
SUCCESS — it is the entire reason the release is copied aside — so that probe
demonstrated nothing, and acting on it would have imposed an invented rule that
retained bytes must equal a source which legitimately moved on. Caught by
read-only review before any product edit.

Re-measured at the PROVISIONING BOUNDARY, making the COPY defective through a
depth-counted seam on the product's own `copytree`:

| case | refused? | retained payload |
| --- | --- | --- |
| pre-copy member OMITTED from the copy, then gone from source before the walk | no | member ABSENT |
| same-length WRONG BYTES actually copied | no | `WRONGXXX` vs source `ORIGINAL` |
| control: coherent copy, source mutated AFTER | no | `ORIGINAL` — correct |

The first two are genuine: a live-source walk cannot see a member the source
has also lost, and size equality cannot see equal-length wrong bytes. Fixed by
taking a pre-copy digest inventory and grading the copy against THAT, which is
also exactly what keeps the control passing — the copy is compared against the
release as it WAS, never as it now is.

Red `2408fd09`, frozen bytes `f219ca14…`, Green `dcfd5e4a`, full aggregate green.
Scope is copy-vs-its-own-source coherence. NOT integrity, tamper-resistance or
supply chain: a digest here detects a copy that did not land faithfully and says
nothing about whether the source was trustworthy.

A fixture note worth keeping, because it is a could-not-have-failed shape: the
unreadable-member arm was first forced with `chmod 0o000`, which PASSES while
measuring nothing because this suite runs as ROOT and root reads a mode-000
file. It is now forced through a seam on `Path.open`.

## Cycle 15 — the inventory's own boundaries, found by review of cycle 14

Cycle 14's fix was correct for the cases it was written for and introduced two
faults in its own new code. Both are regressions against contracts this module
had already established, and both were caught by read-only review rather than
by me.

The inventory call sat between the `mkdtemp` that allocates the holder and the
`try/finally` that removes an unpublished one — OUTSIDE the cleanup boundary.
The established contract is that an INTERRUPTED provision leaves no adoptable
tree, not merely one that errors. Measured: a `KeyboardInterrupt` during the
inventory left a holder standing. It now runs BEFORE `mkdtemp`, beside the
release identity, which already sits there for exactly this reason — so the
likeliest step for an interrupt to land in is also the one that owns no
directory yet.

And `_digest` returned one literal sentinel for any unreadable file on BOTH
sides, which the comparison accepted as a match. Measured with reads denied on
one member in both trees: inventory recorded the sentinel, the copy existed and
was unreadable, their ACTUAL bytes differed, and the comparison reported no gap.
Two unknowns are not a match; an `UNREADABLE` reading on either side is now a
gap, which is the same fail-closed reason an unusable release manifest refuses.

AIMING TRAP, recorded because my first probe for the second fault could not
have found it: pointing the comparison at a copy path that does not EXIST trips
`not copied.is_file()` and reports a gap before `_digest` is ever called. It
returns the right answer for the wrong reason and hides the branch entirely.
The copy has to exist and be unreadable.

Red `e1ea67a8`, frozen bytes `e6c7210f…`, Green consolidated with this report. The
accepted cycle-14 regression at `f219ca14…` is untouched.

## Assertion 4 — what covers it, jointly

Stated because the supplement alone does not carry it. 
`tests/bin/test_payload_parent_reads_asset_after_helper_exit.py` constructs a
`RetainedPayload(holder=...)` and calls `release_payload` DIRECTLY, so it
evidences the ownership rule and the read-after-helper-exit ORDERING, but it is
NOT normal-exit proof: no interpreter shutdown and no `atexit` handler run in
it. The normal-exit and peer-survival legs come from the frozen
`tests/bin/test_payload_lifetime_release.py`, which drives real children to
completion. Assertion 4 is covered by the two TOGETHER, and neither should be
cited alone.

## Assertion 5 — the wrapper leg is UNMEASURABLE here, so it is not fixed

I previously wrote that a credential re-exec scrubbing the environment would
drop the installed-root record, called the resulting candidate collapse
pre-existing, and declared it out of scope. Review correctly rejected the scope
reasoning — assertion 5 explicitly preserves credential-wrapper invocation AND
candidate canary outcomes, so a collapse through that boundary would be
declared, not undeclared.

But the premise was never evidenced either. My support for it was
`_marker_forwarded_argv`'s docstring, which describes sudo rebuilding the
environment. **That is a hypothesis about env handling, not a measurement of
what this wrapper does to the NEW record.** Measured 2026-10-06, presence
boolean only: the configured wrapper's first token is NOT resolvable in this
sandbox — the same "host-provisioned credential wrapper is legitimately absent"
condition the repository's own doctor check reports.

So the supported wrapper's handling of the record CANNOT be measured here. The
disciplined consequences, both of which are deliberate inaction:

- no fix was made, because fixing an unevidenced behaviour would be designing
  against a guess;
- no env-scrub fixture was fabricated, because a test built on an invented
  wrapper would report confidently on a wrapper nobody runs — the
  wrong-population shape this catalogue already documents.

What remains open, stated as an obligation rather than a finding: measure the
supported wrapper or API against the record on a host where it resolves, and if
it does drop it, retain provenance through the EXISTING boundary — the
`env NAME=value` splice after the wrapper separator that already carries the
unattended marker. That is a known mechanism, not new scope.

CANARY DECISIONS — NOW EVIDENCED, and it needed no host. Measured 2026-10-06
at the decision surface: `canary_verdict` yields `pass` at exit 0 and `fail` at
exit 1, the two are distinct, and across both `executing_payload_root()` and
the resolving module's own `__file__` are unchanged. The bounded case already
PASSED, so per the standing instruction it is preserved as a CONTROL
(`tests/bin/test_payload_canary_decision_leaves_execution.py`) rather than
turned into a Red, and no product edit was made. Two observables rather than
one because the root is derived from the module, so either alone could agree
with itself while the module had been reloaded from another tree. This closes
the "path equality is not a decision" gap; it observes no update applied, no
install promoted and no restart, the running Dispatcher being read-only about
its own artifact by contract.

### CORRECTION, 2026-10-06 — the paragraph above OVERCLAIMS, and the canary leg is still owed

The two sentences "NOW EVIDENCED" and "This closes the 'path equality is not a
decision' gap" are **withdrawn.** The measurement itself is accurate and the
control is kept; what is wrong is the claim about what it covers. Read the
callable:

```python
def canary_verdict(*, exit_code: int) -> CanaryVerdictValue:
    """Map a candidate self-check exit code to the canary verdict."""
    return CanaryVerdict.PASS if exit_code == 0 else CanaryVerdict.FAIL
```

That is a **pure total function of one integer** — a one-line mapping with no
I/O. The control calls it with the literal constants `0` and `1`. So it
launches no candidate process, observes no actual candidate result, and drives
no self-update journal decision; the exit codes it maps were written by the
test, not produced by a candidate. Asserting that this mapping is
order-preserving and that the caller's own `__file__` did not move is a real
fact about the DECISION-TO-EXECUTION relationship, and that is all it is.

The distinction matters because the fifth assertion is about candidate canary
OUTCOMES surviving, and an outcome requires a candidate to have produced one.
Substituting `canary_verdict(exit_code=0)` for a real candidate result is the
wrong-population shape this very report catalogues below: a clean pass whose
instrument could not have observed the thing being claimed. It is a mapping
control, not canary proof, and must not be cited as the latter.

No product defect is inferred from this gap. The code under the claim is not
suspected; only the evidence for it was mislabelled.

**What actually discharges the factory leg**, at the exported boundary and
source-checked at `0997466a`:
`_dispatcher_self_update.self_update_after_release(...)` — whose live signature
is `work_item_id`, `candidate_bin`, `scratch_root`, `repo`, `journal`,
`runner`, `poster` — driven from the RETAINED payload after its real
`_bootstrap.bootstrap()`, with the candidate resolved normally through
`candidate_dispatcher_bin()` (never monkeypatched, never the retained helper
passed as the candidate), a real bounded subprocess runner that preserves the
actual rc/stdout/stderr of
`python3 <B>/scripts/bin/dispatcher.py ledger-check --project-root <scratch> --json`,
a recording journal, and an injected recording `NotifyPoster` that makes no
network request. Two cases, each needing an ACTUAL subprocess result:

| Case | Scratch fixture | Expected candidate result | Expected journal stage |
| --- | --- | --- | --- |
| Conditioned positive | private `.livespec.jsonc` selecting the in-memory ledger stand-in (`fake: true`), no factories declared | exit 0, genuine `ledger-check` JSON, no findings | `self-update-restart-due` |
| Setup-refusal negative | a distinct genuinely empty scratch, no `.livespec.jsonc` | real nonzero exit, `ConnectionPrefixMissingError` | `self-update-kept-last-known-good` |

Both stage names are present in `_dispatcher_self_update.py` (`_RESTART_DUE_CLASS`
at line 85; the kept-last-known-good literal at line 311), so the expected
outcomes are source-grounded rather than guessed. In both cases payload A's
code, assets and version must be re-read and shown unchanged — path equality
alone is explicitly insufficient — and the negative is a SETUP refusal, not
evidence the candidate is unhealthy. A `self-update-error` record means the
stage never reached a canary result and is not passing evidence.

That capture is **owed to the downstream `proof_capture` node and its
independent `proof_verify` replay**, which is where this workflow measures
delivered runtime behaviour; it is deliberately not re-attempted here, and no
further already-passing test-plus-prose cycle was authored to stand in for it.

**The wrapper leg is NOT a second outstanding leg, and nothing above moves any
part of the fifth assertion to the host.** An earlier draft of this correction
said the fifth assertion now had "two outstanding legs"; that is withdrawn — it
would have host-deferred a factory assertion, which is not this correction's to
do. Only assertion 6 is host-deferred.

What is actually known about the wrapper, separating the two measurements that
the section above left tangled:

- **Normal host wrapper PRESERVATION was measured**, by the coordinator,
  through the ordinary configured wrapper, using inert process-local
  installed-root / retained-root markers: exit 0, BOTH markers `preserved=true`,
  and credential PRESENCE booleans true. Provenance anchor: wrapper file
  SHA-256 `04e81bd552613df42281fc346a1c71aeb8dd46423c420dd99665fbd033195506`
  (a checksum of the script, not credential material). That diagnostic emitted
  no secret value, performed no identity manipulation, mutated no cache, and
  ran no product CLI. So the record SURVIVES the normal wrapper; the premise
  that it would be dropped is not supported.
- **The generic sudo-scrub account was a HYPOTHESIS and must never be restated
  as observed fact.** It came from a docstring describing sudo rebuilding the
  environment, not from any measurement of this wrapper. No scrub defect is
  inferred, and none should be invented.

The consequence for the factory capture is that it must **honestly exercise the
available wrapper invocation boundary** rather than treat the leg as absent.
The frozen credential double already in the suite is the vehicle, and its
standing is disclosed rather than glossed: it is a deliberately STRONGER
hermetic fixture, **not** an exact replica of the normal host wrapper. Two
candid limits ride with it and must appear in the capture: the configured
wrapper's own executable does not resolve in this sandbox, so **no claim may be
made that the absent host executable ran in factory**; and a hermetic double
passing is evidence about the boundary's contract, not about that host binary.

So exactly one factory leg is owed here — the candidate-canary capture restated
above, taken at the available wrapper invocation boundary. That is a capture
task for `proof_capture` and `proof_verify`, not a maintainer question: no
decision is pending, no spec amendment is implied, and no product defect is
inferred.

## What is NOT a Red, stated plainly

Five artifacts in this work-item are supplemental and must never be cited as
Red-Green evidence:

| Artifact | Status |
| --- | --- |
| `_dispatcher_currency_probe.py` extraction (in cycle 10's Green) | Size-forced cohesion extraction. No nested Red commit. Structural guard only. |
| `_payload_grading.py` extraction (in cycle 11's Green) | Same: recording the payload's source took `_payload.py` past its 250 LLOC hard ceiling, so the grading layer was cut out by cohesion. `test_payload_grading.py` is a structural guard, not a Red. |
| `test_payload_public_cli_routes_after_eviction.py` | Authored after the pairs it covers; passed on first write. Its own docstring says so. |
| `test_payload_public_route_exact_outcomes.py` | Same. Its value is the pre-fix control, not a Red. |
| `test_payload_canary_decision_leaves_execution.py` | Passed on first write; no product edit. A PURE MAPPING control over `canary_verdict`, **not** candidate canary proof — see the correction above. |

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
- **A diagnostic glob that matched pytest's `current` symlink.** pytest keeps
  BOTH a numbered run directory and a `…current` symlink to it under the
  basetemp, so `basetemp/*/<file>` matches the SAME file twice. A `cat` over
  that glob concatenated two copies, which read as a config written twice
  (`json.tool` reporting "Extra data" — i.e. invalid JSON) and as a child that
  ran twice. Both were artifacts of the glob; the file was a valid 649 bytes
  and the child ran once. Discriminated by byte-counting the individual paths.
  **The rule: inspect the exact concrete directory, never a glob over the
  basetemp** — and note the shape of the damage, which is the dangerous part.
  This did not produce an empty or obviously broken reading; it manufactured
  two plausible, mutually-reinforcing SYMPTOMS of a defect that did not exist,
  and both pointed at the fixture being re-entered. Chasing them would have
  produced a fix for nothing.
- **A `.git` at the pytest basetemp root.** `git -C <tmp_path>/install rev-parse
  --absolute-git-dir` answered `<basetemp>/.git`, so EVERY `tmp_path` install
  resolved as a git checkout and took the currency gate's checkout exemption —
  the floor was never evaluated, and the intact control read as a product
  failure. It also meant the evicted cases were dodging the exemption by
  deletion rather than by genuinely not being a checkout. Fixed by placing the
  fixture installation outside the pytest tree, and the fixture now ASSERTS the
  installation is not a checkout so this cannot recur unnoticed.

## Two corrections from read-only review, and one of them is mine

Additive. Nothing below moved a ref or edited an accepted Red.

### A hypothesis that was never a defect: the credential `os.exec` path

A coordinator continuation carried the phrase "Credential `os.exec` must retain
creator cleanup ownership without giving helpers ownership". A read-only review
on 2026-10-06 flagged that as a HYPOTHESIS rather than a measured defect, and
it is right. Measured:

- `grep -rn 'os\.exec' .claude-plugin/scripts/bin/` returns **NOTHING**. The
  API path the phrase presupposes does not exist anywhere in the launcher.
- `_bootstrap._self_heal_credentials` uses `subprocess.run` (line 262) and then
  `raise SystemExit(completed.returncode)` (line 285). The parent process is
  never replaced, so the `atexit` handler registered at line 102 still runs.
- End to end with `TMPDIR` pointed at a private directory and the self-heal
  actually taken: **`payload holders left in TMPDIR: NONE (all cleaned)`**. The
  owning parent removes its own holder after its child wrapper has run.

The line-102 comment already stated the intended guarantee — "Registered BEFORE
the credential self-heal can re-exec … removed exactly once, by its creator" —
and the measurement agrees with it. **No product cycle was added for this, and
none should be.** Recorded so the phrase does not get re-read later as an open
defect.

### A finding I mislabelled as "not a finding"

This one is a correction to my OWN work, and it is the more important of the
two, because the wrong label was written into a merged-bound docstring where it
would stop the next reader from looking.

While building the exact-outcome public-route guard I found that an `exec`-form
credential-wrapper double drove `ledger-check` fine but would not drive
`dispatch` to completion. I recorded that in the test's docstring as "fixture
mechanics, not product behaviour … recorded here so the shape is not mistaken
for a finding", and said the same in my turn summary. **Both were false.**

The mechanism, measured 2026-10-06 and now pinned to exact lines.
`_self_heal_credentials` runs the wrapper with `capture_output=True`, then at
`_bootstrap.py` lines 276-284:

```python
if completed.returncode != 0 and not stdout:
    ...  # write wrapper_launch_failure
elif stderr:
    ...  # write the child's stderr
```

A child that REFUSES — non-zero exit, diagnostic on STDERR, empty STDOUT —
takes the first arm, and the `elif` is therefore SKIPPED. Its real stderr is
**discarded**, not supplemented. The operator receives "credential_wrapper
could not run in this environment … This can happen in a sandbox that blocks
sudo or sets no_new_privs", which names a cause that did not occur.

Measured instance: a dispatch whose genuine outcome was
`ERROR: dispatcher plugin release 7.1.0 is below the committed
dispatcher.minimum_release floor 9.9.9` exited 3 and emitted the wrapper-launch
message, with the real refusal appearing **nowhere** in stdout or stderr. The
sibling supplement's `exec`-form double works only because `ledger-check`
succeeds and prints to stdout, which is the condition that keeps it out of that
arm.

THE FIXTURE'S OWN HONESTY, corrected a second time by the same review. The
double this file's guard uses runs `"$@" > "$LOG" 2>&1` and then `cat`s the
log, so it MERGES stderr into stdout. That merge is the whole reason the
branch above is avoided: non-empty stdout keeps the child out of the
wrapper-launch arm. My first wording called the difference "fixture
mechanics"; my second called the double "what a real `with-<project>-env.sh`
does". **Both are retracted.** A real wrapper does not merge streams, so the
double is an OBSERVATION ADAPTER and must be declared as one.

What that adapter is and is not evidence for matters, because it is easy to
overclaim in either direction. It changes OBSERVABILITY, not the outcome — the
child genuinely refused, genuinely exited 3, and genuinely produced the text
from a packaged asset read out of the retained payload. It supports NO claim
of stream equivalence with production, and specifically no claim that an
operator would see that refusal in production: under a real wrapper they would
NOT, which is this finding, not something the fixture shows.

The two routes also do not depend on it equally. The DRIVE case asserts on
`payload["dispatcher"]["stderr"]`, captured by `drive` from the helper it
spawned itself, which never passes through the credential branch — that
evidence is adapter-independent. Only the direct-route case and the intact
control read the top-level process's output, and both use the SAME adapter,
so the control compares like with like against a real un-evicted installation.

Why this is worth its own entry rather than a line in the trap list: a wrong
measurement gets contradicted by the next reader, but a confident "this is not
a finding" FORECLOSES the examination — which is the exact failure mode this
repository's own verification discipline warns about, committed by the session
that had just finished citing it. The docstring in
`tests/bin/test_payload_public_route_exact_outcomes.py` now carries the
correction and points here.

**Not repaired.** Changing that branch is outside this work-item's declared
assertions, and the read-only review explicitly ruled out added scope. It is
left as a filed finding: any refusal routed through the credential wrapper on
stderr with empty stdout is reported to the operator as a wrapper-launch
failure. Note the blast radius before deciding priority — this is the surface
every wrapped dispatch refusal passes through, and it converts an actionable
diagnostic into a misleading one, which is the same "manufactures a counterfeit
environmental fault" shape AGENTS.md treats as worse than an honest failure.

## Operational disclosure

REDACTED DESCRIPTION. No value, fragment, length or prefix of any credential
appears in this file, and none may be added to it.

While diagnosing the checkout exemption at 2026-10-06T08:27:19Z, a
prefix-filtered environment listing was run in this sandbox. The repository's
own verification discipline forbids exactly that: a line-oriented filter over
environment variables cannot distinguish a value's internal newlines from
record boundaries, and the prescribed form is a per-name presence or length
probe. Two named credentials — the forge token and the forge app private key —
were rendered into the session transcript as a result.

Scope of the exposure, as presence facts only:

- transcript: AFFECTED;
- repository (tracked files, every commit on this branch): NOT affected. Every
  file in this repository matching a credential-shaped pattern predates this
  branch and is a detector literal or a test fixture; the branch-touched set
  matching any such pattern is EMPTY, confirmed by count-only scan;
- session gate logs: no environment output was ever redirected to a file. Logs
  matching a credential-shaped pattern do so because the suite's own token
  fixtures are echoed by pytest. They were NOT inspected to classify further,
  because classifying would mean handling the values.

Containment performed: the coordinator restricted the native transcript and
log directories, and this session set its own artifact directory to `0700`
with every file `0600`. Those raw logs are EXCLUDED from the proof and from
any pull request, are not uploaded, and are not copied into any durable
artifact. They were secured rather than deleted, because restriction was the
instruction and destroying an incident record is not a session's call.

**Remediation is coordinator-owned.** This session performed no credential
rotation and must not: rotating a SHARED credential unilaterally is an
irreversible action on infrastructure other runs depend on. The decision, and
any rotation, belong to the coordinator.

Recorded here rather than left in the transcript alone, because a disclosure
that exists only where it leaked is not a disclosure — and recorded in
redacted form, because a disclosure that repeats the value is a second
exposure.

## What a successor should take from this

1. **Red FIRST means: author and run a VALID behavioural failing test before
   the first corresponding product edit.** That is the whole rule. A test that
   fails for the wrong reason is not a valid Red (cycle 10's floor case), and
   a test authored after the product has already been written once is a late
   baseline replay however genuinely it then fails (cycles 9 and 10).

   **RETRACTED, and do not reinstate it:** an earlier revision of this report
   stated the rule as "measure the defect against the unmodified product
   before writing the test … that is the only thing that makes a Red genuine".
   That is an INVENTED stronger rule. A separate defect probe before the test
   is written is NOT required and never was. Probing first is a useful way to
   aim a fixture — it is how cycle 11 and cycle 12 avoided wrong-premise
   cases — but it is a technique, not the standard, and writing it into a
   successor-facing list would have had the next session believe a conforming
   cycle was non-conforming.
2. **Prove the fixture is ARMED.** Cycle 10's floor case is the pattern, and
   note what it actually did: it FAILED, on a wrong premise, because the
   fixture configured no floor. Assert the precondition you depend on
   (`floor_configured`, "this install is not a checkout") so a case cannot
   report on something it never set up.
3. **An exit code is not an outcome.** Exit 3 was produced in this work-item by
   a credential failure, a factory-binary gate, a worktree preflight, a floor
   refusal, and a floor that could not be evaluated. Only the text separates
   them.
4. **Do not credit a trailer as chronology.** The hook grades the staged tree,
   not the order in which the work actually happened.
