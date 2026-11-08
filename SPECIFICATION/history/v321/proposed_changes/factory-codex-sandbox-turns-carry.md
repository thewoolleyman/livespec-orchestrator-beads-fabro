---
topic: factory-codex-sandbox-turns-carry
author: claude-opus-5-5
created_at: 2026-11-07T20:38:15Z
---

## Proposal: Factory sandbox turns carry the Driver PreToolUse guards, trusted from release-verified bytes

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

A factory sandbox agent turn of either runtime carries its Driver's PreToolUse guards at the Driver release the run pins. On Codex the materialized hooks are trusted only when they byte-match that release tag, a mismatch fails the prepare step naming the plugin and hook, and Codex's hook-trust bypass is never used.

### Motivation

Work-item bd-ib-v75dlb records legacy-coordinator-agent's parity ruling of 2026-11-03: factory Codex turns MUST carry the livespec-driver-codex guards, as Claude turns get a plugin-cache materialization. Its measurement of that date found factory Codex turns use a fresh per-run CODEX_HOME holding only auth.json and an otel-only config.toml, with no plugin or hook tables, so the footgun, raw-bd-create and auto-memory guards do not run in them. Those turns run with danger-full-access and approval policy never, where those guards matter most. The item's spec-change tier judgement found that the ratified section covers Codex full-access gating for the companion plugin and raw codex exec but says nothing about sandbox turns carrying Driver hooks, release-verified trust, or a prepare-step failure on mismatch, and every launch of the item is refused at the wall until a proposal exists. An untrusted PreToolUse guard fails open: measured on the dev host on Codex 0.166.0 on 2026-11-04 and again on 2026-11-07 (livespec-driver-codex-sjwyha), and Codex has no fail-closed setting for it (openai/codex#41979, open). So a hook that is present but not recorded as trusted gives no protection, which is why this clause requires trust to be established and a mismatch to fail the run rather than proceed unguarded. Whether the Claude materialized cache already carries the PreToolUse hooks is unverified on the item; the clause states the required outcome either way.

### Proposed Changes

In `constraints.md` §"Codex full-access runtime constraints", replace the sentence

> These constraints govern when those surfaces MUST
> run with Codex `danger-full-access`.

with

> These constraints govern when those surfaces MUST
> run with Codex `danger-full-access`. The bullet "Factory sandbox turns carry the Driver guards" separately governs factory sandbox agent turns, which are not among those surfaces.

In the same section, insert this bullet immediately before the bullet headed `**Out of scope — operator dogfooding.**`:

- **Factory sandbox turns carry the Driver guards.** A factory Codex sandbox turn's per-run `CODEX_HOME` MUST carry the `livespec-driver-codex` plugin at the Driver release the run pins, with its hooks enabled. The materialized Driver hooks MUST be recorded as trusted in that `CODEX_HOME` only when the materialized hook definitions and hook entrypoints byte-match that Driver release tag, and a mismatch MUST fail the run's prepare step, naming the plugin and the hook. Codex's hook-trust bypass MUST NOT be used to establish that trust. A factory Claude sandbox turn's materialized plugin cache MUST carry the `livespec-driver-claude` plugin's PreToolUse hooks at the release the run pins. A command that a materialized PreToolUse guard forbids MUST be blocked when a sandbox turn of either runtime attempts it.

In the same section, in the bullet headed `**Verification.**`, insert this sentence immediately before the sentence beginning "Review-time verification MUST check":

> The factory sandbox guard rule is decided by a real dispatched factory run on the released orchestrator, in which an implement turn of each runtime attempts a command its guard forbids and the guard blocks it.

In `scenarios.md`, append this scenario under the next free scenario number at ratification:

## Scenario NN — a factory sandbox turn carries its Driver's PreToolUse guards, trusted from release-verified bytes

```gherkin
Given a factory run pins a release of its runtime's Driver plugin
And the run's prepare step has materialized that Driver plugin into the sandbox turn's per-run home
When the materialized Codex hook definitions and hook entrypoints byte-match that Driver release tag
Then the hooks are recorded as trusted in the per-run CODEX_HOME without Codex's hook-trust bypass
And an implement turn's attempt to run a command the guard forbids is blocked by the materialized guard

Given the same run
When a materialized Codex hook definition or hook entrypoint differs from that Driver release tag
Then the run's prepare step fails, naming the plugin and the hook
And no implement turn starts
```

At ratification, `tests/heading-coverage.json` MUST gain a `TODO` entry for the new scenario heading whose `reason` names the integration tier, per the revise co-edit discipline.
