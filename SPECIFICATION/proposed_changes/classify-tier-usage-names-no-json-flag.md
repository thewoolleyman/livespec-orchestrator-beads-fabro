---
topic: classify-tier-usage-names-no-json-flag
author: claude-opus-5-5
created_at: 2026-11-14T01:05:09Z
---

## Proposal: The classify-tier usage line names only the flags classify-tier accepts

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Remove the trailing `[--json]` from the governed usage line of §"Dispatcher classify-tier invocation surface". The command has never accepted that flag, and no clause or scenario defines what a JSON output would carry, so the usage line states a surface the spec does not otherwise specify and the implementation does not have.

### Motivation

Spec-implementation lockstep, plan bd-ib-ax3rds (spec-implementation-lockstep). Drift found by that plan's sessions on 2026-11-13 and logged twice before being filed here. Measured on master 5da2f9db3: contracts.md §"Dispatcher classify-tier invocation surface" gives the usage `classify-tier --repo <path> --item <work-item-id> [--json]`. `add_classify_tier_arguments` in `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_classify_tier.py` declares only `--repo` and `--item`, so `--json` is rejected by argparse (exit 2), and the command writes one human-readable report line through `write_stdout`. No clause under that heading, and no scenario (the classify-tier cases of Scenario 344 and the classify-tier Feature at scenarios.md ~L11548), states a JSON shape or passes `--json`. No caller in the repository, its `.ai/` guidance or its tests passes it. Two remedies exist. Implementing `--json` would add an output whose shape no clause states, which is the unspecified-behaviour pattern this plan exists to stop. Removing the token makes the usage line say exactly what the command accepts and changes no behaviour. This proposal takes the second. It does not touch the separate `tier-screen` surface proposed by a-fleet-launcher-screens-an, which states its own `--json` output (aligned, no conflict).

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Dispatcher classify-tier invocation surface", replace the usage line

> `classify-tier --repo <path> --item <work-item-id> [--json]`

with

> `classify-tier --repo <path> --item <work-item-id>`

No other text changes. No heading is added, removed or renamed, so `tests/heading-coverage.json` needs no edit, and no scenario changes, because no scenario passes `--json` to `classify-tier`.
