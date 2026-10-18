---
topic: janitor-check-suite-venue
author: claude-opus-5-5
created_at: 2026-10-17T21:48:50Z
---

## Proposal: Post-merge janitor check-suite venue

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Ratify the check-suite venue that bd-ib-26deyw shipped in v0.210.0. A committed key, dispatcher.janitor.venue, selects whether the post-merge janitor runs its fresh checkout's check suite on the dispatching host (host_local, the default and the value every doubt resolves to) or as a gate Job on the maintainer-owned cluster through the shared delegated gate (cluster_job). Under cluster_job the verdict is read from the gate client's state word rather than its exit code, and a gate that reached no verdict reads red, never green or degraded.

### Motivation

bd-ib-26deyw shipped the cluster venue in d23458a7 and 70643453, and it was released in v0.210.0. It is live in this repository's own .livespec.jsonc (dispatcher.janitor.venue = cluster_job), but no ratified heading governs it: 'cluster' occurs zero times in SPECIFICATION/spec.md, contracts.md, constraints.md and scenarios.md on origin/master 658614d3. Its evidence is already on record. Canary bd-ib-d3h677 (run 01M55GKWZ05J, PR #3177 merged as 0eb0eed6) ran its post-merge janitor as gates Job gate-livespec-orchestrator-beads-fabro-5db5ee5fbc63; that Job completed with one success between 18:35:46Z and 18:39:45Z on 2026-10-17, and the janitor stage took 263 s against 1037-1194 s for the last eleven host-local janitors. Its host_recorded record is PR #3171 issuecomment-6238845292, and a separately started session verified it in issuecomment-6238961081. Canary bd-ib-djbwai (dispatch dc0c3298c47a41ad85c6d0961215b786, PR #3176, janitor-post-merge row at 2026-10-17T19:46:05Z) also closed unaided on the cluster venue. Then bd-ib-nsrgxl, which journals the venue on the janitor-post-merge row (the companion proposal in this file), was refused at the Definition of Done gate on 2026-10-17 (Fabro run 01M55WT5FB3G, ended needs_human after 4 m 47 s) because none of its cluster assertions had a governing scenario. This proposal ratifies the behaviour as shipped, so the venue is specified rather than merely implemented and its follow-up work can be dispatched against a ratified clause. The fabro-currency coordinator logged this gap as finding F-ae.

### Proposed Changes

Add a new subsection to SPECIFICATION/contracts.md, placed directly after §"Failed post-merge janitor target attribution":

### Post-merge janitor check-suite venue

The janitor VENUE of §"Dispatch preflight and post-merge step discipline" is the ref the fresh checkout is made at (Scenario 98). The check-suite venue is a separate question: which machine runs `janitor-check-suite` against that checkout.

- **Selection.** The governed repository's committed `.livespec.jsonc` key `dispatcher.janitor.venue` selects the check-suite venue. Its two values are `host_local` and `cluster_job`. The Dispatcher MUST select the cluster venue only when the key's value is exactly the string `cluster_job`. An absent `dispatcher.janitor` block, an absent key, a value that is not a string, and any unrecognised string MUST all select `host_local`. A doubtful declaration therefore keeps the suite running on the dispatching host and never moves it onto another machine.
- **`host_local`.** The Dispatcher MUST run the repository's check suite on the dispatching host, in the janitor checkout. The suite's exit code is the verdict: zero is green and non-zero is red.
- **`cluster_job`.** The Dispatcher MUST run the shared delegated gate client as a command executed in the janitor checkout. Its reference default argv is `mise exec -- uv run python -m livespec_dev_tooling.gate_remote_delegate run`. The client pushes the checkout's tree to the gates mirror, runs the suite as a gate Job on the cluster, and reports that Job's verdict. Because §"Inherited from livespec" in `constraints.md` confines the plugin's dependencies to its vendored tree, with no PyPI runtime dependencies, the Dispatcher MUST NOT import the gate client; it runs from the janitor checkout's own environment.
- **The cluster verdict is the state word, never the exit code.** The Dispatcher MUST read the verdict from the `state` field of the last line of the client's output that parses as a JSON object carrying a string `state`. `PASSED` MUST read green, even when the client exits non-zero because it could not write a push token, because a push token authorises a push and does not close a post-merge gate. `FAILED` MUST read red, and the red detail MUST say that the cluster gate Job reported a FAILED verdict. Every other outcome MUST read red: any other state word, output carrying no readable state, and a client that could not start. The red detail for these MUST say that the cluster gate reached no verdict and that the missing verdict, not the tree, is the finding.
- **A lost verdict is never degraded and never green.** A cluster no-verdict MUST NOT be reported as `janitor-env-degraded`, and MUST NOT let the item close. The degraded outcome is reserved for a host environment that stopped the janitor from running at all. A gate that was asked and did not answer is a red post-merge gate, and that is not configurable.
- **Both paths, unchanged neighbours.** This subsection applies to the dispatch path and to `reconcile-merged` alike. The environment scrub of Scenario 189, the retention of §"Failed post-merge janitor output retention", and the target attribution of §"Failed post-merge janitor target attribution" apply under either venue. No step outcome other than the verdict reading above changes.

