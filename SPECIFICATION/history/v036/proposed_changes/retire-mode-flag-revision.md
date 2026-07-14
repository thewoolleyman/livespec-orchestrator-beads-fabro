---
proposal: retire-mode-flag.md
decision: accept
revised_at: 2026-07-14T18:06:34Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accepted after three rounds of independent Fable-model adversarial review returned a final NO-BLOCKERS verdict (the maintainer's standing pre-ratification rule); the accept is maintainer-delegated. The `--mode` run-mode flag is retired entirely and the run-mode term is killed, but the flag's three jobs are re-homed rather than deleted: arming is gone (Full autonomous mode was already retired at v034, and the policy-settings section already forbids any per-run policy-arming argument); queue-drain scope moves onto the surface itself, so `loop` drains the ranked queue by default (bounded by `--budget` and the per-repo `wip_cap`) with a new `--dry-run` that plans without dispatching; and the fail-closed cost gate re-keys onto the PRESENCE of `--item` rather than a mode, preserving today's semantics exactly. Adds `## Dispatcher loop invocation surface` — the first contract this spec carries for the `loop` CLI surface or the cost gate — with the gate's coverage (successful runs with a resolvable run id only), its deliberate fail-open skip, and the always-wired `LIVESPEC_COST_MODE` severity lever all stated explicitly rather than papered over. Scenarios 43-45 bind the new behavior; tests/heading-coverage.json is co-edited in this same payload for the four added H2 headings. Design record: repo thewoolleyman/livespec, plan/autonomous-mode/handoff.md, the "SESSION UPDATE — 2026-07-14 (cont. 14)" section, decisions 1-3. The no-shadow-ledger vocabulary is a different concept and is preserved verbatim.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
