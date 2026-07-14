---
proposal: fabro-factory-integration-branch-standard.md
decision: accept
revised_at: 2026-07-14T06:09:37Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

ACCEPTED. The dark factory's steady state is running a Fabro built from a fork rather than an official upstream release, because it depends on fixes upstream has not shipped. Nothing in the spec named the carrier for those fixes, so the branch the live binary came from was knowable only from whichever plan thread happened to build it — and, as the doctor pass over this proposal discovered, that branch existed ONLY on local disk with no remote ref, leaving the running binary unreproducible if that disk were lost. The section fixes the carrier-branch name, its composition, the base-version ceiling, the rebuild/re-pin duty, and runbook lockstep, converting two severe silent failure modes (an ad-hoc pin whose carried-fix set diverges from what the factory needs; a base modernized past 0.256, where fabro #474 de-templates acp.command and EVERY dispatch dies exit 127) from discoveries into rule violations. The volatile list of currently-carried fixes deliberately lives in the runbook, not here, so the constraint cannot go stale.

INTENT-PRESERVATION ACKNOWLEDGMENT (per spec.md §"Intent preservation and design-record authority"). This revision amends a RATIFIED statement: the constraints.md preamble's claim that every constraint is "a binary, mechanically-checkable rule; lint / type-check / test failures are the enforcement mechanism". The new section cannot satisfy that claim — it governs an operator build step over an EXTERNAL repository, so no member of the `just check` aggregate can enforce it. NO DESIGN RECORD is cited by or reachable for that preamble, so the conflict and the absence of a governing record were surfaced to the maintainer rather than self-resolved; the maintainer explicitly confirmed the preamble amendment on 2026-07-14. The amended preamble keeps the binary/decidable requirement, scopes lint/type-check/test enforcement to constraints governing PLUGIN CODE, and requires any constraint governing an external runtime the plugin does not own (the beads/Dolt server, the Fabro engine) to NAME the command that decides it — `fabro --version` for this section. This is a deliberate widening, not an erosion: the file already contained a "MUST be manually verified" clause under §"Skill orchestration constraints", so the original preamble was already overstated; this revision makes the file honest about what it actually enforces.

NO scenarios.md co-edit, deliberately: every rule in the section constrains which external binary an operator may pin, not an input→output, state transition, or error path of plugin code, so there is no plugin behavior for a Given/When/Then to exercise — consistent with existing practice (no constraints.md heading is bound to an exercising scenario). The tests/heading-coverage.json co-edit adds the new heading with test=TODO and a reason recording exactly this. Making the ceiling MECHANICALLY enforced via a dispatch-preflight engine-version gate is filed separately as ledger item bd-ib-j9x; that gate WOULD be plugin-observable behavior and would then carry its own scenario.

## Resulting Changes

- constraints.md
- ../tests/heading-coverage.json
