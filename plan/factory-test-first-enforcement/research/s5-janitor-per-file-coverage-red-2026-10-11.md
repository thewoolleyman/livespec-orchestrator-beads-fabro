# S5 janitor `check-per-file-coverage` red, 2026-10-11 — unreproduced

This note preserves a single red observation of the `check-per-file-coverage`
aggregate target during the `bd-ib-pwqxso` janitor stage, and records that no
root cause was identified. It is written because the red was real, was
observed on the exact tree this branch publishes, and could not be reproduced
afterwards: a later reader seeing eight green runs recorded nowhere should not
conclude the red never happened.

Nothing below claims the gate is sound, and nothing below classifies the red
as spurious. The claim is narrower and exact: on this tree the target passed
every time it was measured, while the one failing observation names a single
timing-dependent test that no later run reproduced.

**This note's first version asserted that the failing observation's own
diagnostic output no longer existed, and that assertion was FALSE.** The log
is recoverable through a normal `fabro dump` of the run's janitor stage, and
the recovered detail is now in "The failing observation" below. The false
absence is preserved here rather than silently overwritten because it is the
instructive part: an absence asserted after searching only the local
filesystem foreclosed the one question the note was written to leave open,
and nothing downstream would have re-tested it. The scope actually searched
was `/tmp` on the sandbox host; the population that held the answer was the
factory run's own exported artifacts.

## Notation used in this note

"Aggregate" means the whole 92-target `mise exec -- just check` run.
"Target" means the single `check-per-file-coverage` recipe. `pytest_rc` and
`coverage_rc` are the two exit codes `dev-tooling/just-check-per-file-coverage.sh`
computes internally, named after its own shell variables. All times are UTC.
"Exit code consumed" means the status was read directly from the command, not
inferred from its output text through a pipeline.

## The failing observation

| Time (UTC) | Evidence |
| --- | --- |
| 2026-10-11T08:12:55Z | The janitor stage was inside `mise exec -- just check`; its `check-fabro-graph-validity` output carries this timestamp. |
| shortly after | The aggregate ended `Failed targets (1): - check-per-file-coverage`, and `just` reported `error: Recipe 'check' failed with exit code 1`. |

The janitor ran on this exact tree, not an earlier one. Its own
`check-doctor-static` output reports `doctor-git-author-policy` passing with
"all 17 commit(s) introduced by `origin/master..HEAD`", and `origin/master..HEAD`
is 17 commits at `e07dfff62ced308233793dd69cbb2acd00d60206`, the head this
stage inherited and published unchanged.

The janitor's per-target detail IS recoverable, and it has been recovered.
The stage preamble truncates the log with "(3599 lines omitted)", and the
omitted region is exactly where the pytest run and the per-file verifier
reported — but that truncation is a property of the PREAMBLE, not of the
artifact. A normal `fabro dump` of the run against its explicit factory
server exports the full `stages/005-janitor@1/output.log`:

```
/home/ubuntu/.fabro/bin/fabro dump 01M4MV5S7P87BKAWA58JNWQ433 \
  --server https://hp-xubuntu.perch-rudd.ts.net:32276 -o <export-dir>
```

The recovered log settles the `pytest_rc` versus `coverage_rc` question in
favour of `pytest_rc`, and names the case:

| Field | Recovered value |
| --- | --- |
| Failing case | `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_credential_use_guard.py::test_a_fractional_start_still_stops_by_the_absolute_epoch[0.95]` |
| Failure | `subprocess.TimeoutExpired` after 18 seconds, raised inside `_run` → `subprocess.run` → `communicate` |
| Captured output | stdout and stderr both empty |
| Subject | the credential guard wrapping a Python heartbeat child that ignores `SIGTERM` |
| Suite totals | 7165 passed, 1 failed, 1 skipped |
| Coverage | 100% reached |

So the target failed on a FAILING TEST, not on a per-file coverage
shortfall, and the coverage leg of this note's original uncertainty is
closed: coverage was complete in the failing run. The OTel `boom` thread
exception visible in the same log is a separate warning and is not this
failed case.

What remains open is the CAUSE of that 18-second timeout. The later green
runs below are valid NON-REPRODUCTION and are not evidence of a cause.

## Measurements taken on the identical tree

Every run below was executed on `e07dfff6` with a clean working tree, in the
foreground, with the exit code consumed directly.

| Time (UTC) | What ran | Result |
| --- | --- | --- |
| 2026-10-11T08:05:33Z | Aggregate, by the preceding `review_fix` stage | `All 92 targets passed.`; 7166 passed, 1 skipped; total coverage 100.00% |
| 2026-10-11T08:17:18Z | Target alone | exit 0 |
| 2026-10-11T08:25:11Z | Aggregate | exit 0; `All 92 targets passed.`; 7166 passed, 1 skipped; total coverage 100.00% |
| 2026-10-11T08:32:12Z | Target internals, both codes captured separately | `pytest_rc=0 coverage_rc=0` |
| 2026-10-11T08:36:06Z | Target internals, both codes captured separately | `pytest_rc=0 coverage_rc=0` |
| 2026-10-11T08:39:30Z | Target internals, both codes captured separately | `pytest_rc=0 coverage_rc=0` |

That is five full-suite executions, two of them the complete aggregate, with
the suite reporting an identical 7166 passed / 1 skipped and 100.00% total
coverage every time. The single skip is deterministic and unrelated: it is the
live Codex picker acceptance in `tests/e2e-cli/test_codex_skill_picker.py`,
gated on `LIVESPEC_CODEX_SKILL_PICKER != "1"`.

## Hypotheses tested and excluded

Each entry names the instrument and why it could have returned the other
answer. An instrument that cannot return a hit is not evidence, so a
hypothesis is recorded as excluded only where a positive result was reachable.

