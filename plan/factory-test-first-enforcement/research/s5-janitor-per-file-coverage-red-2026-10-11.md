# S5 janitor `check-per-file-coverage` red, 2026-10-11 — unreproduced

This note preserves a single red observation of the `check-per-file-coverage`
aggregate target during the `bd-ib-pwqxso` janitor stage, and records that no
root cause was identified. It is written because the red was real, was
observed on the exact tree this branch publishes, and could not be reproduced
afterwards: a later reader seeing eight green runs recorded nowhere should not
conclude the red never happened.

Nothing below claims the gate is sound, and nothing below classifies the red
as spurious. The claim is narrower and exact: on this tree the target passed
every time it was measured, and the one failing observation's own diagnostic
output no longer exists.

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

The janitor's per-target detail is UNRECOVERABLE. The stage preamble truncates
the log with "(3599 lines omitted)", and the omitted region is exactly where
the pytest run and the per-file verifier reported. A filesystem search for a
surviving copy found none: the only `just check` log on disk is
`/tmp/justcheck.log`, written 2026-10-11T08:05:33Z by the preceding
`review_fix` stage, which is a different and GREEN run. So it is not known
whether the target failed on `pytest_rc` (a failing test) or on
`coverage_rc` (a per-file coverage shortfall). Those two have different causes
and different remedies, and the gate reports neither distinctly.

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
- **Load sensitivity of the suite's wall-clock tests (not reproduced).** The
  suite contains genuinely timing-dependent tests that spawn real processes and
  assert against a `_HARD_TOLERANCE_SECONDS` of 0.5, chiefly in
  `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_credential_use_guard.py`.
  Those files plus the other real-sleep modules were run three times under 24
  induced busy loops on a 16-core host, reaching a one-minute load average of
  31.96. All three runs reported 37 passed. The load processes were started and
  reaped inside a single foreground command and none survived it, confirmed by
  an exact-cmdline scan of `/proc` excluding the scanning shell.
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
  same worker count is unknown. This is the one hypothesis left standing, and
  it is recorded as unresolved rather than dismissed.

## What was not done, and why

No fix was made and no product or test file was changed in response to this
red. A change would have had to be a guess at which of two different failure
modes occurred, and a speculative edit presented as a repair is worse than an
open question: it reads as a discharged finding, so nothing re-examines it.

## If this recurs

Capture the target's two exit codes separately before anything else, because
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
