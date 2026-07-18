---
topic: codex-full-access-contract
author: claude-fable-5
created_at: 2026-07-18T00:00:00Z
---

## Proposal: Manifest-gated Codex full-access contract

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Ratify the permanent Codex full-access contract for the Beads/Fabro
orchestrator. When the current repository is a livespec fleet member or an
official adopter listed by the fleet manifest, the orchestrator MUST enable
Codex's `danger-full-access` posture for the Codex surfaces it relies on:
the Codex companion plugin's interactive review/rescue paths and the
orchestrator-owned `codex exec` paths. Repositories outside that manifest remain
default-off unless they explicitly opt in locally.

The mechanism is intentionally manifest-gated, not global. It gives the
maintainer's own fleet and official adopters the full-access execution required
for honest tests, `git`, `gh`, and networked review, while avoiding a silent
full-access posture for unrelated external users who happen to install the
plugin.

### Motivation

The shipped repo-local fix documented in `plan/codex-yolo-sandbox/handoff.md`
proves the root cause and the working posture: Codex companion review/rescue
threads default to restrictive sandbox modes, ignoring the host's raw
`codex exec` configuration, so adversarial review can appear to run while being
unable to execute the checks it is asked to perform. The permanent design in
`plan/codex-yolo-sandbox/permanent-fix-design.md` resolves the scope issue:
the fix must travel through this orchestrator plugin's distribution for fleet
members and official adopters, and it must be gated by fleet membership or local
opt-in.

This belongs in `constraints.md` because, like the Fabro pin, it governs an
external runtime the plugin does not own. The constraint must name the deciding
signals and verification commands so review can distinguish a conformant
full-access posture from a silently re-sandboxed one.

### Proposed Changes

**(1) Add a new `constraints.md` H2 section immediately after
§"Fabro runtime constraints".**

ADD:

```markdown
## Codex full-access runtime constraints

Codex is an EXTERNAL agent runtime: the plugin does not vendor Codex, does not
own OpenAI's Codex companion plugin, and does not own Codex's host-wide
configuration. **Scope — "the Codex factory surfaces"** means the surfaces this
orchestrator depends on for factory operation and dogfooding: the Codex
companion plugin's interactive review/rescue paths (`codex:codex-rescue`,
`/codex:review`, `/codex:adversarial-review`) and the orchestrator-owned raw
`codex exec` paths (credential refresh and `codex exec <plugin>:<op>`
dogfooding). These constraints govern when those surfaces MUST run with Codex
`danger-full-access`.

- **Manifest gate.** Codex full access MUST default ON only when the current
  repository identity (`owner/repo` resolved from `git remote get-url origin`)
  appears in the livespec core fleet manifest, resolved through the same
  fleet-contract machinery that already reads `.livespec-fleet-manifest.jsonc`
  from livespec core, as either a fleet member or an official adopter. A
  distributed local membership marker MAY cache that decision for hook-time
  execution, but the marker MUST be derived from the core manifest rather than
  introducing a second source of truth. For every other repository, Codex full
  access MUST default OFF and MAY be enabled only by an explicit local opt-in
  signal such as `LIVESPEC_CODEX_FULL_ACCESS=1` or a local `.livespec.jsonc`
  flag. Installing the plugin alone MUST NOT silently put an unrelated external
  repository into a full-access Codex posture.
- **Companion-plugin surface.** When the manifest gate or local opt-in is ON,
  the orchestrator-distributed hook MUST make the active Codex companion
  review/rescue chokepoint resolve to `danger-full-access`, while preserving an
  explicit per-run downgrade escape hatch (for example
  `CODEX_COMPANION_SANDBOX=read-only` or `workspace-write`). Because this
  rewrites a third-party plugin cache that may change shape, the same
  distribution MUST include a canary that verifies the active companion source
  still contains the expected `danger-full-access` sentinel. If the gate is ON
  but the sentinel is absent, the canary MUST emit a loud operator-visible
  warning rather than failing open silently.
- **Raw `codex exec` surface.** When the manifest gate or local opt-in is ON,
  every orchestrator-owned raw `codex exec` invocation that needs execution
  fidelity MUST run in full-access mode, either through
  `--dangerously-bypass-approvals-and-sandbox` or through an equivalent
  host-wide Codex configuration. Raw `codex exec` invocations MUST redirect
  stdin from a source that reaches EOF, normally `< /dev/null` when the prompt is
  passed as an argument, so the process cannot stall while reading inherited
  input.
- **Verification.** The companion-plugin rule is decided by the distributed
  canary's check for the `danger-full-access` sentinel in the active Codex
  companion plugin. The raw `codex exec` rule is decided by the actual rendered
  command/configuration for orchestrator-owned Codex invocations, including the
  full-access flag or effective `sandbox_mode = "danger-full-access"` and the
  stdin EOF redirect. Review-time verification MUST check those deciding
  signals whenever the hook, canary, Codex invocation wrapper, or Codex
  dogfooding instructions change.
```