- **Resource exhaustion of the sandbox cgroup (excluded).** `memory.events`
  reports `max 0`, `oom 0`, `oom_kill 0` and `oom_group_kill 0`, and
  `pids.events` reports `max 0`. These counters are cumulative over the
  cgroup's lifetime, which spans the janitor run, so a kill or a hit against
  either ceiling during that run would still be counted now. Observed headroom
  was wide: `memory.peak` 3,905,781,760 bytes against a `memory.max` of
  8,000,000,000, and `pids.current` 45 against a `pids.max` of 34,482.
- **Load sensitivity of the suite's wall-clock tests (not reproduced, and now
  the hypothesis the recovered log points AT).** The suite contains genuinely
  timing-dependent tests that spawn real processes and assert against a
  `_HARD_TOLERANCE_SECONDS` of 0.5, chiefly in
  `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_credential_use_guard.py`.
  Those files plus the other real-sleep modules were run three times under 24
  induced busy loops on a 16-core host, reaching a one-minute load average of
  31.96. All three runs reported 37 passed. The load processes were started and
  reaped inside a single foreground command and none survived it, confirmed by
  an exact-cmdline scan of `/proc` excluding the scanning shell.
  **The recovered log names a case in exactly this module**, so the failure
  is in the population this probe was aimed at — the probe simply did not
  reproduce it at that load. That makes this the live hypothesis rather than
  an excluded one, and it is NOT established: a non-reproduction under
  induced load does not establish load as the cause, and the recovered
  failure mode is an 18-second `communicate` timeout rather than a
  tolerance-band overshoot, which is a different shape from what the induced
  load was designed to provoke.
- **Nondeterminism in the tests this branch adds (none found).** The branch's
  own test delta is `tests/integration/test_factory_size_justification_gate_scenario153.py`,
  `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_admission_eligibility.py`
  and `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_factory_size_gate.py`.
  A search across them for clocks, sleeps, threads, subprocesses, randomness
  and fixed filesystem paths returns one hit, `sleep=lambda _seconds: None`,
  which is a stub that removes delay rather than depending on it. The
  integration test is hermetic: it sets `LIVESPEC_BEADS_FAKE` and uses
  `monkeypatch`, and reaches no network.
- **Cross-test contamination through module-level mutable state in the new
  product modules (none found).** The seven modules this branch adds were
  searched for caches, `functools` memoisation, `global`, and module-level
  mutable containers. The only module-level container is
  `_RETIRED_INTAKE_LABELS` in `_intake_factory_size_gate.py`, which nothing
  mutates.
- **A differing worker count between the janitor's environment and this
  stage's (not established, and not excluded).** `dev-tooling/just-test-nprocs.sh`
  derives parallelism from `LIVESPEC_CI_LANE` and `LIVESPEC_TEST_PARALLELISM`,
  and the gate script defensively runs `env -u COVERAGE_FILE`, whose own
  comment cites "the dispatcher's namespaced export" — so some callers of this
  gate do carry a different environment. In this stage's shell all of
  `LIVESPEC_CI_LANE`, `LIVESPEC_TEST_PARALLELISM`, `COVERAGE_FILE`,
  `PYTEST_ADDOPTS` and `CI` are unset, which yields four workers. The janitor's
  environment was not observable after the fact, so whether it resolved the
  same worker count is unknown. It is recorded as unresolved rather than
  dismissed. (This note's first version called it "the one hypothesis left
  standing"; that followed from the then-believed unrecoverability of the
  failure mode. With the failing case recovered, the load-sensitivity
  hypothesis above is also standing, and is the more directly implicated of
  the two.)

- **The upstream hermetic-env test patch is NOT an explanation for this
  timeout.** Upstream `543a2147` is now integrated, and a later reader seeing
  both it and this note in the same tree is the reader most likely to treat
  the first as closing the second. It does not: it repaired a different
  fresh-one-hour/start condition, not an 18-second `communicate` timeout
  against a `SIGTERM`-ignoring heartbeat child. Recorded here as an excluded
  explanation rather than omitted, because omitting it leaves the inference
  available and unchallenged.

## What was not done, and why

No fix was made and no product or test file was changed in response to this
red. The failing case is now known, but its CAUSE is not, and the remedies
for the live hypotheses differ. A speculative edit presented as a repair is
worse than an open question: it reads as a discharged finding, so nothing
re-examines it.

In particular, the timing bounds this test asserts against were NOT
weakened. Widening a tolerance is the one change that would make this red
stop appearing without establishing anything about why it appeared, and the
bound is the thing the test exists to hold.

## If this recurs

**First, export the run's own janitor log** — that is where the answer was,
and a local filesystem search cannot see it:

```
/home/ubuntu/.fabro/bin/fabro dump <run-id> --server <factory-server> -o <export-dir>
grep -n 'FAILED\|passed\|failed' <export-dir>/stages/*-janitor@*/output.log
```

Then capture the target's two exit codes separately, because
`dev-tooling/just-check-per-file-coverage.sh` records `pytest_rc` and
`coverage_rc` independently and then returns only one of them, and inside the
92-target aggregate the distinguishing output is buried in a log that the
stage preamble truncates. The two commands, run from the repository root, are
the gate's own two steps:

```
env -u COVERAGE_FILE uv run pytest -n "$(bash dev-tooling/just-test-nprocs.sh)" --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing
env -u COVERAGE_FILE uv run python -m livespec_dev_tooling.checks.per_file_coverage
```

A failing first command names the test. A failing second command names the
file whose per-file coverage fell short. Record also the resolved worker count
and whether `LIVESPEC_CI_LANE` or `LIVESPEC_TEST_PARALLELISM` was set, since
that is the hypothesis this note could not close.
