---
topic: label-every-host-model-judgement
author: claude-opus-5-5
created_at: 2026-10-31T17:46:26Z
---

## Proposal: Every host model-judgement spawn carries a livespec.caller resource attribute

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Generalize the shared attribute vocabulary of contracts.md §"Bounded session waits and observable inventory" with a new subsection, `### Host model-judgement caller labelling`, requiring every host-side launch of a model-judgement subprocess to name its calling judgement in a `livespec.caller` entry of the child's `OTEL_RESOURCE_ATTRIBUTES`. Add one scenario stating the behaviour. The receiver allowlist admits the new attribute.

### Motivation

Work item bd-ib-h23kbx (coordinator ruling, gitops-fleet-capacity-monitoring, 2026-10-26; orchestrator half of livespec-dev-tooling-iznup7). Measured from local transcripts: since 2026-10-25T15:37Z, $293.93 of one Anthropic account went to headless judge subprocesses launched from this repository, $277.14 of it (85 calls) on the shared spec-stated judge prompt. It kept burning after the drift lane stopped, and nothing in the telemetry tells the takings apart, because several judgements share one prompt and one launch seam. The Dispatcher's dispatch-time spec-stated judgement refused to dispatch bd-ib-h23kbx because this behaviour is unstated, and it named §"Bounded session waits and observable inventory" as the heading to generalize: that section already owns the shared attribute vocabulary and the receiver allowlist the producers and consumers co-evolve.

### Proposed Changes

Add the following subsection to SPECIFICATION/contracts.md under `## Bounded session waits and observable inventory`, immediately after `### Dispatch trace correlation`:

### Host model-judgement caller labelling

This subsection extends the shared attribute vocabulary above to the model-judgement subprocesses the plugin launches on the host. A host model-judgement spawn is any subprocess the plugin starts on the host to obtain a model judgement, whichever agent runtime or model the resolved judge chain selects; a module that only wraps a caller-supplied model runner, or only reads verdict types, launches nothing and is not a spawn site.

Every host model-judgement spawn MUST carry a `livespec.caller=<caller>` entry in the `OTEL_RESOURCE_ATTRIBUTES` of the child's environment, naming the judgement that launched it. The caller value MUST be supplied by the launching judgement through the launch seam, and MUST NOT be inferred from the prompt, the model or the call stack, so that two judgements sharing one prompt and one launch seam are still told apart. The caller values are:

- `drift_run` for the drift run's spec-stated judgement;
- `dod_governing_heading` for the host governing-heading verdict, although it reaches the judge through the same launch seam as the drift run;
- `dod_judgement_pre_admission` and `dod_judgement_pre_dispatch` for the Definition-of-Done judgement taken before admission and before dispatch respectively;
- `ledger_intent_scan` for the ledger-intent scan's operator-supplied judge command.

A new spawn site MUST add its own caller value to this list in the same change that introduces it. Every caller value MUST be identifier-shaped as defined in §"Dispatch trace correlation".

When the launching environment already carries `OTEL_RESOURCE_ATTRIBUTES`, the child MUST receive every existing entry unchanged, in its original order, with the `livespec.caller` entry appended as a further comma-separated entry. When it carries none, the child's `OTEL_RESOURCE_ATTRIBUTES` MUST consist of the `livespec.caller` entry alone. Labelling MUST NOT add, remove or rewrite any other environment variable of the child, and a failure to compose the label MUST NOT fail or alter the judgement.

The receiver allowlist MUST admit `livespec.caller` as a resource attribute, so that judge spend can be grouped by caller downstream. The attribute carries the caller identifier only; it MUST NOT carry the prompt, the subject under judgement or any environment value, per the curated-field rule above.

Add one scenario to SPECIFICATION/scenarios.md, numbered with the next free scenario number at revise time, and link it in tests/heading-coverage.json in the same revise:

## Scenario NNN — Each host model-judgement spawn names its caller in OTEL_RESOURCE_ATTRIBUTES, appended to any inherited entries

Given the launching environment carries `OTEL_RESOURCE_ATTRIBUTES=service.namespace=livespec-family`
When the drift run and the host governing-heading verdict each launch a judge subprocess through the shared spec-stated launch seam
Then the drift run's child receives `OTEL_RESOURCE_ATTRIBUTES=service.namespace=livespec-family,livespec.caller=drift_run`
And the governing-heading verdict's child receives `OTEL_RESOURCE_ATTRIBUTES=service.namespace=livespec-family,livespec.caller=dod_governing_heading`
And no other environment variable of either child differs from the launching environment.

Given the launching environment carries no `OTEL_RESOURCE_ATTRIBUTES`
When the Definition-of-Done judgement launches its judge subprocess before dispatch
Then the child receives `OTEL_RESOURCE_ATTRIBUTES=livespec.caller=dod_judgement_pre_dispatch`.
