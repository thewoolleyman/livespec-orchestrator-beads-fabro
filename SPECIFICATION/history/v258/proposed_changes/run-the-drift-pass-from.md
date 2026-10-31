---
topic: run-the-drift-pass-from
author: claude-opus-5-5:split-drift-check-from-cleanup-timer
created_at: 2026-10-31T16:13:23Z
---

## Proposal: The drift job's entry point is the Dispatcher's drift-run subcommand

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State the drift job's invocation surface in the "The drift run." bullet of contracts.md "## The skill surface": `dispatcher.py drift-run --repo <path> --invoker <role:name>` runs one drift-job run, `--json` prints the drift lane outcome as one JSON object, and `--dry-run` runs no drift lane and writes nothing to the detection-coverage anchor. Add a matching scenario to Scenario 207, which already governs the drift run, so no new H2 heading and no heading-coverage change is needed.

### Motivation

v219 ratified that the drift job is separate from the reconcile pass and runs only on a schedule an operator explicitly enables, but did not name how the job is invoked. Work-item bd-ib-dwzkjg, which adds that invocation, was held at dispatch on 2026-10-31 as spec-change tier: the spec-stated judgement against v257 reported its asked-for behaviour partial, naming "## The skill surface" as the heading to generalize, because the ratified text does not state the drift-run subcommand, its --repo/--invoker/--json surface, the JSON payload, or the --dry-run behaviour. The reconcile pass formerly printed the drift lane outcome under its `drift` key; once the lane left the reconcile pass (bd-ib-od7v54) that outcome has no surface, and an operator who enables the job needs one command to schedule and to read.

### Proposed Changes

In SPECIFICATION/contracts.md, "## The skill surface", append to the "**The drift run.**" bullet, after the sentence ending "nothing MAY enable it implicitly.":

```diff
   NOT invoke any model judgement. The drift job MUST run only on a
   schedule an operator explicitly enables; nothing MAY enable it
-  implicitly.
+  implicitly. One drift-job run is the Dispatcher subcommand
+  `dispatcher.py drift-run --repo <path> --invoker <role:name>`, which
+  MUST run the drift pass over every default-branch merge after the
+  recorded frontier exactly as this bullet states, and which is the one
+  command an enabled schedule invokes. With `--json` it MUST print the
+  drift lane outcome as one JSON object on stdout, the outcome a reconcile
+  pass carried under its `drift` key before the drift pass left it. With
+  `--dry-run` it MUST NOT run the drift lane, MUST NOT invoke any model
+  judgement, and MUST NOT write the drift frontier or the
+  detection-coverage anchor. No repository installer MAY install or
+  enable a schedule that invokes `drift-run`.
```

In SPECIFICATION/scenarios.md, "## Scenario 207 — The drift run processes each merge behind a contiguous frontier and files proposals it never accepts", append inside the gherkin block, after the scenario "A reconcile pass runs no drift pass":

```diff
     Then no drift pass runs and no model judgement is invoked
     And the drift frontier and the detection-coverage anchor are unchanged
+
+  Scenario: The drift-run subcommand is the drift job, and a dry run writes nothing
+    Given default-branch merges after the recorded drift frontier
+    When dispatcher.py drift-run --json runs
+    Then the drift pass runs over those merges and stdout carries the drift lane outcome as one JSON object
+    When dispatcher.py drift-run --dry-run runs instead
+    Then no drift pass runs and no model judgement is invoked
+    And the drift frontier and the detection-coverage anchor are unchanged
 ```

The scenario MUST stay under the existing Scenario 207 heading, so `tests/heading-coverage.json` needs no new entry.