Rationale for the new H2 instead of adding bullets to §"Skill orchestration
constraints": the contract is not about skill prose ownership. It is an
external-runtime posture constraint, parallel to §"Fabro runtime constraints",
and it must keep the deciding commands/signals visible at review time.

**(2) Reconcile Scenario 21 so the Codex plugin scenario covers both discovery
and full-access posture.**

REPLACE the H2:

```markdown
## Scenario 21 — Codex skills picker discovers drive by short name
```

WITH:

```markdown
## Scenario 21 — Codex plugin discovery and full-access posture
```

REPLACE the Scenario 21 feature block with:

```gherkin
Feature: Codex plugin discovery and full-access posture
  As an operator using the Codex TUI and Codex-backed factory review
  I want the orchestrator's Codex plugin to be discoverable and full-access only
    under the manifest-gated contract
  So that official fleet/adopter repos get honest executable review without
    silently changing unrelated external repos

Scenario: The /skills picker renders drive under this plugin
  Given the livespec-orchestrator-beads-fabro Codex plugin is installed
  And the operator opens the Codex TUI
  When the operator opens "/skills"
  And chooses "List skills"
  And searches for "drive"
  Then the picker renders "drive (livespec-orchestrator-beads-fabro)"
  And the rendered row is typed as a Skill
  And the operator does not need to search for the colon-qualified
    "livespec-orchestrator-beads-fabro:drive" form

Scenario: A fleet member or official adopter gets Codex full access
  Given the current repository identity appears in the livespec core fleet
    manifest as a fleet member or official adopter
  When the orchestrator's Codex full-access gate is evaluated
  Then the companion-plugin review/rescue surface is patched to
    "danger-full-access"
  And the companion canary verifies the active plugin contains the
    "danger-full-access" sentinel
  And orchestrator-owned raw "codex exec" commands run with a full-access
    sandbox posture and stdin redirected from an EOF-reaching source

Scenario: An unrelated external repository remains default-off
  Given the current repository identity does not appear in the livespec core
    fleet manifest as a fleet member or official adopter
  And no local Codex full-access opt-in is set
  When the orchestrator's Codex full-access gate is evaluated
  Then the companion-plugin review/rescue surface is not patched by this plugin
  And orchestrator-owned raw "codex exec" commands do not infer full access from
    plugin installation alone
```

This keeps the existing picker assertion intact while adding the posture
contract Scenario 21 now needs to carry. The heading still refers to the
orchestrator's Codex plugin, matching the design note that Scenario 21 is the
existing Codex behavior anchor.

**(3) Update `tests/heading-coverage.json` in the revise pass.**

ADD a heading-coverage entry for the new constraints heading:

```json
{
  "heading": "## Codex full-access runtime constraints",
  "spec_root": "SPECIFICATION",
  "spec_file": "constraints.md",
  "test": "TODO",
  "reason": "External-runtime posture constraint over Codex and the OpenAI Codex companion plugin: the deciding signals are the manifest/local opt-in gate, the companion canary sentinel check, and the rendered raw codex exec full-access/EOF behavior. A real test ID becomes bindable when the plugin-shipped hook/canary and codex exec wrapper are implemented."
}
```

UPDATE the existing Scenario 21 entry's heading text from
`## Scenario 21 — Codex skills picker discovers drive by short name` to
`## Scenario 21 — Codex plugin discovery and full-access posture`. Leave its
`test` as `TODO` unless the revise pass also lands an integration-tier test that
exercises the Codex TUI discovery and full-access gate end to end.

### Resulting files

- `SPECIFICATION/constraints.md`
- `SPECIFICATION/scenarios.md`
- `tests/heading-coverage.json`

