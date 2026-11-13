---
topic: a-factory-sandbox-pod-deleted
author: claude:fabro-currency session d8ec15
created_at: 2026-11-13T12:51:47Z
---

## Proposal: A lost factory sandbox is a host error the engine resumes from, and a run that still ends on one is released rather than classified deterministic

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add one paragraph to contracts.md §"Provider-limit permanence and root-cause surfacing" that makes a LOST sandbox a host error. A sandbox is lost when the provider reports it not found while its run is unfinished (on Kubernetes: the pod was deleted or evicted, or was lost with its node). Two layers are bound. (1) The factory engine on every factory server ends the execution as a resumable host error, as it already does for a failed run-store append. The factory server resumes the run onto a re-acquired sandbox, where setup re-runs and the interrupted stage continues; completed nodes are not run again; there are at most three resumes per run. (2) When a run still ends failed on a lost sandbox, the Dispatcher records a lost-sandbox cause and never classifies it deterministic or permanent, whether or not the termination is observable. It releases the item to ready without a human for recovery routing, with no rework-cap cost, and a second consecutive loss keeps the existing route naming both runs. It also amends the OOM paragraph so that the termination reading is taken from the run's own factory cluster with that instance's credentials. A CONTROL keeps every other sandbox-operation failure classified as today. One new scenario, numbered at revise, exercises all of it.

### Motivation

MEASURED 2026-11-13 by kubernetes-sandbox-backend's factory-sandbox-loss drill.

The drill deleted pod petri-01m7a7g3aprtwpmsas30myab7k-l0 (UID 65cb0074-b780-428d-8052-29ba54444f26, k8s Killing at 12:05:07Z). It belonged to run 01M7A7G3APRTWPMSAS30MYAB7K (livespec-dev-tooling-mpv6bp) on fabro-server-candidate :32278, build f4c05ab80e4e, carrier d22808f8e line.
- 12:05:10.650Z: the run FINISHED failed with "the checkpoint commit of `implement` failed: git rev-parse failed (wait failed): sandbox exec failed: Sandbox \"petri-01m7a7g3aprtwpmsas30myab7k-l0\" was not found", category deterministic.
- 12:08:50Z: the Dispatcher loop exited failed. It recorded fabro_failure_category=deterministic and sandbox_termination {observed:false, detail:'kubectl get pods exited 1'}.
- `dispatcher.py resume` refused rc=3 (no pull request).
- `fabro resume --detach` was accepted by the API, then refused by the worker at 12:20:26.912Z: "run already finished — nothing to resume".
So once a run has finished on a lost sandbox, NO surface recovers it. The one recovery that exists is the engine's resumable host error. The serving carrier d22808f8e (lib/components/fabro-petri/src/engine.rs:459-466) takes that path only for HostError::Coordinator(StoreFailed), measured on bd-ib-ljw2xg's run 01M6G24SQHM0: "Petri run ended with a host error ... Petri run interrupted; the server resumes it". A lost sandbox surfaces as hooks.rs:172 "the checkpoint commit of `{node}` failed" and ends the run.

FLEET-WIDE OBSERVER BLINDNESS (the strongest motivation, per legacy-coordinator-agent): read_sandbox_termination (_fabro_sandbox_termination.py:100) runs `kubectl get pods --all-namespaces -o json` with the dispatching host's AMBIENT kubeconfig. The dispatching host vps has kubectl v1.36.2 and NO kubeconfig: kubectl falls back to http://localhost:8080 and is refused (measured 12:4xZ by kubernetes-sandbox-backend, reproduced 13:35Z). Every termination reading of every gmktec run is therefore observed:false. The OOM naming this section already requires (Scenario 335) can never fire for a gmktec run.

No current text covers any of this. The existing OOM paragraph says an unobservable reading keeps the category the failure arrived with, which here was deterministic. Nothing requires the engine to treat a lost sandbox as resumable.

IMPACT: bd-ib-dpsiwz bullet 4 (a run resumed onto a re-acquired sandbox after a host error finds the Dispatcher-materialized plugin cache and helpers present) cannot be proved by any drill until the engine half lands. That gates bd-ib-qx45e6 and the fabro-currency plan, and the currency gate refuses every gmktec dispatch once an upstream release lands on or after 2026-11-21.

The launch pre-screen tiered the filed items, bd-ib-xqgeav (Dispatcher half, this repository) and bd-ib-gngz5d (engine half, Fabro fork), as spec-change under this topic. legacy-coordinator-agent ordered this proposal and assigned it the next orchestrator revise slot at high priority.

FLEET SCOPE: every sandbox-termination observer path (the Kubernetes driver and any non-Kubernetes sandbox kind that reads termination), every factory server's engine, and every bundled workflow. The lost-sandbox classification applies to a not-found sandbox from any provider.

OPEN DESIGN POINT for the grade: the three-resume bound per run, chosen to match the three-release bound of an-anthropic-acp-node-refused.

### Proposed Changes

### 1. `SPECIFICATION/contracts.md` §"Provider-limit permanence and root-cause surfacing": amend the OOM paragraph's read

In the paragraph "**A sandbox killed for memory is named.**", after its first sentence ("When the Dispatcher derives a failed run's outcome, it MUST read the run's sandbox container termination from the sandbox provider before that sandbox is collected."), insert:

```markdown
It MUST take that reading from the cluster of the factory instance that ran
the run, with credentials resolved for that instance, never from whatever
cluster the dispatching host's ambient configuration names.
```

### 2. Same section: add one paragraph after the OOM paragraph