Scenario 190 in `scenarios.md` exercises this section.

Add to SPECIFICATION/scenarios.md:

## Scenario 190 — The post-merge janitor runs its check suite where dispatcher.janitor.venue selects, and a cluster gate that reaches no verdict is red

```gherkin
Feature: Only an exact cluster_job declaration moves the janitor's check suite to the cluster,
  and the cluster venue reads its verdict from the gate client's state word

  Scenario: An absent or unrecognised venue keeps the check suite on the dispatching host
    Given a governed repository whose .livespec.jsonc declares no dispatcher.janitor.venue, or declares an unrecognised value
    When the post-merge janitor runs the check suite for a merged item
    Then the check suite runs on the dispatching host in the janitor checkout
    And its exit code is the janitor's verdict

  Scenario: A cluster gate that reports PASSED reads green even when the client exits non-zero
    Given a governed repository whose .livespec.jsonc declares dispatcher.janitor.venue as cluster_job
    And a delegated gate client whose last state-bearing output line reports state PASSED and which exits non-zero
    When the post-merge janitor runs
    Then the janitor verdict is green

  Scenario: A cluster gate that reports FAILED reads red as a failed Job
    Given a governed repository whose .livespec.jsonc declares dispatcher.janitor.venue as cluster_job
    And a delegated gate client whose last state-bearing output line reports state FAILED
    When the post-merge janitor runs
    Then the janitor verdict is red
    And the red detail says the cluster gate Job reported a FAILED verdict

  Scenario: A cluster gate that reaches no verdict reads red, not degraded
    Given a governed repository whose .livespec.jsonc declares dispatcher.janitor.venue as cluster_job
    And a delegated gate client whose output carries no readable state
    When the post-merge janitor runs
    Then the janitor verdict is red and not janitor-env-degraded
    And the red detail says the cluster gate reached no verdict
    And the item does not close
```

The revise pass that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the Scenario 190 heading in the same change.

## Proposal: Janitor-post-merge journal row records the check-suite venue and the cluster gate's reading

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Require every janitor-post-merge dispatch-journal row to name the check-suite venue that actually ran and when the suite started. Under the cluster venue, the row also carries the gate's state word, the tree hash the gate Job judged, and the Job's identity and timing whenever the gate client reports them. A reader can then tell a cluster run from a host-local run, and a cluster PASSED from an inferred one, from the row alone.

### Motivation

Today the janitor-post-merge row carries only at, detail, exit_code, invoker, invoker_source, removed_env_vars, stage and work_item_id. Nothing on it says which venue ran the suite or what the gate reported, so two independent sessions have had to infer the venue from outside the journal. bd-ib-26deyw's host_verified record (PR #3171 issuecomment-6238961081) inferred PASSED from the Job's own status in the gates namespace plus the venue code's rule that only PASSED reads green. The fabro-currency canary bd-ib-djbwai (dispatch dc0c3298c47a41ad85c6d0961215b786, PR #3176) rested its cluster-venue claim on the canary worktree's .livespec.jsonc and on stage timing. Work item bd-ib-nsrgxl implements these fields; its dispatch (run 01M55WT5FB3G) was refused at the Definition of Done gate because no ratified clause governs them. This proposal supplies that clause. The gate client (livespec_dev_tooling.gate_remote_delegate) currently logs only state and detail on its verdict line; making it report its Job's name, namespace and timing is livespec-dev-tooling-ggoyiq in that tenant, which is outside this spec target. So this clause requires copying those fields when present and forbids synthesizing them.

