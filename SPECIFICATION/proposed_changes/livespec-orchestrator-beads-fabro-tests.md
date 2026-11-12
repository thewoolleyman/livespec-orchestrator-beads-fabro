---
topic: livespec-orchestrator-beads-fabro-tests
author: claude-opus-5-5
created_at: 2026-11-12T22:40:00Z
---

## Proposal: A test's liveness guard is no shorter than 120 seconds and names what it waited for, and a worker thread's exception fails the test

### Target specification files

- SPECIFICATION/constraints.md

### Summary

Amends the bullet "No real-time sleeps or wall-clock verdicts in tests." in constraints.md, section "Forbidden patterns". That bullet already forbids a wall-clock verdict and admits a remaining wall-clock wait "only as a liveness guard against a hang". It does not say how long a liveness guard must be, what its expiry reports, or what happens to an exception raised in a test's worker thread. This proposal adds those three rules and the two kinds of wait they do not govern. It leaves the aggregate check's obligation unchanged. No heading is added, removed or renamed, so `tests/heading-coverage.json` does not change.

### Motivation

livespec-dev-tooling's `tests/livespec_dev_tooling/test_incident_recovery_journal.py::test_exact_concurrent_reservation_survives_restart_and_conflicting_bytes` failed `assert not True` in CI run 43287363009 (livespec-dev-tooling#4359, a diff that touched no incident code). It started two `reserve()` threads behind `Barrier(2).wait(timeout=3)`, then ran `worker.join(3)` and `assert not worker.is_alive()`. On a loaded runner the file-locked reserve took longer than 3 s, so the join returned with the thread still alive and the assert fired, with nothing wrong in the code under test. legacy-coordinator-agent ordered a fleet sweep of the same shape (rule K). The livespec-dev-tooling half of the rule is proposed in livespec-dev-tooling#4395 (topic `test-exact-concurrent-reservation-survives`), which it graded PASS on 2026-11-12. That clause binds only livespec-dev-tooling, because each member's work items are tier-judged against that member's own specification. So each member carries the rule in its own specification, and this is that member's proposal.

The ratified bullet leaves the length of a liveness guard open, and in practice the bounds among this repository's listed hits range from 0.5 s to 90 s. The shared helper `end_run_and_await_launcher_return` in `tests/conftest.py` bounds the launcher-thread join at `_LAUNCHER_RETURN_TIMEOUT_SECONDS = 10.0`, followed by `assert not thread.is_alive()`, and every watchdog launcher fixture inherits it. Its comment calls 10 s generous because it "bounds nothing a healthy fixture depends on". But a 3-second bound of exactly that kind is what failed in livespec-dev-tooling. A guard short enough to fire on a loaded runner is a wall-clock verdict in practice, which is what this bullet forbids. The 120-second floor is 40 times the bound that fired, and below the 180 seconds livespec-dev-tooling already uses for its slowest guarded call.

The aggregate check is deliberately left as it is. It refuses sleeps and elapsed-time verdicts, which are decidable from the source. Whether a given short wait is a liveness guard, a teardown wait or an expected-expiry window needs the per-line judgment the sweep below records, so a static refusal of short guards is not proposed. The same deferral is recorded in livespec-dev-tooling#4395.

The root-fix item for this repository is bd-ib-4aq6ej. It was filed through this repository's capture seam on 2026-11-12 ~21:28Z, and intake held it at the spec-change tier with this topic as its linked proposal. Its cross-tenant link to livespec-dev-tooling (plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub, items livespec-dev-tooling-dqndbz and livespec-dev-tooling-rs6o3q) is recorded in prose on both sides, never as a dependency edge.

### Fleet sweep (this repository)

Swept 2026-11-12 ~21:25Z at the checked-out `HEAD`, over test files (`*test*.py`, `tests/**/*.py`, `conftest.py`), with the pattern:

```text
\.join\(\s*(timeout\s*=\s*)?[0-9][0-9.]*\s*\)|\.wait\(\s*timeout\s*=\s*[0-9]|assert\s+not\s+.*\.is_alive\(\)
```

48 pattern hits in 25 files. The two expected-expiry windows the pattern also matched (`test_dispatcher_secret_review_fixes.py:355` and `test_session_wait_deadline_safety.py:511`) are already left out of this list. These are pattern hits, not per-line verdicts, because the one pattern also matches teardown waits and expected-expiry windows. The root-fix item classifies each line against the ratified rule, fixes every verdict-bearing bound and every swallowed worker exception, and records why it leaves each exempt line alone. Line numbers are as of the sweep.

- `tests/conftest.py`: 1221
- `tests/e2e-cli/test_codex_skill_picker.py`: 316, 320, 323, 361, 380
- `tests/e2e-cli/test_codex_skill_picker_pidfd_fallback.py`: 55, 78
- `tests/e2e/test_session_wait_pane_live_herdr.py`: 162, 395, 396, 655
- `tests/integration/test_needs_human_node_timeout_cut_scenario192.py`: 317
- `tests/integration/test_run_wall_budget_scenario175.py`: 160
- `tests/integration/test_session_wait_telemetry_scenario159.py`: 148, 315, 326, 327, 460, 537
- `tests/integration/test_watchdog_bound_run_poll_scenario173.py`: 132
- `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_heartbeat_probe.py`: 433
- `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_reflector_oob_wiring.py`: 194, 267
- `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_run_wall_budget_launcher.py`: 166
- `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_run_wall_budget_terminal.py`: 132
- `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_secret_review_fixes.py`: 359, 363
- `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_stall_window.py`: 126
- `tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_watchdog.py`: 1291, 1301
- `tests/livespec_orchestrator_beads_fabro/commands/test_otel_receive.py`: 980, 1039
- `tests/livespec_orchestrator_beads_fabro/commands/test_session_obligation_delegation.py`: 175, 180
- `tests/livespec_orchestrator_beads_fabro/commands/test_session_telemetry_export.py`: 128
- `tests/livespec_orchestrator_beads_fabro/commands/test_session_telemetry_export_tolerances.py`: 55, 128, 129
- `tests/livespec_orchestrator_beads_fabro/commands/test_session_wait_cli_budget.py`: 108
- `tests/livespec_orchestrator_beads_fabro/commands/test_session_wait_deadline_safety.py`: 255, 513
- `tests/livespec_orchestrator_beads_fabro/commands/test_session_wait_pane.py`: 196
- `tests/livespec_orchestrator_beads_fabro/commands/test_session_wait_pane_cancel_races.py`: 131
- `tests/livespec_orchestrator_beads_fabro/commands/test_session_wait_telemetry.py`: 326, 343, 344
- `tests/test_provision_honeycomb_tdd_calibration.py`: 393

### Proposed Changes

In `SPECIFICATION/constraints.md`, section "Forbidden patterns", in the bullet that begins "No real-time sleeps or wall-clock verdicts in tests.", append the following text after its last sentence, which ends "for a test whose subject is real time itself." No heading is added, removed or renamed in that file.

  A liveness guard is one value the repository defines once for every such wait, MUST be no shorter than 120 seconds, and its expiry MUST fail the test as a hang that names what the test was waiting for; a test MUST NOT bound a wait for something the code under test is required to do more tightly, as `join(10)` followed by `assert not thread.is_alive()` does. An exception raised in a test's worker thread MUST fail that test, and the failure report MUST name that exception, never surface only as a missing or short result. Two kinds of wait are outside these two rules: a teardown wait whose expiry falls through to a forced stop and decides no verdict, and a wait whose expiry is the outcome the test expects, such as a check that a blocked party has not yet proceeded. The aggregate check's obligation above is unchanged by these two rules.
