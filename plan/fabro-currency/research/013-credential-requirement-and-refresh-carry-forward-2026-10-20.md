# Credential freshness redesign and refresh carry-forward (2026-10-20)

Written by `claude:fabro-currency` on 2026-10-20 at about 23:15Z. Coordinator R344 asked for two things as ONE graph change: the credential freshness redesign that lets the proof-record recapture route (`bd-ib-2oxr6v`) fit a fresh Codex credential, and the `pr_refresh` refresh rule. Coordinator R344(i) asked for no implementation before R342 closes. The proposal this note supports is `SPECIFICATION/proposed_changes/proof-loop-graph-change.md`. Note 012 records the revert this follows.

## 1. Why the recapture route did not fit

`dispatcher.py codex-cred-status` requires `allowance + 3600 s` of remaining credential life. A fresh Codex credential carries 864000 s. Each figure below was computed with `resolve_credential_lifetime_requirement`.

| Tree | Execution allowance | Required lifetime |
| --- | --- | --- |
| v0.229.2 (with the recapture cycle) | 902955 s | 906555 s |
| v0.229.3 (revert) | 840675 s | 844275 s |

`bd-ib-2oxr6v` records that even the contract-exact two recapture laps would need 885795 s. The derivation in `_dispatcher_execution_budget` bills every out-edge of a node at that node's full visit count, although one visit takes exactly one out-edge. So every new loop on the proof path adds its full multiplied cost.

## 2. The two candidate designs

**(a) A tighter derivation.** Bound the sum of a node's out-edge traversals by its visit count. The bound stays sound, but the problem becomes a flow-constrained maximisation rather than the current monotone fixpoint. It is a large change to a module whose docstring warns against deriving harder, and the next loop added to the graph would face the same ceiling again.

**(b) A requirement bounded by enforced limits.** Two facts make this available now that were not true when the current design was approved:

1. The **whole-run wall budget** is ratified and enforced. In `contracts.md` it is the paragraph "The whole-run wall budget", and the key is `dispatcher.run_wall_budget_seconds`, default **21600 s**. It resolves per dispatch and is journaled with its layer. The Dispatcher watchdog cancels a run whose slot-holding time exceeds it, counted from the instant the run is first `running`, and queue time does not count. It arrived with `bd-ib-sdxfsn` on 2026-10-14.
2. The **in-sandbox credential-use guard** (`_dispatcher_credential_use_guard.py`) kills the coding agent at an absolute deadline measured from projection: TERM at `deadline − grace`, then KILL at the deadline. Credential use therefore cannot outlive the deadline, whatever the graph does and whether or not the Dispatcher is alive.

So the deadline can be the smaller of the allowance and `Q + W`. Here `W` is the run's resolved wall budget and `Q` is a bounded allowance for the queue and preparation time before the run is `running`. The freshness requirement is that deadline plus the margin. Host gate and guard keep one arithmetic, as `_dispatcher_credential_deadline` requires. A run that queues longer than `Q` is refused at agent launch, fails closed, and names the cause. That is today's queue-aged refusal, with a stated bound.

With `Q` = 86400 s (proposed default) and `W` = 21600 s, the requirement becomes 108000 + 3600 = **111600 s**. A Codex credential up to about 8.7 days old would pass. Today a credential must be under about 0.23 days old.

## 3. Prior art that binds this

`bd-ib-yx7pdm` (closed; the maintainer approved that redesign on 2026-10-05) fixed the requirement as "the workflow-resolved execution allowance covering configured node timeouts and bounded retries plus the documented safety margin". Design (b) changes that approved definition on evidence that postdates it. It is therefore offered for ratification, and this seat does not adopt it on its own authority. `contracts.md` §"Worker credential projection" itself makes the numeric threshold implementation-owned. The proposal still writes the definition down, because a definition that a later change reverts silently is how the 940000 s guard bound happened.

## 4. The refresh rule

The rule, as the coordinator gave it under R344(i): after the verified proof, a refresh whose base advance merges cleanly and touches neither the item's changed paths nor the proof-cited paths carries the proof forward, with at most one re-proving refresh per run. A real conflict or an overlap takes the full refresh repair. The evidence is that master protection is `strict=false` with only `ci-green` required, so the forge merges a branch that is not up to date. Repeated re-proof for every base advance is stricter than the merge gate itself. Runs measured chasing master: `t3znvw` about 200 minutes, `davaxq` 125 minutes.

The ratified rule (§"Proof carry-forward across a refresh", Scenario 178) carries forward only when every incoming path is in an inert class AND every proof step is a direct file read. The new rule widens the first condition for a run that has already re-proved once. It keeps every overlap, patch-identity and blob-identity test.

## 5. Why both belong in one graph change

Under (b), adding a loop to the proof path no longer raises the credential requirement once `Q + W` is the smaller figure. The recapture route and any future proof-loop edge then stop competing for credential lifetime. The refresh rule changes which existing edges a run takes and adds no edge. Landing them together means the shipped graph is measured once against one definition. `bd-ib-2oxr6v`'s guard test should then bind to the 864000 s fresh-credential lifetime, not to a free bound.