### Proposed Changes

Append to the new §"Post-merge janitor check-suite venue" subsection in SPECIFICATION/contracts.md:

- **The row names the venue that ran.** Every `janitor-post-merge` dispatch-journal row, on the dispatch path and under `reconcile-merged`, MUST carry a `venue` field whose value is `cluster_job` or `host_local`. The value MUST be the venue the check suite actually ran in, resolved at run time by the selection rule above, and MUST NOT be the raw declared configuration value.
- **The row carries the suite's start.** Every `janitor-post-merge` row MUST carry a `started_at` UTC timestamp taken immediately before the check-suite command is launched, so that the stage's own duration can be read from the row's `started_at` and `at` fields.
- **The cluster reading.** On the `cluster_job` venue the row MUST carry a `gate_state` field holding the state word the verdict was read from, or `null` when no state word could be read. It MUST also carry a `gate_tree_hash` field holding the full tree hash of the janitor checkout's HEAD, which is the tree the gate Job judged and the value of that Job's `livespec.gate/tree-hash` label.
- **Job identity and timing are copied, never synthesized.** On the `cluster_job` venue, the gate client's verdict line may carry any of `job_name`, `namespace`, `job_started_at` and `job_finished_at`. The row MUST copy each of those fields that is present, under the same name, and MUST omit each one that is absent. The Dispatcher MUST NOT derive any of them by itself, for example from the Job naming convention.
- **Host-local rows carry no gate fields.** On the `host_local` venue the row MUST NOT carry `gate_state`, `gate_tree_hash`, `job_name`, `namespace`, `job_started_at` or `job_finished_at`.
- **Recording changes nothing.** These fields MUST NOT change the janitor's verdict, the item's disposition, or the journal's existing fields.

Scenario 191 in `scenarios.md` exercises these bullets.

Add to SPECIFICATION/scenarios.md:

## Scenario 191 — The janitor-post-merge journal row names the venue that ran and, on the cluster, the gate's reading

```gherkin
Feature: A reader can tell from the janitor-post-merge row alone where the check suite ran and what the cluster gate said

  Scenario: A host-local janitor row names its venue and start and carries no gate fields
    Given a governed repository whose check-suite venue resolves to host_local
    When the post-merge janitor runs
    Then the janitor-post-merge row carries venue host_local and a started_at timestamp
    And the row carries no gate_state, gate_tree_hash, job_name, namespace, job_started_at or job_finished_at

  Scenario: A cluster janitor row carries the gate's state word and the judged tree
    Given a governed repository whose check-suite venue resolves to cluster_job
    And a delegated gate client whose verdict line reports state PASSED
    When the post-merge janitor runs
    Then the janitor-post-merge row carries venue cluster_job, gate_state PASSED and a started_at timestamp
    And the row's gate_tree_hash equals the full tree hash of the janitor checkout's HEAD

  Scenario: A cluster janitor row copies only the Job fields the client reported
    Given a governed repository whose check-suite venue resolves to cluster_job
    And a delegated gate client whose verdict line carries job_name and namespace but no job_started_at or job_finished_at
    When the post-merge janitor runs
    Then the janitor-post-merge row carries the reported job_name and namespace
    And the row carries no job_started_at or job_finished_at

  Scenario: A cluster gate with no readable state records a null state word
    Given a governed repository whose check-suite venue resolves to cluster_job
    And a delegated gate client whose output carries no readable state
    When the post-merge janitor runs
    Then the janitor-post-merge row carries venue cluster_job and gate_state null
```

The revise pass that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the Scenario 191 heading in the same change.
