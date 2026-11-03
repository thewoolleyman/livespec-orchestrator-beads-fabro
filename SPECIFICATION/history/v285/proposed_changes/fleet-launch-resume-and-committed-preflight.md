---
topic: fleet-launch-resume-and-committed-preflight
author: claude:gmktec-factory-placement
created_at: 2026-11-03T11:25:44Z
---

## Proposal: A fleet-launch resume launcher honours the shared fleet cap and the per-factory FIFO

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend §"Provisional fleet launch scripts" so that `fleet-launch/` may ship a resume launcher for `resume --item <item>`, and so that a resume launcher MUST pass through the same caller-side gates as an impl launcher. It takes a per-factory FIFO ticket, starts only at the live head of the FIFO, starts only while the fleet count it reads under the factory mutex is below the shared fleet cap, and writes a fleet in-flight marker before it releases the mutex. The `check-fleet-launch` harness cases grow accordingly, and a scenario states the behaviour.

### Motivation

Work item bd-ib-uhcn36 (plan gmktec-factory-placement; ruled by legacy-coordinator-agent 2026-11-03 ~11:15Z). The section commits caller-side gates only for `drive --action impl:<item>`, and nothing committed caps a `resume --item` launch. On 2026-11-03 at ~10:16Z a hand-run resume script bypassed both the gmktec FIFO and the fleet cap and pushed the fleet to 17 runs against a cap of 16. An interim, uncommitted capped-resume script was written in response, and it has to survive the x7bwug cutover because no committed path replaces it. The dispatch wall held bd-ib-uhcn36 as spec-change tier against this section.

### Proposed Changes

In SPECIFICATION/contracts.md §"Provisional fleet launch scripts", after the paragraph on the launch-time Definition-of-Done preflight, add:

A `fleet-launch/` launcher MAY also launch `resume --item <item>`. A resume launcher is a caller-side launch exactly as an impl launcher is, and it MUST pass through the same caller-side gates before it invokes `resume`:

- It MUST take a ticket on the target factory's FIFO and MUST start only when its ticket is the live head of that FIFO, so impl launchers and resume launchers queued on one factory bind in one ticket order.
- At the head of the FIFO it MUST take that factory's mutex and read the shared fleet count under it. It MUST start the resume only while that count is below the shared fleet cap. Otherwise it MUST release the mutex, keep its ticket, and wait. A count that cannot be read MUST be treated as at the cap.
- Before it releases the mutex to start a resume, it MUST write a fleet in-flight marker that every launcher's fleet count includes until the resumed run lists on its factory board, and it MUST remove that marker when the resume ends.
- It MUST hold while the hold file exists, as an impl launcher does.

A resume launcher runs no launch-time Definition-of-Done preflight, because a resume re-enters a run whose item was already admitted.

In the same section, the `check-fleet-launch` harness cases MUST also cover a resume launcher that waits while the fleet count is at the cap and starts once it drops below the cap, and a resume launcher queued behind an impl launcher on the same factory that binds after it.

In SPECIFICATION/scenarios.md, add a scenario with the next free scenario number and the title "A fleet-launch resume launcher waits for the fleet cap and the factory FIFO":

```gherkin
Feature: A resume launched through fleet-launch honours the caller-side gates
  Scenario: A resume waits at the shared fleet cap and binds in FIFO order
    Given an impl launcher and then a resume launcher queued on the gmktec FIFO
    And the shared fleet count is at the fleet cap
    When the impl launcher's run ends and the fleet count drops below the cap
    Then the impl launcher binds before the resume launcher
    And the resume launcher starts the resume only once the fleet count it reads under the gmktec mutex is below the cap
    And it writes a fleet in-flight marker before it releases the mutex
```

## Proposal: The committed launch-time preflight runs where a launcher-local copy had to

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State in §"Provisional fleet launch scripts" what the committed `dev-tooling/dod-preflight.sh`, which a `fleet-launch/` launcher runs as its launch-time Definition-of-Done preflight, MUST do so that no seat needs a launcher-local copy. It finds the `claude` and `codex` CLIs under a credential wrapper that resets PATH, accepts a legacy string-form adapter entry as a claude-acp route, runs its judges through the configured Codex-first judge chain, and takes its judge models from the repository's committed judge configuration. A scenario states the behaviour.

### Motivation

Work item bd-ib-pys5lt (plan gmktec-factory-placement; ruled by legacy-coordinator-agent 2026-11-03 ~11:25Z). x7bwug's queued preflight (v0.280.0) is reachable only through committed `fleet-launch/dispatch-dual.sh`, which calls the committed `dev-tooling/dod-preflight.sh`. The gmktec seat still launches through a tmp launcher whose interim block calls a launcher-local copy carrying four deltas. Two are break-fixes of 2026-11-01: a PATH-resetting tenant wrapper hid `claude`/`codex`, and homelab's string-form adapter entry was refused. The other two are the R47/R55 judge-model exports (without them an Opus judge was spawned for bd-ib-6zy3zd at 22:19:31Z on 2026-11-02) and the Codex-first spend ruling, now committed as bd-ib-mfzvdl's judge chain. Moving gmktec onto committed fleet-launch/, the x7bwug cutover, would drop all four. The dispatch wall held bd-ib-pys5lt as spec-change tier against this section, verdict unstated.

### Proposed Changes

In SPECIFICATION/contracts.md §"Provisional fleet launch scripts", after the paragraph on the launch-time Definition-of-Done preflight, add:

The launch-time preflight a `fleet-launch/` launcher runs is the committed `dev-tooling/dod-preflight.sh`. A launcher MUST NOT substitute a launcher-local copy of it, and that script MUST behave as follows wherever a launcher runs it:

- Run under a tenant credential wrapper that resets PATH, it MUST still resolve the `claude` and `codex` CLIs from the operator's user tool directory and complete its judgement, rather than failing with a command-not-found error.
- It MUST treat a legacy string-form adapter entry, consisting of environment assignments followed by a `claude-agent-acp` command line, as a claude-acp route, and MUST run its judgement rather than refuse the entry.
- It MUST run its Definition-of-Done and drift judges through the configured Codex-first judge chain, so that a Codex pass completes the preflight without a Claude judge call.
- It MUST take the models of its governing-heading, Definition-of-Done and reflector judges from the repository's committed judge configuration, including when the launcher that runs it exports no judge model.

In SPECIFICATION/scenarios.md, add a scenario with the next free scenario number and the title "The committed launch-time preflight runs under a PATH-resetting wrapper with a string-form adapter entry":

```gherkin
Feature: The committed launch-time preflight needs no launcher-local copy
  Scenario: A preflight under a PATH-resetting tenant wrapper with a string-form adapter entry completes Codex-first
    Given a tenant whose credential wrapper resets PATH to exclude the operator's user tool directory
    And whose committed adapter entry is a string of environment assignments followed by a claude-agent-acp command line
    When a fleet-launch launcher runs the committed dev-tooling/dod-preflight.sh for one of its items without exporting any judge model
    Then the preflight resolves claude and codex and completes its judgement
    And its judges run through the configured Codex-first chain, so a Codex pass completes it without a Claude judge call
    And each judge runs on the model the repository's committed judge configuration names
```
