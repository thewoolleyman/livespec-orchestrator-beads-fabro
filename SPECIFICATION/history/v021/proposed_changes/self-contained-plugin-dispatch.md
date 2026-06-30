---
topic: self-contained-plugin-dispatch
author: claude-opus-4-8
created_at: 2026-06-30T02:59:24Z
---

## Proposal: Self-contained plugin dispatch

### Target specification files

- SPECIFICATION/contracts.md
- tests/heading-coverage.json

### Summary

Codify that the Fabro implement-work-item workflow payload ships inside the orchestrator plugin's packaged payload and that the Dispatcher resolves it via the plugin root, so the factory dispatches from the enabled plugin alone with no orchestrator-source checkout. Fleet members and adopters therefore consume the orchestrator identically. Adds a new contracts.md H2 and cross-references it from the existing dispatch-time baseline conformance gate section.

### Motivation

Clause #6 of the orchestrator-plugin-self-containment fix. The Dispatcher previously resolved its Fabro workflow from the orchestrator repository root, which presupposed a clone of the orchestrator's own source at dispatch time. Shipping the workflow in the plugin payload and resolving it via the plugin root removes that prerequisite so enabling the plugin is the whole installation; fleet == adopter consumption.

### Proposed Changes

(1) ADD a new H2 section `## Self-contained plugin dispatch` to `SPECIFICATION/contracts.md`, placed immediately AFTER `## Dispatch-time baseline conformance gate` and BEFORE `## Dispatcher admission, WIP cap, and post-merge acceptance`, with this text:

The Fabro `implement-work-item` workflow payload — `workflow.toml`, the workflow graph, and its prompt files — ships INSIDE this plugin's packaged payload (under `.claude-plugin/`), so the plugin installer copies it under the plugin root in the flattened install cache. The Dispatcher (`dispatcher.py`) MUST resolve that workflow via the PLUGIN ROOT — the location that is identical in the source layout (`.claude-plugin/`) and the flattened install cache (`${CLAUDE_PLUGIN_ROOT}`) — NOT via the orchestrator repository root. The explicit `--workflow <path>` override remains the escape hatch.

Because the workflow ships in the payload and resolves from the plugin root, the factory dispatches from the ENABLED PLUGIN ALONE: no clone of the orchestrator's own source is required at dispatch time. Fleet members and adopters therefore consume the orchestrator IDENTICALLY — enabling the plugin is the whole installation. The only repository clones the dispatch path makes are of the dispatch TARGET repo (the work site, cloned host-side and again inside the Fabro sandbox); the orchestrator's own source is never a dispatch-time prerequisite.

The host-side Dispatcher MUST run on the packaged payload alone — the Python standard library plus the vendored runtime under `scripts/_vendor/` — with no dependency on an orchestrator working checkout and no `pyproject.toml` / lockfile install step. Behaviors that presuppose a writable orchestrator checkout or fleet context MUST degrade to clean no-ops rather than failing the dispatch: the post-merge self-update canary records an explicit skip when there is no writable orchestrator checkout to promote, and the fleet-manifest sibling-clone projection renders empty when no fleet manifest is present.

(2) UPDATE the existing `## Dispatch-time baseline conformance gate` section: the closing sentence currently states the prepare chain 'lives in the Dispatcher's Fabro workflow definition (`.fabro/workflows/implement-work-item/workflow.toml`)'. Adjust that parenthetical to cross-reference the new section, matching the within-file §"Heading" citation style: '(the packaged `.fabro/workflows/implement-work-item/workflow.toml`, shipped in the plugin payload and resolved via the plugin root per the §"Self-contained plugin dispatch" contract)'.

(3) CO-EDIT `tests/heading-coverage.json`: add a heading-coverage entry for the new H2 `## Self-contained plugin dispatch` (spec_root SPECIFICATION, spec_file contracts.md), using the TODO/reason shape the neighbouring `## Dispatch-time baseline conformance gate` entry uses — the reason notes the heading is enforced by the dispatcher's plugin-root workflow resolution plus the workflow payload shipped under the plugin root, with a real test id to be populated once an exercising test exists. This is a clause-only contract (no new Gherkin scenario), consistent with the existing dispatch-time baseline conformance gate precedent in this repo.
