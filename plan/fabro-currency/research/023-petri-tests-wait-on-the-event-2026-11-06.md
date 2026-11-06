# 023 — Two fabro-petri tests wait on the event they assert (2026-11-06)

Written by `claude:fabro-currency` (an unattended resume of plan epic `bd-ib-6tcjfx`) on
2026-11-06. It records work-item `bd-ib-4uge7u`. That item fixed two fabro-petri tests that
put a test-local wall-clock deadline in front of the event they wait for. Under host load
they failed although the behaviour was correct: 27.2 s and 33.4 s at load average 100-113 on
2026-11-03. It is the second of the five fork flaky-test items; note 022 covers the first.
All times are UTC.

## Causes

- `tests/hooks.rs`, `required_publication_blocks_the_terminal_result_and_cleanup`: a 15 s
  `time::timeout` wrapped `publisher.entered.notified()`. The run's work in front of the
  publication gate took longer than that under load.
- `tests/projection.rs`, `a_pending_question_carries_its_choice_descriptions_previews_and_context`.
  The cause was NOT the 30 s poll deadline but the gate's own `timeout="1500ms"`. The question
  was pending for only 1.5 s of real time, so under load the projector could catch up only
  after the question had expired. The projection then never showed it pending, and the 30 s
  poll panicked at about 33 s. Removing the poll deadline alone would have turned the failure
  into a hang.

## Fix (fork PR #32, test-only, merged at `f4e90c2af`)

- The publication wait is now just `publisher.entered.notified().await`. `entered` is notified
  with `notify_one`, whose permit outlives an early notify.
- The described gate has no timeout, and `GateRun` keeps its `ControlInterviewer`.
- `pending()` waits with no deadline of its own.
- The test answers `N` once it has seen the question pending, and the `no` marker proves the
  answer routed.

Hang detection is the nextest profile timeout alone (the maintainer's ruling of 2026-11-03).

## Definition-of-Done repair (coordinator ruling R301, option C)

The item's third bullet asked for ten consecutive solo passes at load average above 90. No
venue could supply that load without harm:

- vps (`vmi3006760`) was running the P1 expedited-incident-response-flag gates, and P2 moves
  gate load off it;
- synthetic stress on a fabro-k3s node would slow the live factory runs there.

The owning session therefore replaced the bullet with two bullets:

- a recorded read showing no test-local deadline, timeout or sleep-bounded wait in front of
  either awaited event;
- ten consecutive solo passes on fabro-k3s, each with its job id and load reading.

The mutation evidence that each test still fails without its behaviour is the item's existing
second bullet.

## Evidence, all on `fabro-k3s`

| What | Run | Result |
| --- | --- | --- |
| GREEN, PR head `b996e7363` | `42173638813` | Format, Clippy and Test success: 4423 of 4423 passed and 60 skipped |
| Full-suite mutation run | `42173589758` | Red, but nextest fail-fast stopped at 318/4423 on three `fabro-cli` attach tests the projection mutation also breaks, before reaching the two tests. It is not evidence for them. |
| Targeted mutation run, branch `mutation/4uge7u-behaviour-removed` | `42178165689` | The publication test FAILED (`hooks.rs:1741`: a rejected push no longer fails the run). The question test TIMED OUT at the 120 s profile limit. |
| Ten solo runs, branch `ci/solo-4uge7u`, one archive built from the fix | `42173905772` | 10 of 10 jobs passed both tests, run one at a time. The 1-minute load average was 20.6 to 42.6. |

A detail of the publication mutation: in the accepted-push pass, the test's
`status.is_none()` read did not catch a non-blocking publication. The test detects the
mutation through its rejected-push outcome assertion. A stronger pending-status check would
be a separate change.

Both evidence branches carry throwaway workflows and are deleted after the item closes. No
fork gate or build ran on vps.

## Remaining instances (same shape, not changed)

- `projection.rs`, `an_expired_question_is_pending_while_the_gate_waits_and_closes_on_the_expiry`:
  a 30 s `Instant` deadline and the same 1.5 s real-clock pending window. Expiry is what that
  test covers, so it needs an injectable expiry clock. It has not been filed yet: this
  unattended session could not obtain filing consent.
- `projection.rs` about lines 1391 and 1397: a 15 s `time::timeout` around a finalizer
  notify, and a 5 s timeout around a signal/settle poll.
- `support/mod.rs` `wait_until`: a shared `PATIENCE` deadline, used by many tests.