```markdown
**A lost sandbox is a host error, never a permanent cause.** A run's sandbox
is *lost* when a sandbox operation of the unfinished run is refused because
the sandbox provider reports that sandbox as not found. On the Kubernetes
provider, that happens when the run's pod was deleted or evicted, or was lost
with its node. The factory engine on every factory server MUST end the
execution that met the loss as a host error that leaves the run unfinished,
as it does for a failed run-store append, so that the factory server resumes
the run onto a re-acquired sandbox. The resumed run MUST re-run its setup
steps (§"Self-contained plugin dispatch"), MUST continue from the stage the
loss interrupted, and MUST NOT run again a node it completed before the loss.
The factory server MUST resume one run after a lost sandbox at most three
times; a fourth loss of that run's sandbox ends the run. When a run ends
failed on a lost sandbox anyway (on an engine without this behaviour, or at
that bound), the Dispatcher MUST record the failure with a lost-sandbox cause
naming the run id and the sandbox. It MUST NOT classify that failure as
`deterministic` or permanent, whether or not the sandbox's termination is
observable. It MUST release the item's dispatch claim to `ready` without a
human, leaving the recovery route to recovery routing at the item's next
dispatch, and MUST NOT rest the item at `blocked / needs-human`. That release
MUST NOT consume any budget of §"The three rework caps". When the item's
preceding dispatch also ended on a lost sandbox, the current failure keeps its
existing route, and its needs-human cause record MUST name both runs. A
sandbox operation that fails for any other reason while the sandbox is present
keeps the classification it has today.
```

### 3. `SPECIFICATION/scenarios.md`: add one scenario, numbered at revise

~~~markdown
## Scenario: a run whose sandbox is lost mid-stage is resumed onto a re-acquired sandbox, and a run that still ends on a lost sandbox is released rather than classified deterministic

Governing clause: `contracts.md` §"Provider-limit permanence and root-cause surfacing" → "A lost sandbox is a host error, never a permanent cause." and → "A sandbox killed for memory is named."

```gherkin
Feature: A lost factory sandbox is a host error the factory recovers from

  Scenario: The engine resumes a run whose sandbox was lost onto a re-acquired sandbox
    Given a run at its implement stage on a Kubernetes-sandboxed factory server
    When the run's sandbox pod is deleted and the run's next sandbox operation is refused because the sandbox is not found
    Then the engine ends that execution as a host error and the run is not finished
    And the factory server resumes the run onto a re-acquired sandbox
    And the run's setup steps run again before the interrupted stage continues
    And no node the run completed before the loss runs again

  Scenario: A fourth lost sandbox ends the run
    Given a run whose sandbox was lost and that the factory server resumed three times
    When the run's sandbox is lost a fourth time
    Then the run ends failed with a lost-sandbox cause

  Scenario: A run that ended on a lost sandbox is released, not classified deterministic
    Given a run that ended failed with a sandbox exec error naming a sandbox the provider reports as not found
    And the sandbox's termination cannot be read on that pass
    When the Dispatcher derives the run's outcome
    Then the failure carries a lost-sandbox cause naming the run id and the sandbox
    And the failure is not classified deterministic or permanent
    And the item's dispatch claim is released to ready without a human

  Scenario: A second consecutive lost-sandbox ending keeps the existing route
    Given an item whose preceding dispatch ended failed on a lost sandbox
    When its current dispatch also ends failed on a lost sandbox
    Then the item keeps the existing route for that failure
    And its needs-human cause record names both runs

  Scenario: The termination reading is taken from the run's own factory cluster
    Given a run on a Kubernetes-sandboxed factory instance
    And a dispatching host whose ambient cluster configuration names no cluster
    When the Dispatcher reads the run's sandbox termination
    Then the reading is taken from that instance's cluster with that instance's credentials
    And the run's pod is reported as observed

  Scenario: A checkpoint commit that fails while the sandbox is present ends the run as before
    Given a run whose sandbox is present
    When its checkpoint commit fails for a reason other than a not-found sandbox
    Then the run ends as a workflow error
```
~~~

### 4. `tests/heading-coverage.json`: add the new heading in the same revise

Add one entry, using the heading as numbered at revise:

```json
{"heading": "## Scenario: a run whose sandbox is lost mid-stage is resumed onto a re-acquired sandbox, and a run that still ends on a lost sandbox is released rather than classified deterministic", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "reason": "A real test at the integration tier or above is owed for this heading: the Dispatcher-side cases (a run ending on a not-found sandbox with an unobservable termination is recorded with a lost-sandbox cause, is not classified deterministic and is released to ready; a second consecutive loss keeps the existing route naming both runs; the termination read uses the instance's own cluster credentials) are owned by bd-ib-xqgeav in this repository, beside tests/integration/test_sandbox_oom_classification_scenario335.py. The engine-side cases (interrupt and resume onto a re-acquired sandbox, the three-resume bound, the control) are owned by bd-ib-gngz5d in the Fabro fork and are proved host-captured.", "work_item": "bd-ib-xqgeav"}
```

The matching `tests/heading-coverage-debt.json` row is never authored by hand: the revise MUST regenerate it with `uv run python -m livespec_dev_tooling.heading_coverage_debt` and stage the result. The revise MUST co-edit both files, per AGENTS.md §"Revise co-edit discipline". No existing heading changes.

### 5. Follow-through outside the spec (not part of this revise)

On ratification, the `References:` lines of bd-ib-xqgeav and bd-ib-gngz5d name the new scenario heading as numbered at revise. Both are re-classified (`dispatcher.py classify-tier`), and the coordinator approves them.

